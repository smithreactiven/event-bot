import asyncio
import logging
import typing
from datetime import datetime

from sqlalchemy import select

from bot.models.sql import Event, Round, RoundMessage, Participant, Opinion

ROUND_DURATION_SEC = 10 * 60

_round_view = {}  # (event_id, round_number, user_id) -> 'list' | ('writing', about_user_id, about_name) | 'done'
_countdown_tasks = {}  # (event_id, round_number, user_id) -> asyncio.Task


def cancel_round_countdowns(event_id: int, round_number: int):
    to_cancel = [k for k in list(_countdown_tasks.keys()) if k[0] == event_id and k[1] == round_number]
    for k in to_cancel:
        t = _countdown_tasks.pop(k, None)
        if t and not t.done():
            t.cancel()


async def get_active_event(session_factory) -> typing.Optional[Event]:
    """Мероприятие, на которое можно регистрироваться и вести раунды: is_started и не is_ended."""
    async with session_factory() as s:
        r = await s.execute(
            select(Event).where(Event.is_started == True, Event.is_ended == False).order_by(Event.id.desc()).limit(1)
        )
        return r.scalars().first()


async def get_latest_event(session_factory) -> typing.Optional[Event]:
    async with session_factory() as s:
        r = await s.execute(select(Event).order_by(Event.id.desc()).limit(1))
        return r.scalars().first()


async def get_event_by_id(session_factory, event_id: int) -> typing.Optional[Event]:
    async with session_factory() as s:
        r = await s.execute(select(Event).where(Event.id == event_id))
        return r.scalars().first()


def ensure_registration_open(ev: typing.Optional[Event]) -> typing.Tuple[bool, typing.Optional[str]]:
    """Проверка, что регистрация на мероприятие открыта. (ok, error_message)"""
    if ev is None:
        return False, "Регистрация недоступна. Мероприятие не найдено."
    if not ev.is_started:
        return False, "Регистрация ещё не открыта. Ожидайте старта мероприятия."
    if ev.is_ended:
        return False, "Регистрация закрыта. Мероприятие завершено."
    return True, None


async def get_current_round(session_factory, event_id: int) -> typing.Optional[Round]:
    async with session_factory() as s:
        r = await s.execute(
            select(Round).where(Round.event_id == event_id, Round.ended_at.is_(None)).order_by(Round.number.desc()).limit(1)
        )
        return r.scalars().first()


async def get_round_by_number(session_factory, event_id: int, number: int) -> typing.Optional[Round]:
    async with session_factory() as s:
        r = await s.execute(select(Round).where(Round.event_id == event_id, Round.number == number))
        return r.scalars().first()


async def get_participants(session_factory, event_id: int, exclude_user_id: typing.Optional[int] = None, search: typing.Optional[str] = None) -> typing.List[Participant]:
    async with session_factory() as s:
        q = select(Participant).where(Participant.event_id == event_id)
        if exclude_user_id is not None:
            q = q.where(Participant.user_id != exclude_user_id)
        if search:
            q = q.where(Participant.full_name.ilike(f"%{search}%"))
        r = await s.execute(q.order_by(Participant.full_name))
        return list(r.scalars().all())


async def get_participant(session_factory, event_id: int, user_id: int) -> typing.Optional[Participant]:
    async with session_factory() as s:
        r = await s.execute(select(Participant).where(Participant.event_id == event_id, Participant.user_id == user_id))
        return r.scalars().first()


async def get_opinions_about(session_factory, event_id: int, about_user_id: int) -> typing.List[Opinion]:
    async with session_factory() as s:
        r = await s.execute(
            select(Opinion).where(Opinion.event_id == event_id, Opinion.about_user_id == about_user_id).order_by(Opinion.round_number, Opinion.id)
        )
        return list(r.scalars().all())


async def get_written_opinion_targets(session_factory, event_id: int, round_number: int, from_user_id: int) -> typing.Set[int]:
    """Получить set user_id тех, о ком пользователь уже написал мнение в этом раунде."""
    async with session_factory() as s:
        r = await s.execute(
            select(Opinion.about_user_id).where(
                Opinion.event_id == event_id,
                Opinion.round_number == round_number,
                Opinion.from_user_id == from_user_id
            )
        )
        return set(r.scalars().all())


async def has_opinion_about(session_factory, event_id: int, round_number: int, from_user_id: int, about_user_id: int) -> bool:
    """Проверить, написал ли пользователь мнение о другом участнике в этом раунде."""
    async with session_factory() as s:
        r = await s.execute(
            select(Opinion.id).where(
                Opinion.event_id == event_id,
                Opinion.round_number == round_number,
                Opinion.from_user_id == from_user_id,
                Opinion.about_user_id == about_user_id
            ).limit(1)
        )
        return r.scalars().first() is not None


async def get_rounds_with_opinions_for(session_factory, event_id: int, about_user_id: int) -> typing.List[int]:
    async with session_factory() as s:
        r = await s.execute(
            select(Opinion.round_number).where(
                Opinion.event_id == event_id, Opinion.about_user_id == about_user_id
            ).distinct().order_by(Opinion.round_number)
        )
        return list(r.scalars().all())


