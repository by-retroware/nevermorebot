import os
import random
import asyncio
import time
import logging
import io
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import asyncpg

# ========== НАСТРОЙКА ==========
logging.basicConfig(level=logging.INFO)

# ========== КОНФИГ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMINS = {int(x) for x in os.getenv("ADMINS", "5695593671,1784442476").split(",")}
FAMILY_NAME = "Nevermore"
FAMILY_LINK = "https://t.me/famnevermore"
AUTH_LINK = "https://t.me/famnevermore/19467"
RULES_LINK = "https://t.me/famnevermore/26"
NEWS_LINK = "https://t.me/famnevermore/5"

# ========== БАЗА ДАННЫХ ==========
async def get_db():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    conn = await get_db()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            name TEXT,
            username TEXT,
            nickname TEXT,
            role INTEGER DEFAULT 2,
            warns INTEGER DEFAULT 0,
            rep INTEGER DEFAULT 0,
            spouse_id BIGINT,
            prefix TEXT,
            last_online TEXT,
            msgs INTEGER DEFAULT 0,
            joined TEXT,
            mod_role INTEGER,
            monthly_msgs INTEGER DEFAULT 0
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS mutes (
            user_id BIGINT PRIMARY KEY,
            until TEXT,
            reason TEXT,
            moderator_id BIGINT
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            user_id BIGINT PRIMARY KEY,
            until TEXT,
            reason TEXT,
            moderator_id BIGINT
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS weddings (
            id SERIAL PRIMARY KEY,
            user1 BIGINT,
            user2 BIGINT,
            date TEXT,
            divorced INTEGER DEFAULT 0
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            action TEXT,
            target BIGINT,
            reason TEXT,
            time TEXT
        )
    """)
    await conn.close()
    print("✅ База данных PostgreSQL готова")

# ========== ФУНКЦИИ БД ==========
async def get_user(user_id):
    conn = await get_db()
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return dict(row) if row else None

async def add_user(user):
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

async def update_user(user_id, field, value):
    conn = await get_db()
    await conn.execute(f"UPDATE users SET {field} = $1 WHERE user_id = $2", value, user_id)
    await conn.close()

async def add_log(user_id, action, target=None, reason=None):
    conn = await get_db()
    await conn.execute(
        "INSERT INTO logs (user_id, action, target, reason, time) VALUES ($1, $2, $3, $4, $5)",
        user_id, action, target, reason, datetime.now().isoformat()
    )
    await conn.close()

async def get_all_users():
    conn = await get_db()
    rows = await conn.fetch("SELECT * FROM users")
    await conn.close()
    return [dict(row) for row in rows]

async def get_active_weddings():
    conn = await get_db()
    rows = await conn.fetch("SELECT * FROM weddings WHERE divorced = 0")
    await conn.close()
    return [dict(row) for row in rows]

async def add_wedding(u1, u2):
    conn = await get_db()
    await conn.execute(
        "INSERT INTO weddings (user1, user2, date) VALUES ($1, $2, $3)",
        u1, u2, datetime.now().isoformat()
    )
    await conn.execute("UPDATE users SET spouse_id = $1 WHERE user_id = $2", u2, u1)
    await conn.execute("UPDATE users SET spouse_id = $1 WHERE user_id = $2", u1, u2)
    await conn.close()

async def divorce_wedding(user_id):
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

async def add_mute(user_id, minutes, reason, mod_id):
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    conn = await get_db()
    await conn.execute(
        "INSERT INTO mutes (user_id, until, reason, moderator_id) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO UPDATE SET until = $2, reason = $3, moderator_id = $4",
        user_id, until, reason, mod_id
    )
    await conn.close()

async def remove_mute(user_id):
    conn = await get_db()
    await conn.execute("DELETE FROM mutes WHERE user_id = $1", user_id)
    await conn.close()

async def is_muted(user_id):
    conn = await get_db()
    row = await conn.fetchrow(
        "SELECT until FROM mutes WHERE user_id = $1 AND until > $2",
        user_id, datetime.now().isoformat()
    )
    await conn.close()
    return row is not None

async def add_ban(user_id, days, reason, mod_id):
    until = (datetime.now() + timedelta(days=days)).isoformat()
    conn = await get_db()
    await conn.execute(
        "INSERT INTO bans (user_id, until, reason, moderator_id) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO UPDATE SET until = $2, reason = $3, moderator_id = $4",
        user_id, until, reason, mod_id
    )
    await conn.close()

async def remove_ban(user_id):
    conn = await get_db()
    await conn.execute("DELETE FROM bans WHERE user_id = $1", user_id)
    await conn.close()

async def is_banned(user_id):
    conn = await get_db()
    row = await conn.fetchrow(
        "SELECT until FROM bans WHERE user_id = $1 AND until > $2",
        user_id, datetime.now().isoformat()
    )
    await conn.close()
    return row is not None

async def get_bans_list():
    conn = await get_db()
    rows = await conn.fetch(
        "SELECT * FROM bans WHERE until > $1", datetime.now().isoformat()
    )
    await conn.close()
    return [dict(row) for row in rows]

async def get_mutes_list():
    conn = await get_db()
    rows = await conn.fetch(
        "SELECT * FROM mutes WHERE until > $1", datetime.now().isoformat()
    )
    await conn.close()
    return [dict(row) for row in rows]

async def get_logs(limit=15):
    conn = await get_db()
    rows = await conn.fetch("SELECT * FROM logs ORDER BY id DESC LIMIT $1", limit)
    await conn.close()
    return [dict(row) for row in rows]

async def reset_monthly_stats():
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

async def is_moderator(user_id):
    user = await get_user(user_id)
    return user and user.get("mod_role") is not None and user["mod_role"] >= 8

async def get_user_id_from_input(input_str):
    input_str = input_str.strip()
    if input_str.startswith('@'):
        username = input_str[1:].lower()
        for u in await get_all_users():
            if u.get("username") and u["username"].lower() == username:
                return u["user_id"]
        return None
    try:
        return int(input_str)
    except:
        return None

# ========== ПРАВИЛА И ПРОВЕРКА НАРУШЕНИЙ ==========
RULES = """
📜 *ПРАВИЛА FAM NEVERMORE* 📜

2️⃣ *18+ контент* — запрещено! → мут 120 мин
3️⃣ *Упоминание родителей* — запрещено! → мут 120 мин
4️⃣ *Политика* — мут 60 мин
5️⃣ *Свастики и нацистская символика* — мут 60 мин
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
    await add_user(user)
    await add_log(user.id, "start")
    u = await get_user(user.id)
    keyboard = [[InlineKeyboardButton("📜 Правила", callback_data="rules")]]
    await update.message.reply_text(
        f"🔥 *ДОБРО ПОЖАЛОВАТЬ В FAM {FAMILY_NAME}!* 🔥\n\nПривет, {user.first_name}!\n🎮 Ранг: {get_rank_emoji(u['role'])} *{get_rank_name(u['role'])}*\n⭐ Репутация: {u['rep']}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 Используй /start для начала!")

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES, parse_mode=ParseMode.MARKDOWN)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not u:
        await add_user(user)
        u = await get_user(user.id)
    text = f"👤 *{u['name']}*\n⭐ Репутация: {u['rep']}\n🎮 Ранг: {get_rank_name(u['role'])}\n💫 Ник: {u.get('nickname') or 'Не установлен'}"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    await update.message.reply_text(f"👥 Участников: {len(users)}\n👑 Лидер: @{FAMILY_NAME}")

