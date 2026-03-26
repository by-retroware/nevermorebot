import os
import random
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== КОНФИГ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "8768445585:AAEV44NdL684Fi_NLBRmWk89LROJr15nUZ0")
ADMINS = {int(x) for x in os.getenv("ADMINS", "5695593671,1784442476").split(",")}
FAMILY_NAME = "Nevermore"
FAMILY_LINK = "https://t.me/famnevermore"
AUTH_LINK = "https://t.me/famnevermore/19467"
RULES_LINK = "https://t.me/famnevermore/26"

# ========== ПОДКЛЮЧЕНИЕ К БД ==========
def get_db():
    conn = sqlite3.connect('bot_data.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            nickname TEXT,
            role INTEGER DEFAULT 2,
            warns INTEGER DEFAULT 0,
            rep INTEGER DEFAULT 0,
            spouse_id INTEGER DEFAULT NULL,
            prefix TEXT,
            last_online TEXT DEFAULT CURRENT_TIMESTAMP,
            msgs INTEGER DEFAULT 0,
            joined TEXT DEFAULT CURRENT_TIMESTAMP,
            mod_role INTEGER DEFAULT NULL
        )
    ''')
    
    # Таблица мутов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mutes (
            user_id INTEGER PRIMARY KEY,
            muted_until TEXT,
            reason TEXT,
            moderator_id INTEGER
        )
    ''')
    
    # Таблица банов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            banned_until TEXT,
            reason TEXT,
            moderator_id INTEGER
        )
    ''')
    
    # Таблица свадеб
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1 INTEGER,
            user2 INTEGER,
            date TEXT DEFAULT CURRENT_TIMESTAMP,
            divorced INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица логов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            target INTEGER,
            reason TEXT,
            time TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# ================= ФУНКЦИИ РАБОТЫ С БД =================
def get_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def add_user(user):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users(user_id, name, username, last_online)
        VALUES(?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            name = excluded.name,
            username = excluded.username,
            last_online = CURRENT_TIMESTAMP,
            msgs = msgs + 1
    ''', (user.id, user.first_name, user.username))
    conn.commit()
    conn.close()

def update_user_field(user_id, field, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def add_log(user_id, action, target=None, reason=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO logs(user_id, action, target, reason) VALUES(?, ?, ?, ?)", 
                   (user_id, action, target, reason))
    conn.commit()
    conn.close()

def is_muted(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT muted_until FROM mutes WHERE user_id = ? AND muted_until > CURRENT_TIMESTAMP", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def is_banned(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT banned_until FROM bans WHERE user_id = ? AND banned_until > CURRENT_TIMESTAMP", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_all_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_active_weddings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM weddings WHERE divorced = 0")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_wedding(user1, user2):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO weddings(user1, user2) VALUES(?, ?)", (user1, user2))
    cursor.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (user2, user1))
    cursor.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (user1, user2))
    conn.commit()
    conn.close()

def divorce_wedding(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT spouse_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0]:
        spouse_id = row[0]
        cursor.execute("UPDATE weddings SET divorced = 1 WHERE (user1 = ? OR user2 = ?) AND divorced = 0", (user_id, user_id))
        cursor.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (user_id,))
        cursor.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (spouse_id,))
        conn.commit()
        conn.close()
        return spouse_id
    conn.close()
    return None

