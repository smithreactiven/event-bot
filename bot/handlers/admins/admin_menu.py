from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram import types, Dispatcher, F
from aiogram.filters import Command

from bot import keyboards, config
from bot.services import event_service


async def _admin_panel_text(session) -> str:
    """Актуальный текст главной панели по данным из БД."""
    ev = await event_service.get_active_event(session)
    if ev is None:
        latest = await event_service.get_latest_event(session)
        if latest and latest.is_ended:
            return "Меню администратора.\n\nМероприятие: завершено."
        return "Меню администратора.\n\nМероприятие: не начато."
    participants = await event_service.get_participants(session, ev.id)
    cur = await event_service.get_current_round(session, ev.id)
    if ev.current_round == 0:
        return "Меню администратора.\n\nМероприятие #{}: активно.\nУчастников: {}.\nРаунд: не начат. Всего: {}.".format(
            ev.id, len(participants), ev.total_rounds
        )
    msg_text = "Меню администратора.\n\nМероприятие #{}: активно.\nУчастников: {}.\nРаунд {} из {}.".format(
        ev.id, len(participants), ev.current_round, ev.total_rounds
    )
    if cur:
        if cur.list_shown_at:
            msg_text += "\nФаза: сбор мнений."
        else:
            msg_text += "\nФаза: общение."
            rows = await event_service.get_round_messages(session, ev.id, cur.number)
            msg_text += " Получили уведомление: {}.".format(len(rows))
    return msg_text


def _admin_markup():
    return keyboards.inline.admin.admin_menu.keyboard.as_markup()


async def admin_menu_handler(message: Message, state: FSMContext, session):
    await state.clear()
    msg_text = await _admin_panel_text(session)
    await message.answer(text=msg_text, reply_markup=_admin_markup())


async def admin_refresh_cb(callback: types.CallbackQuery, state: FSMContext, session):
    await callback.answer()
    msg_text = await _admin_panel_text(session)
    try:
        await callback.message.edit_text(text=msg_text, reply_markup=_admin_markup())
    except Exception:
        await callback.message.answer(text=msg_text, reply_markup=_admin_markup())


def setup(dp: Dispatcher):
    dp.message.register(admin_menu_handler, Command("admin"), F.from_user.id.in_(config.BOT_ADMINS))
    dp.callback_query.register(admin_refresh_cb, F.data == "admin_refresh", F.from_user.id.in_(config.BOT_ADMINS))
