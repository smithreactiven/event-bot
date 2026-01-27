from datetime import datetime

from aiogram import types, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import Message
from sqlalchemy import select, update

import tools
from bot import keyboards, config, states
from bot.models.sql import Event, Round, Participant, Opinion
from bot.services import event_service


def _admin_menu_markup():
    return keyboards.inline.admin.admin_menu.keyboard.as_markup()


# ---- Старт мероприятия ----

async def start_event_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    await state.set_state(states.admin_state.EventStartStates.rounds_count)
    t = await tools.filer.read_txt("admin_start_rounds")
    await callback.message.answer(t)


async def rounds_count_msg(message: Message, state: FSMContext, session):
    try:
        n = int((message.text or "").strip())
    except ValueError:
        return await message.answer("Введите число.")
    if n < 1:
        return await message.answer("Введите число больше 0.")
    await state.update_data(rounds_count=n)
    await state.set_state(states.admin_state.EventStartStates.confirm)
    await message.answer("Подтвердите: {} раундов.".format(n), reply_markup=keyboards.inline.admin.admin_confirm_start.keyboard.as_markup())


async def confirm_start_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    if callback.data == "cancel_start_event":
        await state.clear()
        return await callback.message.answer("Отменено.", reply_markup=_admin_menu_markup())

    data = await state.get_data()
    n = data.get("rounds_count", 0)
    if n < 1:
        await state.clear()
        return await callback.message.answer("Ошибка.")

    async with session() as open_session:
        await open_session.execute(
            update(Event).where(Event.is_started == True, Event.is_ended == False).values(is_ended=True)
        )
        ev = Event(is_started=True, is_ended=False, total_rounds=n, current_round=0)
        open_session.add(ev)
        await open_session.commit()

    await state.clear()
    await callback.message.answer(
        "Мероприятие начато. {} раундов.\n\nУчастники регистрируются через /start — пришлите им ссылку на бота. Как только все зарегистрируются, начните первый раунд.".format(n),
        reply_markup=_admin_menu_markup()
    )


# ---- Раунды ----

async def start_round_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await callback.message.answer("Сначала начните мероприятие.")
    if ev.current_round != 0:
        return await callback.message.answer("Первый раунд уже начат.")
    await state.update_data(next_round=False)
    await state.set_state(states.admin_state.RoundNameStates.name)
    t = await tools.filer.read_txt("admin_round_name")
    await callback.message.answer("Введите название 1 раунда:")


async def next_round_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await callback.message.answer("Сначала начните мероприятие.")
    if ev.current_round == 0:
        return await callback.message.answer("Сначала начните 1 раунд.")
    if ev.current_round >= ev.total_rounds:
        return await callback.message.answer("Все раунды проведены.")
    await state.update_data(next_round=True)
    await state.set_state(states.admin_state.RoundNameStates.name)
    await callback.message.answer("Введите название следующего раунда:")


async def round_name_msg(message: Message, state: FSMContext, session, bot):
    data = await state.get_data()
    next_round = data.get("next_round", False)
    name = (message.text or "").strip() or "Раунд"

    ev = await event_service.get_active_event(session)
    if ev is None:
        await state.clear()
        return await message.answer("Мероприятие не активно.")

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
    await callback.answer()
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await callback.message.answer("Нет активного мероприятия.")
    cur = await event_service.get_current_round(session, ev.id)
    if cur is None:
        return await callback.message.answer("Нет активного раунда.")
    if cur.list_shown_at is not None:
        return await callback.message.answer("Список уже показан. Участники пишут мнения.")

    rows = await event_service.get_round_messages(session, ev.id, cur.number)
    if not rows:
        return await callback.message.answer(
            "В раунде нет участников (никто не получил сообщение о старте). Сначала начмите раунд после регистраций.",
            reply_markup=_admin_menu_markup()
        )

    async with session() as open_session:
        r = await open_session.get(Round, cur.id)
        r.list_shown_at = datetime.utcnow()
        await open_session.commit()

    await event_service.finish_round_show_list(callback.bot, session, ev.id, cur.number, tools.filer.read_txt)
    await callback.message.answer("Раунд: фаза сбора мнений (10 мин). Участников: {}.".format(len(rows)), reply_markup=_admin_menu_markup())


async def end_event_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await callback.message.answer("Нет активного мероприятия.")

    async with session() as open_session:
        e = await open_session.get(Event, ev.id)
        e.is_ended = True
        cur = await event_service.get_current_round(session, ev.id)
        if cur:
            event_service.cancel_round_countdowns(ev.id, cur.number)
            r = await open_session.get(Round, cur.id)
            r.ended_at = datetime.utcnow()
        await open_session.commit()

    await callback.message.answer("Мероприятие завершено.", reply_markup=_admin_menu_markup())


# ---- Список участников и поиск ----

