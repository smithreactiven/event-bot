from aiogram import types, Dispatcher
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

import tools
from bot import states, config
from bot.services import event_service

# ID бота из токена (первая часть до двоеточия)
_BOT_ID = int(config.BOT_TOKEN.split(":")[0])


async def start_handler(message: types.Message, state: FSMContext, session, bot):
    # Удаляем предыдущее сообщение бота если есть
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    if prev_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prev_id)
        except Exception:
            pass
    
    await state.clear()
    
    # Защита от регистрации ботов (включая самого себя)
    if message.from_user.is_bot or message.from_user.id == _BOT_ID:
        return await message.answer("Боты не могут регистрироваться.")
    
    ev = await event_service.get_active_event(session)
    if ev is None:
        latest = await event_service.get_latest_event(session)
        if latest and latest.is_ended:
            text = await tools.filer.read_txt("event_ended")
        else:
            text = await tools.filer.read_txt("event_not_started")
        return await message.answer(text=text)

    part = await event_service.get_participant(session, ev.id, message.from_user.id)
    if part is not None:
        text = await tools.filer.read_txt("already_registered")
        return await message.answer(text=text)

    text = await tools.filer.read_txt("registration_full_name")
    await state.update_data(event_id=ev.id)
    await state.set_state(states.user_state.RegistrationStates.full_name)
    sent = await message.answer(text=text)
    await state.update_data(prev_bot_msg_id=sent.message_id)


def setup(dp: Dispatcher):
    dp.message.register(start_handler, CommandStart())
