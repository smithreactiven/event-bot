from aiogram import types, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from sqlalchemy.exc import IntegrityError

import tools
from bot import keyboards, states
from bot.models.sql import Participant
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
    t = await tools.filer.read_txt("registration_instagram")
    await state.set_state(states.user_state.RegistrationStates.instagram)
    sent = await message.answer(t, reply_markup=keyboards.inline.registration.skip_keyboard())
    await state.update_data(prev_bot_msg_id=sent.message_id)


async def reg_instagram_msg(message: types.Message, state: FSMContext, session, bot):
    await _delete_prev_messages(message, state, bot)
    
    event_id, _, err = await _ensure_event_and_open(state, session, message.from_user.id)
    if err:
        await state.clear()
        return await message.answer(err)

    ok, err, val = v.validate_instagram(message.text)
    if not ok:
        sent = await message.answer(err)
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return
    
    await state.update_data(instagram=val)
    t = await tools.filer.read_txt("registration_telegram")
    await state.set_state(states.user_state.RegistrationStates.telegram)
    sent = await message.answer(t, reply_markup=keyboards.inline.registration.skip_keyboard())
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
    t = await tools.filer.read_txt("registration_vk")
    await state.set_state(states.user_state.RegistrationStates.vk)
    sent = await message.answer(t, reply_markup=keyboards.inline.registration.skip_keyboard())
    await state.update_data(prev_bot_msg_id=sent.message_id)


async def reg_vk_msg(message: types.Message, state: FSMContext, session, bot):
    await _delete_prev_messages(message, state, bot)
    
    event_id, _, err = await _ensure_event_and_open(state, session, message.from_user.id)
    if err:
        await state.clear()
        return await message.answer(err)

    ok, err, val = v.validate_vk(message.text)
    if not ok:
        sent = await message.answer(err)
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return
    
    await state.update_data(vk=val)
    await _finish_registration(message, state, session, message.from_user.id)


async def skip_social_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    _, _, err = await _ensure_event_and_open(state, session, callback.from_user.id)
    if err:
        await state.clear()
        try:
            await callback.message.edit_text(err)
        except Exception:
            await callback.message.answer(err)
        return

    s = await state.get_state()
    if s == states.user_state.RegistrationStates.instagram.state:
        await state.update_data(instagram=None)
        t = await tools.filer.read_txt("registration_telegram")
        await state.set_state(states.user_state.RegistrationStates.telegram)
        try:
            await callback.message.edit_text(t, reply_markup=keyboards.inline.registration.skip_keyboard())
        except Exception:
            sent = await callback.message.answer(t, reply_markup=keyboards.inline.registration.skip_keyboard())
            await state.update_data(prev_bot_msg_id=sent.message_id)
    elif s == states.user_state.RegistrationStates.telegram.state:
        await state.update_data(telegram=None)
        t = await tools.filer.read_txt("registration_vk")
        await state.set_state(states.user_state.RegistrationStates.vk)
        try:
            await callback.message.edit_text(t, reply_markup=keyboards.inline.registration.skip_keyboard())
        except Exception:
            sent = await callback.message.answer(t, reply_markup=keyboards.inline.registration.skip_keyboard())
            await state.update_data(prev_bot_msg_id=sent.message_id)
    elif s == states.user_state.RegistrationStates.vk.state:
        await state.update_data(vk=None)
        await _finish_registration(callback.message, state, session, callback.from_user.id, edit=True)
    else:
        await state.clear()
        try:
            await callback.message.edit_text("Ошибка. Начните с /start.")
        except Exception:
            await callback.message.answer("Ошибка. Начните с /start.")


async def _finish_registration(message: types.Message, state: FSMContext, session, user_id: int, edit: bool = False):
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
            instagram=data.get("instagram"),
            telegram=data.get("telegram"),
            vk=data.get("vk"),
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
    dp.message.register(reg_instagram_msg, StateFilter(states.user_state.RegistrationStates.instagram), no_cmd)
    dp.message.register(reg_telegram_msg, StateFilter(states.user_state.RegistrationStates.telegram), no_cmd)
    dp.message.register(reg_vk_msg, StateFilter(states.user_state.RegistrationStates.vk), no_cmd)
    dp.callback_query.register(skip_social_cb, F.data == "skip_social")
