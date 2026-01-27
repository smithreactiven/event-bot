from aiogram.fsm.state import StatesGroup, State


class BroadcastStates(StatesGroup):
    pre_broadcast = State()
    broadcast = State()


class EventStartStates(StatesGroup):
    rounds_count = State()
    confirm = State()


class RoundNameStates(StatesGroup):
    name = State()


class SearchParticipantsStates(StatesGroup):
    query = State()
