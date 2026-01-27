from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

keyboard = InlineKeyboardBuilder()
keyboard.row(InlineKeyboardButton(text="Подтвердить", callback_data="confirm_start_event"))
keyboard.row(InlineKeyboardButton(text="Отмена", callback_data="cancel_start_event"))
