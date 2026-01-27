from aiogram import Dispatcher
from . import errors
from . import users
from . import groups
from . import admins


def setup(dp: Dispatcher):
    for module in (admins, users):
        module.setup(dp)