# ========== АВТОРИЗАЦИЯ ЧЕРЕЗ ФОРМУ ==========
async def auto_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    
    text = message.text.strip()
    keywords = ['Никнейм:', 'Ник:', 'Нижнейм:']
    if not any(kw in text for kw in keywords):
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
    
    u = await get_user(message.from_user.id)
    if u and u.get("nickname"):
        await message.reply_text(f"❌ Вы уже авторизованы! Ваш ник: {u['nickname']}")
        return
    
    existing = None
    for existing_user in await get_all_users():
        if existing_user.get("nickname") and existing_user["nickname"].lower() == nickname.lower():
            existing = existing_user
            break
    
    if existing:
        await message.reply_text(f"❌ Никнейм `{nickname}` уже занят!", parse_mode=ParseMode.MARKDOWN)
        return
    
    await add_user(message.from_user)
    await update_user(message.from_user.id, "nickname", nickname)
    await update_user(message.from_user.id, "role", rank)
    
    await message.reply_text(f"✅ *АВТОРИЗАЦИЯ УСПЕШНА!*\n👤 Ваш ник: {nickname}\n🎮 Ранг: {get_rank_name(rank)}", parse_mode=ParseMode.MARKDOWN)
    await add_log(message.from_user.id, "auto_auth", reason=f"{nickname} ({rank})")
    
    try:
        await message.delete()
    except:
        pass

