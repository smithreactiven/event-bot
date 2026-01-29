from datetime import datetime
import logging
import asyncio

from aiogram import types, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy import select, update

import tools
from bot import keyboards, config, states
from bot.models.sql import Event, Round, Participant, Opinion
from bot.services import event_service

# Хранение задачи автообновления админки
_admin_timer_task = None
_admin_timer_msg = None  # (chat_id, message_id)


def _admin_menu_markup():
    return keyboards.inline.admin.admin_menu.keyboard.as_markup()


def cancel_admin_timer():
    """Отменить автообновление админского таймера."""
    global _admin_timer_task
    if _admin_timer_task and not _admin_timer_task.done():
        _admin_timer_task.cancel()
    _admin_timer_task = None


async def _admin_timer_countdown(bot, session_factory, event_id: int, round_number: int, chat_id: int, message_id: int):
    """Автообновление сообщения админа каждую минуту."""
    global _admin_timer_task, _admin_timer_msg
    from bot.handlers.admins.admin_menu import _admin_panel_text
    
    for m in range(9, -1, -1):  # 9, 8, 7... 0
        await asyncio.sleep(60)
        # Проверяем что раунд всё ещё активен
        ev = await event_service.get_active_event(session_factory)
        if ev is None or ev.id != event_id:
            break
        cur = await event_service.get_current_round(session_factory, event_id)
        if cur is None or cur.number != round_number or cur.list_shown_at is None:
            break
        
        # Обновляем сообщение
        msg_text = await _admin_panel_text(session_factory)
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=msg_text, reply_markup=_admin_menu_markup())
        except Exception:
            pass
    
    _admin_timer_task = None
    _admin_timer_msg = None


async def _safe_edit(callback: types.CallbackQuery, text: str, reply_markup=None):
    """Безопасный edit - если не получится, отправит новое."""
    try:
        await callback.message.edit_text(text=text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text=text, reply_markup=reply_markup)


async def _delete_user_and_bot_msg(message: Message, state: FSMContext, bot):
    """Удалить сообщение пользователя и предыдущее сообщение бота."""
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    try:
        await message.delete()
    except Exception:
        pass
    if prev_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prev_id)
        except Exception:
            pass


# ---- Старт мероприятия ----

async def start_event_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    await state.set_state(states.admin_state.EventStartStates.rounds_count)
    t = await tools.filer.read_txt("admin_start_rounds")
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_start_event"))
    await _safe_edit(callback, t, kb.as_markup())


async def rounds_count_msg(message: Message, state: FSMContext, session, bot):
    await _delete_user_and_bot_msg(message, state, bot)
    
    try:
        n = int((message.text or "").strip())
    except ValueError:
        sent = await message.answer("Введите число.")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return
    if n < 1:
        sent = await message.answer("Введите число больше 0.")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return
    
    await state.update_data(rounds_count=n)
    await state.set_state(states.admin_state.EventStartStates.confirm)
    sent = await message.answer(
        "Подтвердите: {} раундов.".format(n),
        reply_markup=keyboards.inline.admin.admin_confirm_start.keyboard.as_markup()
    )
    await state.update_data(prev_bot_msg_id=sent.message_id)


async def confirm_start_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    if callback.data == "cancel_start_event":
        await state.clear()
        return await _safe_edit(callback, "Отменено.", _admin_menu_markup())

    data = await state.get_data()
    n = data.get("rounds_count", 0)
    if n < 1:
        await state.clear()
        return await _safe_edit(callback, "Ошибка.", _admin_menu_markup())

    async with session() as open_session:
        await open_session.execute(
            update(Event).where(Event.is_started == True, Event.is_ended == False).values(is_ended=True)
        )
        ev = Event(is_started=True, is_ended=False, total_rounds=n, current_round=0)
        open_session.add(ev)
        await open_session.commit()

    await state.clear()
    await _safe_edit(
        callback,
        "Мероприятие начато. {} раундов.\n\nУчастники регистрируются через /start — пришлите им ссылку на бота. Как только все зарегистрируются, начните первый раунд.".format(n),
        _admin_menu_markup()
    )


# ---- Раунды ----

