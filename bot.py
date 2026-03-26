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

# ========== БАЗА ДАННЫХ ==========
def get_db():
    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
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
            mod_role INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS mutes (
            user_id INTEGER PRIMARY KEY,
            until TEXT,
            reason TEXT,
            moderator_id INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            until TEXT,
            reason TEXT,
            moderator_id INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS weddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1 INTEGER,
            user2 INTEGER,
            date TEXT,
            divorced INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            target INTEGER,
            reason TEXT,
            time TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных создана")

# ========== ФУНКЦИИ БД ==========
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_user(user):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO users (user_id, name, username, last_online, joined)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            name = excluded.name,
            username = excluded.username,
            last_online = excluded.last_online,
            msgs = msgs + 1
    ''', (user.id, user.first_name, user.username, datetime.now().isoformat(), datetime.now().isoformat()))
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
    return rows

def get_active_weddings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM weddings WHERE divorced = 0")
    rows = c.fetchall()
    conn.close()
    return rows

def add_wedding(u1, u2):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO weddings (user1, user2, date) VALUES (?, ?, ?)",
              (u1, u2, datetime.now().isoformat()))
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
    return rows

def get_mutes_list():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM mutes WHERE until > ?", (datetime.now().isoformat(),))
    rows = c.fetchall()
    conn.close()
    return rows

def get_logs(limit=15):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

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

# ========== КОМАНДЫ ==========
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
    name = ' '.join(context.args)[:50]
    update_user(update.effective_user.id, "nickname", name)
    await update.message.reply_text(f"✅ Никнейм установлен: {name}")

async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /setprefix [префикс]")
        return
    prefix = ' '.join(context.args)[:20]
    update_user(update.effective_user.id, "prefix", prefix)
    await update.message.reply_text(f"✅ Префикс установлен: {prefix}")

async def wedding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💍 Ответь на сообщение!")
        return
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя на себе!")
        return
    for w in get_active_weddings():
        if w["user1"] == user.id or w["user2"] == user.id:
            await update.message.reply_text("❌ Вы уже в браке!")
            return
        if w["user1"] == target.id or w["user2"] == target.id:
            await update.message.reply_text("❌ Этот пользователь уже в браке!")
            return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да", callback_data=f"wed_accept_{user.id}_{target.id}"),
         InlineKeyboardButton("❌ Нет", callback_data=f"wed_decline_{user.id}_{target.id}")]
    ])
    await update.message.reply_text(
        f"💍 *{user.first_name}* предлагает брак *{target.first_name}*!\n\nУ вас 120 сек!",
        parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )
    pending_weddings[f"{user.id}_{target.id}"] = {"u1": user.id, "u2": target.id, "t": datetime.now(), "s1": False, "s2": False}

async def divorce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = divorce_wedding(update.effective_user.id)
    if res:
        await update.message.reply_text(f"💔 *{update.effective_user.first_name}* развелся(ась)!", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ Вы не в браке!")

async def weddings_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = get_active_weddings()
    if not active:
        await update.message.reply_text("💔 Нет свадеб")
        return
    text = "💍 *АКТИВНЫЕ БРАКИ* 💍\n\n"
    for w in active:
        u1 = get_user(w["user1"])
        u2 = get_user(w["user2"])
        text += f"❤️ {u1['nickname'] or u1['name']} + {u2['nickname'] or u2['name']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⭐ Ответь на сообщение!")
        return
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя себе!")
        return
    t = get_user(target.id)
    if not t:
        add_user(target)
        t = get_user(target.id)
    new_rep = (t["rep"] or 0) + 1
    update_user(target.id, "rep", new_rep)
    await update.message.reply_text(f"⭐ *{user.first_name}* +1 репутации *{target.first_name}*!\nТеперь: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)

async def minus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💀 Ответь на сообщение!")
        return
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя себе!")
        return
    t = get_user(target.id)
    if not t:
        add_user(target)
        t = get_user(target.id)
    new_rep = (t["rep"] or 0) - 1
    update_user(target.id, "rep", new_rep)
    await update.message.reply_text(f"💀 *{user.first_name}* -1 репутации *{target.first_name}*!\nТеперь: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    mod, target = update.effective_user, update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение"
    t = get_user(target.id)
    if not t:
        add_user(target)
        t = get_user(target.id)
    new_warns = (t["warns"] or 0) + 1
    update_user(target.id, "warns", new_warns)
    await update.message.reply_text(f"⚠️ *{target.first_name}* получил варн!\n📝 {reason}\n⚠️ {new_warns}/3", parse_mode=ParseMode.MARKDOWN)
    await notify_admins(context, f"⚠️ *ВЫДАН ВАРН*\n👤 {mod.first_name}\n🔨 {target.first_name}\n📝 {reason}\n⚠️ {new_warns}/3")
    if new_warns >= 3:
        add_mute(target.id, 1440, "Автомут за 3 варна", mod.id)
        await update.message.reply_text(f"🔇 {target.first_name} замучен на 1 день!")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    mod, target = update.effective_user, update.message.reply_to_message.from_user
    dur = context.args[0] if context.args else "60"
    reason = ' '.join(context.args[1:]) or "Нарушение"
    try:
        minutes = int(dur)
    except:
        minutes = 60
    add_mute(target.id, minutes, reason, mod.id)
    await update.message.reply_text(f"🔇 *{target.first_name}* замучен на {minutes} мин!\n📝 {reason}", parse_mode=ParseMode.MARKDOWN)
    await notify_admins(context, f"🔇 *ВЫДАН МУТ*\n👤 {mod.first_name}\n🔨 {target.first_name}\n⏱️ {minutes} мин\n📝 {reason}")

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

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    mod, target = update.effective_user, update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение"
    add_ban(target.id, 365, reason, mod.id)
    await update.message.reply_text(f"🔨 *{target.first_name}* забанен!\n📝 {reason}", parse_mode=ParseMode.MARKDOWN)
    await notify_admins(context, f"🔨 *ВЫДАН БАН*\n👤 {mod.first_name}\n🔨 {target.first_name}\n📝 {reason}")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
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

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if context.args:
        uid = get_user_id_from_input(context.args[0])
        if uid:
            u = get_user(uid)
            if u:
                await update.message.reply_text(f"⚠️ *{u['name']}* имеет {u['warns']}/3 варнов", parse_mode=ParseMode.MARKDOWN)
                return
    await update.message.reply_text("❌ Пользователь не найден")

async def bans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    lst = get_bans_list()
    if not lst:
        await update.message.reply_text("🔨 Нет банов")
        return
    text = "🔨 *Активные баны:*\n\n"
    for b in lst:
        u = get_user(b["user_id"])
        name = u["nickname"] or u["name"] if u else str(b["user_id"])
        text += f"• {name} — до {b['until'][:10]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    lst = get_mutes_list()
    if not lst:
        await update.message.reply_text("🔇 Нет мутов")
        return
    text = "🔇 *Активные муты:*\n\n"
    for m in lst:
        u = get_user(m["user_id"])
        name = u["nickname"] or u["name"] if u else str(m["user_id"])
        text += f"• {name} — до {m['until'][:16]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
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
                msgs = await update.message.chat.get_messages(i+1)
                await msgs.delete()
            except:
                pass
        msg = await update.message.reply_text(f"✅ Очищено {amount} сообщений")
        await asyncio.sleep(3)
        await msg.delete()
    except:
        pass

async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrole [@username] [2-10]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    if role < 2 or role > 10:
        await update.message.reply_text("❌ Роль 2-10")
        return
    update_user(uid, "role", role)
    u = get_user(uid)
    await update.message.reply_text(f"✅ *{u['name']}* получил ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)

async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    if user_id not in ADMINS and (not u or u["mod_role"] != 10):
        await update.message.reply_text("⛔ Только лидер!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /role [@username] [0-10]\n0-снять, 8-модер, 9-зам, 10-лидер")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        mod_role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    if mod_role not in [0,8,9,10]:
        await update.message.reply_text("❌ Роль 0,8,9,10")
        return
    names = {8:"🛡️ Модератор",9:"👑 Зам. лидера",10:"💎 Лидер"}
    if mod_role == 0:
        update_user(uid, "mod_role", None)
        await update.message.reply_text(f"✅ У *{get_user(uid)['name']}* снята роль")
    else:
        update_user(uid, "mod_role", mod_role)
        await update.message.reply_text(f"✅ *{get_user(uid)['name']}* получил роль: {names[mod_role]}", parse_mode=ParseMode.MARKDOWN)

async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await role(update, context)

async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users_list = get_all_users()
    text = "📋 *СПИСОК УЧАСТНИКОВ*\n\n"
    for u in users_list[:50]:
        mod = ""
        if u["mod_role"] == 8:
            mod = " [Мод]"
        elif u["mod_role"] == 9:
            mod = " [Зам]"
        elif u["mod_role"] == 10:
            mod = " [Лид]"
        text += f"• {u['nickname'] or u['name']} ({u['user_id']}){mod} — ранг {u['role']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def grole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /grole [@username] [0-10]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    if role < 0 or role > 10:
        await update.message.reply_text("❌ Роль 0-10")
        return
    if role == 0:
        update_user(uid, "role", 2)
        await update.message.reply_text(f"✅ У *{get_user(uid)['name']}* роль сброшена")
    else:
        update_user(uid, "role", role)
        await update.message.reply_text(f"✅ *{get_user(uid)['name']}* получил ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)

async def gnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /gnick [@username] [ник]")
        return
    uid = get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    nick = ' '.join(context.args[1:])[:50]
    update_user(uid, "nickname", nick)
    await update.message.reply_text(f"✅ *{get_user(uid)['name']}* получил ник: {nick}", parse_mode=ParseMode.MARKDOWN)

async def roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users_list = get_all_users()
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
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    mentions = []
    for u in get_all_users():
        if u["username"]:
            mentions.append(f"@{u['username']}")
        else:
            mentions.append(u['name'])
    if mentions:
        text = "🔔 *ВНИМАНИЕ! ОБЩЕЕ СОБРАНИЕ!* 🔔\n\n" + ' '.join(mentions[:50])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = sorted(get_all_users(), key=lambda x: x["msgs"] or 0, reverse=True)[:10]
    text = "📊 *ТОП ПО СООБЩЕНИЯМ* 📊\n\n"
    for i, u in enumerate(users_list, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {u['nickname'] or u['name']} — {u['msgs']} сообщений\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    online_u, offline_u = [], []
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
        text += f"• {u['nickname'] or u['name']} ({get_rank_emoji(u['role'])} ранг {u['role']})\n"
    text += f"\n⚫ *ОФФЛАЙН ({len(offline_u)}):*\n\n"
    for u in offline_u[:10]:
        last = u["last_online"][:16] if u["last_online"] else "Никогда"
        text += f"• {u['nickname'] or u['name']} — был {last}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check [ник]")
        return
    nick = ' '.join(context.args).lower()
    found = None
    for u in get_all_users():
        if (u["nickname"] and u["nickname"].lower() == nick) or (u["name"].lower() == nick) or (u["username"] and u["username"].lower() == nick):
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
            f"🔍 *РЕЗУЛЬТАТ*\n\n👤 {found['name']}\n💫 Ник: {found['nickname'] or 'Нет'}\n🎮 Ранг: {found['role']} ({get_rank_name(found['role'])}){mod}\n⚠️ Варны: {found['warns']}/3\n⭐ Репа: {found['rep']}\n💬 Сообщений: {found['msgs']}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(f"❌ {nick} не найден")

async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💋 Ответь на сообщение!")
        return
    u, t = update.effective_user, update.message.reply_to_message.from_user
    if u.id == t.id:
        await update.message.reply_text("😳 Нельзя себя!")
        return
    await update.message.reply_text(f"💋 {u.first_name} поцеловал(а) {t.first_name}!")

async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("🤗 Ответь на сообщение!")
        return
    u, t = update.effective_user, update.message.reply_to_message.from_user
    if u.id == t.id:
        await update.message.reply_text("🤗 Обними кого-то!")
        return
    await update.message.reply_text(f"🤗 {u.first_name} обнял(а) {t.first_name}!")

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("👋 Ответь на сообщение!")
        return
    u, t = update.effective_user, update.message.reply_to_message.from_user
    if u.id == t.id:
        await update.message.reply_text("😅 Нельзя себя!")
        return
    await update.message.reply_text(f"👋 {u.first_name} ударил(а) {t.first_name}!")

async def me_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /me [действие]")
        return
    await update.message.reply_text(f"* {update.effective_user.first_name} {' '.join(context.args)}")

async def try_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /try [действие]")
        return
    outcomes = ["✅ Удачно!", "❌ Неудача!", "💀 Провал!", "✨ Получилось!", "🎯 Успех!"]
    await update.message.reply_text(f"🎲 *{update.effective_user.first_name}* {' '.join(context.args)}\n\n{random.choice(outcomes)}", parse_mode=ParseMode.MARKDOWN)

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    if users_list:
        await update.message.reply_text(f"🏳️‍🌈 *Гей дня:* {random.choice(users_list)['name']}!", parse_mode=ParseMode.MARKDOWN)

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = get_all_users()
    if users_list:
        await update.message.reply_text(f"🤡 *Клоун дня:* {random.choice(users_list)['name']}!", parse_mode=ParseMode.MARKDOWN)

async def wish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wishes = ["💰 Богатства", "❤️ Любви", "🔥 Успеха", "🌟 Счастья", "🍀 Удачи", "💪 Силы"]
    await update.message.reply_text(f"✨ *Предсказание:* {random.choice(wishes)} ✨", parse_mode=ParseMode.MARKDOWN)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /report [текст]")
        return
    user = update.effective_user
    reason = ' '.join(context.args)
    global report_id_counter
    report_id_counter += 1
    rid = report_id_counter
    report_votes[rid] = {"id": rid, "user": user.id, "name": user.first_name, "reason": reason, "time": datetime.now(), "votes": {"a":0,"d":0,"o":0}, "voters": []}
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Одобренно", callback_data=f"rep_a_{rid}"),
         InlineKeyboardButton("❌ Отказанно", callback_data=f"rep_d_{rid}"),
         InlineKeyboardButton("📝 Оффтоп", callback_data=f"rep_o_{rid}")]
    ])
    sent = 0
    for u in get_all_users():
        if u["mod_role"] in [8,9,10]:
            try:
                await context.bot.send_message(u["user_id"], f"📢 *ЖАЛОБА #{rid}*\n👤 {user.first_name}\n📝 {reason}", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
                sent += 1
            except:
                pass
    await update.message.reply_text(f"✅ Жалоба #{rid} отправлена {sent} модераторам!")

async def handle_report_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    u = get_user(uid)
    if not u or u["mod_role"] not in [8,9,10]:
        await q.answer("⛔ Только модераторы!", show_alert=True)
        return
    parts = data.split("_")
    action, rid = parts[1], int(parts[2])
    if rid not in report_votes:
        await q.answer("❌ Уже обработано!", show_alert=True)
        await q.message.delete()
        return
    r = report_votes[rid]
    if uid in r["voters"]:
        await q.answer("❌ Уже голосовали!", show_alert=True)
        return
    r["voters"].append(uid)
    if action == "a":
        r["votes"]["a"] += 1
    elif action == "d":
        r["votes"]["d"] += 1
    else:
        r["votes"]["o"] += 1
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ {r['votes']['a']}", callback_data=f"rep_a_{rid}"),
         InlineKeyboardButton(f"❌ {r['votes']['d']}", callback_data=f"rep_d_{rid}"),
         InlineKeyboardButton(f"📝 {r['votes']['o']}", callback_data=f"rep_o_{rid}")]
    ])
    await q.message.edit_reply_markup(reply_markup=kb)
    if r["votes"]["o"] >= 3 or r["votes"]["d"] >= 3:
        report_cooldowns[r["user"]] = datetime.now() + timedelta(hours=6)
        await q.message.edit_text(f"📢 *ИТОГ ЖАЛОБЫ #{rid}*\n👤 {r['name']}\n📝 {r['reason']}\n\n⚖️ Жалоба {'отклонена' if r['votes']['d']>=3 else 'признана оффтопом'}!\n⏱️ {r['name']} не может жаловаться 6 часов!", parse_mode=ParseMode.MARKDOWN)
        del report_votes[rid]

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
            await q.answer("❌ Не ваше!", show_alert=True)
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
                await q.answer("✅ Ожидание...")
        else:
            await q.answer("❌ Устарело!", show_alert=True)
    elif data.startswith("wed_decline"):
        parts = data.split("_")
        u1, u2 = int(parts[2]), int(parts[3])
        key = f"{u1}_{u2}"
        if key in pending_weddings:
            del pending_weddings[key]
            await q.message.edit_text("💔 Брак отклонен!", parse_mode=ParseMode.MARKDOWN)

async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for m in update.message.new_chat_members:
        if m.is_bot:
            continue
        add_user(m)
        text = f"""
👋 *@{m.username or m.first_name}*, добро пожаловать в *FAM {FAMILY_NAME}*!

📝 Напиши ник в авторизацию в течение 24 часов!
📖 Правила: {RULES_LINK}
🔑 Авторизация: {AUTH_LINK}

*Приятного общения!* ❤️
"""
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    if is_banned(user.id) or is_muted(user.id):
        try:
            await update.message.delete()
        except:
            pass
        return
    add_user(user)
    if update.message.text:
        for v in check_rule_violation(update.message.text):
            await apply_punishment(update, user.id, v[1], v[2])
            try:
                await update.message.delete()
            except:
                pass
            return

async def main():
    print("🚀 ЗАПУСК NEVERMORE FAMILY BOT...")
    init_db()
    print("✅ БАЗА ДАННЫХ SQLite ГОТОВА!")
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
    print("✅ БОТ ЗАПУЩЕН! 🔥 FAM NEVERMORE ONLINE!")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