# ========== МОДЕРАЦИЯ ==========
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    t = await get_user(target.id)
    if not t:
        await add_user(target)
        t = await get_user(target.id)
    new_warns = (t["warns"] or 0) + 1
    await update_user(target.id, "warns", new_warns)
    await update.message.reply_text(f"⚠️ *{target.first_name}* получил предупреждение! ({new_warns}/3)", parse_mode=ParseMode.MARKDOWN)
    await add_log(update.effective_user.id, "warn", target.id, reason)
    if new_warns >= 3:
        await add_mute(target.id, 1440, "Автоматический мут за 3 предупреждения", update.effective_user.id)
        await update.message.reply_text(f"🔇 {target.first_name} замучен на 1 день!")

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /unwarn [@username]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    u = await get_user(uid)
    new_warns = max(0, (u["warns"] or 0) - 1)
    await update_user(uid, "warns", new_warns)
    await update.message.reply_text(f"✅ Снято предупреждение! Теперь: {new_warns}/3")
    await add_log(update.effective_user.id, "unwarn", uid)

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    minutes = int(context.args[0]) if context.args else 60
    reason = ' '.join(context.args[1:]) or "Нарушение правил"
    await add_mute(target.id, minutes, reason, update.effective_user.id)
    await update.message.reply_text(f"🔇 *{target.first_name}* замучен на {minutes} минут!", parse_mode=ParseMode.MARKDOWN)
    await add_log(update.effective_user.id, "mute", target.id, f"{minutes}мин - {reason}")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    await remove_mute(target.id)
    await update.message.reply_text(f"🔊 *{target.first_name}* размучен!", parse_mode=ParseMode.MARKDOWN)
    await add_log(update.effective_user.id, "unmute", target.id)

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    await add_ban(target.id, 365, reason, update.effective_user.id)
    await update.message.reply_text(f"🔨 *{target.first_name}* забанен!", parse_mode=ParseMode.MARKDOWN)
    await add_log(update.effective_user.id, "ban", target.id, reason)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /unban [@username]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    await remove_ban(uid)
    await update.message.reply_text(f"🔓 Пользователь разбанен!")
    await add_log(update.effective_user.id, "unban", uid)

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if context.args:
        uid = await get_user_id_from_input(context.args[0])
        if uid:
            u = await get_user(uid)
            await update.message.reply_text(f"⚠️ {u['name']} имеет {u['warns']}/3 предупреждений")
    else:
        await update.message.reply_text("❌ /warns [@username]")

async def bans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    bans = await get_bans_list()
    if not bans:
        await update.message.reply_text("🔨 Нет банов")
        return
    text = "🔨 *Баны:*\n"
    for b in bans:
        u = await get_user(b["user_id"])
        text += f"• {u['name'] if u else b['user_id']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    mutes = await get_mutes_list()
    if not mutes:
        await update.message.reply_text("🔇 Нет мутов")
        return
    text = "🔇 *Муты:*\n"
    for m in mutes:
        u = await get_user(m["user_id"])
        text += f"• {u['name'] if u else m['user_id']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    logs = await get_logs(10)
    if not logs:
        await update.message.reply_text("Нет логов")
        return
    text = "📋 *Логи:*\n"
    for log in logs:
        u = await get_user(log["user_id"])
        text += f"• {u['name'] if u else log['user_id']}: {log['action']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
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
        await add_log(update.effective_user.id, "clear", reason=f"{deleted} сообщений")
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
    report_votes[rid] = {"user": update.effective_user.id, "reason": reason, "votes": {"a": 0, "d": 0}}
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅", callback_data=f"rep_a_{rid}"), InlineKeyboardButton("❌", callback_data=f"rep_d_{rid}")]])
    sent = 0
    for u in await get_all_users():
        if u.get("mod_role") in [8, 9, 10]:
            try:
                await context.bot.send_message(u["user_id"], f"📢 Жалоба #{rid}\nОт: {update.effective_user.first_name}\nТекст: {reason}", reply_markup=keyboard)
                sent += 1
            except:
                pass
    if sent > 0:
        await update.message.reply_text(f"✅ Жалоба #{rid} отправлена {sent} модераторам!")
        await add_log(update.effective_user.id, "report", reason=reason)
    else:
        await update.message.reply_text("❌ Нет доступных модераторов!")

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setname [@username] [ник]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    nickname = ' '.join(context.args[1:])[:50]
    await update_user(uid, "nickname", nickname)
    await update.message.reply_text(f"✅ Ник установлен!")
    await add_log(update.effective_user.id, "set_name", uid, nickname)

