-- Сначала очистим старые данные (опционально)
-- DELETE FROM opinion;
-- DELETE FROM round_message;
-- DELETE FROM round;
-- DELETE FROM participant;
-- DELETE FROM event;

-- Создаём активное мероприятие
INSERT INTO event (is_started, is_ended, total_rounds, current_round, created_at)
VALUES (true, false, 3, 0, NOW())
RETURNING id;

-- Предположим что id мероприятия = 1 (или замени на актуальный)
-- Вставляем 20 тестовых участников с фейковыми telegram user_id

INSERT INTO participant (event_id, user_id, full_name, telegram, created_at) VALUES
(1, 100000001, 'Анна Иванова', 'anna_ivanova', NOW()),
(1, 100000002, 'Борис Петров', 'boris_petrov', NOW()),
(1, 100000003, 'Виктория Сидорова', 'vika_sid', NOW()),
(1, 100000004, 'Григорий Козлов', 'grisha_k', NOW()),
(1, 100000005, 'Дарья Новикова', 'dasha_nov', NOW()),
(1, 100000006, 'Евгений Морозов', 'zhenya_m', NOW()),
(1, 100000007, 'Жанна Волкова', 'zhanna_v', NOW()),
(1, 100000008, 'Захар Лебедев', 'zahar_l', NOW()),
(1, 100000009, 'Ирина Козырева', 'irina_koz', NOW()),
(1, 100000010, 'Кирилл Соколов', 'kirill_sok', NOW()),
(1, 100000011, 'Лариса Попова', 'larisa_pop', NOW()),
(1, 100000012, 'Максим Васильев', 'max_vas', NOW()),
(1, 100000013, 'Наталья Зайцева', 'natasha_z', NOW()),
(1, 100000014, 'Олег Смирнов', 'oleg_smir', NOW()),
(1, 100000015, 'Полина Кузнецова', 'polina_kuz', NOW()),
(1, 100000016, 'Роман Федоров', 'roma_fed', NOW()),
(1, 100000017, 'Светлана Михайлова', 'sveta_mih', NOW()),
(1, 100000018, 'Тимур Алексеев', 'timur_alex', NOW()),
(1, 100000019, 'Ульяна Егорова', 'ulya_egor', NOW()),
(1, 100000020, 'Филипп Николаев', 'filipp_nik', NOW());

-- Проверка
SELECT COUNT(*) as participants_count FROM participant WHERE event_id = 1;
