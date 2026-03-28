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
BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", "-1003613005281"))
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

# ========== АВТОМАТИЧЕСКИЙ БЭКАП ==========
async def auto_backup(context: ContextTypes.DEFAULT_TYPE):
    """Автоматический бэкап базы данных в Telegram канал"""
    try:
        backup_text = get_full_backup_text()
        bio = io.BytesIO(backup_text.encode('utf-8'))
        bio.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        await context.bot.send_document(
            chat_id=BACKUP_CHANNEL_ID,
            document=bio,
            caption=f"📦 *Автобэкап* {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode=ParseMode.MARKDOWN
        )
        print(f"✅ Автобэкап отправлен в канал {BACKUP_CHANNEL_ID}")
    except Exception as e:
        print(f"❌ Ошибка автобэкапа: {e}")

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
pending_weddings = {}
report_votes = {}
report_id_counter = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    add_log(user.id, "start")
    u = get_user(user.id)
    keyboard = [[InlineKeyboardButton("📜 Правила", callback_data="rules")]]
    await update.message.reply_text(
        f"🔥 *ДОБРО ПОЖАЛОВАТЬ В FAM {FAMILY_NAME}!* 🔥\n\nПривет, {user.first_name}!\n🎮 Ранг: {get_rank_emoji(u['role'])} *{get_rank_name(u['role'])}*\n⭐ Репутация: {u['rep']}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
/setrole [@username] [2-10] - Выдать роль
/role [@username] [0-10] - Сменить роль
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

# ========== МОДЕРАЦИЯ ==========
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    t = get_user(target.id)
    if not t:
        add_user(target)
        t = get_user(target.id)
    new_warns = (t["warns"] or 0) + 1
    update_user(target.id, "warns", new_warns)
    await update.message.reply_text(f"⚠️ *{target.first_name}* получил предупреждение! ({new_warns}/3)", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "warn", target.id, reason)
    if new_warns >= 3:
        add_mute(target.id, 1440, "Автоматический мут", update.effective_user.id)
        await update.message.reply_text(f"🔇 {target.first_name} замучен на 1 день!")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /unwarn [@username]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    u = get_user(uid)
    new_warns = max(0, (u["warns"] or 0) - 1)
    update_user(uid, "warns", new_warns)
    await update.message.reply_text(f"✅ Снято предупреждение! Теперь: {new_warns}/3")
    add_log(update.effective_user.id, "unwarn", uid)

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    minutes = int(context.args[0]) if context.args else 60
    reason = ' '.join(context.args[1:]) or "Нарушение правил"
    add_mute(target.id, minutes, reason, update.effective_user.id)
    await update.message.reply_text(f"🔇 *{target.first_name}* замучен на {minutes} минут!", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "mute", target.id, f"{minutes}мин")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
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
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    add_ban(target.id, 365, reason, update.effective_user.id)
    await update.message.reply_text(f"🔨 *{target.first_name}* забанен!", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "ban", target.id, reason)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /unban [@username]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    remove_ban(uid)
    await update.message.reply_text(f"🔓 Пользователь разбанен!")
    add_log(update.effective_user.id, "unban", uid)

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if context.args:
        uid = get_user_id_from_input(context.args[0])
        if uid:
            u = get_user(uid)
            await update.message.reply_text(f"⚠️ {u['name']} имеет {u['warns']}/3 предупреждений")
    else:
        await update.message.reply_text("❌ /warns [@username]")

async def bans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    bans = get_bans_list()
    if not bans:
        await update.message.reply_text("🔨 Нет банов")
        return
    text = "🔨 *Баны:*\n"
    for b in bans:
        u = get_user(b["user_id"])
        text += f"• {u['name'] if u else b['user_id']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    mutes = get_mutes_list()
    if not mutes:
        await update.message.reply_text("🔇 Нет мутов")
        return
    text = "🔇 *Муты:*\n"
    for m in mutes:
        u = get_user(m["user_id"])
        text += f"• {u['name'] if u else m['user_id']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    logs = get_logs(10)
    if not logs:
        await update.message.reply_text("Нет логов")
        return
    text = "📋 *Логи:*\n"
    for log in logs:
        u = get_user(log["user_id"])
        text += f"• {u['name'] if u else log['user_id']}: {log['action']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
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
        pass

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /report [текст]")
        return
    reason = ' '.join(context.args)
    global report_id_counter
    report_id_counter += 1
    rid = report_id_counter
    report_votes[rid] = {"user": update.effective_user.id, "reason": reason}
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅", callback_data=f"rep_a_{rid}"), InlineKeyboardButton("❌", callback_data=f"rep_d_{rid}")]])
    sent = 0
    for u in get_all_users():
        if u.get("mod_role") in [8, 9, 10]:
            try:
                await context.bot.send_message(u["user_id"], f"📢 Жалоба #{rid}\nОт: {update.effective_user.first_name}\nТекст: {reason}", reply_markup=keyboard)
                sent += 1
            except:
                pass
    if sent > 0:
        await update.message.reply_text(f"✅ Жалоба #{rid} отправлена {sent} модераторам!")
        add_log(update.effective_user.id, "report", reason=reason)

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setname [@username] [ник]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    nickname = ' '.join(context.args[1:])[:50]
    update_user(uid, "nickname", nickname)
    await update.message.reply_text(f"✅ Ник установлен!")
    add_log(update.effective_user.id, "set_name", uid, nickname)

async def setnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setname(update, context)

async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setprefix [@username] [префикс]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    prefix = ' '.join(context.args[1:])[:20]
    update_user(uid, "prefix", prefix)
    await update.message.reply_text(f"✅ Префикс установлен!")
    add_log(update.effective_user.id, "set_prefix", uid, prefix)

# ========== АДМИНИСТРИРОВАНИЕ ==========
async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrole [@username] [2-10]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    role = int(context.args[1])
    update_user(uid, "role", role)
    await update.message.reply_text(f"✅ Ранг изменён на {get_rank_name(role)}!")
    add_log(update.effective_user.id, "set_role", uid, f"ранг {role}")

async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только лидер!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /role [@username] [0/8/9/10]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    mod_role = int(context.args[1])
    names = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}
    if mod_role == 0:
        update_user(uid, "mod_role", None)
        await update.message.reply_text(f"✅ Модераторская роль снята!")
    else:
        update_user(uid, "mod_role", mod_role)
        await update.message.reply_text(f"✅ Выдана роль: {names[mod_role]}!")
    add_log(update.effective_user.id, "role", uid, f"роль {mod_role}")