async def setnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setname(update, context)

async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setprefix [@username] [префикс]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    prefix = ' '.join(context.args[1:])[:20]
    await update_user(uid, "prefix", prefix)
    await update.message.reply_text(f"✅ Префикс установлен!")
    await add_log(update.effective_user.id, "set_prefix", uid, prefix)

# ========== АДМИНИСТРИРОВАНИЕ ==========
async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrole [@username] [2-10]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    role = int(context.args[1])
    await update_user(uid, "role", role)
    await update.message.reply_text(f"✅ Ранг изменён на {get_rank_name(role)}!")
    await add_log(update.effective_user.id, "set_role", uid, f"ранг {role}")

async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только лидер!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /role [@username] [0/8/9/10]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    mod_role = int(context.args[1])
    names = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}
    if mod_role == 0:
        await update_user(uid, "mod_role", None)
        await update.message.reply_text(f"✅ Модераторская роль снята!")
    else:
        await update_user(uid, "mod_role", mod_role)
        await update.message.reply_text(f"✅ Выдана роль: {names[mod_role]}!")
    await add_log(update.effective_user.id, "role", uid, f"роль {mod_role}")

async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await role(update, context)

async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = await get_all_users()
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
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = await get_all_users()
    text = "👑 *Модераторские роли:*\n"
    for u in users:
        if u.get("mod_role") in [8, 9, 10]:
            role_name = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}[u["mod_role"]]
            text += f"• {u.get('nickname') or u['name']} — {role_name}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = await get_all_users()
    mentions = [f"@{u['username']}" for u in users if u.get("username")]
    if mentions:
        await update.message.reply_text("🔔 *ВНИМАНИЕ!* 🔔\n" + ' '.join(mentions[:30]), parse_mode=ParseMode.MARKDOWN)
        await add_log(update.effective_user.id, "all_push")

