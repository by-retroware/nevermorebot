import os
import random
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== НАСТРОЙКА ДЛЯ РАБОТЫ В ГРУППЕ ==========
import logging
import asyncpg
logging.basicConfig(level=logging.INFO)

# Включаем обработку команд в группах
class CustomApplication(Application):
    """Кастомное приложение для работы в группах"""
    pass

# Функция для проверки, что сообщение из группы
def is_group(update: Update) -> bool:
    """Проверяет, пришло ли сообщение из группы"""
    return update.effective_chat and update.effective_chat.type in ['group', 'supergroup']

# ========== КОНФИГ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "8768445585:AAHzkCok9liE_sottsWDdTKqSu1jYTzDErA")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMINS = {int(x) for x in os.getenv("ADMINS", "5695593671,1784442476").split(",")}
FAMILY_NAME = "Nevermore"
FAMILY_LINK = "https://t.me/famnevermore"
AUTH_LINK = "https://t.me/famnevermore/19467"
RULES_LINK = "https://t.me/famnevermore/26"
NEWS_LINK = "https://t.me/famnevermore/5"

# ========== БАЗА ДАННЫХ ==========
import asyncpg

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

def init_db():
    print("✅ База данных PostgreSQL готова (таблицы созданы в Supabase)")

# ========== ФУНКЦИИ БД ==========
def get_user(user_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_get_user(user_id))

async def _get_user(user_id):
    conn = await get_db()
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return dict(row) if row else None

def add_user(user):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_add_user(user))

async def _add_user(user):
    conn = await get_db()
    now = datetime.now().isoformat()
    await conn.execute("""
        INSERT INTO users (user_id, name, username, last_online, joined, monthly_msgs)
        VALUES ($1, $2, $3, $4, $5, 0)
        ON CONFLICT (user_id) DO UPDATE SET
            name = EXCLUDED.name,
            username = EXCLUDED.username,
            last_online = EXCLUDED.last_online,
            msgs = users.msgs + 1,
            monthly_msgs = users.monthly_msgs + 1
    """, user.id, user.first_name, user.username, now, now)
    await conn.close()

def update_user(user_id, field, value):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_update_user(user_id, field, value))

async def _update_user(user_id, field, value):
    conn = await get_db()
    await conn.execute(f"UPDATE users SET {field} = $1 WHERE user_id = $2", value, user_id)
    await conn.close()

def add_log(user_id, action, target=None, reason=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_add_log(user_id, action, target, reason))

async def _add_log(user_id, action, target, reason):
    conn = await get_db()
    await conn.execute(
        "INSERT INTO logs (user_id, action, target, reason, time) VALUES ($1, $2, $3, $4, $5)",
        user_id, action, target, reason, datetime.now().isoformat()
    )
    await conn.close()

def get_all_users():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_get_all_users())

async def _get_all_users():
    conn = await get_db()
    rows = await conn.fetch("SELECT * FROM users")
    await conn.close()
    return [dict(row) for row in rows]

def get_active_weddings():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_get_active_weddings())

async def _get_active_weddings():
    conn = await get_db()
    rows = await conn.fetch("SELECT * FROM weddings WHERE divorced = 0")
    await conn.close()
    return [dict(row) for row in rows]

def add_wedding(u1, u2):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_add_wedding(u1, u2))

async def _add_wedding(u1, u2):
    conn = await get_db()
    await conn.execute(
        "INSERT INTO weddings (user1, user2, date) VALUES ($1, $2, $3)",
        u1, u2, datetime.now().isoformat()
    )
    await conn.execute("UPDATE users SET spouse_id = $1 WHERE user_id = $2", u2, u1)
    await conn.execute("UPDATE users SET spouse_id = $1 WHERE user_id = $2", u1, u2)
    await conn.close()

def divorce_wedding(user_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_divorce_wedding(user_id))

async def _divorce_wedding(user_id):
    conn = await get_db()
    row = await conn.fetchrow("SELECT spouse_id FROM users WHERE user_id = $1", user_id)
    if row and row["spouse_id"]:
        spouse = row["spouse_id"]
        await conn.execute(
            "UPDATE weddings SET divorced = 1 WHERE (user1 = $1 OR user2 = $1) AND divorced = 0",
            user_id
        )
        await conn.execute("UPDATE users SET spouse_id = NULL WHERE user_id = $1", user_id)
        await conn.execute("UPDATE users SET spouse_id = NULL WHERE user_id = $1", spouse)
        await conn.close()
        return spouse
    await conn.close()
    return None

def add_mute(user_id, minutes, reason, mod_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_add_mute(user_id, minutes, reason, mod_id))

async def _add_mute(user_id, minutes, reason, mod_id):
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    conn = await get_db()
    await conn.execute(
        "INSERT INTO mutes (user_id, until, reason, moderator_id) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO UPDATE SET until = $2, reason = $3, moderator_id = $4",
        user_id, until, reason, mod_id
    )
    await conn.close()

def remove_mute(user_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_remove_mute(user_id))

async def _remove_mute(user_id):
    conn = await get_db()
    await conn.execute("DELETE FROM mutes WHERE user_id = $1", user_id)
    await conn.close()

def is_muted(user_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_is_muted(user_id))

async def _is_muted(user_id):
    conn = await get_db()
    row = await conn.fetchrow(
        "SELECT until FROM mutes WHERE user_id = $1 AND until > $2",
        user_id, datetime.now().isoformat()
    )
    await conn.close()
    return row is not None

def add_ban(user_id, days, reason, mod_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_add_ban(user_id, days, reason, mod_id))

async def _add_ban(user_id, days, reason, mod_id):
    until = (datetime.now() + timedelta(days=days)).isoformat()
    conn = await get_db()
    await conn.execute(
        "INSERT INTO bans (user_id, until, reason, moderator_id) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO UPDATE SET until = $2, reason = $3, moderator_id = $4",
        user_id, until, reason, mod_id
    )
    await conn.close()

def remove_ban(user_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_remove_ban(user_id))

async def _remove_ban(user_id):
    conn = await get_db()
    await conn.execute("DELETE FROM bans WHERE user_id = $1", user_id)
    await conn.close()

def is_banned(user_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_is_banned(user_id))

async def _is_banned(user_id):
    conn = await get_db()
    row = await conn.fetchrow(
        "SELECT until FROM bans WHERE user_id = $1 AND until > $2",
        user_id, datetime.now().isoformat()
    )
    await conn.close()
    return row is not None

def get_bans_list():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_get_bans_list())

async def _get_bans_list():
    conn = await get_db()
    rows = await conn.fetch(
        "SELECT * FROM bans WHERE until > $1", datetime.now().isoformat()
    )
    await conn.close()
    return [dict(row) for row in rows]

def get_mutes_list():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_get_mutes_list())

async def _get_mutes_list():
    conn = await get_db()
    rows = await conn.fetch(
        "SELECT * FROM mutes WHERE until > $1", datetime.now().isoformat()
    )
    await conn.close()
    return [dict(row) for row in rows]

def get_logs(limit=15):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_get_logs(limit))

async def _get_logs(limit):
    conn = await get_db()
    rows = await conn.fetch("SELECT * FROM logs ORDER BY id DESC LIMIT $1", limit)
    await conn.close()
    return [dict(row) for row in rows]

def reset_monthly_stats():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(_reset_monthly_stats())

async def _reset_monthly_stats():
    conn = await get_db()
    await conn.execute("UPDATE users SET monthly_msgs = 0")
    await conn.close()

# ========== РАНГИ ==========
game_ranks = {
    0: {"name": "⚠️ Заблокирован", "emoji": "🚫"},
    1: {"name": "Не используется", "emoji": "❌"},
    2: {"name": "Новичок", "emoji": "😭"},
    3: {"name": "Любитель скорости", "emoji": "🏎"},
    4: {"name": "Образованный", "emoji": "💻"},
    5: {"name": "Невермор", "emoji": "🎧"},
    6: {"name": "Шарющий", "emoji": "📖"},
    7: {"name": "Барыга", "emoji": "😎"},
    8: {"name": "Премиум", "emoji": "🤩"},
    9: {"name": "Зам. лидера", "emoji": "👑"},
    10: {"name": "Лидер", "emoji": "💎"}
}

def get_rank_name(role):
    return game_ranks.get(role, game_ranks[2])["name"]

def get_rank_emoji(role):
    return game_ranks.get(role, game_ranks[2])["emoji"]

def is_moderator(user_id):
    user = get_user(user_id)
    return user and user["mod_role"] is not None and user["mod_role"] >= 8

def get_user_id_from_input(input_str):
    input_str = input_str.strip()
    if input_str.startswith('@'):
        username = input_str[1:].lower()
        for u in get_all_users():
            if u["username"] and u["username"].lower() == username:
                return u["user_id"]
        return None
    try:
        return int(input_str)
    except:
        return None

# ========== ПРАВИЛА ==========
RULES = """
📜 *ПРАВИЛА FAM NEVERMORE* 📜

*ОСНОВНЫЕ ПРАВИЛА:*

2️⃣ *18+ контент* — запрещено!
   → 1 раз: мут 120 минут
   → повтор: бан

3️⃣ *Упоминание родителей* — запрещено!
   → мут 120 минут
   → неоднократно: бан

4️⃣ *Слив личных данных* — бан

5️⃣ *Уважение к старшим по рангу* — обязательно

6️⃣ *Доксинг, сваты, угрозы* — бан

7️⃣ *Политика* — мут 60 минут

8️⃣ *Выдавать себя за лидера/зама* — бан

9️⃣ *Угрозы баном/киком* (если вы не лидер/зам) — мут

🔟 *Свастики и нацистская символика* — мут 60 минут

*РЕКЛАМА:*

1️⃣ Реклама только в спец теме — мут 30 мин
2️⃣ Не отвлекаться от темы — мут 30 мин
3️⃣ Спам запрещен — мут 30 мин
4️⃣ Вопросы о ценах в отдельный чат — мут 30 мин
"""