async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await role(update, context)

async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = get_all_users()
    users.sort(key=lambda x: x.get("mod_role") or 0, reverse=True)
    text = "📋 *Список участников:*\n"
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
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = get_all_users()
    text = "👑 *Модераторские роли:*\n"
    for u in users:
        if u.get("mod_role") in [8, 9, 10]:
            role_name = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}[u["mod_role"]]
            text += f"• {u.get('nickname') or u['name']} — {role_name}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = get_all_users()
    mentions = [f"@{u['username']}" for u in users if u.get("username")]
    if mentions:
        await update.message.reply_text("🔔 *ВНИМАНИЕ!* 🔔\n" + ' '.join(mentions[:30]), parse_mode=ParseMode.MARKDOWN)
        add_log(update.effective_user.id, "all_push")

# ========== СВАДЬБЫ ==========
async def wedding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💍 Ответь на сообщение!")
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
    await update.message.reply_text(f"💍 *{user.first_name}* предлагает брак *{target.first_name}*!", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    pending_weddings[f"{user.id}_{target.id}"] = {"u1": user.id, "u2": target.id}

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
        await update.message.reply_text("💔 Нет свадеб")
        return
    text = "💍 *АКТИВНЫЕ БРАКИ:*\n"
    for w in active:
        u1 = get_user(w["user1"])
        u2 = get_user(w["user2"])
        name1 = u1.get("nickname") or u1["name"] if u1 else str(w["user1"])
        name2 = u2.get("nickname") or u2["name"] if u2 else str(w["user2"])
        text += f"❤️ {name1} + {name2}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== РЕПУТАЦИЯ ==========
async def plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⭐ Ответь на сообщение!")
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
    await update.message.reply_text(f"⭐ *{user.first_name}* дал +1 репутации *{target.first_name}*!", parse_mode=ParseMode.MARKDOWN)
    add_log(user.id, "rep_plus", target.id)

async def minus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💀 Ответь на сообщение!")
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
    await update.message.reply_text(f"💀 *{user.first_name}* убавил -1 репутации *{target.first_name}*!", parse_mode=ParseMode.MARKDOWN)
    add_log(user.id, "rep_minus", target.id)

# ========== РАЗВЛЕЧЕНИЯ ==========
async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💋 Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    await update.message.reply_text(f"💋 {update.effective_user.first_name} поцеловал(а) {target.first_name}!")
    add_log(update.effective_user.id, "kiss", target.id)

async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("🤗 Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    await update.message.reply_text(f"🤗 {update.effective_user.first_name} обнял(а) {target.first_name}!")
    add_log(update.effective_user.id, "hug", target.id)

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("👋 Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    await update.message.reply_text(f"👋 {update.effective_user.first_name} ударил(а) {target.first_name}!")
    add_log(update.effective_user.id, "slap", target.id)

async def me_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /me [действие]")
        return
    await update.message.reply_text(f"* {update.effective_user.first_name} {' '.join(context.args)}")
    add_log(update.effective_user.id, f"me: {' '.join(context.args)}")

async def try_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /try [действие]")
        return
    outcomes = ["✅ Удачно! 🎉", "❌ Неудача... 😔", "✨ Получилось! ✨"]
    await update.message.reply_text(f"🎲 {update.effective_user.first_name} {' '.join(context.args)}\n{random.choice(outcomes)}")

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    if users:
        target = random.choice(users)
        await update.message.reply_text(f"🏳️‍🌈 *Гей дня:* {target['name']}!", parse_mode=ParseMode.MARKDOWN)

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    if users:
        target = random.choice(users)
        await update.message.reply_text(f"🤡 *Клоун дня:* {target['name']}!", parse_mode=ParseMode.MARKDOWN)

async def wish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wishes = ["💰 Богатства!", "❤️ Любви!", "🔥 Успеха!", "🍀 Удачи!"]
    await update.message.reply_text(f"✨ *Твоё предсказание:*\n{random.choice(wishes)}", parse_mode=ParseMode.MARKDOWN)

# ========== СТАТИСТИКА ==========
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = sorted(get_all_users(), key=lambda x: x.get("monthly_msgs") or 0, reverse=True)[:5]
    if not users:
        await update.message.reply_text("📊 Нет данных")
        return
    rewards = {1: 70, 2: 50, 3: 40, 4: 30, 5: 20}
    text = "📊 *ТОП МЕСЯЦА:*\n"
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
    for u in get_all_users():
        if u.get("last_online"):
            try:
                last = datetime.fromisoformat(u["last_online"])
                if (now - last).seconds < 300:
                    online_list.append(u)
            except:
                pass
    text = f"🟢 *ОНЛАЙН ({len(online_list)}):*\n" + "\n".join([f"• {u.get('nickname') or u['name']}" for u in online_list[:20]])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check [@username]")
        return
    username = context.args[0].lower().replace('@', '')
    for u in get_all_users():
        if u.get("username") and u["username"].lower() == username:
            await update.message.reply_text(f"🔍 {u.get('nickname') or u['name']} — ранг {u['role']}, репа {u['rep']}")
            return
        elif u.get("nickname") and u["nickname"].lower() == username:
            await update.message.reply_text(f"🔍 {u['name']} — ранг {u['role']}, репа {u['rep']}")
            return
    await update.message.reply_text("❌ Не найден")

# ========== БЭКАП ==========
async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для админов!")
        return
    
    backup_text = get_full_backup_text()
    bio = io.BytesIO(backup_text.encode('utf-8'))
    bio.name = f"nevermore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    await update.message.reply_document(document=bio, caption="📦 *Бэкап базы данных*", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "backup_db")

# ========== КНОПКИ ==========
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    if data == "rules":
        await rules(update, context)
    elif data.startswith("rep_"):
        await q.answer("Голос учтён")
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
        await message.reply_text("❌ *Неверный формат!*\nИспользуйте:\nНикнейм: ваш_ник\nРанг: 5", parse_mode=ParseMode.MARKDOWN)
        return
    if ' ' in nickname or len(nickname) < 3 or len(nickname) > 30:
        await message.reply_text("❌ Никнейм должен быть 3-30 символов без пробелов!")
        return
    if rank < 2 or rank > 10:
        await message.reply_text("❌ Ранг должен быть от 2 до 10!")
        return
    
    u = get_user(message.from_user.id)
    if u and u.get("nickname"):
        await message.reply_text(f"❌ Вы уже авторизованы! Ваш ник: {u['nickname']}")
        return
    
    for existing_user in get_all_users():
        if existing_user.get("nickname") and existing_user["nickname"].lower() == nickname.lower():
            await message.reply_text(f"❌ Никнейм `{nickname}` уже занят!", parse_mode=ParseMode.MARKDOWN)
            return
    
    add_user(message.from_user)
    update_user(message.from_user.id, "nickname", nickname)
    update_user(message.from_user.id, "role", rank)
    await message.reply_text(f"✅ *АВТОРИЗАЦИЯ УСПЕШНА!*\n👤 Ваш ник: {nickname}\n🎮 Ранг: {get_rank_name(rank)}", parse_mode=ParseMode.MARKDOWN)
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

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 ЗАПУСК NEVERMORE FAMILY BOT...")
    init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация команд
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_message))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("info", info))
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
    app.add_handler(CommandHandler("setname", setname))
    app.add_handler(CommandHandler("setnick", setnick))
    app.add_handler(CommandHandler("setprefix", setprefix))
    app.add_handler(CommandHandler("setrole", setrole))
    app.add_handler(CommandHandler("role", role))
    app.add_handler(CommandHandler("giveaccess", giveaccess))
    app.add_handler(CommandHandler("nlist", nlist))
    app.add_handler(CommandHandler("grole", grole))
    app.add_handler(CommandHandler("roles", roles))
    app.add_handler(CommandHandler("all", all_command))
    app.add_handler(CommandHandler("wedding", wedding))
    app.add_handler(CommandHandler("divorce", divorce))
    app.add_handler(CommandHandler("weddings", weddings_list))
    app.add_handler(CommandHandler("plus", plus))
    app.add_handler(CommandHandler("minus", minus))
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
    app.add_handler(CommandHandler("backupdb", backup_db))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_auth))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, all_messages))
    
    # Автоматический бэкап каждые 6 часов
    job_queue = app.job_queue
    job_queue.run_repeating(auto_backup, interval=21600, first=10)
    
    print("✅ ВСЕ ОБРАБОТЧИКИ ЗАРЕГИСТРИРОВАНЫ")
    print("✅ БОТ ГОТОВ К ЗАПУСКУ! 🔥")
    print("✅ Автобэкап в Telegram канал запущен (каждые 6 часов)")
    print("🔄 Запускаю polling...")
    app.run_polling()