def build_participants_kb(participants: typing.List[Participant], exclude_user_id: int, already_written: typing.Optional[typing.Set[int]] = None):
    """
    Построить клавиатуру со списком участников.
    already_written - set user_id тех, о ком уже написано мнение (они исключаются из списка).
    """
    from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    already_written = already_written or set()
    for p in participants:
        if p.user_id == exclude_user_id:
            continue
        if p.user_id in already_written:
            continue  # Уже написали мнение об этом участнике
        builder.row(InlineKeyboardButton(text=p.full_name, callback_data=f"opinion_about_{p.user_id}"))
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_timer"))
    builder.row(InlineKeyboardButton(text="✅ Я закончил(а)!", callback_data="done_round"))
    return builder.as_markup()


def build_cancel_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Отмена", callback_data="opinion_cancel"))
    return b.as_markup()


async def get_round_messages(session_factory, event_id: int, round_number: int) -> typing.List[RoundMessage]:
    async with session_factory() as s:
        r = await s.execute(select(RoundMessage).where(RoundMessage.event_id == event_id, RoundMessage.round_number == round_number))
        return list(r.scalars().all())


async def get_round_message(session_factory, event_id: int, round_number: int, user_id: int) -> typing.Optional[RoundMessage]:
    async with session_factory() as s:
        r = await s.execute(select(RoundMessage).where(
            RoundMessage.event_id == event_id, RoundMessage.round_number == round_number, RoundMessage.user_id == user_id
        ))
        return r.scalars().first()


async def delete_previous_round_messages(bot, session_factory, event_id: int, prev_round_number: int):
    """Удалить сообщения предыдущего раунда у всех участников."""
    rows = await get_round_messages(session_factory, event_id, prev_round_number)
    for rm in rows:
        try:
            await bot.delete_message(chat_id=rm.chat_id, message_id=rm.message_id)
        except Exception:
            pass


async def notify_round_start(bot, session_factory, event_id: int, round_number: int, round_name: str, read_txt) -> int:
    """Разослать участникам анонс раунда БЕЗ кнопок (фаза общения). Кнопки появятся после завершения раунда."""
    # Удаляем сообщения предыдущего раунда если есть
    if round_number > 1:
        await delete_previous_round_messages(bot, session_factory, event_id, round_number - 1)
    
    text_tpl = await read_txt("round_announce")
    text_tpl = text_tpl.format(n=round_number, round_name=round_name)
    ok = 0
    async with session_factory() as s:
        r = await s.execute(
            select(Participant).where(Participant.event_id == event_id).order_by(Participant.full_name)
        )
        participants = list(r.scalars().all())
        user_ids = [p.user_id for p in participants]
        logging.info(
            "notify_round_start: event_id=%s round_number=%s participants=%s user_ids=%s",
            event_id, round_number, len(participants), user_ids,
        )
        for p in participants:
            try:
                # Отправляем без кнопок — фаза общения
                msg = await bot.send_message(chat_id=p.user_id, text=text_tpl)
                rm = RoundMessage(
                    event_id=event_id, round_number=round_number,
                    user_id=p.user_id, chat_id=p.user_id, message_id=msg.message_id,
                )
                s.add(rm)
                ok += 1
                logging.info("notify_round_start OK: user_id=%s message_id=%s", p.user_id, msg.message_id)
            except Exception as e:
                logging.exception("notify_round_start FAIL: user_id=%s error=%s", p.user_id, e)
        await s.commit()
    return ok


async def _countdown_task(bot, session_factory, event_id: int, round_number: int, user_id: int, chat_id: int, message_id: int, read_txt):
    key = (event_id, round_number, user_id)
    for m in (9, 8, 7, 6, 5, 4, 3, 2, 1, 0):
        await asyncio.sleep(60)
        if _round_view.get(key) == "done":
            return
        view = _round_view.get(key, "list")
        participants = await get_participants(session_factory, event_id, exclude_user_id=user_id)
        already_written = await get_written_opinion_targets(session_factory, event_id, round_number, user_id)
        kb = build_participants_kb(participants, user_id, already_written)
        if m == 0:
            t = await read_txt("round_list_timeout")
            _round_view[key] = "list"
        elif isinstance(view, tuple) and len(view) == 3 and view[0] == "writing":
            t = (await read_txt("opinion_prompt_writing")).format(name=view[2], m=m)
            kb = build_cancel_kb()
        else:
            t = (await read_txt("round_list")).format(m=m)
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=t, reply_markup=kb)
        except Exception:
            pass
    _countdown_tasks.pop(key, None)


async def start_round_countdowns(bot, session_factory, event_id: int, round_number: int, read_txt):
    rows = await get_round_messages(session_factory, event_id, round_number)
    for rm in rows:
        key = (event_id, round_number, rm.user_id)
        t = asyncio.create_task(_countdown_task(bot, session_factory, event_id, round_number, rm.user_id, rm.chat_id, rm.message_id, read_txt))
        _countdown_tasks[key] = t


async def finish_round_show_list(bot, session_factory, event_id: int, round_number: int, read_txt):
    rows = await get_round_messages(session_factory, event_id, round_number)
    t = (await read_txt("round_list")).format(m=10)
    for rm in rows:
        _round_view[(event_id, round_number, rm.user_id)] = "list"
        participants = await get_participants(session_factory, event_id, exclude_user_id=rm.user_id)
        already_written = await get_written_opinion_targets(session_factory, event_id, round_number, rm.user_id)
        kb = build_participants_kb(participants, rm.user_id, already_written)
        try:
            await bot.edit_message_text(chat_id=rm.chat_id, message_id=rm.message_id, text=t, reply_markup=kb)
        except Exception as e:
            logging.exception("finish_round_show_list to %s: %s", rm.user_id, e)
    await start_round_countdowns(bot, session_factory, event_id, round_number, read_txt)