def add_mute(user_id, duration_minutes, reason, moderator_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO mutes(user_id, muted_until, reason, moderator_id)
        VALUES(?, datetime('now', '+' || ? || ' minutes'), ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET muted_until = excluded.muted_until, reason = excluded.reason
    ''', (user_id, duration_minutes, reason, moderator_id))
    conn.commit()
    conn.close()

def remove_mute(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_ban(user_id, duration_days, reason, moderator_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bans(user_id, banned_until, reason, moderator_id)
        VALUES(?, datetime('now', '+' || ? || ' days'), ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET banned_until = excluded.banned_until, reason = excluded.reason
    ''', (user_id, duration_days, reason, moderator_id))
    conn.commit()
    conn.close()

def remove_ban(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_bans_list():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bans WHERE banned_until > CURRENT_TIMESTAMP")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_mutes_list():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM mutes WHERE muted_until > CURRENT_TIMESTAMP")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_logs(limit=15):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================
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
        users_list = get_all_users()
        for u in users_list:
            if u["username"] and u["username"].lower() == username:
                return u["user_id"]
        return None
    try:
        return int(input_str)
    except:
        return None

def check_rule_violation(text):
    text_lower = text.lower()
    violations = []
    
    adult_words = ['порно', 'секс', '18+', 'голый', 'эротика']
    if any(w in text_lower for w in adult_words):
        violations.append(("adult", 120, "мут 120 минут за 18+ контент"))
    
    parent_words = ['мать', 'отец', 'родители', 'мама', 'папа']
    if any(w in text_lower for w in parent_words):
        violations.append(("parent", 120, "мут 120 минут за упоминание родителей"))
    
    politics = ['путин', 'зеленский', 'политика', 'война', 'россия', 'украина']
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
    users_list = get_all_users()
    for u in users_list:
        if u["mod_role"] and u["mod_role"] in [8, 9, 10]:
            try:
                await context.bot.send_message(u["user_id"], text, parse_mode=ParseMode.MARKDOWN)
            except:
                pass

# ========== ВРЕМЕННЫЕ ДАННЫЕ ==========
pending_weddings = {}
report_cooldowns = {}
report_votes = {}
report_id_counter = 0

# ========== КОМАНДЫ (ВСЕ ТЕ ЖЕ) ==========

async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        add_user(member)
        add_log(member.id, "joined")
        welcome_text = f"""
👋 *@{member.username or member.first_name}*, добро пожаловать в группу *FAM {FAMILY_NAME}*!

📝 Напиши, пожалуйста, свой ник в авторизацию в течение 24 часов, иначе кик.
📖 Просим ознакомиться с правилами чата: {RULES_LINK}
🔑 Ссылка на авторизацию: {AUTH_LINK}

*Приятного общения!* ❤️
"""
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    add_log(user.id, "start")
    
    u = get_user(user.id)
    keyboard = [
        [InlineKeyboardButton("📜 Правила", callback_data="rules")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("⭐ Топ", callback_data="top")],
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
    add_log(update.effective_user.id, "help")
    await update.message.reply_text("""
🔥 *FAM NEVERMORE - КОМАНДЫ* 🔥

👤 *ПРОФИЛЬ:*
/profile - Твой профиль
/info - Инфо о семье
/setname [ник] - Установить ник
/setprefix [префикс] - Установить префикс

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
/top - Топ участников
/online - Кто онлайн
/check [ник] - Проверить игрока

🔨 *МОДЕРАЦИЯ:*
/warn [reply] [причина] - Предупреждение
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

👑 *АДМИНИСТРИРОВАНИЕ:*
/setrole [@username] [2-10] - Выдать роль
/role [@username] [0-10] - Сменить роль
/giveaccess [@username] [8-10] - Выдать доступ
/nlist - Список участников
/grole [@username] [0-10] - Игровая роль
/gnick [@username] [ник] - Дать ник
/roles - Все роли
/all - Призвать всех
""", parse_mode=ParseMode.MARKDOWN)

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES, parse_mode=ParseMode.MARKDOWN)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    if not u:
        add_user(user)
        u = get_user(user.id)
    
    spouse_name = "Нет"
    weddings_list = get_active_weddings()
    for w in weddings_list:
        if w["user1"] == user.id or w["user2"] == user.id:
            spouse_id = w["user1"] if w["user2"] == user.id else w["user2"]
            spouse = get_user(spouse_id)
            if spouse:
                spouse_name = spouse["nickname"] or spouse["name"]
    
    mod_role_text = ""
    if u["mod_role"]:
        mod_names = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}
        mod_role_text = f"\n👑 Мод. роль: {mod_names.get(u['mod_role'], u['mod_role'])}"
    
    profile_text = (
        f"<b>{get_rank_emoji(u['role'])} ПРОФИЛЬ {get_rank_emoji(u['role'])}</b>\n\n"
        f"👤 Имя: <b>{u['name']}</b>\n"
        f"📝 Username: @{u['username'] or 'Нет'}\n"
        f"💫 Никнейм: {u['nickname'] or 'Не установлен'}\n"
        f"🏷️ Префикс: {u['prefix'] or 'Нет'}\n"
        f"🎮 Игровой ранг: <b>{get_rank_name(u['role'])}</b>{mod_role_text}\n\n"
        f"⭐ Репутация: <b>{u['rep']}</b>\n"
        f"⚠️ Варны: {u['warns']}/3\n"
        f"💬 Сообщений: {u['msgs']}\n"
        f"💍 Супруг(а): {spouse_name}\n\n"
        f"📅 В семье с: {u['joined']}\n"
        f"🕐 Последний онлайн: {u['last_online']}"
    )
    
    await update.message.reply_text(profile_text, parse_mode=ParseMode.HTML)
    add_log(user.id, "view_profile")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    leader = None
    for u in users_list:
        if u["mod_role"] == 10:
            leader = u
            break
    
    leader_text = f"@{leader['username'] or leader['name']}" if leader else "Не указан"
    
    await update.message.reply_text(
        f"ℹ️ *ИНФОРМАЦИЯ О СЕМЬЕ {FAMILY_NAME}* ℹ️\n\n"
        f"👑 *Лидер:* {leader_text}\n"
        f"📊 *Участников:* {len(users_list)}\n"
        f"⭐ *Общая репутация:* {sum(u['rep'] for u in users_list)}\n\n"
        f"📌 *Ссылки:*\n• Правила: {RULES_LINK}\n• Авторизация: {AUTH_LINK}",
        parse_mode=ParseMode.MARKDOWN
    )

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /setname [ник]")
        return
    user_id = update.effective_user.id
    nickname = ' '.join(context.args)[:50]
    update_user_field(user_id, "nickname", nickname)
    await update.message.reply_text(f"✅ Никнейм установлен: {nickname}")
    add_log(user_id, "set_name", reason=nickname)

