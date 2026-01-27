# -*- coding: utf-8 -*-
"""Применить миграции (round.list_shown_at, round_message, participant UNIQUE).
Запуск из корня проекта: python -m scripts.run_migrate
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from bot import config
import database.implement


MIGRATIONS = [
    'ALTER TABLE "round" ADD COLUMN IF NOT EXISTS list_shown_at TIMESTAMP',
    """CREATE TABLE IF NOT EXISTS round_message (
        id SERIAL PRIMARY KEY,
        event_id INTEGER NOT NULL REFERENCES event(id),
        round_number SMALLINT NOT NULL,
        user_id BIGINT NOT NULL,
        chat_id BIGINT NOT NULL,
        message_id INTEGER NOT NULL,
        CONSTRAINT uq_round_message UNIQUE (event_id, round_number, user_id)
    )""",
    'ALTER TABLE participant DROP CONSTRAINT IF EXISTS uq_participant_event_user',
    # Удалить дубликаты (event_id, user_id), оставить строку с меньшим id
    """DELETE FROM participant a
       USING participant b
       WHERE a.event_id = b.event_id AND a.user_id = b.user_id AND a.id > b.id""",
    'ALTER TABLE participant ADD CONSTRAINT uq_participant_event_user UNIQUE (event_id, user_id)',
]


async def main():
    db = database.implement.AsyncPostgreSQL(
        database_name=config.PSQL_DB_NAME,
        username=config.PSQL_USERNAME,
        password=config.PSQL_PASSWORD,
        hostname=config.PSQL_HOSTNAME,
        port=5432,
    )
    engine = create_async_engine(str(db))
    async with engine.begin() as conn:
        for i, sql in enumerate(MIGRATIONS, 1):
            try:
                await conn.execute(text(sql))
                print("[{}/{}] OK".format(i, len(MIGRATIONS)))
            except Exception as e:
                print("[{}/{}] Ошибка: {}".format(i, len(MIGRATIONS), e))
    await engine.dispose()
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
