from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

keyboard = InlineKeyboardBuilder()

keyboard.row(InlineKeyboardButton(text="Старт мероприятия", callback_data="start_event"))
keyboard.row(InlineKeyboardButton(text="Начать 1 раунд", callback_data="start_round"))
keyboard.row(InlineKeyboardButton(text="Завершить раунд", callback_data="end_round"))
keyboard.row(InlineKeyboardButton(text="Следующий раунд", callback_data="next_round"))
keyboard.row(InlineKeyboardButton(text="Закончить мероприятие", callback_data="end_event"))
keyboard.row(InlineKeyboardButton(text="Список участников", callback_data="list_participants"))
keyboard.row(InlineKeyboardButton(text="Просмотр списка мнений", callback_data="look_opinions"))
keyboard.row(InlineKeyboardButton(text="Отправить мнения", callback_data="send_opinions"))
keyboard.row(InlineKeyboardButton(text="Обновить", callback_data="admin_refresh"))