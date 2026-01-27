from aiogram import Dispatcher
from . import admin_menu
from . import admin_event
from . import broadcast


def setup(dp: Dispatcher):
    for module in (admin_menu, admin_event, broadcast):
        module.setup(dp)