async def start_round_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await _safe_edit(callback, "Сначала начните мероприятие.", _admin_menu_markup())
    if ev.current_round != 0:
        return await _safe_edit(callback, "Первый раунд уже начат.", _admin_menu_markup())
    
    await state.update_data(next_round=False)
    await state.set_state(states.admin_state.RoundNameStates.name)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_round_name"))
    await _safe_edit(callback, "Введите название 1 раунда:", kb.as_markup())


async def next_round_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    cancel_admin_timer()  # Останавливаем автообновление
    
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await _safe_edit(callback, "Сначала начните мероприятие.", _admin_menu_markup())
    if ev.current_round == 0:
        return await _safe_edit(callback, "Сначала начните 1 раунд.", _admin_menu_markup())
    if ev.current_round >= ev.total_rounds:
        return await _safe_edit(callback, "Все раунды проведены.", _admin_menu_markup())
    
    await state.update_data(next_round=True)
    await state.set_state(states.admin_state.RoundNameStates.name)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_round_name"))
    await _safe_edit(callback, "Введите название следующего раунда:", kb.as_markup())


async def cancel_round_name_cb(callback: types.CallbackQuery, state: FSMContext, session):
    """Отмена ввода названия раунда."""
    await callback.answer()
    await state.clear()
    from bot.handlers.admins.admin_menu import _admin_panel_text
    msg_text = await _admin_panel_text(session)
    await _safe_edit(callback, msg_text, _admin_menu_markup())


async def round_name_msg(message: Message, state: FSMContext, session, bot):
    await _delete_user_and_bot_msg(message, state, bot)
    
    data = await state.get_data()
    next_round = data.get("next_round", False)
    name = (message.text or "").strip() or "Раунд"

    ev = await event_service.get_active_event(session)
    if ev is None:
        await state.clear()
        return await message.answer("Мероприятие не активно.", reply_markup=_admin_menu_markup())

    async with session() as open_session:
        if next_round:
            r = await open_session.execute(select(Round).where(Round.event_id == ev.id, Round.ended_at.is_(None)).limit(1))
            prev = r.scalars().first()
            if prev:
                event_service.cancel_round_countdowns(ev.id, prev.number)
                prev.ended_at = datetime.utcnow()
            num = ev.current_round + 1
        else:
            num = 1
        row = Round(event_id=ev.id, number=num, name=name)
        open_session.add(row)
        ev_obj = await open_session.get(Event, ev.id)
        ev_obj.current_round = num
        ev_obj.round_started_at = datetime.utcnow()
        await open_session.commit()

    await state.clear()
    participants = await event_service.get_participants(session, ev.id)
    n_notified = await event_service.notify_round_start(bot, session, ev.id, num, name, tools.filer.read_txt)
    txt = "Раунд «{}» начат. Участников: {}, получили уведомление: {}.".format(name, len(participants), n_notified)
    if len(participants) > n_notified:
        txt += "\n\n⚠️ Не все получили — возможно, участник не нажимал /start в боте."
    await message.answer(txt, reply_markup=_admin_menu_markup())


async def end_round_cb(callback: types.CallbackQuery, state: FSMContext, session):
    global _admin_timer_task, _admin_timer_msg
    
    await callback.answer()
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await _safe_edit(callback, "Нет активного мероприятия.", _admin_menu_markup())
    cur = await event_service.get_current_round(session, ev.id)
    if cur is None:
        return await _safe_edit(callback, "Нет активного раунда.", _admin_menu_markup())
    if cur.list_shown_at is not None:
        return await _safe_edit(callback, "Список уже показан. Участники пишут мнения.", _admin_menu_markup())

    rows = await event_service.get_round_messages(session, ev.id, cur.number)
    if not rows:
        return await _safe_edit(
            callback,
            "В раунде нет участников (никто не получил сообщение о старте). Сначала начните раунд после регистраций.",
            _admin_menu_markup()
        )

    async with session() as open_session:
        r = await open_session.get(Round, cur.id)
        r.list_shown_at = datetime.utcnow()
        await open_session.commit()

    await event_service.finish_round_show_list(callback.bot, session, ev.id, cur.number, tools.filer.read_txt)
    
    # Показываем админу статус с таймером
    from bot.handlers.admins.admin_menu import _admin_panel_text
    msg_text = await _admin_panel_text(session)
    await _safe_edit(callback, msg_text, _admin_menu_markup())
    
    # Запускаем автообновление таймера для админа
    cancel_admin_timer()
    _admin_timer_msg = (callback.message.chat.id, callback.message.message_id)
    _admin_timer_task = asyncio.create_task(
        _admin_timer_countdown(callback.bot, session, ev.id, cur.number, callback.message.chat.id, callback.message.message_id)
    )