async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /setprefix [префикс]")
        return
    user_id = update.effective_user.id
    prefix = ' '.join(context.args)[:20]
    update_user_field(user_id, "prefix", prefix)
    await update.message.reply_text(f"✅ Префикс установлен: {prefix}")
    add_log(user_id, "set_prefix", reason=prefix)

async def wedding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💍 Ответь на сообщение!")
        return
    
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя на себе!")
        return
    
    weddings_list = get_active_weddings()
    for w in weddings_list:
        if w["user1"] == user.id or w["user2"] == user.id:
            await update.message.reply_text("❌ Вы уже в браке!")
            return
        if w["user1"] == target.id or w["user2"] == target.id:
            await update.message.reply_text("❌ Этот пользователь уже в браке!")
            return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, согласен", callback_data=f"wedding_accept_{user.id}_{target.id}")],
        [InlineKeyboardButton("❌ Нет, не согласен", callback_data=f"wedding_decline_{user.id}_{target.id}")]
    ])
    
    await update.message.reply_text(
        f"💍 *{user.first_name}* предлагает брак *{target.first_name}*!\n\nУ вас есть 120 секунд!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    
    pending_weddings[f"{user.id}_{target.id}"] = {
        "user1": user.id,
        "user2": target.id,
        "time": datetime.now(),
        "status1": False,
        "status2": False
    }

async def divorce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    spouse_id = divorce_wedding(user_id)
    if spouse_id:
        await update.message.reply_text(f"💔 *{update.effective_user.first_name}* развелся(ась)!", parse_mode=ParseMode.MARKDOWN)
        add_log(user_id, "divorce", spouse_id)
    else:
        await update.message.reply_text("❌ Вы не состоите в браке!")

async def weddings_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = get_active_weddings()
    if not active:
        await update.message.reply_text("💔 Нет свадеб")
        return
    
    text = "💍 *АКТИВНЫЕ БРАКИ* 💍\n\n"
    for w in active:
        user1 = get_user(w["user1"])
        user2 = get_user(w["user2"])
        name1 = user1["nickname"] or user1["name"] if user1 else str(w["user1"])
        name2 = user2["nickname"] or user2["name"] if user2 else str(w["user2"])
        text += f"❤️ {name1} + {name2}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def rep_plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⭐ Ответь на сообщение!")
        return
    
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя себе!")
        return
    
    target_user = get_user(target.id)
    if not target_user:
        add_user(target)
        target_user = get_user(target.id)
    
    update_user_field(target.id, "rep", (target_user["rep"] or 0) + 1)
    new_rep = (target_user["rep"] or 0) + 1
    
    await update.message.reply_text(
        f"⭐ *{user.first_name}* +1 репутации *{target.first_name}*!\nТеперь: {new_rep}⭐",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user.id, "rep_plus", target.id)

