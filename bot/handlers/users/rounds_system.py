from datetime import datetime

from aiogram import types, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

import tools
from bot import states
from bot.models.sql import Opinion
from bot.services import event_service


def _key(event_id: int, round_number: int, user_id: int):
    return (event_id, round_number, user_id)


def _format_participant_info(part) -> str:
    """Форматирует информацию об участнике для показа при написании мнения."""
    lines = ["👤 <b>{}</b>".format(part.full_name)]
    if part.instagram:
        lines.append("📷 {}".format(part.instagram))
    if part.telegram:
        lines.append("✈️ @{}".format(part.telegram.lstrip("@")))
    if part.vk:
        lines.append("🔵 {}".format(part.vk))
    return "\n".join(lines)


async def opinion_about_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    try:
        about_user_id = int(callback.data.replace("opinion_about_", ""))
    except ValueError:
        return await callback.message.answer("Ошибка.")

    ev = await event_service.get_active_event(session)
    if ev is None:
        return await callback.message.answer("Мероприятие не активно.")
    cur = await event_service.get_current_round(session, ev.id)
    if cur is None:
        return await callback.message.answer("Раунд завершён.")
    if cur.list_shown_at is None:
        return await callback.message.answer("Сбор мнений ещё не начат.")

    rm = await event_service.get_round_message(session, ev.id, cur.number, callback.from_user.id)
    if rm is None:
        return await callback.message.answer("Ошибка: сообщение раунда не найдено.")

    part = await event_service.get_participant(session, ev.id, about_user_id)
    about_name = part.full_name if part else str(about_user_id)
    elapsed = (datetime.utcnow() - cur.list_shown_at).total_seconds() / 60
    remaining = max(0, 10 - elapsed)

    event_service._round_view[_key(ev.id, cur.number, callback.from_user.id)] = ("writing", about_user_id, about_name)
    await state.update_data(about_user_id=about_user_id, event_id=ev.id, round_number=cur.number)
    await state.set_state(states.user_state.OpinionStates.writing)

    # Формируем текст с информацией об участнике
    if part:
        info = _format_participant_info(part)
    else:
        info = "👤 {}".format(about_name)
    
    if remaining <= 0:
        t = "{}\n\n⏱ Время вышло. Вы можете отправить мнение или нажать Отмена.".format(info)
    else:
        t = "{}\n\n✍️ Напишите мнение об этом участнике.\n⏱ Осталось {} мин.".format(info, int(remaining))
    
    kb = event_service.build_cancel_kb()
    try:
        await callback.bot.edit_message_text(chat_id=rm.chat_id, message_id=rm.message_id, text=t, reply_markup=kb)
    except Exception:
        pass


async def opinion_writing_msg(message: types.Message, state: FSMContext, session, bot):
    # Удаляем сообщение пользователя для чистоты чата
    try:
        await message.delete()
    except Exception:
        pass
    
    data = await state.get_data()
    about_user_id = data.get("about_user_id")
    event_id = data.get("event_id")
    round_number = data.get("round_number")
    if not all([about_user_id, event_id, round_number is not None]):
        await state.clear()
        return await message.answer("Ошибка. Начните с /start.")

    text = (message.text or "").strip()
    if not text:
        return await message.answer("Напишите текст мнения.")

    async with session() as open_session:
        o = Opinion(event_id=event_id, round_number=round_number, from_user_id=message.from_user.id, about_user_id=about_user_id, text=text)
        open_session.add(o)
        await open_session.commit()

    event_service._round_view[_key(event_id, round_number, message.from_user.id)] = "list"
    await state.clear()

    rm = await event_service.get_round_message(session, event_id, round_number, message.from_user.id)
    if rm is None:
        return await message.answer(await tools.filer.read_txt("opinion_saved"))
    r = await event_service.get_round_by_number(session, event_id, round_number)
    remaining = 0
    if r and r.list_shown_at:
        elapsed = (datetime.utcnow() - r.list_shown_at).total_seconds() / 60
        remaining = max(0, int(10 - elapsed))
    
    # Показываем подтверждение + возвращаем список участников
    saved_txt = await tools.filer.read_txt("opinion_saved")
    list_txt = (await tools.filer.read_txt("round_list")).format(m=remaining) if remaining > 0 else await tools.filer.read_txt("round_list_timeout")
    t = "✅ {}\n\n{}".format(saved_txt, list_txt)
    
    participants = await event_service.get_participants(session, event_id, exclude_user_id=message.from_user.id)
    kb = event_service.build_participants_kb(participants, message.from_user.id)
    try:
        await bot.edit_message_text(chat_id=rm.chat_id, message_id=rm.message_id, text=t, reply_markup=kb)
    except Exception:
        await message.answer(saved_txt)


