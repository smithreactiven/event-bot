from aiogram.fsm.state import StatesGroup, State


class RegistrationStates(StatesGroup):
    full_name = State()
    instagram = State()
    telegram = State()
    vk = State()


class OpinionStates(StatesGroup):
    writing = State()
