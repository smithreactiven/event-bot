from datetime import datetime
import asyncio

from aiogram import types, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.exc import IntegrityError

import tools
from bot import keyboards, states
from bot.models.sql import Participant, RoundMessage
from bot.services import event_service
from bot.services import registration_validators as v


async def _ensure_event_and_open(state: FSMContext, session, user_id: int):
    """(event_id, ev, error_message). error_message не None — прервать регистрацию."""
    data = await state.get_data()
    event_id = data.get("event_id")
    if not event_id:
        return None, None, "Ошибка. Начните с /start."
    ev = await event_service.get_event_by_id(session, event_id)
    ok, err = event_service.ensure_registration_open(ev)
    if not ok:
        return event_id, ev, err or "Регистрация недоступна."
    part = await event_service.get_participant(session, event_id, user_id)
    if part is not None:
        return event_id, ev, "Вы уже зарегистрированы на это мероприятие."
    return event_id, ev, None


async def _delete_prev_messages(message: types.Message, state: FSMContext, bot):
    """Удалить предыдущее сообщение бота и сообщение пользователя."""
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass
    # Удаляем предыдущее сообщение бота
    if prev_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prev_id)
        except Exception:
            pass


async def reg_full_name(message: types.Message, state: FSMContext, session, bot):
    await _delete_prev_messages(message, state, bot)
    
    event_id, _, err = await _ensure_event_and_open(state, session, message.from_user.id)
    if err:
        await state.clear()
        return await message.answer(err)

    ok, err = v.validate_full_name(message.text)
    if not ok:
        sent = await message.answer(err)
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    await state.update_data(full_name=(message.text or "").strip())
    t = await tools.filer.read_txt("registration_telegram")
    await state.set_state(states.user_state.RegistrationStates.telegram)
    # Без кнопки "Пропустить" - Telegram ник обязателен
    sent = await message.answer(t)
    await state.update_data(prev_bot_msg_id=sent.message_id)


async def reg_telegram_msg(message: types.Message, state: FSMContext, session, bot):
    await _delete_prev_messages(message, state, bot)
    
    event_id, _, err = await _ensure_event_and_open(state, session, message.from_user.id)
    if err:
        await state.clear()
        return await message.answer(err)

    ok, err, val = v.validate_telegram(message.text)
    if not ok:
        sent = await message.answer(err)
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return
    
    await state.update_data(telegram=val)
    await _finish_registration(message, state, session, message.from_user.id, bot)


async def _finish_registration(message: types.Message, state: FSMContext, session, user_id: int, bot=None, edit: bool = False):
    """
    user_id передаётся явно потому что при callback message.from_user это БОТ, а не пользователь.
    edit=True - редактировать сообщение вместо отправки нового.
    """
    data = await state.get_data()
    event_id = data.get("event_id")
    full_name = data.get("full_name")
    if not event_id or not full_name:
        await state.clear()
        if edit:
            try:
                return await message.edit_text("Ошибка. Начните с /start.")
            except Exception:
                pass
        return await message.answer("Ошибка. Начните с /start.")

    ev = await event_service.get_event_by_id(session, event_id)
    ok, err = event_service.ensure_registration_open(ev)
    if not ok:
        await state.clear()
        text = err or "Регистрация недоступна."
        if edit:
            try:
                return await message.edit_text(text)
            except Exception:
                pass
        return await message.answer(text)

    if await event_service.get_participant(session, event_id, user_id) is not None:
        await state.clear()
        text = "Вы уже зарегистрированы на это мероприятие."
        if edit:
            try:
                return await message.edit_text(text)
            except Exception:
                pass
        return await message.answer(text)

    async with session() as open_session:
        p = Participant(
            event_id=event_id,
            user_id=user_id,
            full_name=full_name,
            telegram=data.get("telegram"),
        )
        open_session.add(p)
        try:
            await open_session.commit()
        except IntegrityError:
            await open_session.rollback()
            await state.clear()
            text = "Вы уже зарегистрированы на это мероприятие."
            if edit:
                try:
                    return await message.edit_text(text)
                except Exception:
                    pass
            return await message.answer(text)

    await state.clear()
    
    # Проверяем есть ли активный раунд - подключаем опоздавших
    cur = await event_service.get_current_round(session, event_id)
    if cur is not None and bot is not None:
        # Есть активный раунд - подключаем участника
        if cur.list_shown_at is None:
            # Фаза общения - отправляем round_announce
            text_tpl = await tools.filer.read_txt("round_announce")
            text_tpl = text_tpl.format(n=cur.number, round_name=cur.name or "Раунд")
            try:
                msg = await bot.send_message(chat_id=user_id, text=text_tpl)
                # Сохраняем RoundMessage для этого участника
                async with session() as open_session:
                    rm = RoundMessage(
                        event_id=event_id, round_number=cur.number,
                        user_id=user_id, chat_id=user_id, message_id=msg.message_id,
                    )
                    open_session.add(rm)
                    await open_session.commit()
            except Exception:
                pass
        else:
            # Фаза сбора мнений - отправляем список участников
            elapsed = (datetime.utcnow() - cur.list_shown_at).total_seconds() / 60
            remaining = max(0, int(10 - elapsed))
            
            if remaining > 0:
                t = (await tools.filer.read_txt("round_list")).format(m=remaining)
            else:
                t = await tools.filer.read_txt("round_list_timeout")
            
            participants = await event_service.get_participants(session, event_id, exclude_user_id=user_id)
            already_written = await event_service.get_written_opinion_targets(session, event_id, cur.number, user_id)
            kb = event_service.build_participants_kb(participants, user_id, already_written)
            
            try:
                msg = await bot.send_message(chat_id=user_id, text=t, reply_markup=kb)
                # Сохраняем RoundMessage
                async with session() as open_session:
                    rm = RoundMessage(
                        event_id=event_id, round_number=cur.number,
                        user_id=user_id, chat_id=user_id, message_id=msg.message_id,
                    )
                    open_session.add(rm)
                    await open_session.commit()
                
                # Запускаем countdown task для этого участника
                if remaining > 0:
                    key = (event_id, cur.number, user_id)
                    event_service._round_view[key] = "list"
                    task = asyncio.create_task(
                        event_service._countdown_task(bot, session, event_id, cur.number, user_id, user_id, msg.message_id, tools.filer.read_txt)
                    )
                    event_service._countdown_tasks[key] = task
            except Exception:
                pass
        return  # Не показываем стандартное сообщение registration_done
    
    # Нет активного раунда - стандартное сообщение
    t = await tools.filer.read_txt("registration_done")
    if edit:
        try:
            return await message.edit_text(t)
        except Exception:
            pass
    await message.answer(t)


def _not_command():
    return ~F.text.startswith("/")


def setup(dp: Dispatcher):
    no_cmd = _not_command()
    dp.message.register(reg_full_name, StateFilter(states.user_state.RegistrationStates.full_name), no_cmd)
    dp.message.register(reg_telegram_msg, StateFilter(states.user_state.RegistrationStates.telegram), no_cmd)
