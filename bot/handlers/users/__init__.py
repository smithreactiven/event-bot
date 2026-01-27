from aiogram import Dispatcher
from . import start
from . import registration
from . import rounds_system


def setup(dp: Dispatcher):
    for module in (start, registration, rounds_system):
        module.setup(dp)