def check_rule_violation(text):
    text_lower = text.lower()
    violations = []
    
    adult = ['порно', 'секс', '18+', 'голый', 'эротика']
    if any(w in text_lower for w in adult):
        violations.append(("adult", 120, "мут 120 минут за 18+ контент"))
    
    parent = ['мать', 'отец', 'родители', 'мама', 'папа']
    if any(w in text_lower for w in parent):
        violations.append(("parent", 120, "мут 120 минут за упоминание родителей"))
    
    politics = ['путин', 'зеленский', 'политика', 'война']
    if any(w in text_lower for w in politics):
        violations.append(("politics", 60, "мут 60 минут за политику"))
    
    nazi = ['свастика', 'нацист', 'гитлер']
    if any(w in text_lower for w in nazi):
        violations.append(("nazi", 60, "мут 60 минут за нацистскую символику"))
    
    return violations

async def apply_punishment(update, user_id, duration, reason):
    add_mute(user_id, duration, reason, 0)
    try:
        user = await update.message.chat.get_member(user_id)
        await update.message.reply_text(f"🔇 {user.user.first_name}, {reason}", parse_mode=ParseMode.MARKDOWN)
    except:
        pass
    add_log(0, "auto_mute", user_id, reason)

async def notify_admins(context, text):
    for u in get_all_users():
        if u["mod_role"] and u["mod_role"] in [8, 9, 10]:
            try:
                await context.bot.send_message(u["user_id"], text, parse_mode=ParseMode.MARKDOWN)
            except:
                pass

async def notify_moderators(context, text):
    for u in get_all_users():
        if u["mod_role"] and u["mod_role"] >= 8:
            try:
                await context.bot.send_message(u["user_id"], text, parse_mode=ParseMode.MARKDOWN)
            except:
                pass