async def setuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 3:
        await update.message.reply_text("❌ /setuser [@username] [ник] [ранг]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    nickname = context.args[1][:50]
    role = int(context.args[2])
    await update_user(uid, "nickname", nickname)
    await update_user(uid, "role", role)
    await update.message.reply_text(f"✅ Пользователь обновлён!\nНик: {nickname}\nРанг: {get_rank_name(role)}")
    await add_log(update.effective_user.id, "setuser", uid, f"ник:{nickname}, ранг:{role}")

async def delnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /delnick [@username]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    u = await get_user(uid)
    old_nick = u.get("nickname") or "Не был установлен"
    await update_user(uid, "nickname", None)
    await update.message.reply_text(f"✅ Ник удалён!")
    await add_log(update.effective_user.id, "delnick", uid, old_nick)

async def editnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setname(update, context)

async def setrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setrole(update, context)

# ========== КОМАНДЫ ДЛЯ СОЗДАТЕЛЯ ==========
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
/backup - Бэкап БД

⭐ *РЕПУТАЦИЯ:*
/takerep [@username] [кол-во] - Забрать репутацию
/resetrep [@username] - Сбросить репутацию

👤 *ПОЛЬЗОВАТЕЛИ:*
/resetuser [@username] - Полный сброс

🔧 *СИСТЕМНЫЕ:*
/stats - Статистика
/clearlogs - Очистить логи
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    users = await get_all_users()
    text = "📊 *ПОЛЬЗОВАТЕЛИ:*\n"
    for u in users[:20]:
        text += f"• {u.get('nickname') or u['name']} — ранг {u['role']}, репа {u['rep']}\n"
    text += f"\n📊 Всего: {len(users)}"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_mutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    mutes = await get_mutes_list()
    if not mutes:
        await update.message.reply_text("🔇 Нет мутов")
        return
    text = "🔇 *АКТИВНЫЕ МУТЫ:*\n"
    for m in mutes:
        u = await get_user(m["user_id"])
        text += f"• {u['name'] if u else m['user_id']} — до {m['until'][:16]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_bans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    bans = await get_bans_list()
    if not bans:
        await update.message.reply_text("🔨 Нет банов")
        return
    text = "🔨 *АКТИВНЫЕ БАНЫ:*\n"
    for b in bans:
        u = await get_user(b["user_id"])
        text += f"• {u['name'] if u else b['user_id']} — до {b['until'][:10]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_weddings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    weddings = await get_active_weddings()
    if not weddings:
        await update.message.reply_text("💔 Нет свадеб")
        return
    text = "💍 *АКТИВНЫЕ СВАДЬБЫ:*\n"
    for w in weddings:
        u1 = await get_user(w["user1"])
        u2 = await get_user(w["user2"])
        text += f"• {u1['name'] if u1 else w['user1']} + {u2['name'] if u2 else w['user2']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def sql_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /sql [запрос]")
        return
    query = ' '.join(context.args)
    try:
        conn = await get_db()
        if query.strip().upper().startswith('SELECT'):
            rows = await conn.fetch(query)
            if rows:
                text = "📊 *РЕЗУЛЬТАТ:*\n"
                for row in rows[:10]:
                    text += f"• {dict(row)}\n"
                await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("✅ Пусто")
        else:
            await conn.execute(query)
            await update.message.reply_text("✅ Выполнено!")
        await conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    users = await get_all_users()
    mutes = await get_mutes_list()
    bans = await get_bans_list()
    weddings = await get_active_weddings()
    logs = await get_logs(100)
    
    backup_text = f"# Бэкап NEVERMORE BOT\n# Дата: {datetime.now()}\n\n"
    backup_text += f"USERS ({len(users)}):\n" + "\n".join([str(u) for u in users]) + "\n\n"
    backup_text += f"MUTES ({len(mutes)}):\n" + "\n".join([str(m) for m in mutes]) + "\n\n"
    backup_text += f"BANS ({len(bans)}):\n" + "\n".join([str(b) for b in bans]) + "\n\n"
    backup_text += f"WEDDINGS ({len(weddings)}):\n" + "\n".join([str(w) for w in weddings]) + "\n\n"
    backup_text += f"LOGS ({len(logs)}):\n" + "\n".join([str(l) for l in logs])
    
    bio = io.BytesIO(backup_text.encode('utf-8'))
    bio.name = f"nevermore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    await update.message.reply_document(document=bio, caption="📦 Бэкап базы данных")
    await add_log(update.effective_user.id, "backup_db")

async def take_rep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /takerep [@username] [кол-во]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    amount = int(context.args[1])
    u = await get_user(uid)
    new_rep = max(0, (u["rep"] or 0) - amount)
    await update_user(uid, "rep", new_rep)
    await update.message.reply_text(f"💀 Забрано {amount} репутации! Теперь: {new_rep}⭐")
    await add_log(update.effective_user.id, "take_rep", uid, f"-{amount}")

async def reset_rep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /resetrep [@username]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    u = await get_user(uid)
    old_rep = u["rep"] or 0
    await update_user(uid, "rep", 0)
    await update.message.reply_text(f"🔄 Репутация сброшена! Было: {old_rep}⭐")
    await add_log(update.effective_user.id, "reset_rep", uid)

async def reset_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /resetuser [@username]")
        return
    uid = await get_user_id_from_input(context.args[0])
    if not uid:
        await update.message.reply_text("❌ Не найден!")
        return
    await update_user(uid, "nickname", None)
    await update_user(uid, "role", 2)
    await update_user(uid, "warns", 0)
    await update_user(uid, "rep", 0)
    await update_user(uid, "spouse_id", None)
    await update_user(uid, "prefix", None)
    await update_user(uid, "mod_role", None)
    await update.message.reply_text(f"🔄 *ВСЕ ДАННЫЕ СБРОШЕНЫ!*", parse_mode=ParseMode.MARKDOWN)
    await add_log(update.effective_user.id, "reset_user", uid)