async def list_participants_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session) or await event_service.get_latest_event(session)
    if ev is None:
        return await callback.message.answer("Нет мероприятия.")

    participants = await event_service.get_participants(session, ev.id)
    if not participants:
        await callback.message.answer("Нет участников.")
        return

    lines = ["Список участников:"] + ["{}. {}".format(i + 1, p.full_name) for i, p in enumerate(participants)]
    from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Поиск", callback_data="search_participants"))
    await callback.message.answer("\n".join(lines), reply_markup=kb.as_markup())


async def search_participants_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session) or await event_service.get_latest_event(session)
    if ev is None:
        return await callback.message.answer("Нет мероприятия.")
    await state.update_data(search_event_id=ev.id)
    await state.set_state(states.admin_state.SearchParticipantsStates.query)
    t = await tools.filer.read_txt("admin_search_participants")
    await callback.message.answer(t)


async def search_query_msg(message: Message, state: FSMContext, session):
    data = await state.get_data()
    event_id = data.get("search_event_id")
    if not event_id:
        await state.clear()
        return await message.answer("Ошибка. Начните заново.")

    participants = await event_service.get_participants(session, event_id, search=(message.text or "").strip())
    await state.clear()
    if not participants:
        return await message.answer("Никого не найдено.")
    lines = ["Результаты:"] + ["{}. {}".format(i + 1, p.full_name) for i, p in enumerate(participants)]
    await message.answer("\n".join(lines))


# ---- Просмотр мнений ----

async def look_opinions_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_active_event(session) or await event_service.get_latest_event(session)
    if ev is None:
        return await callback.message.answer("Нет мероприятия.")
    participants = await event_service.get_participants(session, ev.id)
    if not participants:
        return await callback.message.answer("Нет участников.")

    from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    for p in participants:
        kb.row(InlineKeyboardButton(text=p.full_name, callback_data="look_opinions_{}".format(p.user_id)))
    await callback.message.answer("Выберите участника:", reply_markup=kb.as_markup())


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
    by_round = {}
    for o in opinions:
        by_round.setdefault(o.round_number, []).append(o.text)
    if not by_round:
        await callback.message.answer("У участника {} нет мнений.".format(name))
        return
    lines = ["Участник: {}".format(name)]
    for r in sorted(by_round.keys()):
        lines.append("\nРаунд {}:".format(r))
        for t in by_round[r]:
            lines.append("— {}".format(t))
    await callback.message.answer("\n".join(lines))


# ---- Отправить мнения ----

async def send_opinions_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    ev = await event_service.get_latest_event(session)
    if ev is None or not ev.is_ended:
        return await callback.message.answer("Сначала завершите мероприятие.")

    participants = await event_service.get_participants(session, ev.id)
    t_intro = await tools.filer.read_txt("your_opinions_intro")
    from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

    for p in participants:
        rounds = await event_service.get_rounds_with_opinions_for(session, ev.id, p.user_id)
        kb = InlineKeyboardBuilder()
        for r in rounds:
            kb.row(InlineKeyboardButton(text="Раунд {}".format(r), callback_data="opinions_round_{}".format(r)))
        try:
            if rounds:
                await callback.bot.send_message(chat_id=p.user_id, text=t_intro, reply_markup=kb.as_markup())
            else:
                await callback.bot.send_message(chat_id=p.user_id, text="У вас пока нет мнений.")
        except Exception as e:
            import logging
            logging.exception("send_opinions to %s: %s", p.user_id, e)

    await callback.message.answer("Мнения отправлены.", reply_markup=_admin_menu_markup())


def setup(dp: Dispatcher):
    dp.callback_query.register(confirm_start_cb, F.data.in_({"confirm_start_event", "cancel_start_event"}), F.from_user.id.in_(config.BOT_ADMINS))
    dp.message.register(rounds_count_msg, StateFilter(states.admin_state.EventStartStates.rounds_count), F.from_user.id.in_(config.BOT_ADMINS))
    dp.message.register(round_name_msg, StateFilter(states.admin_state.RoundNameStates.name), F.from_user.id.in_(config.BOT_ADMINS))
    dp.message.register(search_query_msg, StateFilter(states.admin_state.SearchParticipantsStates.query), F.from_user.id.in_(config.BOT_ADMINS))

    for cb, data in [
        (start_event_cb, "start_event"),
        (start_round_cb, "start_round"),
        (next_round_cb, "next_round"),
        (end_round_cb, "end_round"),
        (end_event_cb, "end_event"),
        (list_participants_cb, "list_participants"),
        (search_participants_cb, "search_participants"),
        (look_opinions_cb, "look_opinions"),
        (send_opinions_cb, "send_opinions"),
    ]:
        dp.callback_query.register(cb, F.data == data, F.from_user.id.in_(config.BOT_ADMINS))

    dp.callback_query.register(look_opinions_user_cb, F.data.startswith("look_opinions_"), F.from_user.id.in_(config.BOT_ADMINS))