async def end_event_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    cancel_admin_timer()  # Останавливаем автообновление
    
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await _safe_edit(callback, "Нет активного мероприятия.", _admin_menu_markup())

    async with session() as open_session:
        e = await open_session.get(Event, ev.id)
        e.is_ended = True
        cur = await event_service.get_current_round(session, ev.id)
        if cur:
            event_service.cancel_round_countdowns(ev.id, cur.number)
            r = await open_session.get(Round, cur.id)
            r.ended_at = datetime.utcnow()
        await open_session.commit()

    # Уведомляем всех участников о завершении
    participants = await event_service.get_participants(session, ev.id)
    notify_text = """Мероприятие завершено, спасибо за участие! Скоро здесь появятся мнения других участников о Вас, ожидайте!

А пока подпишитесь на наш телеграм-канал, чтобы прийти на другие форматы для знакомств (френдинги, детективно-ролевые игры): https://t.me/+Bjifa2n2IAs0OThi"""
    notified = 0
    for p in participants:
        try:
            await callback.bot.send_message(chat_id=p.user_id, text=notify_text)
            notified += 1
        except Exception as e:
            logging.exception("end_event notify %s: %s", p.user_id, e)

    await _safe_edit(callback, "Мероприятие завершено. Уведомлено участников: {}/{}.".format(notified, len(participants)), _admin_menu_markup())


# ---- Список участников ----

async def list_participants_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session) or await event_service.get_latest_event(session)
    if ev is None:
        return await _safe_edit(callback, "Нет мероприятия.", _admin_menu_markup())

    participants = await event_service.get_participants(session, ev.id)
    if not participants:
        return await _safe_edit(callback, "Нет участников.", _admin_menu_markup())

    kb = InlineKeyboardBuilder()
    for p in participants:
        kb.row(InlineKeyboardButton(text=p.full_name, callback_data="admin_participant_{}".format(p.user_id)))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_refresh"))
    await _safe_edit(callback, "Участников: {}. Выберите для просмотра:".format(len(participants)), kb.as_markup())


async def admin_participant_cb(callback: types.CallbackQuery, state: FSMContext, session):
    """Показать информацию об участнике админу."""
    await callback.answer()
    try:
        uid = int(callback.data.replace("admin_participant_", ""))
    except ValueError:
        return
    ev = await event_service.get_active_event(session) or await event_service.get_latest_event(session)
    if ev is None:
        return

    part = await event_service.get_participant(session, ev.id, uid)
    if not part:
        return await _safe_edit(callback, "Участник не найден.", _admin_menu_markup())

    lines = [
        "👤 <b>{}</b>".format(part.full_name),
        "",
        "🆔 Telegram ID: <code>{}</code>".format(part.user_id),
    ]
    if part.telegram:
        lines.append("✈️ Telegram: @{}".format(part.telegram.lstrip("@")))

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ К списку", callback_data="list_participants"))
    await _safe_edit(callback, "\n".join(lines), kb.as_markup())


# ---- Просмотр мнений ----

async def look_opinions_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session) or await event_service.get_latest_event(session)
    if ev is None:
        return await _safe_edit(callback, "Нет мероприятия.", _admin_menu_markup())
    participants = await event_service.get_participants(session, ev.id)
    if not participants:
        return await _safe_edit(callback, "Нет участников.", _admin_menu_markup())

    kb = InlineKeyboardBuilder()
    for p in participants:
        kb.row(InlineKeyboardButton(text=p.full_name, callback_data="look_opinions_{}".format(p.user_id)))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_refresh"))
    await _safe_edit(callback, "Выберите участника:", kb.as_markup())