async def rep_minus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💀 Ответь на сообщение!")
        return
    
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя себе!")
        return
    
    target_user = get_user(target.id)
    if not target_user:
        add_user(target)
        target_user = get_user(target.id)
    
    update_user_field(target.id, "rep", (target_user["rep"] or 0) - 1)
    new_rep = (target_user["rep"] or 0) - 1
    
    await update.message.reply_text(
        f"💀 *{user.first_name}* -1 репутации *{target.first_name}*!\nТеперь: {new_rep}⭐",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user.id, "rep_minus", target.id)

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    moderator = update.effective_user
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение"
    
    target_user = get_user(target.id)
    if not target_user:
        add_user(target)
        target_user = get_user(target.id)
    
    new_warns = (target_user["warns"] or 0) + 1
    update_user_field(target.id, "warns", new_warns)
    
    await update.message.reply_text(
        f"⚠️ *{target.first_name}* получил предупреждение!\n📝 Причина: {reason}\n⚠️ Предупреждений: {new_warns}/3",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await notify_admins(context, f"⚠️ *ВЫДАНО ПРЕДУПРЕЖДЕНИЕ*\n\n👤 Модератор: {moderator.first_name}\n🔨 Нарушитель: {target.first_name}\n📝 Причина: {reason}\n⚠️ Всего варнов: {new_warns}/3")
    add_log(moderator.id, "warn", target.id, reason)
    
    if new_warns >= 3:
        add_mute(target.id, 1440, "Автомут за 3 предупреждения", moderator.id)
        await update.message.reply_text(f"🔇 {target.first_name} замучен на 1 день!")
        await notify_admins(context, f"🔇 *АВТОМАТИЧЕСКИЙ МУТ*\n\n👤 Пользователь: {target.first_name}\n⏱️ Длительность: 1 день")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    moderator = update.effective_user
    target = update.message.reply_to_message.from_user
    duration = context.args[0] if context.args else "60"
    reason = ' '.join(context.args[1:]) or "Нарушение"
    
    try:
        minutes = int(duration)
    except:
        minutes = 60
    
    add_mute(target.id, minutes, reason, moderator.id)
    
    await update.message.reply_text(
        f"🔇 *{target.first_name}* замучен!\n⏱️ Длительность: {minutes} минут\n📝 Причина: {reason}",
        parse_mode=ParseMode.MARKDOWN
    )
    await notify_admins(context, f"🔇 *ВЫДАН МУТ*\n\n👤 Модератор: {moderator.first_name}\n🔨 Нарушитель: {target.first_name}\n⏱️ Длительность: {minutes} минут\n📝 Причина: {reason}")
    add_log(moderator.id, "mute", target.id, f"{minutes}мин - {reason}")

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
    
    moderator = update.effective_user
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение"
    
    add_ban(target.id, 365, reason, moderator.id)
    
    await update.message.reply_text(
        f"🔨 *{target.first_name}* забанен!\n📝 Причина: {reason}",
        parse_mode=ParseMode.MARKDOWN
    )
    await notify_admins(context, f"🔨 *ВЫДАН БАН*\n\n👤 Модератор: {moderator.first_name}\n🔨 Нарушитель: {target.first_name}\n📝 Причина: {reason}")
    add_log(moderator.id, "ban", target.id, reason)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /unban [@username или user_id]")
        return
    
    target_input = context.args[0]
    target_id = get_user_id_from_input(target_input)
    
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    remove_ban(target_id)
    await update.message.reply_text(f"🔓 Пользователь {target_input} разбанен!")
    add_log(update.effective_user.id, "unban", target_id)

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    target = None
    if context.args:
        target_input = context.args[0]
        target_id = get_user_id_from_input(target_input)
        if target_id:
            target = get_user(target_id)
        else:
            await update.message.reply_text(f"❌ Пользователь {target_input} не найден")
            return
    elif update.message.reply_to_message:
        target = get_user(update.message.reply_to_message.from_user.id)
    
    if not target:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    await update.message.reply_text(f"⚠️ *{target['name']}* имеет {target['warns']}/3 предупреждений", parse_mode=ParseMode.MARKDOWN)

async def bans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    bans_list = get_bans_list()
    if not bans_list:
        await update.message.reply_text("🔨 Нет активных банов")
        return
    
    text = "🔨 *Активные баны:*\n\n"
    for b in bans_list:
        user = get_user(b["user_id"])
        name = user["nickname"] or user["name"] if user else str(b["user_id"])
        text += f"• {name} — до {b['banned_until']}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    mutelist = get_mutes_list()
    if not mutelist:
        await update.message.reply_text("🔇 Нет активных мутов")
        return
    
    text = "🔇 *Активные муты:*\n\n"
    for m in mutelist:
        user = get_user(m["user_id"])
        name = user["nickname"] or user["name"] if user else str(m["user_id"])
        text += f"• {name} — до {m['muted_until']}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    logs_list = get_logs(15)
    if not logs_list:
        await update.message.reply_text("Нет логов")
        return
    
    text = "📋 *Последние действия:*\n\n"
    for log in logs_list:
        user = get_user(log["user_id"])
        name = user["nickname"] or user["name"] if user else str(log["user_id"])
        text += f"• {log['time']} — {name}: {log['action']}\n"
    
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
        for i in range(amount):
            try:
                msgs = await update.message.chat.get_messages(i + 1)
                await msgs.delete()
            except:
                pass
        msg = await update.message.reply_text(f"✅ Очищено {amount} сообщений")
        await asyncio.sleep(3)
        await msg.delete()
    except:
        pass

async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS and not is_moderator(user_id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrole [@username] [2-10]\n\nПример: /setrole @username 5")
        return
    
    target_input = context.args[0]
    try:
        role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат роли!")
        return
    
    if role < 2 or role > 10:
        await update.message.reply_text("❌ Роль должна быть от 2 до 10")
        return
    
    target_id = get_user_id_from_input(target_input)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    update_user_field(target_id, "role", role)
    target_user = get_user(target_id)
    await update.message.reply_text(f"✅ *{target_user['name']}* получил игровой ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)
    add_log(user_id, "set_role", target_id, f"ранг {role}")

async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        current_user = get_user(user_id)
        if not current_user or current_user["mod_role"] != 10:
            await update.message.reply_text("⛔ Нет прав! Только лидер!")
            return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /role [@username] [0-10]\n\n0 - снять\n8 - Модератор\n9 - Зам\n10 - Лидер")
        return
    
    target_input = context.args[0]
    try:
        mod_role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    
    if mod_role < 0 or mod_role > 10:
        await update.message.reply_text("❌ Роль должна быть от 0 до 10")
        return
    
    target_id = get_user_id_from_input(target_input)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    role_names = {8: "🛡️ Модератор", 9: "👑 Зам. лидера", 10: "💎 Лидер"}
    
    if mod_role == 0:
        update_user_field(target_id, "mod_role", None)
        target_user = get_user(target_id)
        await update.message.reply_text(f"✅ У *{target_user['name']}* снята модераторская роль", parse_mode=ParseMode.MARKDOWN)
        add_log(user_id, "role_removed", target_id)
    else:
        if mod_role not in role_names:
            await update.message.reply_text("❌ Роль может быть: 8, 9, 10")
            return
        
        update_user_field(target_id, "mod_role", mod_role)
        target_user = get_user(target_id)
        await update.message.reply_text(f"✅ *{target_user['name']}* получил роль: {role_names[mod_role]}", parse_mode=ParseMode.MARKDOWN)
        add_log(user_id, "role_granted", target_id, f"роль {mod_role}")
        
        try:
            await context.bot.send_message(target_id, f"🎉 *Поздравляем!*\n\nТы получил роль: {role_names[mod_role]}", parse_mode=ParseMode.MARKDOWN)
        except:
            pass

async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await role(update, context)

async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    users_list = get_all_users()
    if not users_list:
        await update.message.reply_text("📋 Список пуст")
        return
    
    text = "📋 *СПИСОК УЧАСТНИКОВ*\n\n"
    for u in users_list[:50]:
        mod_role = ""
        if u["mod_role"] == 8:
            mod_role = " [🛡️Мод]"
        elif u["mod_role"] == 9:
            mod_role = " [👑Зам]"
        elif u["mod_role"] == 10:
            mod_role = " [💎Лид]"
        
        text += f"• {u['nickname'] or u['name']} ({u['user_id']}){mod_role} — ранг {u['role']}\n"
        if len(text) > 4000:
            text += "\n... и другие"
            break
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def grole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /grole [@username] [0-10]")
        return
    
    target_input = context.args[0]
    try:
        role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    
    if role < 0 or role > 10:
        await update.message.reply_text("❌ Роль должна быть от 0 до 10")
        return
    
    target_id = get_user_id_from_input(target_input)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    if role == 0:
        update_user_field(target_id, "role", 2)
        target_user = get_user(target_id)
        await update.message.reply_text(f"✅ У *{target_user['name']}* игровая роль сброшена до Новичка")
    else:
        update_user_field(target_id, "role", role)
        target_user = get_user(target_id)
        await update.message.reply_text(f"✅ *{target_user['name']}* получил игровой ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)
    
    add_log(update.effective_user.id, "grole", target_id, f"ранг {role}")

async def gnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /gnick [@username] [ник]")
        return
    
    target_input = context.args[0]
    nickname = ' '.join(context.args[1:])[:50]
    
    target_id = get_user_id_from_input(target_input)
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    update_user_field(target_id, "nickname", nickname)
    target_user = get_user(target_id)
    await update.message.reply_text(f"✅ *{target_user['name']}* получил ник: {nickname}", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "gnick", target_id, nickname)

async def roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    users_list = get_all_users()
    if not users_list:
        await update.message.reply_text("Нет участников")
        return
    
    text = "👑 *РОЛИ УЧАСТНИКОВ*\n\n"
    for u in users_list[:50]:
        mod_text = ""
        mod_role = u["mod_role"]
        if mod_role == 8:
            mod_text = " | 🛡️ Модер"
        elif mod_role == 9:
            mod_text = " | 👑 Зам"
        elif mod_role == 10:
            mod_text = " | 💎 Лидер"
        
        text += f"• {u['nickname'] or u['name']} — ранг {u['role']} ({get_rank_name(u['role'])}){mod_text}\n"
        if len(text) > 4000:
            text += "\n... и другие"
            break
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    
    users_list = get_all_users()
    mentions = []
    for u in users_list:
        if u["username"]:
            mentions.append(f"@{u['username']}")
        else:
            mentions.append(u['name'])
    
    if not mentions:
        await update.message.reply_text("Нет участников")
        return
    
    text = "🔔 *ВНИМАНИЕ! ОБЩЕЕ СОБРАНИЕ!* 🔔\n\n"
    chunk = ""
    for mention in mentions:
        if len(chunk + mention) > 4000:
            await update.message.reply_text(text + chunk, parse_mode=ParseMode.MARKDOWN)
            chunk = mention + " "
        else:
            chunk += mention + " "
    
    if chunk:
        await update.message.reply_text(text + chunk, parse_mode=ParseMode.MARKDOWN)
    
    add_log(update.effective_user.id, "all_push")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    sorted_users = sorted(users_list, key=lambda x: x["msgs"] or 0, reverse=True)[:10]
    
    text = "📊 *ТОП ПО СООБЩЕНИЯМ* 📊\n\n"
    for i, u in enumerate(sorted_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = u["nickname"] or u["name"]
        text += f"{medal} {name} — {u['msgs']} сообщений\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    users_list = get_all_users()
    online_users = []
    offline_users = []
    
    for u in users_list:
        last = u["last_online"]
        if last:
            try:
                last_time = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
                if (now - last_time).seconds < 300:
                    online_users.append(u)
                else:
                    offline_users.append(u)
            except:
                offline_users.append(u)
        else:
            offline_users.append(u)
    
    text = f"🟢 *ОНЛАЙН ({len(online_users)}):*\n\n"
    for u in online_users[:20]:
        text += f"• {u['nickname'] or u['name']} ({get_rank_emoji(u['role'])} ранг {u['role']})\n"
    
    text += f"\n⚫ *ОФФЛАЙН ({len(offline_users)}):*\n\n"
    for u in offline_users[:10]:
        last = u["last_online"] or "Никогда"
        text += f"• {u['nickname'] or u['name']} — был {last}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check [ник]")
        return
    
    nickname = ' '.join(context.args).lower()
    users_list = get_all_users()
    found = None
    
    for u in users_list:
        if u["nickname"] and u["nickname"].lower() == nickname:
            found = u
            break
        elif u["name"].lower() == nickname:
            found = u
            break
        elif u["username"] and u["username"].lower() == nickname:
            found = u
            break
    
    if found:
        mod_text = ""
        if found["mod_role"] == 8:
            mod_text = " | 🛡️ Модер"
        elif found["mod_role"] == 9:
            mod_text = " | 👑 Зам"
        elif found["mod_role"] == 10:
            mod_text = " | 💎 Лидер"
        
        await update.message.reply_text(
            f"🔍 *РЕЗУЛЬТАТ ПОИСКА*\n\n"
            f"👤 Имя: {found['name']}\n"
            f"💫 Ник: {found['nickname'] or 'Нет'}\n"
            f"🎮 Ранг: {found['role']} ({get_rank_name(found['role'])}){mod_text}\n"
            f"⚠️ Варны: {found['warns']}/3\n"
            f"⭐ Репа: {found['rep']}\n"
            f"💬 Сообщений: {found['msgs']}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(f"❌ Пользователь с ником '{nickname}' не найден")

async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💋 Ответь на сообщение!")
        return
    
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("😳 Нельзя себя!")
        return
    
    await update.message.reply_text(f"💋 {user.first_name} поцеловал(а) {target.first_name}!")
    add_log(user.id, "kiss", target.id)

async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("🤗 Ответь на сообщение!")
        return
    
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("🤗 Обними кого-то!")
        return
    
    await update.message.reply_text(f"🤗 {user.first_name} обнял(а) {target.first_name}!")
    add_log(user.id, "hug", target.id)

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("👋 Ответь на сообщение!")
        return
    
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("😅 Нельзя себя!")
        return
    
    await update.message.reply_text(f"👋 {user.first_name} ударил(а) {target.first_name}!")
    add_log(user.id, "slap", target.id)

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
    
    outcomes = ["✅ Удачно!", "❌ Неудача!", "💀 Провал!", "✨ Получилось!", "🎯 Успех!"]
    await update.message.reply_text(f"🎲 *{update.effective_user.first_name}* {' '.join(context.args)}\n\n{random.choice(outcomes)}", parse_mode=ParseMode.MARKDOWN)

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    if users_list:
        target = random.choice(users_list)
        await update.message.reply_text(f"🏳️‍🌈 *Гей дня:* {target['name']}!", parse_mode=ParseMode.MARKDOWN)

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    if users_list:
        target = random.choice(users_list)
        await update.message.reply_text(f"🤡 *Клоун дня:* {target['name']}!", parse_mode=ParseMode.MARKDOWN)

async def wish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wishes = ["💰 Богатства", "❤️ Любви", "🔥 Успеха", "🌟 Счастья", "🍀 Удачи", "💪 Силы"]
    await update.message.reply_text(f"✨ *Предсказание:* {random.choice(wishes)} ✨", parse_mode=ParseMode.MARKDOWN)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /report [текст жалобы]")
        return
    
    user = update.effective_user
    reason = ' '.join(context.args)
    
    global report_id_counter
    report_id_counter += 1
    report_id = report_id_counter
    
    report_votes[report_id] = {
        "id": report_id,
        "user": user.id,
        "user_name": user.first_name,
        "reason": reason,
        "time": datetime.now(),
        "votes": {"approve": 0, "deny": 0, "offtopic": 0},
        "voters": []
    }
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Одобренно", callback_data=f"report_approve_{report_id}"),
         InlineKeyboardButton("❌ Отказанно", callback_data=f"report_deny_{report_id}"),
         InlineKeyboardButton("📝 Оффтоп", callback_data=f"report_offtopic_{report_id}")]
    ])
    
    sent = 0
    users_list = get_all_users()
    for u in users_list:
        if u["mod_role"] in [8, 9, 10]:
            try:
                await context.bot.send_message(u["user_id"], f"📢 *ЖАЛОБА #{report_id}*\n\n👤 От: {user.first_name}\n📝 {reason}", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
                sent += 1
            except:
                pass
    
    if sent > 0:
        await update.message.reply_text(f"✅ Жалоба #{report_id} отправлена {sent} модераторам!")
    else:
        await update.message.reply_text("❌ Нет доступных модераторов!")

async def handle_report_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    user = get_user(user_id)
    if not user or user["mod_role"] not in [8, 9, 10]:
        await query.answer("⛔ Только модераторы могут голосовать!", show_alert=True)
        return
    
    parts = data.split("_")
    if len(parts) < 3:
        await query.answer("Ошибка")
        return
    
    action = parts[1]
    report_id = int(parts[2])
    
    if report_id not in report_votes:
        await query.answer("❌ Жалоба уже обработана!", show_alert=True)
        await query.message.delete()
        return
    
    report = report_votes[report_id]
    
    if user_id in report["voters"]:
        await query.answer("❌ Вы уже голосовали!", show_alert=True)
        return
    
    report["voters"].append(user_id)
    
    if action == "approve":
        report["votes"]["approve"] += 1
        await query.answer("✅ Вы одобрили жалобу")
    elif action == "deny":
        report["votes"]["deny"] += 1
        await query.answer("❌ Вы отклонили жалобу")
    elif action == "offtopic":
        report["votes"]["offtopic"] += 1
        await query.answer("📝 Вы отметили жалобу как оффтоп")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ {report['votes']['approve']}", callback_data=f"report_approve_{report_id}"),
         InlineKeyboardButton(f"❌ {report['votes']['deny']}", callback_data=f"report_deny_{report_id}"),
         InlineKeyboardButton(f"📝 {report['votes']['offtopic']}", callback_data=f"report_offtopic_{report_id}")]
    ])
    
    try:
        await query.message.edit_reply_markup(reply_markup=keyboard)
    except:
        pass
    
    if report["votes"]["offtopic"] >= 3:
        report_cooldowns[report["user"]] = datetime.now() + timedelta(hours=6)
        await query.message.edit_text(
            f"📢 *ИТОГ ЖАЛОБЫ #{report_id}*\n\n"
            f"👤 От: {report['user_name']}\n"
            f"📝 Текст: {report['reason']}\n\n"
            f"⚖️ *РЕШЕНИЕ:* Жалоба признана оффтопом (3+ голосов)\n"
            f"⏱️ *НАКАЗАНИЕ:* {report['user_name']} не может отправлять жалобы 6 часов!",
            parse_mode=ParseMode.MARKDOWN
        )
        del report_votes[report_id]
    
    elif report["votes"]["deny"] >= 3:
        report_cooldowns[report["user"]] = datetime.now() + timedelta(hours=6)
        await query.message.edit_text(
            f"📢 *ИТОГ ЖАЛОБЫ #{report_id}*\n\n"
            f"👤 От: {report['user_name']}\n"
            f"📝 Текст: {report['reason']}\n\n"
            f"⚖️ *РЕШЕНИЕ:* Жалоба отклонена (3+ голосов)\n"
            f"⏱️ *НАКАЗАНИЕ:* {report['user_name']} не может отправлять жалобы 6 часов!",
            parse_mode=ParseMode.MARKDOWN
        )
        del report_votes[report_id]

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "rules":
        await rules(update, context)
    elif data == "profile":
        await profile(update, context)
    elif data == "top":
        await top(update, context)
    elif data == "weddings":
        await weddings_list(update, context)
    elif data.startswith("report_"):
        await handle_report_vote(update, context)
    elif data.startswith("wedding_accept"):
        parts = data.split("_")
        user1 = int(parts[2])
        user2 = int(parts[3])
        
        if query.from_user.id not in [user1, user2]:
            await query.answer("❌ Это не ваше предложение!", show_alert=True)
            return
        
        key = f"{user1}_{user2}"
        if key in pending_weddings:
            if query.from_user.id == user1:
                pending_weddings[key]["status1"] = True
            else:
                pending_weddings[key]["status2"] = True
            
            if pending_weddings[key]["status1"] and pending_weddings[key]["status2"]:
                add_wedding(user1, user2)
                await query.message.edit_text(
                    f"💍 *ПОЗДРАВЛЯЕМ!*\n\nБрак заключен! 🎉",
                    parse_mode=ParseMode.MARKDOWN
                )
                del pending_weddings[key]
            else:
                await query.answer("✅ Ожидание ответа...")
        else:
            await query.answer("❌ Предложение устарело!", show_alert=True)
    elif data.startswith("wedding_decline"):
        parts = data.split("_")
        user1 = int(parts[2])
        user2 = int(parts[3])
        key = f"{user1}_{user2}"
        if key in pending_weddings:
            del pending_weddings[key]
            await query.message.edit_text(f"💔 Брак отклонен!", parse_mode=ParseMode.MARKDOWN)