async def opinion_cancel_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    await state.clear()
    ev = await event_service.get_active_event(session)
    if ev is None:
        return
    cur = await event_service.get_current_round(session, ev.id)
    if cur is None:
        return
    rm = await event_service.get_round_message(session, ev.id, cur.number, callback.from_user.id)
    if rm is None:
        return

    event_service._round_view[_key(ev.id, cur.number, callback.from_user.id)] = "list"
    remaining = 0
    if cur.list_shown_at:
        elapsed = (datetime.utcnow() - cur.list_shown_at).total_seconds() / 60
        remaining = max(0, int(10 - elapsed))
    t = (await tools.filer.read_txt("round_list")).format(m=remaining) if remaining > 0 else await tools.filer.read_txt("round_list_timeout")
    participants = await event_service.get_participants(session, ev.id, exclude_user_id=callback.from_user.id)
    kb = event_service.build_participants_kb(participants, callback.from_user.id)
    try:
        await callback.bot.edit_message_text(chat_id=rm.chat_id, message_id=rm.message_id, text=t, reply_markup=kb)
    except Exception:
        pass


async def refresh_timer_cb(callback: types.CallbackQuery, state: FSMContext, session):
    """Обновить таймер и список участников."""
    await callback.answer("Обновлено")
    ev = await event_service.get_active_event(session)
    if ev is None:
        return
    cur = await event_service.get_current_round(session, ev.id)
    if cur is None or cur.list_shown_at is None:
        return
    rm = await event_service.get_round_message(session, ev.id, cur.number, callback.from_user.id)
    if rm is None:
        return

    elapsed = (datetime.utcnow() - cur.list_shown_at).total_seconds() / 60
    remaining = max(0, int(10 - elapsed))
    if remaining > 0:
        t = (await tools.filer.read_txt("round_list")).format(m=remaining)
    else:
        t = await tools.filer.read_txt("round_list_timeout")
    participants = await event_service.get_participants(session, ev.id, exclude_user_id=callback.from_user.id)
    kb = event_service.build_participants_kb(participants, callback.from_user.id)
    try:
        await callback.bot.edit_message_text(chat_id=rm.chat_id, message_id=rm.message_id, text=t, reply_markup=kb)
    except Exception:
        pass


async def done_round_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    await state.clear()
    ev = await event_service.get_active_event(session)
    if ev is None:
        return await callback.message.answer("Мероприятие не активно.")
    cur = await event_service.get_current_round(session, ev.id)
    if cur is None:
        return await callback.message.answer("Нет активного раунда.")
    rm = await event_service.get_round_message(session, ev.id, cur.number, callback.from_user.id)
    if rm is None:
        return await callback.message.answer(await tools.filer.read_txt("round_finished"))

    key = (ev.id, cur.number, callback.from_user.id)
    event_service._round_view[key] = "done"
    task = event_service._countdown_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()
    t = await tools.filer.read_txt("round_finished")
    try:
        await callback.bot.edit_message_text(chat_id=rm.chat_id, message_id=rm.message_id, text=t, reply_markup=None)
    except Exception:
        pass


async def opinions_round_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    try:
        n = int(callback.data.replace("opinions_round_", ""))
    except ValueError:
        return

    ev = await event_service.get_latest_event(session)
    if ev is None or not ev.is_ended:
        return await callback.message.answer("Нет доступных мнений.")

    opinions = await event_service.get_opinions_about(session, ev.id, callback.from_user.id)
    opinions = [o for o in opinions if o.round_number == n]
    if not opinions:
        await callback.message.answer("Раунд {}: нет мнений.".format(n))
        return
    lines = ["Раунд {}:".format(n)] + ["— " + o.text for o in opinions]
    await callback.message.answer("\n".join(lines))


def setup(dp: Dispatcher):
    dp.callback_query.register(opinion_about_cb, F.data.startswith("opinion_about_"))
    dp.message.register(opinion_writing_msg, StateFilter(states.user_state.OpinionStates.writing))
    dp.callback_query.register(opinion_cancel_cb, F.data == "opinion_cancel")
    dp.callback_query.register(refresh_timer_cb, F.data == "refresh_timer")
    dp.callback_query.register(done_round_cb, F.data == "done_round")
    dp.callback_query.register(opinions_round_cb, F.data.startswith("opinions_round_"))
