from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

def skip_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Пропустить", callback_data="skip_social"))
    return builder.as_markup()