async def look_opinions_user_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    try:
        uid = int(callback.data.replace("look_opinions_", ""))
    except ValueError:
        return
    ev = await event_service.get_active_event(session) or await event_service.get_latest_event(session)
    if ev is None:
        return

    part = await event_service.get_participant(session, ev.id, uid)
    name = part.full_name if part else str(uid)
    opinions = await event_service.get_opinions_about(session, ev.id, uid)
    
    # Получаем всех участников для определения авторов
    all_participants = await event_service.get_participants(session, ev.id)
    participants_map = {p.user_id: p for p in all_participants}
    
    by_round = {}
    for o in opinions:
        author = participants_map.get(o.from_user_id)
        author_name = author.full_name if author else "ID:{}".format(o.from_user_id)
        by_round.setdefault(o.round_number, []).append((o.text, author_name))
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="look_opinions"))
    
    if not by_round:
        return await _safe_edit(callback, "У участника {} нет мнений.".format(name), kb.as_markup())
    
    lines = ["Мнения об участнике: <b>{}</b>".format(name)]
    for r in sorted(by_round.keys()):
        lines.append("\n<b>Раунд {}:</b>".format(r))
        for text, author_name in by_round[r]:
            lines.append("— {} <i>(от: {})</i>".format(text, author_name))
    await _safe_edit(callback, "\n".join(lines), kb.as_markup())


# ---- Отправить мнения ----

async def send_opinions_cb(callback: types.CallbackQuery, state: FSMContext, session):
    import random
    
    await callback.answer()
    ev = await event_service.get_latest_event(session)
    if ev is None or not ev.is_ended:
        return await _safe_edit(callback, "Сначала завершите мероприятие.", _admin_menu_markup())

    participants = await event_service.get_participants(session, ev.id)
    t_intro = await tools.filer.read_txt("your_opinions_intro")

    sent_count = 0
    for p in participants:
        opinions = await event_service.get_opinions_about(session, ev.id, p.user_id)
        if not opinions:
            try:
                await callback.bot.send_message(chat_id=p.user_id, text="У вас пока нет мнений.")
                sent_count += 1
            except Exception as e:
                logging.exception("send_opinions to %s: %s", p.user_id, e)
            continue
        
        # Перемешиваем мнения для анонимности
        texts = [o.text for o in opinions]
        random.shuffle(texts)
        
        lines = [t_intro, ""]
        for i, txt in enumerate(texts, 1):
            lines.append("{}. {}".format(i, txt))
        
        try:
            await callback.bot.send_message(chat_id=p.user_id, text="\n".join(lines))
            sent_count += 1
        except Exception as e:
            logging.exception("send_opinions to %s: %s", p.user_id, e)

    await _safe_edit(callback, "Мнения отправлены ({}/{}).".format(sent_count, len(participants)), _admin_menu_markup())


def setup(dp: Dispatcher):
    dp.callback_query.register(confirm_start_cb, F.data.in_({"confirm_start_event", "cancel_start_event"}), F.from_user.id.in_(config.BOT_ADMINS))
    dp.callback_query.register(cancel_round_name_cb, F.data == "cancel_round_name", F.from_user.id.in_(config.BOT_ADMINS))
    dp.message.register(rounds_count_msg, StateFilter(states.admin_state.EventStartStates.rounds_count), F.from_user.id.in_(config.BOT_ADMINS))
    dp.message.register(round_name_msg, StateFilter(states.admin_state.RoundNameStates.name), F.from_user.id.in_(config.BOT_ADMINS))

    for cb, data in [
        (start_event_cb, "start_event"),
        (start_round_cb, "start_round"),
        (next_round_cb, "next_round"),
        (end_round_cb, "end_round"),
        (end_event_cb, "end_event"),
        (list_participants_cb, "list_participants"),
        (look_opinions_cb, "look_opinions"),
        (send_opinions_cb, "send_opinions"),
    ]:
        dp.callback_query.register(cb, F.data == data, F.from_user.id.in_(config.BOT_ADMINS))

    dp.callback_query.register(admin_participant_cb, F.data.startswith("admin_participant_"), F.from_user.id.in_(config.BOT_ADMINS))
    dp.callback_query.register(look_opinions_user_cb, F.data.startswith("look_opinions_"), F.from_user.id.in_(config.BOT_ADMINS))