async def all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user = update.effective_user
    
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
    
    if update.message.text:
        violations = check_rule_violation(update.message.text)
        for violation_type, duration, reason in violations:
            await apply_punishment(update, user.id, duration, reason)
            try:
                await update.message.delete()
            except:
                pass
            return

# ========== ЗАПУСК ==========
async def main():
    print("🚀 ЗАПУСК NEVERMORE FAMILY BOT...")
    init_db()
    print("✅ БАЗА ДАННЫХ ГОТОВА!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_message))
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("setname", setname))
    app.add_handler(CommandHandler("setprefix", setprefix))
    
    app.add_handler(CommandHandler("wedding", wedding))
    app.add_handler(CommandHandler("divorce", divorce))
    app.add_handler(CommandHandler("weddings", weddings_list))
    
    app.add_handler(CommandHandler("plus", rep_plus))
    app.add_handler(CommandHandler("minus", rep_minus))
    
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
    
    app.add_handler(CommandHandler("warn", warn))
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
    
    app.add_handler(CommandHandler("setrole", setrole))
    app.add_handler(CommandHandler("role", role))
    app.add_handler(CommandHandler("giveaccess", giveaccess))
    app.add_handler(CommandHandler("nlist", nlist))
    app.add_handler(CommandHandler("grole", grole))
    app.add_handler(CommandHandler("gnick", gnick))
    app.add_handler(CommandHandler("roles", roles))
    app.add_handler(CommandHandler("all", all_command))
    
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, all_messages))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ БОТ УСПЕШНО ЗАПУЩЕН!")
    print("🤖 ВСЕ КОМАНДЫ ГОТОВЫ!")
    print("🔥 FAM NEVERMORE ONLINE!")
    
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
