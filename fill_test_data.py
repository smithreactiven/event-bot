"""Скрипт для заполнения тестовых данных - 20 участников."""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Данные подключения из .env
DB_URL = "postgresql+asyncpg://gen_user:3u79JGd2p9yjQ2h4@5.129.203.85:5432/default_db"

TEST_PARTICIPANTS = [
    (100000001, 'Анна Иванова', 'anna_ivanova'),
    (100000002, 'Борис Петров', 'boris_petrov'),
    (100000003, 'Виктория Сидорова', 'vika_sid'),
    (100000004, 'Григорий Козлов', 'grisha_k'),
    (100000005, 'Дарья Новикова', 'dasha_nov'),
    (100000006, 'Евгений Морозов', 'zhenya_m'),
    (100000007, 'Жанна Волкова', 'zhanna_v'),
    (100000008, 'Захар Лебедев', 'zahar_l'),
    (100000009, 'Ирина Козырева', 'irina_koz'),
    (100000010, 'Кирилл Соколов', 'kirill_sok'),
    (100000011, 'Лариса Попова', 'larisa_pop'),
    (100000012, 'Максим Васильев', 'max_vas'),
    (100000013, 'Наталья Зайцева', 'natasha_z'),
    (100000014, 'Олег Смирнов', 'oleg_smir'),
    (100000015, 'Полина Кузнецова', 'polina_kuz'),
    (100000016, 'Роман Федоров', 'roma_fed'),
    (100000017, 'Светлана Михайлова', 'sveta_mih'),
    (100000018, 'Тимур Алексеев', 'timur_alex'),
    (100000019, 'Ульяна Егорова', 'ulya_egor'),
    (100000020, 'Филипп Николаев', 'filipp_nik'),
]


async def main():
    engine = create_async_engine(DB_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Проверяем есть ли активное мероприятие
        result = await session.execute(text(
            "SELECT id FROM event WHERE is_started = true AND is_ended = false ORDER BY id DESC LIMIT 1"
        ))
        row = result.fetchone()
        
        if row:
            event_id = row[0]
            print(f"Найдено активное мероприятие: {event_id}")
        else:
            # Создаём новое мероприятие
            await session.execute(text(
                "INSERT INTO event (is_started, is_ended, total_rounds, current_round, created_at) "
                "VALUES (true, false, 3, 0, NOW())"
            ))
            await session.commit()
            result = await session.execute(text("SELECT id FROM event ORDER BY id DESC LIMIT 1"))
            event_id = result.fetchone()[0]
            print(f"Создано новое мероприятие: {event_id}")
        
        # Удаляем старых тестовых участников (с user_id 100000001-100000020)
        await session.execute(text(
            "DELETE FROM participant WHERE user_id >= 100000001 AND user_id <= 100000020"
        ))
        
        # Добавляем тестовых участников
        for user_id, full_name, telegram in TEST_PARTICIPANTS:
            await session.execute(text(
                "INSERT INTO participant (event_id, user_id, full_name, telegram, created_at) "
                "VALUES (:event_id, :user_id, :full_name, :telegram, NOW())"
            ), {"event_id": event_id, "user_id": user_id, "full_name": full_name, "telegram": telegram})
        
        await session.commit()
        
        # Проверяем
        result = await session.execute(text(
            "SELECT COUNT(*) FROM participant WHERE event_id = :event_id"
        ), {"event_id": event_id})
        count = result.fetchone()[0]
        print(f"Участников в мероприятии {event_id}: {count}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
