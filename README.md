# Univeersity_bot
# Telegram Бот для Управления Студенческими Данными

![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue)

## Описание

Этот проект представляет собой Telegram бота, разработанного для автоматизации управления студенческими данными в учебных заведениях. Бот позволяет студентам регистрироваться, просматривать расписание, отслеживать аттестацию, а классным представителям и администраторам выполнять дополнительные функции, такие как назначение старост, рассылка сообщений, резервное копирование базы данных и экспорт данных.

## Основные Возможности

- **Регистрация студентов**: Студенты могут зарегистрироваться, указав свои имя, фамилию и группу.
- **Просмотр расписания**: Пользователи могут просматривать расписание на сегодня, завтра или на неделю.
- **Аттестация**: Студенты могут просматривать свои оценки, а старосты — выставлять оценки студентам.
- **Объяснительные записки**: Студенты могут отправлять объяснительные записки, которые просматриваются старостой группы.
- **Рассылка сообщений**: Классные представители могут отправлять массовые сообщения всем членам группы.
- **Управление старостами**: Администраторы могут назначать пользователей старостами групп.
- **Резервное копирование и экспорт данных**: Администраторы могут создавать резервные копии базы данных и экспортировать данные в формате CSV или JSON.

## Установка

### Предварительные Требования

- Python 3.7 или выше
- PostgreSQL
- `pg_dump` для резервного копирования базы данных

### Шаги по Установке

1. **Клонируйте Репозиторий**

   ```bash
   git clone https://github.com/Padre12Rus/Univeersity_bot.git
   cd telegram-student-bot
   ```

2. **Создайте и Активируйте Виртуальное Окружение**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Для Linux/macOS
   venv\Scripts\activate     # Для Windows
   ```

3. **Установите Зависимости**

   ```bash
   pip install -r requirements.txt
   ```

4. **Настройте Переменные Окружения**

   Создайте файл `.env` в корне проекта и добавьте следующие переменные:

   ```env
   BOT_TOKEN=your_telegram_bot_token
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=your_database_name
   DB_USER=your_database_user
   DB_PASSWORD=your_database_password
   ADMIN_IDS=123456789,987654321  # Telegram ID администраторов, разделенные запятой
   ```

5. **Настройте Базу Данных**

   Убедитесь, что у вас есть настроенная база данных PostgreSQL с необходимыми таблицами. Пример SQL для создания таблиц:

   ```sql
   -- Пример таблиц, адаптируйте под свои нужды
   CREATE TABLE students (
       id SERIAL PRIMARY KEY,
       first_name VARCHAR(50),
       last_name VARCHAR(50),
       group_id INTEGER REFERENCES groups(id),
       telegram_id BIGINT UNIQUE
   );

   CREATE TABLE groups (
       id SERIAL PRIMARY KEY,
       name VARCHAR(50) UNIQUE
   );

   CREATE TABLE class_representatives (
       telegram_id BIGINT PRIMARY KEY,
       group_id INTEGER REFERENCES groups(id)
   );

   CREATE TABLE schedules (
       id SERIAL PRIMARY KEY,
       group_id INTEGER REFERENCES groups(id),
       day_of_week VARCHAR(10),
       week_type VARCHAR(10),
       subject_id INTEGER REFERENCES subjects(id),
       start_time TIME,
       end_time TIME,
       class_type VARCHAR(20)
   );

   CREATE TABLE subjects (
       id SERIAL PRIMARY KEY,
       name VARCHAR(100) UNIQUE
   );

   CREATE TABLE attestations (
       student_id INTEGER REFERENCES students(id),
       subject_id INTEGER REFERENCES subjects(id),
       grade INTEGER,
       PRIMARY KEY (student_id, subject_id)
   );

   CREATE TABLE explanations (
       id SERIAL PRIMARY KEY,
       student_id INTEGER REFERENCES students(id),
       subject_id INTEGER REFERENCES subjects(id),
       date DATE,
       explanation TEXT
   );

   CREATE TABLE temp_attendance (
       student_id INTEGER REFERENCES students(id),
       subject_id INTEGER REFERENCES subjects(id),
       class_time TIMESTAMP,
       status VARCHAR(10),
       PRIMARY KEY (student_id, subject_id, class_time)
   );

   CREATE TABLE attendance_journal (
       student_id INTEGER REFERENCES students(id),
       subject_id INTEGER REFERENCES subjects(id),
       date DATE,
       status VARCHAR(10),
       PRIMARY KEY (student_id, subject_id, date)
   );
   ```

6. **Запустите Бота**

   ```bash
   python your_bot_script.py
   ```

## Использование

### Команды для Пользователей

- `/start` — Начало взаимодействия с ботом и регистрация.
- **📅 Расписание** — Просмотр расписания.
- **📝 Аттестация** — Просмотр или выставление аттестаций.
- **📨 Объяснительные** — Отправка объяснительных записок (для старост).
- **📢 Рассылка сообщения** — Отправка массовых сообщений (для старост).
- **👤 Назначить старосту** — Назначение старосты (для администраторов).
- **💾 Резервное копирование** — Создание резервной копии базы данных (для администраторов).
- **📤 Экспорт данных** — Экспорт данных из таблиц базы данных (для администраторов).

### Администраторские Функции

- **Назначение Старосты**: Администраторы могут назначать пользователей старостами групп, введя их Telegram ID.
- **Удаление Пользователей**: Администраторы могут удалить всех пользователей из базы данных.
- **Резервное Копирование**: Создание резервных копий базы данных и отправка их администраторам.
- **Экспорт Данных**: Экспорт данных из выбранной таблицы в формате CSV или JSON.

## Настройка Автоматических Задач

Бот использует `APScheduler` для автоматического резервного копирования базы данных каждые 3 часа и планирования уведомлений о занятиях.

## Логирование

Логирование настроено с уровнем `INFO`. Логи помогают отслеживать работу бота и выявлять ошибки.

## Вклад

Будем рады вашему вкладу! Пожалуйста, следуйте следующим шагам:

1. Форкните репозиторий.
2. Создайте новую ветку (`git checkout -b feature/YourFeature`).
3. Сделайте коммит ваших изменений (`git commit -m 'Add some feature'`).
4. Запушьте ветку (`git push origin feature/YourFeature`).
5. Откройте Pull Request.

## Лицензия

Этот проект лицензирован под лицензией MIT. Подробнее см. файл [LICENSE](LICENSE).

## Контакты

Если у вас есть вопросы или предложения, свяжитесь с нами по адресу [padre12rus@icloud.com](mailto:padre12rus@icloud.com).
tg - @Depparain

---

*Разработано с любовью ❤️*