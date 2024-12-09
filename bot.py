import logging
import os
import subprocess
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS').split(',')]

ENTER_FIRST_NAME, ENTER_LAST_NAME, SELECT_GROUP = range(3)
SELECT_STUDENT, ENTER_GRADE = range(3, 5)
EXPORT_SELECT_TABLE, EXPORT_SELECT_FORMAT = range(5, 7)
BROADCAST_MESSAGE = range(7, 8)
ASSIGN_REPRESENTATIVE, ASSIGN_DEPUTY = range(8, 10)
CLASS_REPRESENTATIVE_MENU, ADMIN_MENU = range(10, 12)

connection_pool = SimpleConnectionPool(1, 20,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)

def get_connection():
    return connection_pool.getconn()

def release_connection(conn):
    connection_pool.putconn(conn)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

scheduler = None

def main_menu():
    keyboard = [
        ['📅 Расписание', '📝 Аттестация']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def class_representative_main_menu():
    keyboard = [
        ['📋 Меню старосты'],
        ['📅 Расписание', '📝 Аттестация']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_main_menu():
    keyboard = [
        ['⚙️ Админ-меню'],
        ['📅 Расписание', '📝 Аттестация']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def combined_main_menu():
    keyboard = [
        ['📋 Меню старосты', '⚙️ Админ-меню'],
        ['📅 Расписание', '📝 Аттестация']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def class_representative_menu():
    keyboard = [
        ['📨 Объяснительные', '📝 Выставить аттестацию'],
        ['📢 Рассылка сообщения'],
        ['👥 Назначить заместителя', '🔙 Главное меню']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_menu():
    keyboard = [
        ['👤 Назначить старосту', '🗑 Удалить пользователей'],
        ['💾 Резервное копирование', '📤 Экспорт данных'],
        ['🔙 Главное меню']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_menu(telegram_id):
    is_admin = telegram_id in ADMIN_IDS
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM class_representatives WHERE telegram_id = %s", (telegram_id,))
        is_representative = cursor.fetchone() is not None
        cursor.execute("SELECT 1 FROM deputy_class_representatives WHERE telegram_id = %s", (telegram_id,))
        is_deputy = cursor.fetchone() is not None
    finally:
        cursor.close()
        release_connection(conn)

    if is_admin and (is_representative or is_deputy):
        return combined_main_menu()
    elif is_admin:
        return admin_main_menu()
    elif is_representative or is_deputy:
        return class_representative_main_menu()
    else:
        return main_menu()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM students WHERE telegram_id = %s", (telegram_id,))
        result = cursor.fetchone()
    except Exception as e:
        logger.error(f"Ошибка в start: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при обработке вашего запроса.')
        return ConversationHandler.END
    finally:
        cursor.close()
        release_connection(conn)

    if result:
        menu = get_user_menu(telegram_id)
        await update.message.reply_text(
            'Вы уже зарегистрированы!',
            reply_markup=menu
        )
        return ConversationHandler.END
    else:
        keyboard = [[KeyboardButton('Назад')]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            'Добро пожаловать! Пожалуйста, представьтесь. Введите ваше имя:',
            reply_markup=reply_markup
        )
        return ENTER_FIRST_NAME

async def enter_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == 'Назад':
        await update.message.reply_text('Регистрация отменена.', reply_markup=main_menu())
        return ConversationHandler.END
    context.user_data['first_name'] = text
    keyboard = [[KeyboardButton('Назад')]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text('Введите вашу фамилию:', reply_markup=reply_markup)
    return ENTER_LAST_NAME

async def enter_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == 'Назад':
        keyboard = [[KeyboardButton('Назад')]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text('Введите ваше имя:', reply_markup=reply_markup)
        return ENTER_FIRST_NAME
    context.user_data['last_name'] = text

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM groups")
        groups = cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка при получении списка групп: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при получении списка групп.')
        return ConversationHandler.END
    finally:
        cursor.close()
        release_connection(conn)

    group_buttons = [KeyboardButton(group[0]) for group in groups]
    group_buttons.append(KeyboardButton('Назад'))
    keyboard = [group_buttons[i:i+2] for i in range(0, len(group_buttons), 2)]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text('Пожалуйста, выберите вашу группу:', reply_markup=reply_markup)
    return SELECT_GROUP

async def select_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_name = update.message.text.strip()
    if group_name == 'Назад':
        keyboard = [[KeyboardButton('Назад')]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text('Введите вашу фамилию:', reply_markup=reply_markup)
        return ENTER_LAST_NAME
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM groups WHERE name = %s", (group_name,))
        result = cursor.fetchone()
        if result:
            group_id = result[0]
            try:
                cursor.execute(
                    "INSERT INTO students (first_name, last_name, group_id, telegram_id) VALUES (%s, %s, %s, %s)",
                    (
                        context.user_data['first_name'],
                        context.user_data['last_name'],
                        group_id,
                        update.message.from_user.id
                    )
                )
                conn.commit()
                menu = get_user_menu(update.message.from_user.id)
                await update.message.reply_text(
                    'Вы успешно зарегистрированы!',
                    reply_markup=menu
                )
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                menu = get_user_menu(update.message.from_user.id)
                await update.message.reply_text(
                    'Вы уже зарегистрированы!',
                    reply_markup=menu
                )
                return ConversationHandler.END
            except Exception as e:
                conn.rollback()
                logger.error(f"Ошибка при регистрации студента: {e}", exc_info=True)
                await update.message.reply_text('Произошла ошибка при регистрации.')
                return ConversationHandler.END
        else:
            await update.message.reply_text(
                'Группа не найдена. Пожалуйста, выберите группу из списка или нажмите "Назад".'
            )
            return SELECT_GROUP
    except Exception as e:
        logger.error(f"Ошибка при регистрации студента: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при регистрации.')
    finally:
        cursor.close()
        release_connection(conn)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Регистрация отменена.', reply_markup=main_menu()
    )
    return ConversationHandler.END

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_broadcast'):
        await handle_broadcast_message(update, context)
        return
    if context.user_data.get('awaiting_representative_id'):
        await handle_assign_representative(update, context)
        return
    if context.user_data.get('awaiting_deputy_id'):
        await handle_assign_deputy(update, context)
        return
    if context.user_data.get('awaiting_explanation'):
        await handle_explanation(update, context)
        return

    text = update.message.text
    telegram_id = update.message.from_user.id
    is_admin = telegram_id in ADMIN_IDS
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM class_representatives WHERE telegram_id = %s", (telegram_id,))
        is_representative = cursor.fetchone() is not None
        cursor.execute("SELECT 1 FROM deputy_class_representatives WHERE telegram_id = %s", (telegram_id,))
        is_deputy = cursor.fetchone() is not None
    finally:
        cursor.close()
        release_connection(conn)

    if text == '📅 Расписание':
        await schedule_menu(update, context)
    elif text == '📝 Аттестация':
        await view_attestation(update, context)
    elif text == 'Главное меню':
        menu = get_user_menu(telegram_id)
        await update.message.reply_text(
            'Вы в главном меню.', reply_markup=menu
        )
    elif text == '📋 Меню старосты' and (is_representative or is_deputy):
        reply_markup = class_representative_menu()
        await update.message.reply_text('Выберите действие из меню старосты:', reply_markup=reply_markup)
    elif text == '⚙️ Админ-меню' and is_admin:
        reply_markup = admin_menu()
        await update.message.reply_text('Выберите действие из админ-меню:', reply_markup=reply_markup)
    elif text == '🔙 Главное меню':
        menu = get_user_menu(telegram_id)
        await update.message.reply_text(
            'Вы вернулись в главное меню.', reply_markup=menu
        )
    elif text in ['Сегодня', 'Завтра', 'На неделю']:
        await show_schedule(update, context)
    elif (is_representative or is_deputy) and text == '📨 Объяснительные':
        await view_explanations(update, context)
    elif (is_representative or is_deputy) and text == '📝 Выставить аттестацию':
        await set_attestation(update, context)
        return SELECT_STUDENT
    elif (is_representative or is_deputy) and text == '📢 Рассылка сообщения':
        await broadcast_message(update, context)
        return BROADCAST_MESSAGE
    elif is_representative and text == '👥 Назначить заместителя':
        await assign_deputy(update, context)
        return ASSIGN_DEPUTY
    elif is_admin and text == '👤 Назначить старосту':
        await assign_representative(update, context)
        return ASSIGN_REPRESENTATIVE
    elif is_admin and text == '🗑 Удалить пользователей':
        await clean_users(update, context)
    elif is_admin and text == '💾 Резервное копирование':
        await backup_database(update, context)
    elif is_admin and text == '📤 Экспорт данных':
        await export_data_start(update, context)
        return EXPORT_SELECT_TABLE
    else:
        menu = get_user_menu(telegram_id)
        await update.message.reply_text(
            'Пожалуйста, выберите действие из меню.',
            reply_markup=menu
        )

async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ['Сегодня', 'Завтра'],
        ['На неделю'],
        ['Главное меню']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        'Выберите период для просмотра расписания:',
        reply_markup=reply_markup
    )

def get_week_type(target_date):
    week_number = target_date.isocalendar()[1]
    return 'only_even' if week_number % 2 == 0 else 'only_odd'

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    period = update.message.text
    telegram_id = update.message.from_user.id
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT g.id FROM students s
            JOIN groups g ON s.group_id = g.id
            WHERE s.telegram_id = %s
        """, (telegram_id,))
        result = cursor.fetchone()

        if result:
            group_id = result['id']
            today = datetime.now()
            today_date = today.date()

            if period == 'Сегодня':
                target_dates = [today_date]
            elif period == 'Завтра':
                target_dates = [today_date + timedelta(days=1)]
            elif period == 'На неделю':
                today_weekday = today.weekday()
                monday_date = today_date - timedelta(days=today_weekday)
                target_dates = [monday_date + timedelta(days=i) for i in range(7)]
            else:
                await update.message.reply_text('Неверный период.')
                return

            response = ''
            for target_date in target_dates:
                day_of_week = target_date.strftime('%A')
                week_type = get_week_type(target_date)
                cursor.execute("""
                    SELECT s.start_time, s.end_time, sub.name, s.class_type
                    FROM schedules s
                    JOIN subjects sub ON s.subject_id = sub.id
                    WHERE s.group_id = %s AND s.day_of_week = %s AND s.week_type IN ('all', %s)
                    ORDER BY s.start_time
                """, (group_id, day_of_week, week_type))
                schedule_rows = cursor.fetchall()
                date_str = target_date.strftime('%d.%m.%Y')
                if schedule_rows:
                    response += f'\n📅 Расписание на {date_str}:\n'
                    for row in schedule_rows:
                        start_time = row['start_time'].strftime('%H:%M')
                        end_time = row['end_time'].strftime('%H:%M')
                        subject_name = row['name']
                        class_type = row['class_type']
                        class_type_ru = {
                            'lecture': 'Лекция',
                            'practice': 'Практика',
                            'lab': 'Лабораторная работа'
                        }.get(class_type, class_type)
                        response += f"{start_time} - {end_time}: {subject_name} ({class_type_ru})\n"
                else:
                    response += f'\nНа {date_str} занятий нет.\n'
            await update.message.reply_text(response, reply_markup=get_user_menu(telegram_id))
        else:
            await update.message.reply_text(
                'Вы не зарегистрированы. Пожалуйста, используйте команду /start для регистрации.'
            )
    except Exception as e:
        logger.error(f"Ошибка в show_schedule: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при получении расписания.')
    finally:
        cursor.close()
        release_connection(conn)

async def view_attestation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT id FROM students WHERE telegram_id = %s", (telegram_id,))
        student = cursor.fetchone()

        if student:
            student_id = student['id']
            cursor.execute("""
                SELECT sub.name AS subject_name, a.grade
                FROM attestations a
                JOIN subjects sub ON a.subject_id = sub.id
                WHERE a.student_id = %s
                ORDER BY sub.name
            """, (student_id,))
            attestation_rows = cursor.fetchall()

            if attestation_rows:
                response = '📝 Ваша аттестация:\n'
                for row in attestation_rows:
                    subject_name = row['subject_name']
                    grade = row['grade']
                    response += f"{subject_name}: {grade}\n"
                await update.message.reply_text(response, reply_markup=get_user_menu(telegram_id))
            else:
                await update.message.reply_text('У вас нет данных об аттестации.', reply_markup=get_user_menu(telegram_id))
        else:
            await update.message.reply_text('Вы не зарегистрированы. Пожалуйста, используйте команду /start для регистрации.')
    except Exception as e:
        logger.error(f"Ошибка в view_attestation: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при получении аттестации.')
    finally:
        cursor.close()
        release_connection(conn)

def get_week_type_for_db(target_date):
    week_number = target_date.isocalendar()[1]
    return 'only_even' if week_number % 2 == 0 else 'only_odd'

async def schedule_daily_notifications(application):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now()
        today = now.date()
        day_of_week = today.strftime('%A')
        week_type = get_week_type_for_db(today)

        logger.warning(f"Планирование уведомлений на {today} ({day_of_week}), неделя {week_type}")

        cursor.execute("""
            SELECT s.group_id, s.subject_id, s.start_time, s.class_type
            FROM schedules s
            WHERE s.day_of_week = %s AND s.week_type IN (%s, 'all')
        """, (day_of_week, week_type))
        classes = cursor.fetchall()

        for class_info in classes:
            group_id, subject_id, start_time, class_type = class_info
            class_datetime = datetime.combine(today, start_time)

            notification_time = class_datetime - timedelta(minutes=5)
            if notification_time > now:
                scheduler.add_job(
                    send_class_notification_job,
                    trigger=DateTrigger(run_date=notification_time),
                    args=[application, group_id, subject_id, start_time, class_type]
                )
                logger.warning(f"Запланировано уведомление для группы {group_id} по предмету {subject_id} на {notification_time}")

            attendance_collection_time = class_datetime + timedelta(minutes=5)
            if attendance_collection_time > now:
                scheduler.add_job(
                    collect_attendance_job,
                    trigger=DateTrigger(run_date=attendance_collection_time),
                    args=[application, group_id, subject_id, start_time]
                )
                logger.warning(f"Запланирован сбор посещаемости для группы {group_id} по предмету {subject_id} на {attendance_collection_time}")

    except Exception as e:
        logger.error(f"Ошибка в schedule_daily_notifications: {e}", exc_info=True)
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_connection(conn)

async def send_class_notification_job(application, group_id, subject_id, start_time, class_type):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM subjects WHERE id = %s", (subject_id,))
        subject_name = cursor.fetchone()[0]

        cursor.execute("SELECT telegram_id, id FROM students WHERE group_id = %s", (group_id,))
        students = cursor.fetchall()

        # Get class representative and deputy
        cursor.execute("SELECT telegram_id FROM class_representatives WHERE group_id = %s", (group_id,))
        starosta_result = cursor.fetchone()
        cursor.execute("SELECT telegram_id FROM deputy_class_representatives WHERE group_id = %s", (group_id,))
        deputy_result = cursor.fetchone()

        starosta_telegram_id = starosta_result[0] if starosta_result else None
        deputy_telegram_id = deputy_result[0] if deputy_result else None

        class_type_ru = {
            'lecture': 'Лекция',
            'practice': 'Практика',
            'lab': 'Лабораторная работа'
        }.get(class_type, class_type)

        for telegram_id, student_id in students:
            keyboard = [
                [InlineKeyboardButton("✅ Буду на паре", callback_data=f'present_{subject_id}_{student_id}')],
                [InlineKeyboardButton("❌ Отсутствую", callback_data=f'absent_{subject_id}_{student_id}')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                message = await application.bot.send_message(
                    chat_id=telegram_id,
                    text=f'Напоминание о начале пары "{subject_name}" ({class_type_ru}) в {start_time.strftime("%H:%M")}.\n'
                         f'Пожалуйста, отметьте свое присутствие.',
                    reply_markup=reply_markup
                )
                # Store message ID to delete later
                context = application.bot_data.setdefault('attendance_messages', {})
                context[telegram_id] = message.message_id
                logger.warning(f"Отправлено уведомление пользователю {telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения пользователю {telegram_id}: {e}", exc_info=True)

            class_datetime = datetime.combine(datetime.now().date(), start_time)
            try:
                cursor.execute("""
                    INSERT INTO temp_attendance (student_id, subject_id, class_time)
                    VALUES (%s, %s, %s)
                """, (student_id, subject_id, class_datetime))
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
            except Exception as e:
                conn.rollback()
                logger.error(f"Ошибка при вставке в temp_attendance: {e}", exc_info=True)

        # Notify class representative and deputy
        for rep_id in [starosta_telegram_id, deputy_telegram_id]:
            if rep_id:
                try:
                    await application.bot.send_message(
                        chat_id=rep_id,
                        text=f'Напоминание о начале пары "{subject_name}" ({class_type_ru}) в {start_time.strftime("%H:%M")}.',
                    )
                    logger.warning(f"Отправлено уведомление старосте/заместителю {rep_id}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения старосте/заместителю {rep_id}: {e}", exc_info=True)

        conn.commit()

    except Exception as e:
        logger.error(f"Ошибка в send_class_notification_job: {e}", exc_info=True)
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_connection(conn)

async def collect_attendance_job(application, group_id, subject_id, start_time):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now()
        class_time = datetime.combine(now.date(), start_time)

        # Get class representative and deputy
        cursor.execute("SELECT telegram_id FROM class_representatives WHERE group_id = %s", (group_id,))
        starosta_result = cursor.fetchone()
        cursor.execute("SELECT telegram_id FROM deputy_class_representatives WHERE group_id = %s", (group_id,))
        deputy_result = cursor.fetchone()

        reps = []
        if starosta_result:
            reps.append(starosta_result[0])
        if deputy_result:
            reps.append(deputy_result[0])

        if reps:
            cursor.execute("""
                SELECT ta.student_id, s.first_name, s.last_name, ta.status
                FROM temp_attendance ta
                JOIN students s ON ta.student_id = s.id
                WHERE ta.subject_id = %s AND ta.class_time = %s AND s.group_id = %s
                ORDER BY s.last_name, s.first_name
            """, (subject_id, class_time, group_id))
            attendance_records = cursor.fetchall()

            for rep_id in reps:
                # Build the attendance list
                attendance_text = 'Список посещаемости:\n'
                for idx, (student_id, first_name, last_name, status) in enumerate(attendance_records):
                    status_text = {
                        None: 'Не ответил',
                        'present': 'Будет присутствовать',
                        'absent': 'Отсутствует'
                    }.get(status, 'Неизвестно')
                    attendance_text += f"{idx+1}. {first_name} {last_name} - {status_text}\n"

                # Send message with options to modify each student's status
                keyboard = [
                    [InlineKeyboardButton(f"Изменить статус {idx+1}", callback_data=f'edit_{idx}_{subject_id}_{class_time.timestamp()}')]
                    for idx in range(len(attendance_records))
                ]
                keyboard.append([InlineKeyboardButton("✅ Подтвердить и отправить", callback_data=f'confirm_all_{subject_id}_{class_time.timestamp()}')])
                reply_markup = InlineKeyboardMarkup(keyboard)

                try:
                    await application.bot.send_message(
                        chat_id=rep_id,
                        text=attendance_text,
                        reply_markup=reply_markup
                    )
                    logger.warning(f"Отправлен список посещаемости старосте/заместителю {rep_id}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения старосте/заместителю {rep_id}: {e}", exc_info=True)

        conn.commit()

    except Exception as e:
        logger.error(f"Ошибка в collect_attendance_job: {e}", exc_info=True)
    finally:
        if cursor:
            cursor.close()
        if conn:
            release_connection(conn)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    telegram_id = query.from_user.id
    data = query.data

    parts = data.split('_')

    if parts[0] in ['present', 'absent']:
        action, subject_id, student_id = parts
        subject_id = int(subject_id)
        student_id = int(student_id)
        status = 'present' if action == 'present' else 'absent'
        await query.answer('Спасибо за ваш ответ.')
        await query.message.delete()
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT class_time FROM temp_attendance
                WHERE student_id = %s AND subject_id = %s
            """, (student_id, subject_id))
            result = cursor.fetchone()
            if result:
                class_time = result[0]
                cursor.execute("""
                    UPDATE temp_attendance
                    SET status = %s
                    WHERE student_id = %s AND subject_id = %s AND class_time = %s
                """, (status, student_id, subject_id, class_time))
                conn.commit()
            else:
                logger.error(f"Не удалось найти запись в temp_attendance для студента {student_id} и предмета {subject_id}")
        except Exception as e:
            logger.error(f"Ошибка в button_callback (present/absent): {e}", exc_info=True)
            await query.answer('Произошла ошибка при записи статуса.')
        finally:
            cursor.close()
            release_connection(conn)
        if action == 'absent':
            context.user_data['awaiting_explanation'] = True
            context.user_data['subject_id'] = subject_id
            context.user_data['student_id'] = student_id
            await context.bot.send_message(chat_id=telegram_id, text='Введите причину отсутствия.')
    elif parts[0] == 'edit':
        idx, subject_id, class_time_ts = int(parts[1]), int(parts[2]), float(parts[3])
        class_time = datetime.fromtimestamp(class_time_ts)

        context.user_data['edit_idx'] = idx
        context.user_data['subject_id'] = subject_id
        context.user_data['class_time'] = class_time
        context.user_data['telegram_id'] = telegram_id

        # Fetch student info
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ta.student_id, s.first_name, s.last_name, ta.status
                FROM temp_attendance ta
                JOIN students s ON ta.student_id = s.id
                WHERE ta.subject_id = %s AND ta.class_time = %s
                ORDER BY s.last_name, s.first_name
            """, (subject_id, class_time))
            attendance_records = cursor.fetchall()
            if idx < 0 or idx >= len(attendance_records):
                await query.answer('Неверный индекс.')
                return
            student_id, first_name, last_name, status = attendance_records[idx]
            status_text = {
                None: 'Не ответил',
                'present': 'Будет присутствовать',
                'absent': 'Отсутствует'
            }.get(status, 'Неизвестно')

            keyboard = [
                [
                    InlineKeyboardButton("✅ Присутствует", callback_data=f'change_present_{student_id}_{subject_id}_{class_time_ts}'),
                    InlineKeyboardButton("❌ Отсутствует", callback_data=f'change_absent_{student_id}_{subject_id}_{class_time_ts}')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=f"Студент: {first_name} {last_name}\nТекущий статус: {status_text}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании статуса: {e}", exc_info=True)
            await query.answer('Произошла ошибка.')
        finally:
            cursor.close()
            release_connection(conn)

    elif parts[0] == 'change':
        status_action, student_id, subject_id, class_time_ts = parts[1], int(parts[2]), int(parts[3]), float(parts[4])
        class_time = datetime.fromtimestamp(class_time_ts)
        status = 'present' if status_action == 'present' else 'absent'

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE temp_attendance
                SET status = %s
                WHERE student_id = %s AND subject_id = %s AND class_time = %s
            """, (status, student_id, subject_id, class_time))
            conn.commit()
            await query.answer('Статус обновлен.')
            # Optionally, you can re-display the attendance list here
            await query.message.delete()
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса: {e}", exc_info=True)
            await query.answer('Произошла ошибка при обновлении статуса.')
        finally:
            cursor.close()
            release_connection(conn)

    elif parts[0] == 'confirm':
        if parts[1] == 'all':
            subject_id, class_time_ts = int(parts[2]), float(parts[3])
            class_time = datetime.fromtimestamp(class_time_ts)

            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT student_id, status FROM temp_attendance
                    WHERE subject_id = %s AND class_time = %s
                """, (subject_id, class_time))
                records = cursor.fetchall()
                for student_id, status in records:
                    if status:
                        try:
                            cursor.execute("""
                                INSERT INTO attendance_journal (student_id, subject_id, date, status)
                                VALUES (%s, %s, %s, %s)
                            """, (student_id, subject_id, class_time.date(), status))
                        except psycopg2.errors.UniqueViolation:
                            conn.rollback()
                            cursor.execute("""
                                UPDATE attendance_journal SET status=%s
                                WHERE student_id=%s AND subject_id=%s AND date=%s
                            """, (status, student_id, subject_id, class_time.date()))
                conn.commit()
                await query.answer('Посещаемость сохранена.')
                await query.edit_message_text('Посещаемость успешно сохранена.')
            except Exception as e:
                logger.error(f"Ошибка при сохранении посещаемости: {e}", exc_info=True)
                await query.answer('Произошла ошибка при сохранении посещаемости.')
            finally:
                cursor.close()
                release_connection(conn)
    else:
        # Handle other callback data
        pass

async def handle_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_explanation'):
        explanation = update.message.text
        telegram_id = update.message.from_user.id
        subject_id = context.user_data['subject_id']
        student_id = context.user_data['student_id']
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO explanations (student_id, subject_id, date, explanation)
                VALUES (%s, %s, %s, %s)
            """, (student_id, subject_id, datetime.now().date(), explanation))
            conn.commit()
            await update.message.reply_text('Спасибо, ваша объяснительная отправлена старосте.')
        except Exception as e:
            logger.error(f"Ошибка в handle_explanation: {e}", exc_info=True)
            await update.message.reply_text('Произошла ошибка при отправке объяснительной.')
        finally:
            cursor.close()
            release_connection(conn)
        context.user_data['awaiting_explanation'] = False

def is_class_representative():
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            telegram_id = update.effective_user.id
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT group_id FROM class_representatives WHERE telegram_id = %s", (telegram_id,))
                result = cursor.fetchone()
                if result:
                    context.user_data['group_id'] = result[0]
                    return await func(update, context, *args, **kwargs)
                cursor.execute("SELECT group_id FROM deputy_class_representatives WHERE telegram_id = %s", (telegram_id,))
                result = cursor.fetchone()
                if result:
                    context.user_data['group_id'] = result[0]
                    return await func(update, context, *args, **kwargs)
            finally:
                cursor.close()
                release_connection(conn)
            await update.message.reply_text('У вас нет прав для выполнения этой команды.')
        return wrapper
    return decorator

def is_admin():
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            telegram_id = update.effective_user.id
            if telegram_id in ADMIN_IDS:
                return await func(update, context, *args, **kwargs)
            else:
                await update.message.reply_text('У вас нет прав администратора.')
        return wrapper
    return decorator

@is_class_representative()
async def view_explanations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = context.user_data['group_id']
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT s.first_name, s.last_name, sub.name, e.date, e.explanation
            FROM explanations e
            JOIN students s ON e.student_id = s.id
            JOIN subjects sub ON e.subject_id = sub.id
            WHERE s.group_id = %s
            ORDER BY e.date DESC
        """, (group_id,))
        explanations = cursor.fetchall()
        if explanations:
            response = '📨 Объяснительные от студентов:\n'
            for row in explanations:
                first_name = row['first_name']
                last_name = row['last_name']
                subject_name = row['name']
                date = row['date'].strftime('%d.%m.%Y')
                explanation = row['explanation']
                response += f"{date} - {first_name} {last_name} ({subject_name}):\n{explanation}\n\n"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text('Нет новых объяснительных.')
    except Exception as e:
        logger.error(f"Ошибка в view_explanations: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при получении объяснительных.')
    finally:
        cursor.close()
        release_connection(conn)

@is_class_representative()
async def set_attestation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = context.user_data['group_id']
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, first_name, last_name FROM students WHERE group_id = %s
        """, (group_id,))
        students = cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка в set_attestation: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при получении списка студентов.')
        return ConversationHandler.END
    finally:
        cursor.close()
        release_connection(conn)

    if students:
        student_buttons = [KeyboardButton(f"{student[1]} {student[2]}") for student in students]
        student_buttons.append(KeyboardButton('Назад'))
        keyboard = [student_buttons[i:i+2] for i in range(0, len(student_buttons), 2)]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text('Выберите студента для выставления аттестации:', reply_markup=reply_markup)
        context.user_data['students'] = {f"{s[1]} {s[2]}": s[0] for s in students}
        return SELECT_STUDENT
    else:
        await update.message.reply_text('В вашей группе нет студентов.')
        return ConversationHandler.END

async def select_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_student = update.message.text.strip()
    if selected_student == 'Назад':
        await update.message.reply_text('Операция отменена.', reply_markup=get_user_menu(update.message.from_user.id))
        return ConversationHandler.END
    student_id = context.user_data['students'].get(selected_student)

    if student_id:
        context.user_data['selected_student_id'] = student_id
        conn = get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT id, name FROM subjects ORDER BY name ASC")
            subjects = cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка в select_student: {e}", exc_info=True)
            await update.message.reply_text('Произошла ошибка при получении списка предметов.')
            return ConversationHandler.END
        finally:
            cursor.close()
            release_connection(conn)

        if subjects:
            context.user_data['subjects'] = subjects
            context.user_data['current_subject_index'] = 0
            first_subject = subjects[0]['name']
            keyboard = [[KeyboardButton('Назад')]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(f'Введите оценку для предмета "{first_subject}":', reply_markup=reply_markup)
            return ENTER_GRADE
        else:
            await update.message.reply_text('Список предметов пуст.')
            return ConversationHandler.END
    else:
        await update.message.reply_text('Пожалуйста, выберите студента из списка.')
        return SELECT_STUDENT

async def enter_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == 'Назад':
        await set_attestation(update, context)
        return SELECT_STUDENT
    try:
        grade = int(text)
        if grade < 2 or grade > 5:
            await update.message.reply_text('Пожалуйста, введите оценку от 2 до 5 или нажмите "Назад".')
            return ENTER_GRADE
        student_id = context.user_data['selected_student_id']
        subject_id = context.user_data['subjects'][context.user_data['current_subject_index']]['id']

        conn = get_connection()
        try:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO attestations (student_id, subject_id, grade)
                    VALUES (%s, %s, %s)
                """, (student_id, subject_id, grade))
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                cursor.execute("""
                    UPDATE attestations SET grade=%s
                    WHERE student_id=%s AND subject_id=%s
                """, (grade, student_id, subject_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Ошибка в enter_grade: {e}", exc_info=True)
            await update.message.reply_text('Произошла ошибка при сохранении оценки.')
            return ENTER_GRADE
        finally:
            cursor.close()
            release_connection(conn)

        context.user_data['current_subject_index'] += 1
        if context.user_data['current_subject_index'] < len(context.user_data['subjects']):
            next_subject = context.user_data['subjects'][context.user_data['current_subject_index']]['name']
            keyboard = [[KeyboardButton('Назад')]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(f'Введите оценку для предмета "{next_subject}":', reply_markup=reply_markup)
            return ENTER_GRADE
        else:
            await update.message.reply_text('Все оценки успешно выставлены.', reply_markup=get_user_menu(update.message.from_user.id))
            return ConversationHandler.END
    except ValueError:
        await update.message.reply_text('Пожалуйста, введите корректное числовое значение оценки или нажмите "Назад".')
        return ENTER_GRADE

@is_class_representative()
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Введите сообщение для рассылки:')
    context.user_data['awaiting_broadcast'] = True
    return BROADCAST_MESSAGE

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_broadcast'):
        message = update.message.text
        group_id = context.user_data['group_id']
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id FROM students WHERE group_id = %s", (group_id,))
            students = cursor.fetchall()
            for (telegram_id,) in students:
                try:
                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=f"📢 Сообщение от старосты:\n\n{message}"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке сообщения пользователю {telegram_id}: {e}", exc_info=True)
            await update.message.reply_text('Сообщение отправлено всем членам группы.', reply_markup=get_user_menu(update.message.from_user.id))
            context.user_data['awaiting_broadcast'] = False
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Ошибка в handle_broadcast_message: {e}", exc_info=True)
            await update.message.reply_text('Произошла ошибка при отправке сообщения.')
        finally:
            cursor.close()
            release_connection(conn)

@is_admin()
async def assign_representative(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Введите Telegram ID пользователя для назначения старостой:')
    context.user_data['awaiting_representative_id'] = True
    return ASSIGN_REPRESENTATIVE

async def handle_assign_representative(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_representative_id'):
        try:
            telegram_id = int(update.message.text)
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT group_id FROM students WHERE telegram_id = %s", (telegram_id,))
                result = cursor.fetchone()
                if result:
                    group_id = result[0]
                    try:
                        cursor.execute("""
                            INSERT INTO class_representatives (telegram_id, group_id)
                            VALUES (%s, %s)
                        """, (telegram_id, group_id))
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        cursor.execute("""
                            UPDATE class_representatives SET group_id=%s
                            WHERE telegram_id=%s
                        """, (group_id, telegram_id))
                    conn.commit()
                    await update.message.reply_text('Пользователь назначен старостой группы.', reply_markup=get_user_menu(update.message.from_user.id))
                else:
                    await update.message.reply_text('Студент с таким Telegram ID не найден.')
            except Exception as e:
                conn.rollback()
                logger.error(f"Ошибка в handle_assign_representative: {e}", exc_info=True)
                await update.message.reply_text('Произошла ошибка при назначении старосты.')
            finally:
                cursor.close()
                release_connection(conn)
        except ValueError:
            await update.message.reply_text('Пожалуйста, введите корректный Telegram ID.')
        context.user_data['awaiting_representative_id'] = False
        return ConversationHandler.END

@is_class_representative()
async def assign_deputy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Введите Telegram ID пользователя для назначения заместителем старосты:')
    context.user_data['awaiting_deputy_id'] = True
    return ASSIGN_DEPUTY

async def handle_assign_deputy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_deputy_id'):
        try:
            telegram_id = int(update.message.text)
            group_id = context.user_data['group_id']
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM students WHERE telegram_id = %s AND group_id = %s", (telegram_id, group_id))
                result = cursor.fetchone()
                if result:
                    try:
                        cursor.execute("""
                            INSERT INTO deputy_class_representatives (telegram_id, group_id)
                            VALUES (%s, %s)
                        """, (telegram_id, group_id))
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        cursor.execute("""
                            UPDATE deputy_class_representatives SET group_id=%s
                            WHERE telegram_id=%s
                        """, (group_id, telegram_id))
                    conn.commit()
                    await update.message.reply_text('Пользователь назначен заместителем старосты группы.', reply_markup=get_user_menu(update.message.from_user.id))
                else:
                    await update.message.reply_text('Студент с таким Telegram ID не найден в вашей группе.')
            except Exception as e:
                conn.rollback()
                logger.error(f"Ошибка в handle_assign_deputy: {e}", exc_info=True)
                await update.message.reply_text('Произошла ошибка при назначении заместителя старосты.')
            finally:
                cursor.close()
                release_connection(conn)
        except ValueError:
            await update.message.reply_text('Пожалуйста, введите корректный Telegram ID.')
        context.user_data['awaiting_deputy_id'] = False
        return ConversationHandler.END

@is_admin()
async def clean_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM students")
        conn.commit()
        await update.message.reply_text('Все пользователи были удалены.')
    except Exception as e:
        logger.error(f"Ошибка в clean_users: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при удалении пользователей.')
    finally:
        cursor.close()
        release_connection(conn)

@is_admin()
async def backup_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Создаю резервную копию базы данных...')

    await perform_backup_and_send(context.application, update.effective_chat.id)

async def perform_backup_and_send(application, chat_id):
    pg_dump_path = "pg_dump"
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = os.getenv("DB_PORT")
    backup_file = "backup.sql"

    try:
        command = [
            pg_dump_path,
            "-U", db_user,
            "-h", db_host,
            "-p", db_port,
            db_name
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = os.getenv("DB_PASSWORD")

        with open(backup_file, 'w', encoding='utf-8') as outfile:
            subprocess.run(command, env=env, check=True, stdout=outfile, stderr=subprocess.STDOUT, text=True)

        try:
            with open(backup_file, "rb") as file:
                await application.bot.send_document(
                    chat_id=chat_id,
                    document=file,
                    caption="Резервная копия базы данных."
                )
                logger.warning(f'Резервная копия успешно создана и отправлена администратору {chat_id}.')
        except Exception as e:
            logger.error(f"Ошибка при отправке файла: {e}", exc_info=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка резервного копирования: {e}", exc_info=True)
    finally:
        if os.path.exists(backup_file):
            os.remove(backup_file)

async def automatic_backup_database(application):
    logger.warning("Запуск автоматического резервного копирования базы данных.")
    for admin_id in ADMIN_IDS:
        await perform_backup_and_send(application, admin_id)

@is_admin()
async def export_data_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
            AND table_type='BASE TABLE';
        """)
        tables = cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка в export_data_start: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при получении списка таблиц.')
        return ConversationHandler.END
    finally:
        cursor.close()
        release_connection(conn)
    
    if tables:
        table_names = [table[0] for table in tables]
        table_names.append('Назад')
        keyboard = [KeyboardButton(name) for name in table_names]
        keyboard = [keyboard[i:i+2] for i in range(0, len(keyboard), 2)]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text('Выберите таблицу для экспорта данных:', reply_markup=reply_markup)
        context.user_data['available_tables'] = table_names
        return EXPORT_SELECT_TABLE
    else:
        await update.message.reply_text('В базе данных нет доступных таблиц для экспорта.')
        return ConversationHandler.END

async def handle_table_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_table = update.message.text
    if selected_table == 'Назад':
        await update.message.reply_text('Операция экспорта отменена.', reply_markup=get_user_menu(update.message.from_user.id))
        return ConversationHandler.END
    if selected_table in context.user_data.get('available_tables', []):
        context.user_data['selected_table'] = selected_table
        keyboard = [
            [KeyboardButton('CSV'), KeyboardButton('JSON')],
            [KeyboardButton('Назад')]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text('Выберите формат экспорта данных:', reply_markup=reply_markup)
        return EXPORT_SELECT_FORMAT
    else:
        await update.message.reply_text('Пожалуйста, выберите таблицу из списка или нажмите "Назад".')
        return EXPORT_SELECT_TABLE

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_format = update.message.text.upper()
    if selected_format == 'НАЗАД':
        await export_data_start(update, context)
        return EXPORT_SELECT_TABLE
    if selected_format in ['CSV', 'JSON']:
        table_name = context.user_data['selected_table']
        await export_table_data(update, context, table_name, selected_format)
        return ConversationHandler.END
    else:
        await update.message.reply_text('Пожалуйста, выберите формат из списка: CSV или JSON, или нажмите "Назад".')
        return EXPORT_SELECT_FORMAT

async def export_table_data(update: Update, context: ContextTypes.DEFAULT_TYPE, table_name: str, file_format: str):
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(f"SELECT * FROM {table_name}")
        records = cursor.fetchall()
        if records:
            if file_format == 'CSV':
                import csv
                file_name = f"{table_name}.csv"
                with open(file_name, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=records[0].keys())
                    writer.writeheader()
                    writer.writerows(records)
            elif file_format == 'JSON':
                import json
                file_name = f"{table_name}.json"
                with open(file_name, 'w', encoding='utf-8') as jsonfile:
                    json.dump(records, jsonfile, ensure_ascii=False, indent=4)
            else:
                await update.message.reply_text('Неподдерживаемый формат файла.')
                return
            with open(file_name, 'rb') as file:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=file,
                    caption=f'Экспортированные данные из таблицы {table_name} в формате {file_format}.'
                )
            os.remove(file_name)
            await update.message.reply_text('Данные успешно экспортированы и отправлены.')
        else:
            await update.message.reply_text(f'Таблица {table_name} не содержит данных.')
    except Exception as e:
        logger.error(f"Ошибка в export_table_data: {e}", exc_info=True)
        await update.message.reply_text('Произошла ошибка при экспорте данных.')
    finally:
        cursor.close()
        release_connection(conn)

def schedule_jobs(application):
    global scheduler
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.start()

    scheduler.add_job(
        automatic_backup_database,
        trigger=IntervalTrigger(hours=3),
        args=[application]
    )

    scheduler.add_job(
        schedule_daily_notifications,
        trigger=CronTrigger(hour=0, minute=0),
        args=[application]
    )

    scheduler.add_job(
        schedule_daily_notifications,
        trigger=DateTrigger(run_date=datetime.now()),
        args=[application]
    )

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    registration_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            ENTER_FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_first_name)],
            ENTER_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_last_name)],
            SELECT_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_group)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(registration_conv_handler)

    attestation_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📝 Выставить аттестацию$'), set_attestation)],
        states={
            SELECT_STUDENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_student)],
            ENTER_GRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_grade)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(attestation_conv_handler)

    export_data_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📤 Экспорт данных$'), export_data_start)],
        states={
            EXPORT_SELECT_TABLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_table_selection)],
            EXPORT_SELECT_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_format_selection)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(export_data_conv_handler)

    broadcast_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📢 Рассылка сообщения$'), broadcast_message)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(broadcast_conv_handler)

    assign_representative_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^👤 Назначить старосту$'), assign_representative)],
        states={
            ASSIGN_REPRESENTATIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_assign_representative)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(assign_representative_conv_handler)

    assign_deputy_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^👥 Назначить заместителя$'), assign_deputy)],
        states={
            ASSIGN_DEPUTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_assign_deputy)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    application.add_handler(assign_deputy_conv_handler)

    application.add_handler(CallbackQueryHandler(button_callback))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    schedule_jobs(application)

    application.run_polling()

if __name__ == '__main__':
    main()
