from typing import Any

from .throttling import MessageThrottlingMiddleware, CallbackThrottlingMiddleware
from .database import DatabaseMiddleware
from .bot import BotMiddleware
from aiogram import Dispatcher


def setup(dp: Dispatcher, *, session: Any = None, bot: Any = None):
    if session is not None:
        db = DatabaseMiddleware(session)
        dp.message.middleware(db)
        dp.callback_query.middleware(db)
    if bot is not None:
        bm = BotMiddleware(bot)
        dp.message.middleware(bm)
        dp.callback_query.middleware(bm)
    dp.message.middleware(MessageThrottlingMiddleware())
    dp.callback_query.middleware(CallbackThrottlingMiddleware())