async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    users = await get_all_users()
    mutes = await get_mutes_list()
    bans = await get_bans_list()
    weddings = await get_active_weddings()
    logs = await get_logs(1000)
    text = f"📊 *СТАТИСТИКА:*\n👥 Пользователей: {len(users)}\n🔇 Мутов: {len(mutes)}\n🔨 Банов: {len(bans)}\n💍 Свадеб: {len(weddings)}\n📋 Логов: {len(logs)}"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def clear_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    conn = await get_db()
    await conn.execute("DELETE FROM logs")
    await conn.close()
    await update.message.reply_text("🗑️ *Логи очищены!*", parse_mode=ParseMode.MARKDOWN)
    await add_log(update.effective_user.id, "clear_logs")

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
    res = await divorce_wedding(update.effective_user.id)
    if res:
        await update.message.reply_text(f"💔 *{update.effective_user.first_name}* развелся(ась)!", parse_mode=ParseMode.MARKDOWN)
        await add_log(update.effective_user.id, "divorce", res)
    else:
        await update.message.reply_text("❌ Вы не состоите в браке!")

async def weddings_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = await get_active_weddings()
    if not active:
        await update.message.reply_text("💔 Нет свадеб")
        return
    text = "💍 *АКТИВНЫЕ БРАКИ:*\n"
    for w in active:
        u1 = await get_user(w["user1"])
        u2 = await get_user(w["user2"])
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
    t = await get_user(target.id)
    if not t:
        await add_user(target)
        t = await get_user(target.id)
    new_rep = (t["rep"] or 0) + 1
    await update_user(target.id, "rep", new_rep)
    await update.message.reply_text(f"⭐ *{user.first_name}* дал +1 репутации *{target.first_name}*!", parse_mode=ParseMode.MARKDOWN)
    await add_log(user.id, "rep_plus", target.id)

async def minus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💀 Ответь на сообщение!")
        return
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя убавить репутацию себе!")
        return
    t = await get_user(target.id)
    if not t:
        await add_user(target)
        t = await get_user(target.id)
    new_rep = (t["rep"] or 0) - 1
    await update_user(target.id, "rep", new_rep)
    await update.message.reply_text(f"💀 *{user.first_name}* убавил -1 репутации *{target.first_name}*!", parse_mode=ParseMode.MARKDOWN)
    await add_log(user.id, "rep_minus", target.id)

# ========== РАЗВЛЕЧЕНИЯ ==========
async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💋 Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    await update.message.reply_text(f"💋 {update.effective_user.first_name} поцеловал(а) {target.first_name}!")
    await add_log(update.effective_user.id, "kiss", target.id)

