import os
import random
import sqlite3
import asyncio
import time
import logging
import io
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== НАСТРОЙКА ==========
logging.basicConfig(level=logging.INFO)

# ========== КОНФИГ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = {int(x) for x in os.getenv("ADMINS", "5695593671,1784442476").split(",")}
FAMILY_NAME = "Nevermore"
FAMILY_LINK = "https://t.me/famnevermore"
AUTH_LINK = "https://t.me/famnevermore/19467"
RULES_LINK = "https://t.me/famnevermore/26"
NEWS_LINK = "https://t.me/famnevermore/5"

# ========== БАЗА ДАННЫХ SQLITE ==========
def get_db():
    return sqlite3.connect('data.db')

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT,
        nickname TEXT,
        role INTEGER DEFAULT 2,
        warns INTEGER DEFAULT 0,
        rep INTEGER DEFAULT 0,
        spouse_id INTEGER,
        prefix TEXT,
        last_online TEXT,
        msgs INTEGER DEFAULT 0,
        joined TEXT,
        mod_role INTEGER,
        monthly_msgs INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS mutes (
        user_id INTEGER PRIMARY KEY,
        until TEXT,
        reason TEXT,
        moderator_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bans (
        user_id INTEGER PRIMARY KEY,
        until TEXT,
        reason TEXT,
        moderator_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS weddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user1 INTEGER,
        user2 INTEGER,
        date TEXT,
        divorced INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        target INTEGER,
        reason TEXT,
        time TEXT
    )''')
    conn.commit()
    conn.close()
    print("✅ База данных SQLite готова")

# ========== ФУНКЦИИ БД ==========
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(zip(['user_id', 'name', 'username', 'nickname', 'role', 'warns', 'rep', 'spouse_id', 'prefix', 'last_online', 'msgs', 'joined', 'mod_role', 'monthly_msgs'], row))
    return None

def add_user(user):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''INSERT INTO users (user_id, name, username, last_online, joined, monthly_msgs)
        VALUES (?, ?, ?, ?, ?, 0)
        ON CONFLICT(user_id) DO UPDATE SET
            name = excluded.name,
            username = excluded.username,
            last_online = excluded.last_online,
            msgs = users.msgs + 1,
            monthly_msgs = users.monthly_msgs + 1''',
        (user.id, user.first_name, user.username, now, now))
    conn.commit()
    conn.close()

def update_user(user_id, field, value):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def add_log(user_id, action, target=None, reason=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO logs (user_id, action, target, reason, time) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, target, reason, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    rows = c.fetchall()
    conn.close()
    return [dict(zip(['user_id', 'name', 'username', 'nickname', 'role', 'warns', 'rep', 'spouse_id', 'prefix', 'last_online', 'msgs', 'joined', 'mod_role', 'monthly_msgs'], row)) for row in rows]

def get_active_weddings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM weddings WHERE divorced = 0")
    rows = c.fetchall()
    conn.close()
    return [dict(zip(['id', 'user1', 'user2', 'date', 'divorced'], row)) for row in rows]

def add_wedding(u1, u2):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO weddings (user1, user2, date) VALUES (?, ?, ?)", (u1, u2, datetime.now().isoformat()))
    c.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (u2, u1))
    c.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (u1, u2))
    conn.commit()
    conn.close()

def divorce_wedding(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT spouse_id FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row and row[0]:
        spouse = row[0]
        c.execute("UPDATE weddings SET divorced = 1 WHERE (user1 = ? OR user2 = ?) AND divorced = 0", (user_id, user_id))
        c.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (user_id,))
        c.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (spouse,))
        conn.commit()
        conn.close()
        return spouse
    conn.close()
    return None

def add_mute(user_id, minutes, reason, mod_id):
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO mutes (user_id, until, reason, moderator_id) VALUES (?, ?, ?, ?)",
        (user_id, until, reason, mod_id))
    conn.commit()
    conn.close()

def remove_mute(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_muted(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT until FROM mutes WHERE user_id = ? AND until > ?", (user_id, datetime.now().isoformat()))
    row = c.fetchone()
    conn.close()
    return row is not None

def add_ban(user_id, days, reason, mod_id):
    until = (datetime.now() + timedelta(days=days)).isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO bans (user_id, until, reason, moderator_id) VALUES (?, ?, ?, ?)",
        (user_id, until, reason, mod_id))
    conn.commit()
    conn.close()

def remove_ban(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT until FROM bans WHERE user_id = ? AND until > ?", (user_id, datetime.now().isoformat()))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_bans_list():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM bans WHERE until > ?", (datetime.now().isoformat(),))
    rows = c.fetchall()
    conn.close()
    return [dict(zip(['user_id', 'until', 'reason', 'moderator_id'], row)) for row in rows]

def get_mutes_list():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM mutes WHERE until > ?", (datetime.now().isoformat(),))
    rows = c.fetchall()
    conn.close()
    return [dict(zip(['user_id', 'until', 'reason', 'moderator_id'], row)) for row in rows]

def get_logs(limit=15):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(zip(['id', 'user_id', 'action', 'target', 'reason', 'time'], row)) for row in rows]