# ========== КОМАНДЫ ==========
pending_weddings = {}
report_cooldowns = {}
report_votes = {}
report_id_counter = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    add_log(user.id, "start")
    u = get_user(user.id)
    
    keyboard = [
        [InlineKeyboardButton("📜 Правила", callback_data="rules")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("⭐ Топ месяца", callback_data="top")],
        [InlineKeyboardButton("💍 Свадьбы", callback_data="weddings")]
    ]
    
    await update.message.reply_text(
        f"🔥 *ДОБРО ПОЖАЛОВАТЬ В FAM {FAMILY_NAME}!* 🔥\n\n"
        f"Привет, {user.first_name}! 👋\n"
        f"🎮 Твой игровой ранг: {get_rank_emoji(u['role'])} *{get_rank_name(u['role'])}*\n"
        f"⭐ Репутация: {u['rep']}\n"
        f"👑 Модераторская роль: {u['mod_role'] or 'Нет'}\n\n"
        f"Используй /help для списка команд!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список команд"""
    user_id = update.effective_user.id
    is_creator = user_id in ADMINS
    
    help_text = """
🔥 *FAM NEVERMORE - КОМАНДЫ* 🔥

👤 *ПРОФИЛЬ:*
/profile - Твой профиль
/info - Инфо о семье

💍 *СЕМЬЯ:*
/wedding [reply] - Предложить брак
/divorce - Развестись
/weddings - Список свадеб

⭐ *РЕПУТАЦИЯ:*
/plus [reply] - +1 репутации
/minus [reply] - -1 репутации

🎮 *РАЗВЛЕЧЕНИЯ:*
/kiss [reply] - Поцеловать 💋
/hug [reply] - Обнять 🤗
/slap [reply] - Ударить 👋
/me [действие] - Описать действие
/try [действие] - Попытать удачу 🎯
/gay - Гей дня 🏳️‍🌈
/clown - Клоун дня 🤡
/wish - Предсказание ✨

📊 *СТАТИСТИКА:*
/top - Топ месяца
/online - Кто онлайн
/check [@username] - Проверить игрока

🔨 *МОДЕРАЦИЯ (роль 8+):*
/warn [reply] [причина] - Предупреждение
/unwarn [@username] - Снять варн
/mute [reply] [время] - Замутить
/unmute [reply] - Размутить
/ban [reply] [причина] - Забанить
/unban [@username] - Разбанить
/warns [@username] - Варны пользователя
/bans - Список забаненных
/mutelist - Список замученных
/logs - Логи действий
/clear [кол-во] - Очистить чат
/report [текст] - Пожаловаться
/setname [@username] [ник] - Установить ник
/setprefix [@username] [префикс] - Установить префикс

👑 *АДМИНИСТРИРОВАНИЕ (роль 9-10):*
/setuser [@username] [ник] [ранг] - Роль и ранг одной командой
/setrole [@username] [2-10] - Выдать роль
/role [@username] [0-10] - Сменить роль
/giveaccess [@username] [8-10] - Выдать доступ
/nlist - Список участников
/delnick - Удалить ник
/setnick - Установить ник (алиас)
/editnick - Изменить ник
/setrank - Изменить ранг
/grole [@username] [0-10] - Игровая роль
/roles - Все роли
/all - Призвать всех

📜 *ПРАВИЛА:*
/rules - Показать правила
"""
    
    # Добавляем секцию для создателя (только если пользователь в ADMINS)
    if is_creator:
        creator_section = """

👑 *ДЛЯ СОЗДАТЕЛЯ* 👑

📊 *УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ:*
/checkdb - Все пользователи
/checkmutes - Активные муты
/checkbans - Активные баны
/checkweddings - Активные свадьбы
/sql [запрос] - Выполнить SQL запрос
/backup - Создать бэкап БД

⭐ *УПРАВЛЕНИЕ РЕПУТАЦИЕЙ:*
/takerep [@username] [кол-во] - Забрать репутацию
/resetrep [@username] - Сбросить репутацию

👤 *УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ:*
/editnick [@username] [новый_ник] - Изменить ник
/delnick [@username] - Удалить ник
/setrank [@username] [ранг] - Изменить ранг
/resetuser [@username] - Полный сброс пользователя

🔧 *СИСТЕМНЫЕ:*
/creator - Панель создателя
/stats - Статистика бота
/clearlogs - Очистить логи
"""
        help_text += creator_section
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES, parse_mode=ParseMode.MARKDOWN)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    if not u:
        add_user(user)
        u = get_user(user.id)
    
    spouse_name = "Нет"
    for w in get_active_weddings():
        if w["user1"] == user.id or w["user2"] == user.id:
            spouse_id = w["user1"] if w["user2"] == user.id else w["user2"]
            spouse = get_user(spouse_id)
            if spouse:
                spouse_name = spouse["nickname"] or spouse["name"]
    
    mod_role_text = ""
    if u["mod_role"]:
        mod_names = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}
        mod_role_text = f"\n👑 Мод. роль: {mod_names.get(u['mod_role'], u['mod_role'])}"
    
    text = (
        f"<b>{get_rank_emoji(u['role'])} ПРОФИЛЬ {get_rank_emoji(u['role'])}</b>\n\n"
        f"👤 Имя: <b>{u['name']}</b>\n"
        f"📝 Username: @{u['username'] or 'Нет'}\n"
        f"💫 Никнейм: {u['nickname'] or 'Не установлен'}\n"
        f"🏷️ Префикс: {u['prefix'] or 'Нет'}\n"
        f"🎮 Игровой ранг: <b>{get_rank_name(u['role'])}</b>{mod_role_text}\n\n"
        f"⭐ Репутация: <b>{u['rep']}</b>\n"
        f"⚠️ Варны: {u['warns']}/3\n"
        f"💬 Сообщений: {u['msgs']}\n"
        f"💍 Супруг(а): {spouse_name}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    
    leader = None
    deputy = None
    moderators = []
    
    for u in users_list:
        if u["mod_role"] == 10:
            leader = u
        elif u["mod_role"] == 9:
            deputy = u
        elif u["mod_role"] == 8:
            moderators.append(u)
    
    leader_text = f"@{leader['username'] or leader['name']}" if leader else "Не указан"
    deputy_text = f"@{deputy['username'] or deputy['name']}" if deputy else "Не указан"
    moderators_text = ", ".join([f"@{m['username'] or m['name']}" for m in moderators]) if moderators else "Не указаны"
    
    try:
        chat = await context.bot.get_chat(update.effective_chat.id)
        members_count = await chat.get_member_count()
    except:
        members_count = len(users_list)
    
    info_text = f"""
ℹ️ *ИНФОРМАЦИЯ О СЕМЬЕ {FAMILY_NAME}* ℹ️

«Все будет, но не сразу.»

🛡 *РУКОВОДСТВО:*
👑 Лидер: {leader_text}
⚔️ Зам. лидера: {deputy_text}
🛡 Модератор: {moderators_text}

📊 *СТАТИСТИКА:*
👥 Участников: {members_count}
💞 Альянс: Weiss, Libre
📅 Семья Основана: 04.06.2025

📌 *ПОЛЕЗНЫЕ ССЫЛКИ:*
📜 Правила: {RULES_LINK}
🔑 Авторизация: {AUTH_LINK}
📢 Новости: {NEWS_LINK}
"""
    await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить ник пользователю по @username или ID или реплаю"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    target_user = None
    nickname = None
    
    # Если есть аргументы
    if context.args:
        target_input = context.args[0]
        
        # Если есть второй аргумент - это ник
        if len(context.args) >= 2:
            nickname = ' '.join(context.args[1:])[:50]
        
        # Пытаемся получить пользователя
        target_id = get_user_id_from_input(target_input)
        if target_id:
            target_user = get_user(target_id)
            if not target_user:
                # Добавляем в базу если нет
                try:
                    chat_member = await context.bot.get_chat_member(update.effective_chat.id, target_id)
                    add_user(chat_member.user)
                    target_user = get_user(target_id)
                except:
                    pass
        
        # Если не нашли пользователя, значит первый аргумент может быть ником
        if not target_user and nickname is None:
            nickname = target_input
            target_user = get_user(update.effective_user.id)
    
    # Если есть реплай
    elif update.message.reply_to_message:
        target_user = get_user(update.message.reply_to_message.from_user.id)
        if not target_user:
            add_user(update.message.reply_to_message.from_user)
            target_user = get_user(update.message.reply_to_message.from_user.id)
        if context.args:
            nickname = ' '.join(context.args)[:50]
    
    # Если нет цели
    if not target_user:
        await update.message.reply_text(
            "❌ *Неверный формат!*\n\n"
            "Используйте:\n"
            "• `/setname @username Ник`\n"
            "• `/setname [user_id] Ник`\n"
            "• `/setname Ник` (в ответ на сообщение)\n\n"
            "Пример: `/setname @vipkotax Крутой_Чел`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if not nickname:
        await update.message.reply_text("❌ Укажите никнейм!\n\nПример: `/setname @username Крутой_Чел`", parse_mode=ParseMode.MARKDOWN)
        return
    
    # Устанавливаем ник
    update_user(target_user["user_id"], "nickname", nickname)
    
    await update.message.reply_text(
        f"✅ *Никнейм установлен!*\n\n"
        f"👤 Пользователь: {target_user['name']}\n"
        f"💫 Новый ник: `{nickname}`",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(update.effective_user.id, "set_name", target_user["user_id"], nickname)

async def setnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Алиас для /setname"""
    await setname(update, context)
async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setprefix [@username] [префикс]\n\nПример: /setprefix @username [VIP]")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    prefix = ' '.join(context.args[1:])[:20]
    update_user(uid, "prefix", prefix)
    u = get_user(uid)
    await update.message.reply_text(f"✅ *{u['name']}* получил префикс: {prefix}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "set_prefix", uid, prefix)

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not context.args:
        await update.message.reply_text("❌ /unwarn [@username]\n\nПример: /unwarn @username")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    u = get_user(uid)
    if not u:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    new_warns = max(0, (u["warns"] or 0) - 1)
    update_user(uid, "warns", new_warns)
    await update.message.reply_text(f"✅ *{u['name']}* снято предупреждение! Теперь: {new_warns}/3", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "unwarn", uid)

async def giverep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    giver = get_user(update.effective_user.id)
    if (giver["rep"] or 0) < 150 and update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ Недостаточно репутации! Нужно 150⭐ для выдачи репутации.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /giverep [@username] [кол-во]\n\nПример: /giverep @username 10")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    try:
        amount = int(context.args[1])
        if amount <= 0:
            await update.message.reply_text("❌ Количество должно быть положительным!")
            return
    except:
        await update.message.reply_text("❌ Неверный формат количества!")
        return
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    new_rep = (target["rep"] or 0) + amount
    update_user(uid, "rep", new_rep)
    await update.message.reply_text(f"⭐ *{target['name']}* получил +{amount} репутации!\nТеперь: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "giverep", uid, f"+{amount}")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not context.args:
        await update.message.reply_text("❌ /clear [кол-во]\n\nПример: /clear 10")
        return
    
    try:
        amount = min(int(context.args[0]), 100)
        await update.message.delete()
        
        deleted = 0
        async for msg in update.message.chat.get_messages():
            if deleted >= amount:
                break
            try:
                await msg.delete()
                deleted += 1
                await asyncio.sleep(0.1)
            except:
                pass
        
        msg = await update.message.reply_text(f"✅ Очищено {deleted} сообщений")
        await asyncio.sleep(3)
        await msg.delete()
        add_log(update.effective_user.id, "clear", reason=f"{deleted} сообщений")
    except:
        await update.message.reply_text("❌ Ошибка при очистке")

# ========== СВАДЬБЫ ==========
async def wedding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💍 Ответь на сообщение того, кому хочешь предложить брак!")
        return
    
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя жениться на себе!")
        return
    
    for w in get_active_weddings():
        if w["user1"] == user.id or w["user2"] == user.id:
            await update.message.reply_text("❌ Вы уже в браке!")
            return
        if w["user1"] == target.id or w["user2"] == target.id:
            await update.message.reply_text("❌ Этот пользователь уже в браке!")
            return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, согласен", callback_data=f"wed_accept_{user.id}_{target.id}"),
         InlineKeyboardButton("❌ Нет, не согласен", callback_data=f"wed_decline_{user.id}_{target.id}")]
    ])
    
    await update.message.reply_text(
        f"💍 *{user.first_name}* предлагает брак *{target.first_name}*!\n\nУ вас есть 120 секунд, чтобы ответить!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    
    pending_weddings[f"{user.id}_{target.id}"] = {"u1": user.id, "u2": target.id, "t": datetime.now(), "s1": False, "s2": False}

async def divorce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = divorce_wedding(update.effective_user.id)
    if res:
        await update.message.reply_text(f"💔 *{update.effective_user.first_name}* развелся(ась)!", parse_mode=ParseMode.MARKDOWN)
        add_log(update.effective_user.id, "divorce", res)
    else:
        await update.message.reply_text("❌ Вы не состоите в браке!")

async def weddings_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = get_active_weddings()
    if not active:
        await update.message.reply_text("💔 Пока нет ни одной свадьбы")
        return
    
    text = "💍 *АКТИВНЫЕ БРАКИ* 💍\n\n"
    for w in active:
        u1 = get_user(w["user1"])
        u2 = get_user(w["user2"])
        name1 = u1["nickname"] or u1["name"] if u1 else str(w["user1"])
        name2 = u2["nickname"] or u2["name"] if u2 else str(w["user2"])
        date = w["date"][:10] if w["date"] else "Неизвестно"
        text += f"❤️ {name1} + {name2}\n📅 {date}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== РЕПУТАЦИЯ ==========
async def plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⭐ Ответь на сообщение того, кому хочешь добавить репутацию!")
        return
    
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя дать репутацию себе!")
        return
    
    t = get_user(target.id)
    if not t:
        add_user(target)
        t = get_user(target.id)
    
    new_rep = (t["rep"] or 0) + 1
    update_user(target.id, "rep", new_rep)
    
    await update.message.reply_text(
        f"⭐ *{user.first_name}* дал(а) +1 репутации *{target.first_name}*!\nТеперь: {new_rep}⭐",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user.id, "rep_plus", target.id)

async def minus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💀 Ответь на сообщение того, кому хочешь убавить репутацию!")
        return
    
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя убавить репутацию себе!")
        return
    
    t = get_user(target.id)
    if not t:
        add_user(target)
        t = get_user(target.id)
    
    new_rep = (t["rep"] or 0) - 1
    update_user(target.id, "rep", new_rep)
    
    await update.message.reply_text(
        f"💀 *{user.first_name}* убавил(а) -1 репутации *{target.first_name}*!\nТеперь: {new_rep}⭐",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user.id, "rep_minus", target.id)

# ========== МОДЕРАЦИЯ ==========
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    mod = update.effective_user
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    
    t = get_user(target.id)
    if not t:
        add_user(target)
        t = get_user(target.id)
    
    new_warns = (t["warns"] or 0) + 1
    update_user(target.id, "warns", new_warns)
    
    await update.message.reply_text(
        f"⚠️ *{target.first_name}* получил предупреждение!\n"
        f"📝 Причина: {reason}\n"
        f"⚠️ Предупреждений: {new_warns}/3",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await notify_moderators(context, 
        f"⚠️ *ВЫДАНО ПРЕДУПРЕЖДЕНИЕ*\n\n"
        f"👤 Модератор: {mod.first_name}\n"
        f"🔨 Нарушитель: {target.first_name}\n"
        f"📝 Причина: {reason}\n"
        f"⚠️ Всего варнов: {new_warns}/3"
    )
    add_log(mod.id, "warn", target.id, reason)
    
    if new_warns >= 3:
        add_mute(target.id, 1440, "Автоматический мут за 3 предупреждения", mod.id)
        await update.message.reply_text(f"🔇 {target.first_name} автоматически замучен на 1 день!")
        await notify_moderators(context,
            f"🔇 *АВТОМАТИЧЕСКИЙ МУТ*\n\n"
            f"👤 Пользователь: {target.first_name}\n"
            f"⏱️ Длительность: 1 день\n"
            f"📝 Причина: 3 предупреждения"
        )

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    mod = update.effective_user
    target = update.message.reply_to_message.from_user
    dur = context.args[0] if context.args else "60"
    reason = ' '.join(context.args[1:]) or "Нарушение правил"
    
    try:
        minutes = int(dur)
    except:
        minutes = 60
    
    add_mute(target.id, minutes, reason, mod.id)
    
    await update.message.reply_text(
        f"🔇 *{target.first_name}* замучен!\n"
        f"⏱️ Длительность: {minutes} минут\n"
        f"📝 Причина: {reason}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await notify_moderators(context,
        f"🔇 *ВЫДАН МУТ*\n\n"
        f"👤 Модератор: {mod.first_name}\n"
        f"🔨 Нарушитель: {target.first_name}\n"
        f"⏱️ Длительность: {minutes} минут\n"
        f"📝 Причина: {reason}"
    )
    add_log(mod.id, "mute", target.id, f"{minutes}мин - {reason}")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    target = update.message.reply_to_message.from_user
    remove_mute(target.id)
    await update.message.reply_text(f"🔊 *{target.first_name}* размучен!", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "unmute", target.id)

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    mod = update.effective_user
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    
    add_ban(target.id, 365, reason, mod.id)
    
    await update.message.reply_text(
        f"🔨 *{target.first_name}* забанен!\n"
        f"📝 Причина: {reason}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await notify_moderators(context,
        f"🔨 *ВЫДАН БАН*\n\n"
        f"👤 Модератор: {mod.first_name}\n"
        f"🔨 Нарушитель: {target.first_name}\n"
        f"📝 Причина: {reason}\n"
        f"⏱️ Длительность: Навсегда"
    )
    add_log(mod.id, "ban", target.id, reason)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not context.args:
        await update.message.reply_text("❌ /unban [@username]\n\nПример: /unban @username")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    remove_ban(uid)
    await update.message.reply_text(f"🔓 Пользователь {context.args[0]} разбанен!")
    add_log(update.effective_user.id, "unban", uid)

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if context.args:
        uid = get_user_id_from_input(context.args[0])
        if uid:
            u = get_user(uid)
            if u:
                await update.message.reply_text(f"⚠️ *{u['name']}* имеет {u['warns']}/3 предупреждений", parse_mode=ParseMode.MARKDOWN)
                return
    await update.message.reply_text("❌ Пользователь не найден")

async def bans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    lst = get_bans_list()
    if not lst:
        await update.message.reply_text("🔨 Нет активных банов")
        return
    
    text = "🔨 *Активные баны:*\n\n"
    for b in lst:
        u = get_user(b["user_id"])
        name = u["nickname"] or u["name"] if u else str(b["user_id"])
        text += f"• {name} — до {b['until'][:10]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    lst = get_mutes_list()
    if not lst:
        await update.message.reply_text("🔇 Нет активных мутов")
        return
    
    text = "🔇 *Активные муты:*\n\n"
    for m in lst:
        u = get_user(m["user_id"])
        name = u["nickname"] or u["name"] if u else str(m["user_id"])
        text += f"• {name} — до {m['until'][:16]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    lst = get_logs(15)
    if not lst:
        await update.message.reply_text("Нет логов")
        return
    
    text = "📋 *Последние действия:*\n\n"
    for log in lst:
        u = get_user(log["user_id"])
        name = u["nickname"] or u["name"] if u else str(log["user_id"])
        text += f"• {log['time'][:16]} — {name}: {log['action']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== АДМИНИСТРИРОВАНИЕ ==========
async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrole [@username] [2-10]\n\nПример: /setrole @username 5")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    try:
        role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат роли!")
        return
    
    if role < 2 or role > 10:
        await update.message.reply_text("❌ Роль должна быть от 2 до 10")
        return
    
    update_user(uid, "role", role)
    u = get_user(uid)
    await update.message.reply_text(f"✅ *{u['name']}* получил игровой ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "set_role", uid, f"ранг {role}")

async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    if user_id not in ADMINS and (not u or u["mod_role"] != 10):
        await update.message.reply_text("⛔ Нет прав! Только лидер может выдавать модераторские роли!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /role [@username] [0-10]\n\n0 - снять роль\n8 - Модератор\n9 - Зам. лидера\n10 - Лидер\n\nПример: /role @username 8")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    try:
        mod_role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат роли!")
        return
    
    if mod_role not in [0, 8, 9, 10]:
        await update.message.reply_text("❌ Роль может быть: 0, 8, 9, 10")
        return
    
    names = {8: "🛡️ Модератор", 9: "👑 Зам. лидера", 10: "💎 Лидер"}
    marks = {8: " [🛡️Мод]", 9: " [👑Зам]", 10: " [💎Лид]"}
    
    if mod_role == 0:
        update_user(uid, "mod_role", None)
        await update.message.reply_text(f"✅ У *{get_user(uid)['name']}* снята модераторская роль", parse_mode=ParseMode.MARKDOWN)
        add_log(user_id, "role_removed", uid)
    else:
        update_user(uid, "mod_role", mod_role)
        await update.message.reply_text(
            f"✅ *{get_user(uid)['name']}* получил роль: {names[mod_role]} {marks[mod_role]}",
            parse_mode=ParseMode.MARKDOWN
        )
        add_log(user_id, "role_granted", uid, f"роль {mod_role}")
        
        try:
            await context.bot.send_message(uid, f"🎉 *Поздравляем!*\n\nТы получил роль: {names[mod_role]}\n\nТеперь ты можешь использовать команды модерации!", parse_mode=ParseMode.MARKDOWN)
        except:
            pass

async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    if user_id not in ADMINS and (not u or u["mod_role"] != 10):
        await update.message.reply_text("⛔ Нет прав! Только лидер может выдавать доступ!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /giveaccess [@username] [8-10]\n\n8 - Модератор\n9 - Администратор\n10 - Руководитель\n\nПример: /giveaccess @username 8")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    try:
        level = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат уровня!")
        return
    
    if level not in [8, 9, 10]:
        await update.message.reply_text("❌ Уровень доступа: 8-модер, 9-администратор, 10-руководитель")
        return
    
    names = {8: "🛡️ Модератор", 9: "👑 Администратор", 10: "💎 Руководитель"}
    marks = {8: " [🛡️Мод]", 9: " [👑Админ]", 10: " [💎Рук]"}
    
    update_user(uid, "mod_role", level)
    await update.message.reply_text(
        f"✅ *{get_user(uid)['name']}* получил доступ: {names[level]} {marks[level]}",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user_id, "give_access", uid, f"уровень {level}")
    
    try:
        await context.bot.send_message(uid, f"🎉 *Поздравляем!*\n\nТы получил роль: {names[level]}\n\nТеперь ты можешь использовать команды модерации!", parse_mode=ParseMode.MARKDOWN)
    except:
        pass

async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список участников с их никами и username"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    users_list = get_all_users()
    if not users_list:
        await update.message.reply_text("📋 Список пуст")
        return
    
    # Сортируем по рангу (от высшего к низшему)
    users_list = sorted(users_list, key=lambda x: x["role"] or 0, reverse=True)
    
    text = "📋 *СПИСОК УЧАСТНИКОВ*\n\n"
    
    for u in users_list:
        # Никнейм (с подчеркиваниями)
        if u["nickname"]:
            name = u["nickname"]
        else:
            name = u["name"]
        
        # Username в скобках
        username = f" (@{u['username']})" if u["username"] else ""
        
        # Ранг
        rank_text = f"{u['role']} ранг"
        
        # Модераторская роль
        mod_role = ""
        if u["mod_role"] == 8:
            mod_role = " [Модератор]"
        elif u["mod_role"] == 9:
            mod_role = " [Администратор]"
        elif u["mod_role"] == 10:
            mod_role = " [Руководитель]"
        
        text += f"• {name}{username} — {rank_text}{mod_role}\n"
        
        if len(text) > 4000:
            text += "\n... и другие"
            break
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def grole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /grole [@username] [0-10]\n\n0 - сбросить до 2 ранга\n\nПример: /grole @username 5")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    try:
        role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат роли!")
        return
    
    if role < 0 or role > 10:
        await update.message.reply_text("❌ Роль должна быть от 0 до 10")
        return
    
    if role == 0:
        update_user(uid, "role", 2)
        await update.message.reply_text(f"✅ У *{get_user(uid)['name']}* игровая роль сброшена до Новичка")
    else:
        update_user(uid, "role", role)
        await update.message.reply_text(f"✅ *{get_user(uid)['name']}* получил игровой ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)
    
    add_log(update.effective_user.id, "grole", uid, f"ранг {role}")

async def roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    users_list = get_all_users()
    if not users_list:
        await update.message.reply_text("Нет участников")
        return
    
    text = "👑 *РОЛИ УЧАСТНИКОВ*\n\n"
    for u in users_list[:50]:
        mod = ""
        if u["mod_role"] == 8:
            mod = " | 🛡️ Модер"
        elif u["mod_role"] == 9:
            mod = " | 👑 Зам"
        elif u["mod_role"] == 10:
            mod = " | 💎 Лидер"
        
        text += f"• {u['nickname'] or u['name']} — ранг {u['role']} ({get_rank_name(u['role'])}){mod}\n"
        if len(text) > 4000:
            text += "\n... и другие"
            break
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    mentions = []
    for u in get_all_users():
        if u["username"]:
            mentions.append(f"@{u['username']}")
        else:
            mentions.append(u['name'])
    
    if not mentions:
        await update.message.reply_text("Нет участников")
        return
    
    text = "🔔 *ВНИМАНИЕ! ОБЩЕЕ СОБРАНИЕ!* 🔔\n\n" + ' '.join(mentions[:50])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "all_push")

# ========== СТАТИСТИКА ==========
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = sorted(get_all_users(), key=lambda x: x["monthly_msgs"] or 0, reverse=True)[:5]
    
    if not users_list:
        await update.message.reply_text("📊 Нет данных за этот месяц")
        return
    
    rewards = {1: 70, 2: 50, 3: 40, 4: 30, 5: 20}
    
    text = "📊 *ТОП АКТИВНЫХ ЗА МЕСЯЦ* 📊\n\n"
    for i, u in enumerate(users_list, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = u['nickname'] or u['name']
        reward = rewards.get(i, 0)
        text += f"{medal} {name} — {u['monthly_msgs']} сообщений\n"
        if reward > 0:
            text += f"   🎁 Награда: +{reward}⭐\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    online_u = []
    offline_u = []
    
    for u in get_all_users():
        if u["last_online"]:
            try:
                last = datetime.fromisoformat(u["last_online"])
                if (now - last).seconds < 300:
                    online_u.append(u)
                else:
                    offline_u.append(u)
            except:
                offline_u.append(u)
        else:
            offline_u.append(u)
    
    text = f"🟢 *ОНЛАЙН ({len(online_u)}):*\n\n"
    for u in online_u[:20]:
        username = f"@{u['username']}" if u['username'] else u['name']
        text += f"• {username} ({get_rank_emoji(u['role'])} ранг {u['role']})\n"
    
    text += f"\n⚫ *ОФФЛАЙН ({len(offline_u)}):*\n\n"
    for u in offline_u[:20]:
        username = f"@{u['username']}" if u['username'] else u['name']
        last = u["last_online"][:16] if u["last_online"] else "Никогда"
        text += f"• {username} — был {last}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check [@username]\n\nПример: /check @username")
        return
    
    username = context.args[0].lower()
    if username.startswith('@'):
        username = username[1:]
    
    found = None
    for u in get_all_users():
        if u["username"] and u["username"].lower() == username:
            found = u
            break
        elif u["nickname"] and u["nickname"].lower() == username:
            found = u
            break
        elif u["name"].lower() == username:
            found = u
            break
    
    if found:
        mod = ""
        if found["mod_role"] == 8:
            mod = " | 🛡️ Модер"
        elif found["mod_role"] == 9:
            mod = " | 👑 Зам"
        elif found["mod_role"] == 10:
            mod = " | 💎 Лидер"
        
        await update.message.reply_text(
            f"🔍 *РЕЗУЛЬТАТ ПОИСКА*\n\n"
            f"👤 Имя: {found['name']}\n"
            f"📝 Username: @{found['username'] or 'Нет'}\n"
            f"💫 Никнейм: {found['nickname'] or 'Не установлен'}\n"
            f"🎮 Игровой ранг: {found['role']} ({get_rank_name(found['role'])}){mod}\n"
            f"⚠️ Варны: {found['warns']}/3\n"
            f"⭐ Репутация: {found['rep']}\n"
            f"💬 Сообщений: {found['msgs']}\n"
            f"📊 Активность в этом месяце: {found['monthly_msgs']} сообщений",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(f"❌ Пользователь {username} не найден")

# ========== РАЗВЛЕЧЕНИЯ ==========
async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💋 Ответь на сообщение!")
        return
    
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("😳 Нельзя поцеловать себя!")
        return
    
    kisses = [
        f"💋 {user.first_name} нежно поцеловал(а) {target.first_name} в щёчку!",
        f"😘 {user.first_name} подарил(а) страстный поцелуй {target.first_name}!",
        f"💕 {user.first_name} и {target.first_name} обменялись нежными поцелуями!"
    ]
    await update.message.reply_text(random.choice(kisses))
    add_log(user.id, "kiss", target.id)

async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("🤗 Ответь на сообщение!")
        return
    
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("🤗 Обними кого-то другого!")
        return
    
    hugs = [
        f"🤗 {user.first_name} крепко обнял(а) {target.first_name}!",
        f"💞 {user.first_name} и {target.first_name} обнялись!",
        f"🫂 {user.first_name} подарил(а) тёплые объятия {target.first_name}!"
    ]
    await update.message.reply_text(random.choice(hugs))
    add_log(user.id, "hug", target.id)

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("👋 Ответь на сообщение!")
        return
    
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("😅 Нельзя ударить себя!")
        return
    
    slaps = [
        f"🤚 {user.first_name} дал(а) подзатыльник {target.first_name}!",
        f"💥 {user.first_name} шлёпнул(а) {target.first_name}!",
        f"👋 {user.first_name} отвесил(а) оплеуху {target.first_name}!"
    ]
    await update.message.reply_text(random.choice(slaps))
    add_log(user.id, "slap", target.id)

async def me_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /me [действие]\n\nПример: /me танцует")
        return
    
    action = ' '.join(context.args)
    await update.message.reply_text(f"* {update.effective_user.first_name} {action}")
    add_log(update.effective_user.id, f"me: {action}")

async def try_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /try [действие]\n\nПример: /try прыгнуть")
        return
    
    action = ' '.join(context.args)
    outcomes = [
        "✅ Удачно! 🎉",
        "❌ Неудача... 😔",
        "💀 Полный провал! 💀",
        "✨ Неожиданно получилось! ✨",
        "🎯 Успех! 💪"
    ]
    await update.message.reply_text(f"🎲 *{update.effective_user.first_name}* пытается {action}\n\n{random.choice(outcomes)}", parse_mode=ParseMode.MARKDOWN)

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    if users_list:
        target = random.choice(users_list)
        await update.message.reply_text(f"🏳️‍🌈 *Гей дня:* {target['name']}! 🏳️‍🌈", parse_mode=ParseMode.MARKDOWN)

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    if users_list:
        target = random.choice(users_list)
        await update.message.reply_text(f"🤡 *Клоун дня:* {target['name']}! 🤡", parse_mode=ParseMode.MARKDOWN)

async def wish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wishes = [
        "💰 Богатства и процветания!",
        "❤️ Настоящей любви!",
        "🔥 Успеха во всём!",
        "🌟 Исполнения мечт!",
        "🍀 Удачи!",
        "💪 Силы и энергии!",
        "🎉 Веселья и радости!"
    ]
    await update.message.reply_text(f"✨ *Твоё предсказание:*\n{random.choice(wishes)} ✨", parse_mode=ParseMode.MARKDOWN)

# ========== ЖАЛОБЫ ==========
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /report [текст жалобы]\n\nПример: /report Оскорбление участника")
        return
    
    user = update.effective_user
    reason = ' '.join(context.args)
    
    global report_id_counter
    report_id_counter += 1
    rid = report_id_counter
    
    report_votes[rid] = {
        "id": rid,
        "user": user.id,
        "name": user.first_name,
        "reason": reason,
        "time": datetime.now(),
        "votes": {"a": 0, "d": 0, "o": 0},
        "voters": []
    }
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Одобренно", callback_data=f"rep_a_{rid}"),
         InlineKeyboardButton("❌ Отказанно", callback_data=f"rep_d_{rid}"),
         InlineKeyboardButton("📝 Оффтоп", callback_data=f"rep_o_{rid}")]
    ])
    
    sent = 0
    for u in get_all_users():
        if u["mod_role"] in [8, 9, 10]:
            try:
                await context.bot.send_message(
                    u["user_id"],
                    f"📢 *НОВАЯ ЖАЛОБА #{rid}!*\n\n"
                    f"👤 От: {user.first_name}\n"
                    f"📝 Текст: {reason}\n"
                    f"🕐 Время: {datetime.now().strftime('%H:%M %d.%m')}\n\n"
                    f"*Голосуйте:*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
                sent += 1
            except:
                pass
    
    if sent > 0:
        await update.message.reply_text(f"✅ Жалоба #{rid} отправлена {sent} модераторам!")
        add_log(user.id, "report", reason=reason)
    else:
        await update.message.reply_text("❌ Нет доступных модераторов!")

async def handle_report_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    
    u = get_user(uid)
    if not u or u["mod_role"] not in [8, 9, 10]:
        await q.answer("⛔ Только модераторы могут голосовать!", show_alert=True)
        return
    
    parts = data.split("_")
    if len(parts) < 3:
        await q.answer("Ошибка")
        return
    
    action, rid = parts[1], int(parts[2])
    
    if rid not in report_votes:
        await q.answer("❌ Жалоба уже обработана!", show_alert=True)
        await q.message.delete()
        return
    
    r = report_votes[rid]
    if uid in r["voters"]:
        await q.answer("❌ Вы уже голосовали по этой жалобе!", show_alert=True)
        return
    
    r["voters"].append(uid)
    
    if action == "a":
        r["votes"]["a"] += 1
        await q.answer("✅ Вы одобрили жалобу")
    elif action == "d":
        r["votes"]["d"] += 1
        await q.answer("❌ Вы отклонили жалобу")
    else:
        r["votes"]["o"] += 1
        await q.answer("📝 Вы отметили жалобу как оффтоп")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ {r['votes']['a']}", callback_data=f"rep_a_{rid}"),
         InlineKeyboardButton(f"❌ {r['votes']['d']}", callback_data=f"rep_d_{rid}"),
         InlineKeyboardButton(f"📝 {r['votes']['o']}", callback_data=f"rep_o_{rid}")]
    ])
    
    try:
        await q.message.edit_reply_markup(reply_markup=keyboard)
    except:
        pass
    
    if r["votes"]["o"] >= 3:
        report_cooldowns[r["user"]] = datetime.now() + timedelta(hours=6)
        await q.message.edit_text(
            f"📢 *ИТОГ ЖАЛОБЫ #{rid}*\n\n"
            f"👤 От: {r['name']}\n"
            f"📝 Текст: {r['reason']}\n\n"
            f"⚖️ *РЕШЕНИЕ:* Жалоба признана оффтопом (3+ голосов)\n"
            f"⏱️ *НАКАЗАНИЕ:* {r['name']} не может отправлять жалобы 6 часов!",
            parse_mode=ParseMode.MARKDOWN
        )
        try:
            await context.bot.send_message(
                r["user"],
                f"⚠️ *Ваша жалоба #{rid} признана оффтопом!*\n\n"
                f"📝 Текст: {r['reason']}\n"
                f"⏱️ Вы не можете отправлять жалобы 6 часов!",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        del report_votes[rid]
    
    elif r["votes"]["d"] >= 3:
        report_cooldowns[r["user"]] = datetime.now() + timedelta(hours=6)
        await q.message.edit_text(
            f"📢 *ИТОГ ЖАЛОБЫ #{rid}*\n\n"
            f"👤 От: {r['name']}\n"
            f"📝 Текст: {r['reason']}\n\n"
            f"⚖️ *РЕШЕНИЕ:* Жалоба отклонена (3+ голосов)\n"
            f"⏱️ *НАКАЗАНИЕ:* {r['name']} не может отправлять жалобы 6 часов!",
            parse_mode=ParseMode.MARKDOWN
        )
        try:
            await context.bot.send_message(
                r["user"],
                f"⚠️ *Ваша жалоба #{rid} отклонена!*\n\n"
                f"📝 Текст: {r['reason']}\n"
                f"⏱️ Вы не можете отправлять жалобы 6 часов!",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        del report_votes[rid]

# ========== КНОПКИ ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    
    if data == "rules":
        await rules(update, context)
    elif data == "profile":
        await profile(update, context)
    elif data == "top":
        await top(update, context)
    elif data == "weddings":
        await weddings_list(update, context)
    elif data.startswith("rep_"):
        await handle_report_vote(update, context)
    elif data.startswith("wed_accept"):
        parts = data.split("_")
        u1, u2 = int(parts[2]), int(parts[3])
        if q.from_user.id not in [u1, u2]:
            await q.answer("❌ Это не ваше предложение!", show_alert=True)
            return
        key = f"{u1}_{u2}"
        if key in pending_weddings:
            if q.from_user.id == u1:
                pending_weddings[key]["s1"] = True
            else:
                pending_weddings[key]["s2"] = True
            if pending_weddings[key]["s1"] and pending_weddings[key]["s2"]:
                add_wedding(u1, u2)
                await q.message.edit_text("💍 *ПОЗДРАВЛЯЕМ!* Брак заключен! 🎉", parse_mode=ParseMode.MARKDOWN)
                del pending_weddings[key]
            else:
                await q.answer("✅ Ожидание ответа второй стороны...")
        else:
            await q.answer("❌ Предложение устарело!", show_alert=True)
    elif data.startswith("wed_decline"):
        parts = data.split("_")
        u1, u2 = int(parts[2]), int(parts[3])
        key = f"{u1}_{u2}"
        if key in pending_weddings:
            del pending_weddings[key]
            await q.message.edit_text("💔 Брак отклонен!", parse_mode=ParseMode.MARKDOWN)

# ========== ПРИВЕТСТВИЕ ==========
async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for m in update.message.new_chat_members:
        if m.is_bot:
            continue
        add_user(m)
        text = f"""
👋 *@{m.username or m.first_name}*, добро пожаловать в *FAM {FAMILY_NAME}*!

📝 Напиши, пожалуйста, свой ник в авторизацию в течение 24 часов, иначе кик.
📖 Просим ознакомиться с правилами чата: {RULES_LINK}
🔑 Ссылка на авторизацию: {AUTH_LINK}

*Приятного общения!* ❤️
"""
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
async def all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех сообщений"""
    if not update.message or not update.message.text:
        return
    
    # Пропускаем команды (они обрабатываются отдельно)
    if update.message.text.startswith('/'):
        return
    
    user = update.effective_user
    text = update.message.text
    
    # Пропускаем сообщения с формой авторизации
    if 'Никнейм:' in text or 'Ник:' in text or 'Нижнейм:' in text:
        return
    
    # Проверяем бан и мут
    if is_banned(user.id):
        try:
            await update.message.delete()
        except:
            pass
        return
    
    if is_muted(user.id):
        try:
            await update.message.delete()
        except:
            pass
        return
    
    # Обновляем статистику
    add_user(user)
    
    # Проверка на нарушения
    if text:
        violations = check_rule_violation(text)
        for v in violations:
            await apply_punishment(update, user.id, v[1], v[2])
            try:
                await update.message.delete()
            except:
                pass
            return
    
    add_user(user)
    
    if text:
        violations = check_rule_violation(text)
        for v in violations:
            await apply_punishment(update, user.id, v[1], v[2])
            try:
                await update.message.delete()
            except:
                pass
            return

# ========== АВТОМАТИЧЕСКАЯ АВТОРИЗАЦИЯ ==========
# ========== АВТОМАТИЧЕСКАЯ АВТОРИЗАЦИЯ ==========
async def auto_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автоматическая обработка сообщений с формой авторизации"""
    
    # ОТЛАДКА - УБЕРИ ПОТОМ
    print("🔍 auto_auth вызвана!")
    if update.message:
        print(f"📝 Текст сообщения: {update.message.text[:200]}")
        print(f"👤 От пользователя: {update.message.from_user.id}")
    
    message = update.message
    if not message or not message.text:
        print("❌ Нет сообщения или текста")
        return
    
    user = message.from_user
    text = message.text.strip()
    
    # Проверяем, что сообщение содержит ключевые слова
    keywords = ['Никнейм:', 'Ник:', 'Нижнейм:', 'Никнём:']
    if not any(kw in text for kw in keywords):
        print("❌ Нет ключевых слов в сообщении")
        return
    
    print("✅ Ключевые слова найдены, начинаю парсинг...")
    
    # Парсим сообщение
    lines = text.split('\n')
    nickname = None
    rank = None
    
    for line in lines:
        line = line.strip()
        # Ищем никнейм
        if line.startswith('Никнейм:') or line.startswith('Ник:') or line.startswith('Нижнейм:') or line.startswith('Никнём:'):
            nickname = line.split(':', 1)[1].strip()
            print(f"📌 Найден никнейм: {nickname}")
        # Ищем ранг
        elif line.startswith('Ранг:') or line.startswith('Парт:') or line.startswith('Уровень:'):
            try:
                rank = int(line.split(':', 1)[1].strip())
                print(f"📌 Найден ранг: {rank}")
            except:
                print(f"⚠️ Ошибка парсинга ранга: {line}")
                pass
    
    # Проверяем данные
    if not nickname or not rank:
        print(f"❌ Не найдены данные: nickname={nickname}, rank={rank}")
        await message.reply_text(
            "❌ *Неверный формат!*\n\n"
            "Используйте:\n"
            "```\n"
            "Никнейм: ваш_ник\n"
            "Ранг: 5\n"
            "```\n\n"
            "*Пример:*\n"
            "```\n"
            "Никнейм: Diego_Retroware\n"
            "Ранг: 5\n"
            "```",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверяем никнейм
    if ' ' in nickname:
        await message.reply_text("❌ Никнейм не должен содержать пробелов!")
        return
    
    if len(nickname) < 3 or len(nickname) > 30:
        await message.reply_text("❌ Никнейм должен быть от 3 до 30 символов!")
        return
    
    # Проверяем ранг (2-10)
    if rank < 2 or rank > 10:
        await message.reply_text("❌ Ранг должен быть от 2 до 10!")
        return
    
    # Проверяем, не авторизован ли уже этот пользователь
    u = get_user(user.id)
    if u and u["nickname"]:
        await message.reply_text(
            f"❌ *Вы уже авторизованы!*\n\n"
            f"Ваш ник: `{u['nickname']}`\n"
            f"Ваш ранг: {get_rank_name(u['role'])} ({u['role']})\n\n"
            f"Изменить данные может только модератор.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверяем, что ник не занят (уникальность)
    existing = None
    for existing_user in get_all_users():
        if existing_user["nickname"] and existing_user["nickname"].lower() == nickname.lower():
            existing = existing_user
            break
    
    if existing:
        await message.reply_text(
            f"❌ *Никнейм `{nickname}` уже занят!*\n\n"
            f"Пользователь: {existing['name']}\n"
            f"Пожалуйста, выберите другой никнейм.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Добавляем пользователя в базу
    add_user(user)
    update_user(user.id, "nickname", nickname)
    update_user(user.id, "role", rank)
    
    # Успех
    await message.reply_text(
        f"✅ *АВТОРИЗАЦИЯ УСПЕШНА!* ✅\n\n"
        f"👤 Ваш ник: `{nickname}`\n"
        f"🎮 Ваш ранг: {get_rank_name(rank)} ({rank})\n\n"
        f"🔥 Добро пожаловать в семью *{FAMILY_NAME}*!",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Уведомляем модераторов
    await notify_moderators(
        context,
        f"📢 *НОВЫЙ УЧАСТНИК!*\n\n"
        f"👤 Пользователь: {user.first_name}\n"
        f"💫 Никнейм: {nickname}\n"
        f"🎮 Ранг: {get_rank_name(rank)} ({rank})"
    )
    
    # Удаляем сообщение с формой
    try:
        await message.delete()
        print("✅ Сообщение удалено")
    except:
        print("⚠️ Не удалось удалить сообщение")

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER (ИСПРАВЛЕННЫЙ) ==========
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime
import time
import socket
import sys

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health' or self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "status": "ok",
                "bot": "Nevermore Family Bot",
                "timestamp": datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<h1>Nevermore Bot is running!</h1><p>Status: ONLINE</p><a href="/health">Health Check</a>')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Отключаем логи
        pass

def start_web_server():
    """Запускает веб-сервер и гарантированно открывает порт"""
    port = int(os.getenv("PORT", 10000))
    
    # Пробуем запустить сервер с повторными попытками
    max_retries = 5
    for attempt in range(max_retries):
        try:
            server = HTTPServer(('0.0.0.0', port), HealthHandler)
            print(f"✅ Веб-сервер запущен на порту {port}")
            print(f"🔗 Health check: http://localhost:{port}/health")
            
            # Держим сервер запущенным
            server.serve_forever()
            break
        except OSError as e:
            if "Address already in use" in str(e) and attempt < max_retries - 1:
                print(f"⚠️ Порт {port} занят, пробуем {port + 1}...")
                port += 1
            else:
                print(f"❌ Не удалось запустить сервер: {e}")
                # Не падаем, просто продолжаем
                return
        except Exception as e:
            print(f"❌ Ошибка при запуске сервера: {e}")
            return

# Запускаем сервер НЕ в фоновом потоке, а в основном
# Но используем threading, чтобы не блокировать бота
import threading
web_thread = threading.Thread(target=start_web_server, daemon=False)
web_thread.start()

# Даём время серверу запуститься
time.sleep(2)

# Проверяем, что порт открыт
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', int(os.getenv("PORT", 10000))))
    if result == 0:
        print(f"✅ Порт {os.getenv('PORT', 10000)} успешно открыт")
    else:
        print(f"⚠️ Порт {os.getenv('PORT', 10000)} не открыт")
    sock.close()
except Exception as e:
    print(f"⚠️ Не удалось проверить порт: {e}")

print("✅ Веб-сервер успешно настроен")

# ========== ПРОСМОТР БАЗЫ ДАННЫХ ==========
async def check_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить содержимое базы данных (только для админов)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Нет прав! Только владелец!")
        return
    
    users = get_all_users()
    
    if not users:
        await update.message.reply_text("📋 База данных пуста")
        return
    
    text = "📊 *БАЗА ДАННЫХ - ВСЕ ПОЛЬЗОВАТЕЛИ*\n\n"
    for u in users[:20]:
        name = u["nickname"] or u["name"]
        username = f" (@{u['username']})" if u["username"] else ""
        mod_text = ""
        if u["mod_role"] == 8:
            mod_text = " [Мод]"
        elif u["mod_role"] == 9:
            mod_text = " [Зам]"
        elif u["mod_role"] == 10:
            mod_text = " [Лид]"
        
        text += f"• {name}{username} — ранг {u['role']}, репа {u['rep']}{mod_text}\n"
        
        if len(text) > 4000:
            text += "\n... и другие"
            break
    
    text += f"\n📊 *Всего:* {len(users)} пользователей"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_mutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить активные муты"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Нет прав! Только владелец!")
        return
    
    lst = get_mutes_list()
    if not lst:
        await update.message.reply_text("🔇 Нет активных мутов")
        return
    
    text = "🔇 *АКТИВНЫЕ МУТЫ*\n\n"
    for m in lst:
        u = get_user(m["user_id"])
        name = u["nickname"] or u["name"] if u else str(m["user_id"])
        text += f"• {name} — до {m['until'][:16]}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_bans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить активные баны"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Нет прав! Только владелец!")
        return
    
    lst = get_bans_list()
    if not lst:
        await update.message.reply_text("🔨 Нет активных банов")
        return
    
    text = "🔨 *АКТИВНЫЕ БАНЫ*\n\n"
    for b in lst:
        u = get_user(b["user_id"])
        name = u["nickname"] or u["name"] if u else str(b["user_id"])
        text += f"• {name} — до {b['until'][:10]}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_weddings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить активные свадьбы"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Нет прав! Только владелец!")
        return
    
    active = get_active_weddings()
    if not active:
        await update.message.reply_text("💔 Нет активных свадеб")
        return
    
    text = "💍 *АКТИВНЫЕ СВАДЬБЫ*\n\n"
    for w in active:
        u1 = get_user(w["user1"])
        u2 = get_user(w["user2"])
        name1 = u1["nickname"] or u1["name"] if u1 else str(w["user1"])
        name2 = u2["nickname"] or u2["name"] if u2 else str(w["user2"])
        text += f"• {name1} + {name2}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def setuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить ник и ранг пользователя"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("❌ /setuser [@username] [ник] [ранг]\n\nПример: /setuser @username Diego_Retroware 5")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    nickname = context.args[1][:50]
    try:
        role = int(context.args[2])
        if role < 2 or role > 10:
            await update.message.reply_text("❌ Ранг должен быть от 2 до 10")
            return
    except:
        await update.message.reply_text("❌ Неверный формат ранга!")
        return
    
    u = get_user(uid)
    if not u:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    old_nick = u["nickname"] or "Не установлен"
    old_role = u["role"]
    
    update_user(uid, "nickname", nickname)
    update_user(uid, "role", role)
    
    await update.message.reply_text(
        f"✅ *{u['name']}* обновлён!\n\n"
        f"📝 Ник: {old_nick} → {nickname}\n"
        f"🎮 Ранг: {old_role} → {role} ({get_rank_name(role)})",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(update.effective_user.id, "setuser", uid, f"ник:{nickname}, ранг:{role}")

async def edit_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменить никнейм пользователя (только для роли 9-10)"""
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    if user_id not in ADMINS and (not u or u["mod_role"] not in [9, 10]):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 9+")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /editnick [@username] [новый_ник]\n\nПример: /editnick @username ПравильныйНик")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    new_nick = ' '.join(context.args[1:])[:50]
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    # Проверка на уникальность
    existing = None
    for existing_user in get_all_users():
        if existing_user["nickname"] and existing_user["nickname"].lower() == new_nick.lower() and existing_user["user_id"] != uid:
            existing = existing_user
            break
    
    if existing:
        await update.message.reply_text(f"❌ Никнейм `{new_nick}` уже занят! Выберите другой.", parse_mode=ParseMode.MARKDOWN)
        return
    
    old_nick = target["nickname"] or "Не был установлен"
    update_user(uid, "nickname", new_nick)
    
    await update.message.reply_text(
        f"✅ *{target['name']}* никнейм изменён!\n"
        f"📝 Старый: {old_nick}\n"
        f"💫 Новый: {new_nick}",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user_id, "edit_nick", uid, f"{old_nick} -> {new_nick}")

async def delnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить никнейм пользователя (только для роли 9-10)"""
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    if user_id not in ADMINS and (not u or u["mod_role"] not in [9, 10]):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 9+")
        return
    
    if not context.args:
        await update.message.reply_text("❌ /delnick [@username]\n\nПример: /delnick @username")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    old_nick = target["nickname"] or "Не был установлен"
    update_user(uid, "nickname", None)
    
    await update.message.reply_text(
        f"✅ У *{target['name']}* удалён никнейм\n"
        f"📝 Старый ник: {old_nick}",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user_id, "delnick", uid, old_nick)

# ========== ДЛЯ СОЗДАТЕЛЯ (ТОЛЬКО ВЛАДЕЛЕЦ) ==========

async def creator_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель создателя (только для владельца)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Доступ запрещен! Только для создателя.")
        return
    
    text = """
👑 *ПАНЕЛЬ СОЗДАТЕЛЯ* 👑

📊 *УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ:*
/checkdb - Все пользователи
/checkmutes - Активные муты
/checkbans - Активные баны
/checkweddings - Активные свадьбы
/sql [запрос] - Выполнить SQL запрос
/backup - Создать бэкап БД

⭐ *УПРАВЛЕНИЕ РЕПУТАЦИЕЙ:*
/giverep [@username] [кол-во] - Выдать репутацию
/take rep [@username] [кол-во] - Забрать репутацию
/resetrep [@username] - Сбросить репутацию

👤 *УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ:*
/editnick [@username] [новый_ник] - Изменить ник
/delnick [@username] - Удалить ник
/setrank [@username] [ранг] - Изменить ранг
/resetuser [@username] - Сбросить все данные

🔧 *СИСТЕМНЫЕ:*
/restart - Перезагрузить бота
/clearlogs - Очистить логи
/stats - Статистика бота
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def take_rep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Забрать репутацию у пользователя (только для создателя)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /takerep [@username] [кол-во]\n\nПример: /takerep @username 50")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    try:
        amount = int(context.args[1])
        if amount <= 0:
            await update.message.reply_text("❌ Количество должно быть положительным!")
            return
    except:
        await update.message.reply_text("❌ Неверный формат количества!")
        return
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    old_rep = target["rep"] or 0
    new_rep = max(0, old_rep - amount)
    update_user(uid, "rep", new_rep)
    
    await update.message.reply_text(
        f"💀 *{target['name']}* потерял {amount} репутации!\n"
        f"Было: {old_rep}⭐ → Стало: {new_rep}⭐",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(update.effective_user.id, "take_rep", uid, f"-{amount}")

async def reset_rep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить репутацию пользователя (только для создателя)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ /resetrep [@username]\n\nПример: /resetrep @username")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    old_rep = target["rep"] or 0
    update_user(uid, "rep", 0)
    
    await update.message.reply_text(
        f"🔄 Репутация *{target['name']}* сброшена!\n"
        f"Было: {old_rep}⭐ → Стало: 0⭐",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(update.effective_user.id, "reset_rep", uid, f"было {old_rep}")

async def edit_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменить никнейм пользователя (только для роли 9-10)"""
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    # Проверяем роль 9 или 10
    if user_id not in ADMINS and (not u or u["mod_role"] not in [9, 10]):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 9+")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /editnick [@username] [новый_ник]\n\nПример: /editnick @username ПравильныйНик")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    new_nick = ' '.join(context.args[1:])[:50]
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    # Проверка на уникальность ника
    existing = None
    for existing_user in get_all_users():
        if existing_user["nickname"] and existing_user["nickname"].lower() == new_nick.lower() and existing_user["user_id"] != uid:
            existing = existing_user
            break
    
    if existing:
        await update.message.reply_text(f"❌ Никнейм `{new_nick}` уже занят! Выберите другой.", parse_mode=ParseMode.MARKDOWN)
        return
    
    old_nick = target["nickname"] or "Не был установлен"
    update_user(uid, "nickname", new_nick)
    
    await update.message.reply_text(
        f"✅ *{target['name']}* никнейм изменён!\n"
        f"📝 Старый: {old_nick}\n"
        f"💫 Новый: {new_nick}",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user_id, "edit_nick", uid, f"{old_nick} -> {new_nick}")

async def delnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить никнейм пользователя (только для роли 9-10)"""
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    if user_id not in ADMINS and (not u or u["mod_role"] not in [9, 10]):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 9+")
        return
    
    if not context.args:
        await update.message.reply_text("❌ /delnick [@username]\n\nПример: /delnick @username")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    old_nick = target["nickname"] or "Не был установлен"
    update_user(uid, "nickname", None)
    
    await update.message.reply_text(
        f"✅ У *{target['name']}* удалён никнейм\n"
        f"📝 Старый ник: {old_nick}",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user_id, "delnick", uid, old_nick)

async def set_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Изменить игровой ранг пользователя (только для роли 9-10)"""
    user_id = update.effective_user.id
    u = get_user(user_id)
    
    if user_id not in ADMINS and (not u or u["mod_role"] not in [9, 10]):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 9+")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrank [@username] [2-10]\n\nПример: /setrank @username 5")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    try:
        rank = int(context.args[1])
        if rank < 2 or rank > 10:
            await update.message.reply_text("❌ Ранг должен быть от 2 до 10")
            return
    except:
        await update.message.reply_text("❌ Неверный формат ранга!")
        return
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    old_rank = target["role"]
    update_user(uid, "role", rank)
    
    await update.message.reply_text(
        f"🔄 Ранг *{target['name']}* изменён!\n"
        f"Было: {old_rank} ({get_rank_name(old_rank)})\n"
        f"Стало: {rank} ({get_rank_name(rank)})",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user_id, "set_rank", uid, f"{old_rank}→{rank}")

async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить все данные пользователя (только для создателя)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ /resetuser [@username]\n\nПример: /resetuser @username")
        return
    
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    target = get_user(uid)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    
    # Сбрасываем все данные
    update_user(uid, "nickname", None)
    update_user(uid, "role", 2)
    update_user(uid, "warns", 0)
    update_user(uid, "rep", 0)
    update_user(uid, "spouse_id", None)
    update_user(uid, "prefix", None)
    update_user(uid, "mod_role", None)
    
    await update.message.reply_text(
        f"🔄 *ВСЕ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ СБРОШЕНЫ!*\n\n"
        f"👤 Пользователь: {target['name']}\n"
        f"✅ Никнейм удалён\n"
        f"✅ Ранг сброшен до 2\n"
        f"✅ Варны обнулены\n"
        f"✅ Репутация обнулена\n"
        f"✅ Брак расторгнут\n"
        f"✅ Модераторская роль снята",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(update.effective_user.id, "reset_user", uid, "полный сброс")

async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать бэкап базы данных (только для создателя)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    
    import io
    conn = get_db()
    c = conn.cursor()
    
    # Получаем все данные
    tables = ['users', 'mutes', 'bans', 'weddings', 'logs']
    backup_text = f"# Бэкап NEVERMORE BOT\n# Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    for table in tables:
        c.execute(f"SELECT * FROM {table}")
        rows = c.fetchall()
        backup_text += f"\n## {table.upper()} ({len(rows)} записей)\n"
        for row in rows:
            backup_text += f"{dict(row)}\n"
    
    conn.close()
    
    # Отправляем файл
    bio = io.BytesIO(backup_text.encode('utf-8'))
    bio.name = f"nevermore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    await update.message.reply_document(
        document=bio,
        caption=f"📦 *Бэкап базы данных*\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    add_log(update.effective_user.id, "backup_db")

async def clear_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить логи (только для создателя)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM logs")
    conn.commit()
    conn.close()
    
    await update.message.reply_text("🗑️ *Логи очищены!*", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "clear_logs")

async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика бота (только для создателя)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    
    users_count = len(get_all_users())
    mutes_count = len(get_mutes_list())
    bans_count = len(get_bans_list())
    weddings_count = len(get_active_weddings())
    
    logs_count = 0
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM logs")
    logs_count = c.fetchone()[0]
    conn.close()
    
    text = f"""
📊 *СТАТИСТИКА БОТА* 📊

👥 Пользователей: {users_count}
🔇 Активных мутов: {mutes_count}
🔨 Активных банов: {bans_count}
💍 Активных свадеб: {weddings_count}
📋 Логов действий: {logs_count}

📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}
🤖 Бот: @{FAMILY_NAME}_bot
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def sql_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнить SQL запрос (только для создателя)"""
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ /sql [SQL запрос]\n\n"
            "📝 *Примеры:*\n"
            "```sql\n"
            "SELECT * FROM users\n"
            "SELECT user_id, name, nickname, role FROM users\n"
            "UPDATE users SET role = 5 WHERE user_id = 123456789\n"
            "DELETE FROM logs WHERE time < '2024-01-01'\n"
            "```",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    query = ' '.join(context.args)
    conn = get_db()
    c = conn.cursor()
    
    try:
        c.execute(query)
        
        # Если это SELECT запрос
        if query.strip().upper().startswith('SELECT'):
            rows = c.fetchall()
            if rows:
                # Получаем названия колонок
                columns = [description[0] for description in c.description]
                
                # Формируем красивый вывод
                text = f"📊 *РЕЗУЛЬТАТ SQL ЗАПРОСА*\n\n"
                text += f"📋 Колонки: {', '.join(columns)}\n"
                text += f"📈 Найдено: {len(rows)} записей\n\n"
                
                for i, row in enumerate(rows[:20], 1):
                    text += f"*{i}.* "
                    for j, col in enumerate(columns):
                        value = row[j]
                        if value is None:
                            value = "NULL"
                        text += f"`{col}`: {value}"
                        if j < len(columns) - 1:
                            text += ", "
                    text += "\n"
                    
                    if len(text) > 4000:
                        text += "\n... и ещё"
                        break
                
                await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("✅ Запрос выполнен, результат пуст")
        
        # Если это INSERT, UPDATE, DELETE
        else:
            conn.commit()
            await update.message.reply_text(
                f"✅ *Запрос выполнен!*\n\n"
                f"📝 `{query[:100]}`\n"
                f"📊 Изменено строк: {c.rowcount}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        add_log(update.effective_user.id, "sql_query", reason=query[:100])
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ *Ошибка SQL!*\n\n"
            f"```\n{str(e)}\n```",
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        conn.close()

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка работоспособности бота"""
    print(f"🏓 Ping от {update.effective_user.id}")
    await update.message.reply_text(
        "🏓 Pong!\n"
        f"🤖 Bot is alive\n"
        f"📊 Users: {len(get_all_users())}\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 ЗАПУСК NEVERMORE FAMILY BOT...")
    init_db()
    print("✅ БАЗА ДАННЫХ SQLite ГОТОВА!")
    
    print("1️⃣ Создаю приложение...")
    app = Application.builder().token(BOT_TOKEN).build()
    print("2️⃣ Приложение создано")
    
    print("3️⃣ Регистрирую обработчики...")
    
    # Приветствие
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_message))
    print("  ✓ welcome_message")
    
    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("info", info))
    print("  ✓ start, help, rules, profile, info")
    
    # Модерация
    app.add_handler(CommandHandler("setname", setname))
    app.add_handler(CommandHandler("setprefix", setprefix))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("giverep", giverep))
    app.add_handler(CommandHandler("clear", clear))
    print("  ✓ setname, setprefix, unwarn, giverep, clear")
    
    # Свадьбы
    app.add_handler(CommandHandler("wedding", wedding))
    app.add_handler(CommandHandler("divorce", divorce))
    app.add_handler(CommandHandler("weddings", weddings_list))
    print("  ✓ wedding, divorce, weddings")
    
    # Репутация
    app.add_handler(CommandHandler("plus", plus))
    app.add_handler(CommandHandler("minus", minus))
    print("  ✓ plus, minus")
    
    # Развлечения
    app.add_handler(CommandHandler("kiss", kiss))
    app.add_handler(CommandHandler("hug", hug))
    app.add_handler(CommandHandler("slap", slap))
    app.add_handler(CommandHandler("me", me_action))
    app.add_handler(CommandHandler("try", try_action))
    app.add_handler(CommandHandler("gay", gay))
    app.add_handler(CommandHandler("clown", clown))
    app.add_handler(CommandHandler("wish", wish))
    print("  ✓ kiss, hug, slap, me, try, gay, clown, wish")
    
    # Статистика
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("online", online))
    app.add_handler(CommandHandler("check", check))
    print("  ✓ top, online, check")
    
    # Модерационные команды
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("warns", warns_command))
    app.add_handler(CommandHandler("bans", bans_list))
    app.add_handler(CommandHandler("mutelist", mutelist))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("delnick", delnick))
    app.add_handler(CommandHandler("setnick", setnick))
    print("  ✓ warn, mute, unmute, ban, unban, warns, bans, mutelist, logs, report, setuser, delnick, setnick")
    
    # Администрирование
    app.add_handler(CommandHandler("setrole", setrole))
    app.add_handler(CommandHandler("role", role))
    app.add_handler(CommandHandler("giveaccess", giveaccess))
    app.add_handler(CommandHandler("nlist", nlist))
    app.add_handler(CommandHandler("grole", grole))
    app.add_handler(CommandHandler("roles", roles))
    app.add_handler(CommandHandler("all", all_command))
    print("  ✓ setrole, role, giveaccess, nlist, grole, roles, all")
    
    # Команды для создателя
    app.add_handler(CommandHandler("creator", creator_panel))
    app.add_handler(CommandHandler("checkdb", check_db))
    app.add_handler(CommandHandler("checkmutes", check_mutes))
    app.add_handler(CommandHandler("checkbans", check_bans))
    app.add_handler(CommandHandler("checkweddings", check_weddings))
    app.add_handler(CommandHandler("takerep", take_rep))
    app.add_handler(CommandHandler("resetrep", reset_rep))
    app.add_handler(CommandHandler("editnick", edit_nick))
    app.add_handler(CommandHandler("setrank", set_rank))
    app.add_handler(CommandHandler("resetuser", reset_user))
    app.add_handler(CommandHandler("backup", backup_db))
    app.add_handler(CommandHandler("clearlogs", clear_logs))
    app.add_handler(CommandHandler("stats", bot_stats))
    app.add_handler(CommandHandler("sql", sql_query))
    app.add_handler(CommandHandler("setuser", setuser))
    
    # Автоматическая авторизация
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_auth))
    print("  ✓ auto_auth")
    
    # Обработка сообщений
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, all_messages))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("  ✓ all_messages, button_callback")
    
    print("4️⃣ ВСЕ ОБРАБОТЧИКИ ЗАРЕГИСТРИРОВАНЫ")
    print("✅ БОТ ГОТОВ К ЗАПУСКУ! 🔥 FAM NEVERMORE ONLINE!")
    
    print("5️⃣ Запускаю polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