async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("🤗 Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    await update.message.reply_text(f"🤗 {update.effective_user.first_name} обнял(а) {target.first_name}!")
    await add_log(update.effective_user.id, "hug", target.id)

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("👋 Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    await update.message.reply_text(f"👋 {update.effective_user.first_name} ударил(а) {target.first_name}!")
    await add_log(update.effective_user.id, "slap", target.id)

async def me_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /me [действие]")
        return
    await update.message.reply_text(f"* {update.effective_user.first_name} {' '.join(context.args)}")
    await add_log(update.effective_user.id, f"me: {' '.join(context.args)}")

async def try_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /try [действие]")
        return
    outcomes = ["✅ Удачно! 🎉", "❌ Неудача... 😔", "✨ Получилось! ✨", "💀 Полный провал!", "🎯 Успех!"]
    await update.message.reply_text(f"🎲 {update.effective_user.first_name} {' '.join(context.args)}\n{random.choice(outcomes)}")

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    if users:
        target = random.choice(users)
        await update.message.reply_text(f"🏳️‍🌈 *Гей дня:* {target['name']}!", parse_mode=ParseMode.MARKDOWN)

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    if users:
        target = random.choice(users)
        await update.message.reply_text(f"🤡 *Клоун дня:* {target['name']}!", parse_mode=ParseMode.MARKDOWN)

async def wish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wishes = ["💰 Богатства!", "❤️ Любви!", "🔥 Успеха!", "🌟 Исполнения мечт!", "🍀 Удачи!", "💪 Силы!"]
    await update.message.reply_text(f"✨ *Твоё предсказание:*\n{random.choice(wishes)}", parse_mode=ParseMode.MARKDOWN)

# ========== СТАТИСТИКА ==========
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = sorted(await get_all_users(), key=lambda x: x.get("monthly_msgs") or 0, reverse=True)[:5]
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
    for u in await get_all_users():
        if u.get("last_online"):
            try:
                last = datetime.fromisoformat(u["last_online"])
                if (now - last).seconds < 300:
                    online_list.append(u)
            except:
                pass
    text = f"🟢 *ОНЛАЙН ({len(online_list)}):*\n" + "\n".join([f"• {u.get('nickname') or u['name']} ({get_rank_emoji(u['role'])} ранг {u['role']})" for u in online_list[:20]])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check [@username]")
        return
    username = context.args[0].lower().replace('@', '')
    for u in await get_all_users():
        if u.get("username") and u["username"].lower() == username:
            await update.message.reply_text(f"🔍 {u.get('nickname') or u['name']} — ранг {u['role']}, репа {u['rep']}")
            return
        elif u.get("nickname") and u["nickname"].lower() == username:
            await update.message.reply_text(f"🔍 {u['name']} — ранг {u['role']}, репа {u['rep']}")
            return
    await update.message.reply_text("❌ Не найден")

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
            await add_wedding(u1, u2)
            await q.message.edit_text("💍 *ПОЗДРАВЛЯЕМ!* Брак заключен! 🎉", parse_mode=ParseMode.MARKDOWN)
            del pending_weddings[key]
    elif data.startswith("wed_decline"):
        await q.message.edit_text("💔 Брак отклонен!", parse_mode=ParseMode.MARKDOWN)

# ========== ПРИВЕТСТВИЕ ==========
async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for m in update.message.new_chat_members:
        if m.is_bot:
            continue
        await add_user(m)
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
    
    # Проверка на нарушения правил
    violations = check_rule_violation(text)
    for v in violations:
        await add_mute(user.id, v[1], f"Автоматический мут: {v[0]}", 0)
        try:
            await update.message.delete()
            await update.message.reply_text(f"🔇 {user.first_name}, нарушение правил! Мут {v[1]} минут.")
        except:
            pass
        return
    
    if await is_banned(user.id):
        try:
            await update.message.delete()
        except:
            pass
        return
    
    if await is_muted(user.id):
        try:
            await update.message.delete()
        except:
            pass
        return
    
    await add_user(user)

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 ЗАПУСК NEVERMORE FAMILY BOT...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация всех обработчиков
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_message))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("info", info))
    
    # Модерация
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
    
    # Администрирование
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
    
    # Команды создателя
    app.add_handler(CommandHandler("creator", creator_panel))
    app.add_handler(CommandHandler("checkdb", check_db))
    app.add_handler(CommandHandler("checkmutes", check_mutes))
    app.add_handler(CommandHandler("checkbans", check_bans))
    app.add_handler(CommandHandler("checkweddings", check_weddings))
    app.add_handler(CommandHandler("sql", sql_query))
    app.add_handler(CommandHandler("backup", backup_db))
    app.add_handler(CommandHandler("takerep", take_rep))
    app.add_handler(CommandHandler("resetrep", reset_rep))
    app.add_handler(CommandHandler("resetuser", reset_user))
    app.add_handler(CommandHandler("stats", bot_stats))
    app.add_handler(CommandHandler("clearlogs", clear_logs))
    
    # Свадьбы
    app.add_handler(CommandHandler("wedding", wedding))
    app.add_handler(CommandHandler("divorce", divorce))
    app.add_handler(CommandHandler("weddings", weddings_list))
    
    # Репутация
    app.add_handler(CommandHandler("plus", plus))
    app.add_handler(CommandHandler("minus", minus))
    
    # Развлечения
    app.add_handler(CommandHandler("kiss", kiss))
    app.add_handler(CommandHandler("hug", hug))
    app.add_handler(CommandHandler("slap", slap))
    app.add_handler(CommandHandler("me", me_action))
    app.add_handler(CommandHandler("try", try_action))
    app.add_handler(CommandHandler("gay", gay))
    app.add_handler(CommandHandler("clown", clown))
    app.add_handler(CommandHandler("wish", wish))
    
    # Статистика
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("online", online))
    app.add_handler(CommandHandler("check", check))
    
    # Авторизация и обработка сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_auth))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, all_messages))
    
    print("✅ ВСЕ ОБРАБОТЧИКИ ЗАРЕГИСТРИРОВАНЫ")
    print("✅ БОТ ГОТОВ К ЗАПУСКУ! 🔥")
    print("🔄 Запускаю polling...")
    
    app.run_polling()