def get_full_backup_text():
    conn = get_db()
    c = conn.cursor()
    tables = ['users', 'mutes', 'bans', 'weddings', 'logs']
    backup_text = f"# Бэкап NEVERMORE BOT\n# Дата: {datetime.now()}\n\n"
    for table in tables:
        c.execute(f"SELECT * FROM {table}")
        rows = c.fetchall()
        backup_text += f"\n## {table.upper()} ({len(rows)} записей)\n"
        for row in rows:
            backup_text += f"{row}\n"
    conn.close()
    return backup_text

# ========== РАНГИ ==========
game_ranks = {
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
    return user and user.get("mod_role") is not None and user["mod_role"] >= 8

def get_user_id_from_input(input_str):
    input_str = input_str.strip()
    if input_str.startswith('@'):
        username = input_str[1:].lower()
        for u in get_all_users():
            if u.get("username") and u["username"].lower() == username:
                return u["user_id"]
        return None
    try:
        return int(input_str)
    except:
        return None

# ========== ПРАВИЛА ==========
RULES = """
📜 *ПРАВИЛА FAM NEVERMORE* 📜

2️⃣ *18+ контент* — запрещено! → мут 120 мин
3️⃣ *Упоминание родителей* — запрещено! → мут 120 мин
4️⃣ *Слив личных данных* — бан
5️⃣ *Политика* — мут 60 мин
6️⃣ *Свастики и нацистская символика* — мут 60 мин
"""

def check_rule_violation(text):
    text_lower = text.lower()
    violations = []
    adult = ['порно', 'секс', '18+', 'голый', 'эротика']
    if any(w in text_lower for w in adult):
        violations.append(("adult", 120))
    parent = ['мать', 'отец', 'родители', 'мама', 'папа']
    if any(w in text_lower for w in parent):
        violations.append(("parent", 120))
    politics = ['путин', 'зеленский', 'политика', 'война']
    if any(w in text_lower for w in politics):
        violations.append(("politics", 60))
    nazi = ['свастика', 'нацист', 'гитлер']
    if any(w in text_lower for w in nazi):
        violations.append(("nazi", 60))
    return violations

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
pending_weddings = {}
report_votes = {}
report_id_counter = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    add_log(user.id, "start")
    u = get_user(user.id)
    
    status_emoji = "👤"
    if u.get("mod_role") == 10:
        status_emoji = "👑"
    elif u.get("mod_role") == 9:
        status_emoji = "⚔️"
    elif u.get("mod_role") == 8:
        status_emoji = "🛡️"
    
    welcome_text = f"""
╔══════════════════════════════════╗
║   🔥 *FAM {FAMILY_NAME}* 🔥   ║
╚══════════════════════════════════╝

{status_emoji} *Привет, {user.first_name}!*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎮 *ТВОЙ ПРОФИЛЬ:*
┌─────────────────────────────┐
│ 👤 Имя: {user.first_name}
│ 🎮 Ранг: {get_rank_emoji(u['role'])} *{get_rank_name(u['role'])}*
│ ⭐ Репутация: {u['rep']}
│ 💬 Сообщений: {u['msgs']}
│ ⚠️ Варны: {u['warns']}/3
└─────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 *ЧТО ДАЛЬШЕ?*

🔹 *Авторизация* — отправь сообщение:
   `Никнейм: твой_ник`
   `Ранг: 5`

🔹 *Команды* — используй /help

🔹 *Правила* — /rules

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*Добро пожаловать в семью!* ❤️
"""
    
    keyboard = [
        [InlineKeyboardButton("📜 Правила", callback_data="rules"),
         InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("⭐ Топ месяца", callback_data="top"),
         InlineKeyboardButton("💍 Свадьбы", callback_data="weddings")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
/kiss [reply] - Поцеловать
/hug [reply] - Обнять
/slap [reply] - Ударить
/me [действие] - Описать действие
/try [действие] - Попытать удачу
/gay - Гей дня
/clown - Клоун дня
/wish - Предсказание

📊 *СТАТИСТИКА:*
/top - Топ месяца
/online - Кто онлайн
/check [@username] - Проверить игрока

🔨 *МОДЕРАЦИЯ (роль 8+):*
/warn [reply] - Предупреждение
/unwarn [@username] - Снять варн
/mute [reply] [время] - Замутить
/unmute [reply] - Размутить
/ban [reply] - Забанить
/unban [@username] - Разбанить
/warns [@username] - Варны
/bans - Список банов
/mutelist - Список мутов
/logs - Логи
/clear [кол-во] - Очистить чат
/report [текст] - Пожаловаться
/setname [@username] [ник] - Установить ник
/setprefix [@username] [префикс] - Префикс

👑 *АДМИНИСТРИРОВАНИЕ (роль 9-10):*
/setrole [@username] [2-10] - Выдать ранг
/role [@username] [0/8/9/10] - Сменить роль
/giveaccess [@username] [8-10] - Выдать доступ
/nlist - Список участников
/grole [@username] [0-10] - Игровая роль
/roles - Все роли
/all - Призвать всех

📜 *ПРАВИЛА:*
/rules - Показать правила

💾 *БЭКАП:*
/backupdb - Скачать базу данных
"""
    
    if is_creator:
        creator_section = """

👑 *ДЛЯ СОЗДАТЕЛЯ* 👑

📊 *УПРАВЛЕНИЕ БД:*
/checkdb - Все пользователи
/checkmutes - Активные муты
/checkbans - Активные баны
/checkweddings - Активные свадьбы
/sql [запрос] - Выполнить SQL

⭐ *РЕПУТАЦИЯ:*
/takerep [@username] [кол-во] - Забрать репутацию
/resetrep [@username] - Сбросить репутацию

👤 *ПОЛЬЗОВАТЕЛИ:*
/resetuser [@username] - Полный сброс

🔧 *СИСТЕМНЫЕ:*
/creator - Панель создателя
/stats - Статистика
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
                spouse_name = spouse.get("nickname") or spouse["name"]
    
    mod_role_text = ""
    if u.get("mod_role"):
        mod_names = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}
        mod_role_text = f"\n👑 Мод. роль: {mod_names.get(u['mod_role'], u['mod_role'])}"
    
    text = (
        f"<b>{get_rank_emoji(u['role'])} ПРОФИЛЬ {get_rank_emoji(u['role'])}</b>\n\n"
        f"👤 Имя: <b>{u['name']}</b>\n"
        f"📝 Username: @{u.get('username') or 'Нет'}\n"
        f"💫 Никнейм: {u.get('nickname') or 'Не установлен'}\n"
        f"🏷️ Префикс: {u.get('prefix') or 'Нет'}\n"
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
        if u.get("mod_role") == 10:
            leader = u
        elif u.get("mod_role") == 9:
            deputy = u
        elif u.get("mod_role") == 8:
            moderators.append(u)
    
    leader_text = f"@{leader['username'] or leader['name']}" if leader else "Не указан"
    deputy_text = f"@{deputy['username'] or deputy['name']}" if deputy else "Не указан"
    moderators_text = ", ".join([f"@{m['username'] or m['name']}" for m in moderators]) if moderators else "Не указаны"
    
    info_text = f"""
ℹ️ *ИНФОРМАЦИЯ О СЕМЬЕ {FAMILY_NAME}* ℹ️

🛡 *РУКОВОДСТВО:*
👑 Лидер: {leader_text}
⚔️ Зам. лидера: {deputy_text}
🛡 Модератор: {moderators_text}

📊 *СТАТИСТИКА:*
👥 Участников: {len(users_list)}

📌 *ССЫЛКИ:*
📜 Правила: {RULES_LINK}
🔑 Авторизация: {AUTH_LINK}
"""
    await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)

# ========== РАЗВЛЕЧЕНИЯ (ОПТИМИЗИРОВАНЫ) ==========
async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💋 Ответь на сообщение того, кого хочешь поцеловать!")
        return
    target = update.message.reply_to_message.from_user
    text = random.choice([
        f"💋 {update.effective_user.first_name} нежно поцеловал(а) {target.first_name} в щёчку!",
        f"😘 {update.effective_user.first_name} подарил(а) страстный поцелуй {target.first_name}!",
        f"💕 {update.effective_user.first_name} и {target.first_name} обменялись нежными поцелуями!"
    ])
    await update.message.reply_text(text)
    add_log(update.effective_user.id, "kiss", target.id)

async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("🤗 Ответь на сообщение того, кого хочешь обнять!")
        return
    target = update.message.reply_to_message.from_user
    text = random.choice([
        f"🤗 {update.effective_user.first_name} крепко обнял(а) {target.first_name}!",
        f"💞 {update.effective_user.first_name} и {target.first_name} обнялись!",
        f"🫂 {update.effective_user.first_name} подарил(а) тёплые объятия {target.first_name}!"
    ])
    await update.message.reply_text(text)
    add_log(update.effective_user.id, "hug", target.id)

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("👋 Ответь на сообщение того, кого хочешь ударить!")
        return
    target = update.message.reply_to_message.from_user
    text = random.choice([
        f"🤚 {update.effective_user.first_name} дал(а) подзатыльник {target.first_name}!",
        f"💥 {update.effective_user.first_name} шлёпнул(а) {target.first_name}!",
        f"👋 {update.effective_user.first_name} отвесил(а) оплеуху {target.first_name}!"
    ])
    await update.message.reply_text(text)
    add_log(update.effective_user.id, "slap", target.id)

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
    users = get_all_users()
    if not users:
        await update.message.reply_text("🏳️‍🌈 Нет участников для выбора!")
        return
    target = random.choice(users)
    await update.message.reply_text(f"🏳️‍🌈 *Гей дня:* {target['name']}! 🏳️‍🌈", parse_mode=ParseMode.MARKDOWN)

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    if not users:
        await update.message.reply_text("🤡 Нет участников для выбора!")
        return
    target = random.choice(users)
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

# ========== ОСТАЛЬНЫЕ КОМАНДЫ (ВСЕ КОРОТКИЕ ВЕРСИИ) ==========
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = sorted(get_all_users(), key=lambda x: x.get("monthly_msgs") or 0, reverse=True)[:5]
    if not users:
        await update.message.reply_text("📊 Нет данных за этот месяц")
        return
    rewards = {1: 70, 2: 50, 3: 40, 4: 30, 5: 20}
    text = "📊 *ТОП АКТИВНЫХ ЗА МЕСЯЦ* 📊\n\n"
    for i, u in enumerate(users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        reward = rewards.get(i, 0)
        text += f"{medal} {u.get('nickname') or u['name']} — {u.get('monthly_msgs', 0)} сообщений\n"
        if reward > 0:
            text += f"   🎁 Награда: +{reward}⭐\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    online_list = []
    offline_list = []
    for u in get_all_users():
        if u.get("last_online"):
            try:
                last = datetime.fromisoformat(u["last_online"])
                if (now - last).seconds < 300:
                    online_list.append(u)
                else:
                    offline_list.append(u)
            except:
                offline_list.append(u)
        else:
            offline_list.append(u)
    
    text = f"🟢 *ОНЛАЙН ({len(online_list)}):*\n\n"
    for u in online_list[:20]:
        text += f"• {u.get('nickname') or u['name']}\n"
    text += f"\n⚫ *ОФФЛАЙН ({len(offline_list)}):*\n\n"
    for u in offline_list[:20]:
        last = u["last_online"][:16] if u.get("last_online") else "Никогда"
        text += f"• {u.get('nickname') or u['name']} — был {last}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check [@username]\n\nПример: /check @username")
        return
    username = context.args[0].lower().replace('@', '')
    for u in get_all_users():
        if u.get("username") and u["username"].lower() == username:
            await update.message.reply_text(f"🔍 *{u.get('nickname') or u['name']}* — ранг {u['role']}, репа {u['rep']}", parse_mode=ParseMode.MARKDOWN)
            return
        elif u.get("nickname") and u["nickname"].lower() == username:
            await update.message.reply_text(f"🔍 *{u['name']}* — ранг {u['role']}, репа {u['rep']}", parse_mode=ParseMode.MARKDOWN)
            return
    await update.message.reply_text("❌ Пользователь не найден")

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setname [@username] [ник]\n\nПример: /setname @username Крутой_Чел")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    nickname = ' '.join(context.args[1:])[:50]
    update_user(uid, "nickname", nickname)
    await update.message.reply_text(f"✅ *{get_user(uid)['name']}* получил ник: {nickname}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "set_name", uid, nickname)

async def setnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setname(update, context)

async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setprefix [@username] [префикс]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    prefix = ' '.join(context.args[1:])[:20]
    update_user(uid, "prefix", prefix)
    await update.message.reply_text(f"✅ Префикс установлен!")
    add_log(update.effective_user.id, "set_prefix", uid, prefix)

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение нарушителя!")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    t = get_user(target.id)
    if not t:
        add_user(target)
        t = get_user(target.id)
    new_warns = (t["warns"] or 0) + 1
    update_user(target.id, "warns", new_warns)
    await update.message.reply_text(f"⚠️ *{target.first_name}* получил предупреждение!\n📝 Причина: {reason}\n⚠️ Предупреждений: {new_warns}/3", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "warn", target.id, reason)
    if new_warns >= 3:
        add_mute(target.id, 1440, "Автоматический мут за 3 предупреждения", update.effective_user.id)
        await update.message.reply_text(f"🔇 {target.first_name} автоматически замучен на 1 день!")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not context.args:
        await update.message.reply_text("❌ /unwarn [@username]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    u = get_user(uid)
    new_warns = max(0, (u["warns"] or 0) - 1)
    update_user(uid, "warns", new_warns)
    await update.message.reply_text(f"✅ *{u['name']}* снято предупреждение! Теперь: {new_warns}/3", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "unwarn", uid)

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение нарушителя!")
        return
    target = update.message.reply_to_message.from_user
    minutes = int(context.args[0]) if context.args else 60
    reason = ' '.join(context.args[1:]) or "Нарушение правил"
    add_mute(target.id, minutes, reason, update.effective_user.id)
    await update.message.reply_text(f"🔇 *{target.first_name}* замучен на {minutes} минут!\n📝 Причина: {reason}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "mute", target.id, f"{minutes}мин")

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
        await update.message.reply_text("❌ Ответь на сообщение нарушителя!")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    add_ban(target.id, 365, reason, update.effective_user.id)
    await update.message.reply_text(f"🔨 *{target.first_name}* забанен!\n📝 Причина: {reason}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "ban", target.id, reason)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not context.args:
        await update.message.reply_text("❌ /unban [@username]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    remove_ban(uid)
    await update.message.reply_text(f"🔓 Пользователь разбанен!")
    add_log(update.effective_user.id, "unban", uid)

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if context.args:
        uid = get_user_id_from_input(context.args[0])
        if uid:
            u = get_user(uid)
            await update.message.reply_text(f"⚠️ *{u['name']}* имеет {u['warns']}/3 предупреждений", parse_mode=ParseMode.MARKDOWN)
            return
    await update.message.reply_text("❌ /warns [@username]")

async def bans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    bans = get_bans_list()
    if not bans:
        await update.message.reply_text("🔨 Нет активных банов")
        return
    text = "🔨 *Активные баны:*\n\n"
    for b in bans:
        u = get_user(b["user_id"])
        text += f"• {u['name'] if u else b['user_id']} — до {b['until'][:10]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    mutes = get_mutes_list()
    if not mutes:
        await update.message.reply_text("🔇 Нет активных мутов")
        return
    text = "🔇 *Активные муты:*\n\n"
    for m in mutes:
        u = get_user(m["user_id"])
        text += f"• {u['name'] if u else m['user_id']} — до {m['until'][:16]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    logs = get_logs(10)
    if not logs:
        await update.message.reply_text("Нет логов")
        return
    text = "📋 *Последние действия:*\n\n"
    for log in logs:
        u = get_user(log["user_id"])
        text += f"• {log['time'][:16]} — {u['name'] if u else log['user_id']}: {log['action']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not context.args:
        await update.message.reply_text("❌ /clear [кол-во]")
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
        await update.message.reply_text(f"✅ Очищено {deleted} сообщений")
        add_log(update.effective_user.id, "clear", reason=f"{deleted} сообщений")
    except:
        await update.message.reply_text("❌ Ошибка при очистке")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /report [текст жалобы]")
        return
    reason = ' '.join(context.args)
    global report_id_counter
    report_id_counter += 1
    rid = report_id_counter
    report_votes[rid] = {"user": update.effective_user.id, "reason": reason, "votes": 0}
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Рассмотреть", callback_data=f"rep_{rid}")]])
    sent = 0
    for u in get_all_users():
        if u.get("mod_role") in [8, 9, 10]:
            try:
                await context.bot.send_message(u["user_id"], f"📢 *НОВАЯ ЖАЛОБА #{rid}!*\n\nОт: {update.effective_user.first_name}\nТекст: {reason}", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
                sent += 1
            except:
                pass
    if sent > 0:
        await update.message.reply_text(f"✅ Жалоба #{rid} отправлена {sent} модераторам!")
        add_log(update.effective_user.id, "report", reason=reason)
    else:
        await update.message.reply_text("❌ Нет доступных модераторов!")

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
    await update.message.reply_text(f"⭐ *{user.first_name}* дал(а) +1 репутации *{target.first_name}*!\nТеперь: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)
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
    await update.message.reply_text(f"💀 *{user.first_name}* убавил(а) -1 репутации *{target.first_name}*!\nТеперь: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)
    add_log(user.id, "rep_minus", target.id)

async def wedding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💍 Ответь на сообщение того, кому хочешь предложить брак!")
        return
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя жениться на себе!")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да", callback_data=f"wed_accept_{user.id}_{target.id}"),
         InlineKeyboardButton("❌ Нет", callback_data=f"wed_decline_{user.id}_{target.id}")]
    ])
    await update.message.reply_text(f"💍 *{user.first_name}* предлагает брак *{target.first_name}*!\nУ вас есть 120 секунд, чтобы ответить!", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    pending_weddings[f"{user.id}_{target.id}"] = {"u1": user.id, "u2": target.id, "time": datetime.now()}

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
        name1 = u1.get("nickname") or u1["name"] if u1 else str(w["user1"])
        name2 = u2.get("nickname") or u2["name"] if u2 else str(w["user2"])
        date = w["date"][:10] if w["date"] else "Неизвестно"
        text += f"❤️ {name1} + {name2}\n📅 {date}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrole [@username] [2-10]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    role = int(context.args[1])
    update_user(uid, "role", role)
    await update.message.reply_text(f"✅ *{get_user(uid)['name']}* получил игровой ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "set_role", uid, f"ранг {role}")

async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только лидер может выдавать модераторские роли!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /role [@username] [0/8/9/10]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    mod_role = int(context.args[1])
    names = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}
    if mod_role == 0:
        update_user(uid, "mod_role", None)
        await update.message.reply_text(f"✅ У *{get_user(uid)['name']}* снята модераторская роль", parse_mode=ParseMode.MARKDOWN)
    else:
        update_user(uid, "mod_role", mod_role)
        await update.message.reply_text(f"✅ *{get_user(uid)['name']}* получил роль: {names[mod_role]}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "role", uid, f"роль {mod_role}")

async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await role(update, context)

async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    users = get_all_users()
    if not users:
        await update.message.reply_text("📋 Список пуст")
        return
    users.sort(key=lambda x: x.get("role") or 0, reverse=True)
    text = "📋 *СПИСОК УЧАСТНИКОВ*\n\n"
    for u in users[:30]:
        mod = ""
        if u.get("mod_role") == 10:
            mod = " [Лидер]"
        elif u.get("mod_role") == 9:
            mod = " [Зам]"
        elif u.get("mod_role") == 8:
            mod = " [Мод]"
        text += f"• {u.get('nickname') or u['name']} — ранг {u['role']}{mod}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def grole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setrole(update, context)

async def roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    users = get_all_users()
    text = "👑 *МОДЕРАТОРСКИЕ РОЛИ*\n\n"
    for u in users:
        if u.get("mod_role") in [8, 9, 10]:
            role_name = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}[u["mod_role"]]
            text += f"• {u.get('nickname') or u['name']} — {role_name}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    mentions = []
    for u in get_all_users():
        if u.get("username"):
            mentions.append(f"@{u['username']}")
        else:
            mentions.append(u.get('nickname') or u['name'])
    if not mentions:
        await update.message.reply_text("Нет участников")
        return
    text = "🔔 *ВНИМАНИЕ! ОБЩЕЕ СОБРАНИЕ!* 🔔\n\n" + ' '.join(mentions[:50])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "all_push")

async def setuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    update_user(uid, "nickname", nickname)
    update_user(uid, "role", role)
    await update.message.reply_text(f"✅ *{get_user(uid)['name']}* обновлён!\n📝 Ник: {nickname}\n🎮 Ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "setuser", uid, f"ник:{nickname}, ранг:{role}")

async def delnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not context.args:
        await update.message.reply_text("❌ /delnick [@username]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    u = get_user(uid)
    old_nick = u.get("nickname") or "Не был установлен"
    update_user(uid, "nickname", None)
    await update.message.reply_text(f"✅ У *{u['name']}* удалён никнейм\n📝 Старый ник: {old_nick}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "delnick", uid, old_nick)

async def editnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setname(update, context)

async def setrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setrole(update, context)

# ========== КОМАНДЫ СОЗДАТЕЛЯ ==========
async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    backup_text = get_full_backup_text()
    bio = io.BytesIO(backup_text.encode('utf-8'))
    bio.name = f"nevermore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    await update.message.reply_document(document=bio, caption="📦 *Бэкап базы данных*", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "backup_db")

async def check_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    users = get_all_users()
    if not users:
        await update.message.reply_text("📋 База данных пуста")
        return
    text = "📊 *ПОЛЬЗОВАТЕЛИ:*\n\n"
    for u in users[:20]:
        text += f"• {u.get('nickname') or u['name']} — ранг {u['role']}, репа {u['rep']}\n"
    text += f"\n📊 Всего: {len(users)}"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_mutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    mutes = get_mutes_list()
    if not mutes:
        await update.message.reply_text("🔇 Нет активных мутов")
        return
    text = "🔇 *АКТИВНЫЕ МУТЫ*\n\n"
    for m in mutes:
        u = get_user(m["user_id"])
        text += f"• {u['name'] if u else m['user_id']} — до {m['until'][:16]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_bans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    bans = get_bans_list()
    if not bans:
        await update.message.reply_text("🔨 Нет активных банов")
        return
    text = "🔨 *АКТИВНЫЕ БАНЫ*\n\n"
    for b in bans:
        u = get_user(b["user_id"])
        text += f"• {u['name'] if u else b['user_id']} — до {b['until'][:10]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_weddings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    weddings = get_active_weddings()
    if not weddings:
        await update.message.reply_text("💔 Нет активных свадеб")
        return
    text = "💍 *АКТИВНЫЕ СВАДЬБЫ*\n\n"
    for w in weddings:
        u1 = get_user(w["user1"])
        u2 = get_user(w["user2"])
        text += f"• {u1['name'] if u1 else w['user1']} + {u2['name'] if u2 else w['user2']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def sql_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /sql [запрос]\n\nПример: /sql SELECT * FROM users")
        return
    query = ' '.join(context.args)
    try:
        conn = get_db()
        c = conn.cursor()
        if query.strip().upper().startswith('SELECT'):
            c.execute(query)
            rows = c.fetchall()
            if rows:
                text = "📊 *РЕЗУЛЬТАТ*\n\n"
                for row in rows[:10]:
                    text += f"• {row}\n"
                await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("✅ Пусто")
        else:
            c.execute(query)
            conn.commit()
            await update.message.reply_text("✅ Выполнено!")
        conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def take_rep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /takerep [@username] [кол-во]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    amount = int(context.args[1])
    u = get_user(uid)
    new_rep = max(0, (u["rep"] or 0) - amount)
    update_user(uid, "rep", new_rep)
    await update.message.reply_text(f"💀 Забрано {amount} репутации!\nБыло: {u['rep']}⭐ → Стало: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "take_rep", uid, f"-{amount}")

async def reset_rep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /resetrep [@username]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    u = get_user(uid)
    old_rep = u["rep"] or 0
    update_user(uid, "rep", 0)
    await update.message.reply_text(f"🔄 Репутация сброшена!\nБыло: {old_rep}⭐ → Стало: 0⭐", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "reset_rep", uid)

async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /resetuser [@username]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    update_user(uid, "nickname", None)
    update_user(uid, "role", 2)
    update_user(uid, "warns", 0)
    update_user(uid, "rep", 0)
    update_user(uid, "spouse_id", None)
    update_user(uid, "prefix", None)
    update_user(uid, "mod_role", None)
    await update.message.reply_text(f"🔄 *ВСЕ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ СБРОШЕНЫ!*\n\n👤 Пользователь: {get_user(uid)['name']}\n✅ Никнейм удалён\n✅ Ранг сброшен до 2\n✅ Варны обнулены\n✅ Репутация обнулена\n✅ Брак расторгнут\n✅ Модераторская роль снята", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "reset_user", uid)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    users = get_all_users()
    mutes = get_mutes_list()
    bans = get_bans_list()
    weddings = get_active_weddings()
    logs = get_logs(1000)
    text = f"📊 *СТАТИСТИКА БОТА*\n\n👥 Пользователей: {len(users)}\n🔇 Активных мутов: {len(mutes)}\n🔨 Активных банов: {len(bans)}\n💍 Активных свадеб: {len(weddings)}\n📋 Логов действий: {len(logs)}"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def clear_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def creator_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    text = """
👑 *ПАНЕЛЬ СОЗДАТЕЛЯ* 👑

📊 *УПРАВЛЕНИЕ БД:*
/checkdb - Все пользователи
/checkmutes - Активные муты
/checkbans - Активные баны
/checkweddings - Активные свадьбы
/sql [запрос] - Выполнить SQL

⭐ *РЕПУТАЦИЯ:*
/takerep [@username] [кол-во] - Забрать репутацию
/resetrep [@username] - Сбросить репутацию

👤 *ПОЛЬЗОВАТЕЛИ:*
/resetuser [@username] - Полный сброс

🔧 *СИСТЕМНЫЕ:*
/stats - Статистика
/clearlogs - Очистить логи
/backupdb - Скачать бэкап
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== КНОПКИ ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()
    
    if data == "rules":
        await rules(update, context)
    elif data == "profile":
        await profile(update, context)
    elif data == "top":
        await top(update, context)
    elif data == "weddings":
        await weddings_list(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data.startswith("rep_"):
        rid = int(data.split("_")[1])
        if rid in report_votes:
            await q.message.edit_text(f"📢 *Жалоба #{rid}*\n\nОт: {report_votes[rid]['user']}\nТекст: {report_votes[rid]['reason']}\n\n✅ Жалоба принята в обработку!", parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("wed_accept"):
        parts = data.split("_")
        u1, u2 = int(parts[2]), int(parts[3])
        key = f"{u1}_{u2}"
        if key in pending_weddings:
            add_wedding(u1, u2)
            await q.message.edit_text("💍 *ПОЗДРАВЛЯЕМ!* Брак заключен! 🎉", parse_mode=ParseMode.MARKDOWN)
            del pending_weddings[key]
    elif data.startswith("wed_decline"):
        await q.message.edit_text("💔 Брак отклонен!", parse_mode=ParseMode.MARKDOWN)

# ========== АВТОРИЗАЦИЯ ==========
async def auto_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    text = message.text.strip()
    if not any(kw in text for kw in ['Никнейм:', 'Ник:', 'Нижнейм:']):
        return
    
    lines = text.split('\n')
    nickname = None
    rank = None
    for line in lines:
        line = line.strip()
        if line.startswith('Никнейм:') or line.startswith('Ник:') or line.startswith('Нижнейм:'):
            nickname = line.split(':', 1)[1].strip()
        elif line.startswith('Ранг:') or line.startswith('Парт:'):
            try:
                rank = int(line.split(':', 1)[1].strip())
            except:
                pass
    
    if not nickname or not rank:
        await message.reply_text("❌ *Неверный формат!*\n\nИспользуйте:\n```\nНикнейм: ваш_ник\nРанг: 5\n```\n\n*Пример:*\n```\nНикнейм: Diego_Retroware\nРанг: 5\n```", parse_mode=ParseMode.MARKDOWN)
        return
    if ' ' in nickname or len(nickname) < 3 or len(nickname) > 30:
        await message.reply_text("❌ Никнейм должен быть 3-30 символов без пробелов!")
        return
    if rank < 2 or rank > 10:
        await message.reply_text("❌ Ранг должен быть от 2 до 10!")
        return
    
    u = get_user(message.from_user.id)
    if u and u.get("nickname"):
        await message.reply_text(f"❌ *Вы уже авторизованы!*\n\nВаш ник: `{u['nickname']}`\nВаш ранг: {get_rank_name(u['role'])} ({u['role']})\n\nИзменить данные может только модератор.", parse_mode=ParseMode.MARKDOWN)
        return
    
    for existing_user in get_all_users():
        if existing_user.get("nickname") and existing_user["nickname"].lower() == nickname.lower():
            await message.reply_text(f"❌ *Никнейм `{nickname}` уже занят!*\n\nПользователь: {existing_user['name']}\nПожалуйста, выберите другой никнейм.", parse_mode=ParseMode.MARKDOWN)
            return
    
    add_user(message.from_user)
    update_user(message.from_user.id, "nickname", nickname)
    update_user(message.from_user.id, "role", rank)
    await message.reply_text(f"✅ *АВТОРИЗАЦИЯ УСПЕШНА!* ✅\n\n👤 Ваш ник: `{nickname}`\n🎮 Ваш ранг: {get_rank_name(rank)} ({rank})\n\n🔥 Добро пожаловать в семью *{FAMILY_NAME}*!", parse_mode=ParseMode.MARKDOWN)
    add_log(message.from_user.id, "auto_auth", reason=f"{nickname} ({rank})")
    try:
        await message.delete()
    except:
        pass

# ========== ПРИВЕТСТВИЕ ==========
async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for m in update.message.new_chat_members:
        if m.is_bot:
            continue
        add_user(m)
        text = f"""👋 *@{m.username or m.first_name}*, добро пожаловать в *FAM {FAMILY_NAME}*!

📝 Напиши свой ник в авторизацию в течение 24 часов, иначе кик.
📖 Правила: {RULES_LINK}
🔑 Авторизация: {AUTH_LINK}

*Приятного общения!* ❤️"""
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
async def all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if update.message.text.startswith('/'):
        return
    
    user = update.effective_user
    text = update.message.text
    
    violations = check_rule_violation(text)
    for v in violations:
        add_mute(user.id, v[1], f"Нарушение: {v[0]}", 0)
        try:
            await update.message.delete()
            await update.message.reply_text(f"🔇 {user.first_name}, нарушение правил! Мут {v[1]} минут.")
        except:
            pass
        return
    
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
    
    add_user(user)

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<h1>Nevermore Bot is running!</h1>')
    
    def log_message(self, format, *args):
        pass

def run_web_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ Веб-сервер запущен на порту {port}")
    server.serve_forever()

web_thread = threading.Thread(target=run_web_server, daemon=True)
web_thread.start()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 ЗАПУСК NEVERMORE FAMILY BOT...")
    init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация всех команд
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_message))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("kiss", kiss))
    app.add_handler(CommandHandler("hug", hug))
    app.add_handler(CommandHandler("slap", slap))
    app.add_handler(CommandHandler("me", me_action))
    app.add_handler(CommandHandler("try", try_action))
    app.add_handler(CommandHandler("gay", gay))
    app.add_handler(CommandHandler("clown", clown))
    app.add_handler(CommandHandler("wish", wish))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("online", online))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("setname", setname))
    app.add_handler(CommandHandler("setnick", setnick))
    app.add_handler(CommandHandler("setprefix", setprefix))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("warns", warns_command))
    app.add_handler(CommandHandler("bans", bans_list))
    app.add_handler(CommandHandler("mutelist", mutelist))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("plus", plus))
    app.add_handler(CommandHandler("minus", minus))
    app.add_handler(CommandHandler("wedding", wedding))
    app.add_handler(CommandHandler("divorce", divorce))
    app.add_handler(CommandHandler("weddings", weddings_list))
    app.add_handler(CommandHandler("setrole", setrole))
    app.add_handler(CommandHandler("role", role))
    app.add_handler(CommandHandler("giveaccess", giveaccess))
    app.add_handler(CommandHandler("nlist", nlist))
    app.add_handler(CommandHandler("grole", grole))
    app.add_handler(CommandHandler("roles", roles))
    app.add_handler(CommandHandler("all", all_command))
    app.add_handler(CommandHandler("setuser", setuser))
    app.add_handler(CommandHandler("delnick", delnick))
    app.add_handler(CommandHandler("editnick", editnick))
    app.add_handler(CommandHandler("setrank", setrank))
    app.add_handler(CommandHandler("backupdb", backup_db))
    app.add_handler(CommandHandler("creator", creator_panel))
    app.add_handler(CommandHandler("checkdb", check_db))
    app.add_handler(CommandHandler("checkmutes", check_mutes))
    app.add_handler(CommandHandler("checkbans", check_bans))
    app.add_handler(CommandHandler("checkweddings", check_weddings))
    app.add_handler(CommandHandler("sql", sql_query))
    app.add_handler(CommandHandler("takerep", take_rep))
    app.add_handler(CommandHandler("resetrep", reset_rep))
    app.add_handler(CommandHandler("resetuser", reset_user))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("clearlogs", clear_logs))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_auth))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, all_messages))
    
    print("✅ ВСЕ ОБРАБОТЧИКИ ЗАРЕГИСТРИРОВАНЫ")
    print("✅ БОТ ГОТОВ К ЗАПУСКУ! 🔥")
    
    import time
    time.sleep(3)
    print("🔄 Запускаю polling...")
    app.run_polling()
