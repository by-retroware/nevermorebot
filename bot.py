import os
import random
import asyncio
import time
import threading
import logging
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
AUTH_LINK = "https://t.me/famnevermore/19467"
RULES_LINK = "https://t.me/famnevermore/26"
NEWS_LINK = "https://t.me/famnevermore/5"

# Проверка переменных
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не установлен!")

# ========== БАЗА ДАННЫХ ==========
async def get_db():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    try:
        conn = await get_db()
        print("✅ Подключение к PostgreSQL установлено")
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")

# ========== ФУНКЦИИ БД (АСИНХРОННЫЕ) ==========
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

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def is_moderator(user):
    return user and user["mod_role"] is not None and user["mod_role"] >= 8

def get_rank_name(role):
    ranks = {
        2: "Новичок", 3: "Любитель скорости", 4: "Образованный",
        5: "Невермор", 6: "Шарющий", 7: "Барыга",
        8: "Премиум", 9: "Зам. лидера", 10: "Лидер"
    }
    return ranks.get(role, "Новичок")

def get_rank_emoji(role):
    emojis = {2: "😭", 3: "🏎", 4: "💻", 5: "🎧", 6: "📖", 7: "😎", 8: "🤩", 9: "👑", 10: "💎"}
    return emojis.get(role, "😭")

def get_user_id_from_input(input_str, users):
    input_str = input_str.strip()
    if input_str.startswith('@'):
        username = input_str[1:].lower()
        for u in users:
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

2️⃣ *18+ контент* — запрещено! → мут 120 мин
3️⃣ *Упоминание родителей* — запрещено! → мут 120 мин
4️⃣ *Слив личных данных* — бан
5️⃣ *Уважение к старшим по рангу* — обязательно
6️⃣ *Доксинг, сваты, угрозы* — бан
7️⃣ *Политика* — мут 60 мин
8️⃣ *Выдавать себя за лидера/зама* — бан
9️⃣ *Угрозы баном/киком* — мут
🔟 *Свастики и нацистская символика* — мут 60 мин
"""

def check_rule_violation(text):
    text_lower = text.lower()
    violations = []
    if any(w in text_lower for w in ['порно', 'секс', '18+', 'голый']):
        violations.append(("adult", 120, "мут 120 минут за 18+ контент"))
    if any(w in text_lower for w in ['мать', 'отец', 'родители', 'мама', 'папа']):
        violations.append(("parent", 120, "мут 120 минут за упоминание родителей"))
    if any(w in text_lower for w in ['путин', 'зеленский', 'политика']):
        violations.append(("politics", 60, "мут 60 минут за политику"))
    return violations

async def apply_punishment(update, user_id, duration, reason):
    await add_mute(user_id, duration, reason, 0)
    try:
        user = await update.message.chat.get_member(user_id)
        await update.message.reply_text(f"🔇 {user.user.first_name}, {reason}", parse_mode=ParseMode.MARKDOWN)
    except:
        pass
    await add_log(0, "auto_mute", user_id, reason)

async def notify_moderators(context, text):
    for u in await get_all_users():
        if u["mod_role"] and u["mod_role"] >= 8:
            try:
                await context.bot.send_message(u["user_id"], text, parse_mode=ParseMode.MARKDOWN)
            except:
                pass

# ========== КОМАНДЫ ==========
pending_weddings = {}
report_votes = {}
report_id_counter = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_user(user)
    await add_log(user.id, "start")
    u = await get_user(user.id)
    
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
    user_id = update.effective_user.id
    is_creator = user_id in ADMINS
    
    help_text = """
🔥 *FAM NEVERMORE - КОМАНДЫ* 🔥

👤 /profile - Профиль | /info - Инфо о семье
💍 /wedding - Предложить брак | /divorce - Развестись | /weddings - Список свадеб
⭐ /plus - +1 репутации | /minus - -1 репутации
🎮 /kiss, /hug, /slap, /me, /try, /gay, /clown, /wish
📊 /top, /online, /check
🔨 /warn, /unwarn, /mute, /unmute, /ban, /unban, /warns, /bans, /mutelist, /logs, /clear, /report, /setname, /setprefix
👑 /setrole, /role, /giveaccess, /nlist, /grole, /roles, /all, /editnick, /setrank, /delnick, /setnick
📜 /rules
"""
    
    if is_creator:
        help_text += "\n👑 *ДЛЯ СОЗДАТЕЛЯ*\n/checkdb, /checkmutes, /checkbans, /checkweddings, /sql, /backup, /takerep, /resetrep, /resetuser, /stats, /creator"
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES, parse_mode=ParseMode.MARKDOWN)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not u:
        await add_user(user)
        u = await get_user(user.id)
    
    spouse_name = "Нет"
    for w in await get_active_weddings():
        if w["user1"] == user.id or w["user2"] == user.id:
            spouse_id = w["user1"] if w["user2"] == user.id else w["user2"]
            spouse = await get_user(spouse_id)
            if spouse:
                spouse_name = spouse["nickname"] or spouse["name"]
    
    await update.message.reply_text(
        f"<b>👤 ПРОФИЛЬ</b>\n\n"
        f"👤 Имя: <b>{u['name']}</b>\n"
        f"💫 Никнейм: {u['nickname'] or 'Не установлен'}\n"
        f"🎮 Ранг: <b>{get_rank_name(u['role'])}</b>\n"
        f"⭐ Репутация: <b>{u['rep']}</b>\n"
        f"⚠️ Варны: {u['warns']}/3\n"
        f"💬 Сообщений: {u['msgs']}\n"
        f"💍 Супруг(а): {spouse_name}",
        parse_mode=ParseMode.HTML
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = await get_all_users()
    leader = None
    for u in users_list:
        if u["mod_role"] == 10:
            leader = u
            break
    leader_text = f"@{leader['username'] or leader['name']}" if leader else "Не указан"
    await update.message.reply_text(
        f"ℹ️ *ИНФОРМАЦИЯ О СЕМЬЕ {FAMILY_NAME}*\n\n"
        f"👑 Лидер: {leader_text}\n"
        f"👥 Участников: {len(users_list)}\n\n"
        f"📜 Правила: {RULES_LINK}\n"
        f"🔑 Авторизация: {AUTH_LINK}",
        parse_mode=ParseMode.MARKDOWN
    )

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
    pending_weddings[f"{user.id}_{target.id}"] = {"u1": user.id, "u2": target.id, "s1": False, "s2": False}

async def divorce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = await divorce_wedding(update.effective_user.id)
    await update.message.reply_text(f"💔 *{update.effective_user.first_name}* развелся!" if res else "❌ Вы не в браке!", parse_mode=ParseMode.MARKDOWN)

async def weddings_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = await get_active_weddings()
    if not active:
        await update.message.reply_text("💔 Нет свадеб")
        return
    text = "💍 *АКТИВНЫЕ БРАКИ*\n\n"
    for w in active:
        u1 = await get_user(w["user1"])
        u2 = await get_user(w["user2"])
        text += f"❤️ {(u1['nickname'] or u1['name']) if u1 else w['user1']} + {(u2['nickname'] or u2['name']) if u2 else w['user2']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== РЕПУТАЦИЯ ==========
async def plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⭐ Ответь на сообщение!")
        return
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя себе!")
        return
    t = await get_user(target.id)
    if not t:
        await add_user(target)
        t = await get_user(target.id)
    new_rep = (t["rep"] or 0) + 1
    await update_user(target.id, "rep", new_rep)
    await update.message.reply_text(f"⭐ *{user.first_name}* дал +1 *{target.first_name}*! Теперь: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)

async def minus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💀 Ответь на сообщение!")
        return
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя себе!")
        return
    t = await get_user(target.id)
    if not t:
        await add_user(target)
        t = await get_user(target.id)
    new_rep = (t["rep"] or 0) - 1
    await update_user(target.id, "rep", new_rep)
    await update.message.reply_text(f"💀 *{user.first_name}* убавил -1 *{target.first_name}*! Теперь: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)

# ========== МОДЕРАЦИЯ ==========
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
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
    await update.message.reply_text(f"⚠️ *{target.first_name}* получил предупреждение! Причина: {reason}\n⚠️ {new_warns}/3", parse_mode=ParseMode.MARKDOWN)
    if new_warns >= 3:
        await add_mute(target.id, 1440, "Автоматический мут за 3 предупреждения", user.id)
        await update.message.reply_text(f"🔇 {target.first_name} замучен на 1 день!")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    dur = context.args[0] if context.args else "60"
    reason = ' '.join(context.args[1:]) or "Нарушение правил"
    try:
        minutes = int(dur)
    except:
        minutes = 60
    await add_mute(target.id, minutes, reason, user.id)
    await update.message.reply_text(f"🔇 *{target.first_name}* замучен на {minutes} мин! Причина: {reason}", parse_mode=ParseMode.MARKDOWN)

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    await remove_mute(target.id)
    await update.message.reply_text(f"🔊 *{target.first_name}* размучен!", parse_mode=ParseMode.MARKDOWN)

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    await add_ban(target.id, 365, reason, user.id)
    await update.message.reply_text(f"🔨 *{target.first_name}* забанен! Причина: {reason}", parse_mode=ParseMode.MARKDOWN)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /unban @username")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    await remove_ban(uid)
    await update.message.reply_text(f"🔓 Пользователь разбанен!")

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if context.args:
        users = await get_all_users()
        uid = get_user_id_from_input(context.args[0], users)
        if uid:
            u = await get_user(uid)
            if u:
                await update.message.reply_text(f"⚠️ *{u['name']}* имеет {u['warns']}/3 предупреждений", parse_mode=ParseMode.MARKDOWN)
                return
    await update.message.reply_text("❌ Пользователь не найден")

async def bans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    lst = await get_bans_list()
    if not lst:
        await update.message.reply_text("🔨 Нет активных банов")
        return
    text = "🔨 *Активные баны:*\n\n"
    for b in lst:
        u = await get_user(b["user_id"])
        name = u["nickname"] or u["name"] if u else str(b["user_id"])
        text += f"• {name} — до {b['until'][:10]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    lst = await get_mutes_list()
    if not lst:
        await update.message.reply_text("🔇 Нет активных мутов")
        return
    text = "🔇 *Активные муты:*\n\n"
    for m in lst:
        u = await get_user(m["user_id"])
        name = u["nickname"] or u["name"] if u else str(m["user_id"])
        text += f"• {name} — до {m['until'][:16]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    lst = await get_logs(15)
    if not lst:
        await update.message.reply_text("Нет логов")
        return
    text = "📋 *Последние действия:*\n\n"
    for log in lst:
        u = await get_user(log["user_id"])
        name = u["nickname"] or u["name"] if u else str(log["user_id"])
        text += f"• {log['time'][:16]} — {name}: {log['action']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /clear 10")
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
    except:
        pass

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setname @username Ник")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    nickname = ' '.join(context.args[1:])[:50]
    await update_user(uid, "nickname", nickname)
    target = await get_user(uid)
    await update.message.reply_text(f"✅ *{target['name']}* получил ник: {nickname}", parse_mode=ParseMode.MARKDOWN)

async def setnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await setname(update, context)

async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setprefix @username [префикс]")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    prefix = ' '.join(context.args[1:])[:20]
    await update_user(uid, "prefix", prefix)
    target = await get_user(uid)
    await update.message.reply_text(f"✅ *{target['name']}* получил префикс: {prefix}", parse_mode=ParseMode.MARKDOWN)

async def unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if not context.args:
        await update.message.reply_text("❌ /unwarn @username")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    target = await get_user(uid)
    new_warns = max(0, (target["warns"] or 0) - 1)
    await update_user(uid, "warns", new_warns)
    await update.message.reply_text(f"✅ *{target['name']}* снято предупреждение! Теперь: {new_warns}/3", parse_mode=ParseMode.MARKDOWN)

async def giverep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /giverep @username кол-во")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    target = await get_user(uid)
    new_rep = (target["rep"] or 0) + amount
    await update_user(uid, "rep", new_rep)
    await update.message.reply_text(f"⭐ *{target['name']}* получил +{amount} репутации! Теперь: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)

# ========== СТАТИСТИКА ==========
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    users_list = sorted(users, key=lambda x: x["monthly_msgs"] or 0, reverse=True)[:5]
    if not users_list:
        await update.message.reply_text("📊 Нет данных")
        return
    text = "📊 *ТОП МЕСЯЦА*\n\n"
    for i, u in enumerate(users_list, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {u['nickname'] or u['name']} — {u['monthly_msgs']} сообщений\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    users = await get_all_users()
    online_u = []
    for u in users:
        if u["last_online"]:
            try:
                if (now - datetime.fromisoformat(u["last_online"])).seconds < 300:
                    online_u.append(u)
            except:
                pass
    text = f"🟢 *ОНЛАЙН ({len(online_u)}):*\n"
    for u in online_u[:20]:
        text += f"• @{u['username'] or u['name']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check @username")
        return
    username = context.args[0].replace('@', '').lower()
    users = await get_all_users()
    found = None
    for u in users:
        if u["username"] and u["username"].lower() == username:
            found = u
            break
        elif u["nickname"] and u["nickname"].lower() == username:
            found = u
            break
    if found:
        await update.message.reply_text(
            f"🔍 *{found['nickname'] or found['name']}*\n"
            f"🎮 Ранг: {found['role']}\n"
            f"⭐ Репутация: {found['rep']}\n"
            f"⚠️ Варны: {found['warns']}/3",
            parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ Не найден")

# ========== РАЗВЛЕЧЕНИЯ ==========
async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💋 Ответь на сообщение!")
        return
    user, target = update.effective_user, update.message.reply_to_message.from_user
    await update.message.reply_text(f"💋 {user.first_name} поцеловал(а) {target.first_name}!")

async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("🤗 Ответь на сообщение!")
        return
    user, target = update.effective_user, update.message.reply_to_message.from_user
    await update.message.reply_text(f"🤗 {user.first_name} обнял(а) {target.first_name}!")

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("👋 Ответь на сообщение!")
        return
    user, target = update.effective_user, update.message.reply_to_message.from_user
    await update.message.reply_text(f"👋 {user.first_name} ударил(а) {target.first_name}!")

async def me_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /me действие")
        return
    await update.message.reply_text(f"* {update.effective_user.first_name} {' '.join(context.args)}")

async def try_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /try действие")
        return
    outcomes = ["✅ Удачно!", "❌ Неудача!", "💀 Провал!", "✨ Получилось!", "🎯 Успех!"]
    await update.message.reply_text(f"🎲 {update.effective_user.first_name} пытается {' '.join(context.args)}\n{random.choice(outcomes)}", parse_mode=ParseMode.MARKDOWN)

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    if users:
        await update.message.reply_text(f"🏳️‍🌈 *Гей дня:* {random.choice(users)['name']}!", parse_mode=ParseMode.MARKDOWN)

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    if users:
        await update.message.reply_text(f"🤡 *Клоун дня:* {random.choice(users)['name']}!", parse_mode=ParseMode.MARKDOWN)

async def wish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wishes = ["💰 Богатства!", "❤️ Любви!", "🔥 Успеха!", "🌟 Мечты сбудутся!", "🍀 Удачи!"]
    await update.message.reply_text(f"✨ *Предсказание:* {random.choice(wishes)} ✨", parse_mode=ParseMode.MARKDOWN)

# ========== ЖАЛОБЫ ==========
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /report текст жалобы")
        return
    user = update.effective_user
    reason = ' '.join(context.args)
    global report_id_counter
    report_id_counter += 1
    rid = report_id_counter
    report_votes[rid] = {"id": rid, "user": user.id, "name": user.first_name, "reason": reason, "votes": {"a": 0, "d": 0, "o": 0}, "voters": []}
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Одобренно", callback_data=f"rep_a_{rid}"),
         InlineKeyboardButton("❌ Отказанно", callback_data=f"rep_d_{rid}"),
         InlineKeyboardButton("📝 Оффтоп", callback_data=f"rep_o_{rid}")]])
    sent = 0
    for u in await get_all_users():
        if u["mod_role"] in [8, 9, 10]:
            try:
                await context.bot.send_message(u["user_id"], f"📢 *ЖАЛОБА #{rid}*\nОт: {user.first_name}\n{reason}", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
                sent += 1
            except:
                pass
    await update.message.reply_text(f"✅ Жалоба #{rid} отправлена {sent} модераторам!")

async def handle_report_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    u = await get_user(uid)
    if not u or u["mod_role"] not in [8, 9, 10]:
        await q.answer("⛔ Только модераторы!")
        return
    parts = data.split("_")
    if len(parts) < 3: return
    action, rid = parts[1], int(parts[2])
    if rid not in report_votes:
        await q.answer("Жалоба обработана!")
        return
    r = report_votes[rid]
    if uid in r["voters"]:
        await q.answer("Вы уже голосовали!")
        return
    r["voters"].append(uid)
    if action == "a": r["votes"]["a"] += 1
    elif action == "d": r["votes"]["d"] += 1
    else: r["votes"]["o"] += 1
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ {r['votes']['a']}", callback_data=f"rep_a_{rid}"),
         InlineKeyboardButton(f"❌ {r['votes']['d']}", callback_data=f"rep_d_{rid}"),
         InlineKeyboardButton(f"📝 {r['votes']['o']}", callback_data=f"rep_o_{rid}")]])
    await q.message.edit_reply_markup(reply_markup=keyboard)

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
            await q.answer("❌ Не ваше предложение!")
            return
        key = f"{u1}_{u2}"
        if key in pending_weddings:
            if q.from_user.id == u1:
                pending_weddings[key]["s1"] = True
            else:
                pending_weddings[key]["s2"] = True
            if pending_weddings[key]["s1"] and pending_weddings[key]["s2"]:
                await add_wedding(u1, u2)
                await q.message.edit_text("💍 *Брак заключен!* 🎉", parse_mode=ParseMode.MARKDOWN)
                del pending_weddings[key]
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
        await add_user(m)
        await update.message.reply_text(
            f"👋 *@{m.username or m.first_name}*, добро пожаловать в *FAM {FAMILY_NAME}*!\n\n"
            f"📝 Напиши свой ник в авторизацию\n"
            f"📖 Правила: {RULES_LINK}\n🔑 Авторизация: {AUTH_LINK}",
            parse_mode=ParseMode.MARKDOWN)

# ========== АВТОРИЗАЦИЯ ==========
async def auto_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    text = message.text.strip()
    if 'Никнейм:' not in text and 'Ник:' not in text:
        return
    nickname = None
    rank = None
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('Никнейм:') or line.startswith('Ник:'):
            nickname = line.split(':', 1)[1].strip()
        elif line.startswith('Ранг:'):
            try:
                rank = int(line.split(':', 1)[1].strip())
            except:
                pass
    if not nickname or not rank:
        await message.reply_text("❌ Неверный формат!\nНикнейм: ваш_ник\nРанг: 5")
        return
    if ' ' in nickname or len(nickname) < 3:
        await message.reply_text("❌ Никнейм без пробелов, от 3 символов!")
        return
    if rank < 2 or rank > 10:
        await message.reply_text("❌ Ранг от 2 до 10!")
        return
    u = await get_user(message.from_user.id)
    if u and u["nickname"]:
        await message.reply_text(f"❌ Вы уже авторизованы! Ваш ник: {u['nickname']}")
        return
    for existing in await get_all_users():
        if existing["nickname"] and existing["nickname"].lower() == nickname.lower():
            await message.reply_text(f"❌ Никнейм {nickname} уже занят!")
            return
    await add_user(message.from_user)
    await update_user(message.from_user.id, "nickname", nickname)
    await update_user(message.from_user.id, "role", rank)
    await message.reply_text(f"✅ *АВТОРИЗАЦИЯ УСПЕШНА!*\n👤 Ваш ник: {nickname}\n🎮 Ранг: {get_rank_name(rank)}", parse_mode=ParseMode.MARKDOWN)
    await notify_moderators(context, f"📢 *НОВЫЙ УЧАСТНИК!*\n👤 {message.from_user.first_name}\n💫 {nickname}\n🎮 {get_rank_name(rank)}")
    try:
        await message.delete()
    except:
        pass

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
async def all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if update.message.text.startswith('/'):
        return
    user = update.effective_user
    text = update.message.text
    if 'Никнейм:' in text or 'Ник:' in text:
        return
    if await is_banned(user.id) or await is_muted(user.id):
        try:
            await update.message.delete()
        except:
            pass
        return
    await add_user(user)
    for v in check_rule_violation(text):
        await apply_punishment(update, user.id, v[1], v[2])
        try:
            await update.message.delete()
        except:
            pass
        return

# ========== АДМИНИСТРИРОВАНИЕ ==========
async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrole @username 2-10")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    if role < 2 or role > 10:
        await update.message.reply_text("❌ Роль от 2 до 10")
        return
    await update_user(uid, "role", role)
    target = await get_user(uid)
    await update.message.reply_text(f"✅ *{target['name']}* получил ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)

async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только лидер!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /role @username 0/8/9/10")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        mod_role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    if mod_role not in [0, 8, 9, 10]:
        await update.message.reply_text("❌ Роль: 0,8,9,10")
        return
    names = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}
    if mod_role == 0:
        await update_user(uid, "mod_role", None)
        await update.message.reply_text(f"✅ У *{await get_user(uid)['name']}* снята роль")
    else:
        await update_user(uid, "mod_role", mod_role)
        await update.message.reply_text(f"✅ *{await get_user(uid)['name']}* получил роль: {names[mod_role]}")

async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только лидер!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /giveaccess @username 8-10")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        level = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    if level not in [8, 9, 10]:
        await update.message.reply_text("❌ Уровень: 8,9,10")
        return
    names = {8: "Модератор", 9: "Администратор", 10: "Руководитель"}
    await update_user(uid, "mod_role", level)
    await update.message.reply_text(f"✅ *{await get_user(uid)['name']}* получил доступ: {names[level]}")

async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = await get_all_users()
    users = sorted(users, key=lambda x: x["role"] or 0, reverse=True)
    text = "📋 *СПИСОК УЧАСТНИКОВ*\n\n"
    for u in users[:50]:
        name = u["nickname"] or u["name"]
        mod_role = ""
        if u["mod_role"] == 8: mod_role = " [Мод]"
        elif u["mod_role"] == 9: mod_role = " [Зам]"
        elif u["mod_role"] == 10: mod_role = " [Лид]"
        text += f"• {name} — {u['role']} ранг{mod_role}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def grole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /grole @username 0-10")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
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
        await update_user(uid, "role", 2)
        await update.message.reply_text(f"✅ У *{await get_user(uid)['name']}* роль сброшена до Новичка")
    else:
        await update_user(uid, "role", role)
        await update.message.reply_text(f"✅ *{await get_user(uid)['name']}* получил ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)

async def roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = await get_all_users()
    text = "👑 *РОЛИ УЧАСТНИКОВ*\n\n"
    for u in users[:50]:
        mod = ""
        if u["mod_role"] == 8: mod = " | 🛡️ Модер"
        elif u["mod_role"] == 9: mod = " | 👑 Зам"
        elif u["mod_role"] == 10: mod = " | 💎 Лидер"
        text += f"• {u['nickname'] or u['name']} — {u['role']} ранг ({get_rank_name(u['role'])}){mod}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    mentions = []
    for u in await get_all_users():
        if u["username"]:
            mentions.append(f"@{u['username']}")
    if not mentions:
        await update.message.reply_text("Нет участников")
        return
    await update.message.reply_text("🔔 *ВНИМАНИЕ! ОБЩЕЕ СОБРАНИЕ!* 🔔\n\n" + ' '.join(mentions[:50]), parse_mode=ParseMode.MARKDOWN)

async def editnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not u or u["mod_role"] not in [9, 10]:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 9+")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /editnick @username новый_ник")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    new_nick = ' '.join(context.args[1:])[:50]
    for existing in users:
        if existing["nickname"] and existing["nickname"].lower() == new_nick.lower() and existing["user_id"] != uid:
            await update.message.reply_text(f"❌ Никнейм {new_nick} уже занят!")
            return
    target = await get_user(uid)
    old_nick = target["nickname"] or "Не был установлен"
    await update_user(uid, "nickname", new_nick)
    await update.message.reply_text(f"✅ *{target['name']}* никнейм изменён!\nСтарый: {old_nick}\nНовый: {new_nick}", parse_mode=ParseMode.MARKDOWN)

async def setrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not u or u["mod_role"] not in [9, 10]:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 9+")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrank @username 2-10")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        rank = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    if rank < 2 or rank > 10:
        await update.message.reply_text("❌ Ранг от 2 до 10")
        return
    target = await get_user(uid)
    old_rank = target["role"]
    await update_user(uid, "role", rank)
    await update.message.reply_text(f"🔄 Ранг *{target['name']}* изменён!\nБыло: {old_rank}\nСтало: {rank} ({get_rank_name(rank)})", parse_mode=ParseMode.MARKDOWN)

async def delnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not u or u["mod_role"] not in [9, 10]:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 9+")
        return
    if not context.args:
        await update.message.reply_text("❌ /delnick @username")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    target = await get_user(uid)
    old_nick = target["nickname"] or "Не был установлен"
    await update_user(uid, "nickname", None)
    await update.message.reply_text(f"✅ У *{target['name']}* удалён никнейм\nСтарый ник: {old_nick}", parse_mode=ParseMode.MARKDOWN)

async def setuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = await get_user(user.id)
    if not is_moderator(u):
        await update.message.reply_text("⛔ Нет прав!")
        return
    if len(context.args) < 3:
        await update.message.reply_text("❌ /setuser @username ник ранг")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    nickname = context.args[1][:50]
    try:
        role = int(context.args[2])
    except:
        await update.message.reply_text("❌ Неверный формат ранга!")
        return
    if role < 2 or role > 10:
        await update.message.reply_text("❌ Ранг от 2 до 10")
        return
    target = await get_user(uid)
    await update_user(uid, "nickname", nickname)
    await update_user(uid, "role", role)
    await update.message.reply_text(f"✅ *{target['name']}* обновлён!\nНик: {nickname}\nРанг: {role} ({get_rank_name(role)})", parse_mode=ParseMode.MARKDOWN)

async def creator_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Доступ запрещен!")
        return
    await update.message.reply_text(
        "👑 *ПАНЕЛЬ СОЗДАТЕЛЯ*\n\n"
        "📊 /checkdb, /checkmutes, /checkbans, /checkweddings\n"
        "⭐ /takerep, /resetrep\n"
        "👤 /resetuser\n"
        "🔧 /stats, /clearlogs, /sql",
        parse_mode=ParseMode.MARKDOWN)

async def check_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Нет прав!")
        return
    users = await get_all_users()
    if not users:
        await update.message.reply_text("📋 База данных пуста")
        return
    text = "📊 *БАЗА ДАННЫХ*\n\n"
    for u in users[:20]:
        text += f"• {u['nickname'] or u['name']} (@{u['username']}) — ранг {u['role']}, репа {u['rep']}\n"
    text += f"\n📊 Всего: {len(users)} пользователей"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_mutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Нет прав!")
        return
    lst = await get_mutes_list()
    if not lst:
        await update.message.reply_text("🔇 Нет активных мутов")
        return
    text = "🔇 *АКТИВНЫЕ МУТЫ*\n\n"
    for m in lst:
        u = await get_user(m["user_id"])
        name = u["nickname"] or u["name"] if u else str(m["user_id"])
        text += f"• {name} — до {m['until'][:16]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_bans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Нет прав!")
        return
    lst = await get_bans_list()
    if not lst:
        await update.message.reply_text("🔨 Нет активных банов")
        return
    text = "🔨 *АКТИВНЫЕ БАНЫ*\n\n"
    for b in lst:
        u = await get_user(b["user_id"])
        name = u["nickname"] or u["name"] if u else str(b["user_id"])
        text += f"• {name} — до {b['until'][:10]}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check_weddings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Нет прав!")
        return
    active = await get_active_weddings()
    if not active:
        await update.message.reply_text("💔 Нет активных свадеб")
        return
    text = "💍 *АКТИВНЫЕ СВАДЬБЫ*\n\n"
    for w in active:
        u1 = await get_user(w["user1"])
        u2 = await get_user(w["user2"])
        text += f"• {(u1['nickname'] or u1['name']) if u1 else w['user1']} + {(u2['nickname'] or u2['name']) if u2 else w['user2']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def takerep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /takerep @username кол-во")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    try:
        amount = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат!")
        return
    target = await get_user(uid)
    old_rep = target["rep"] or 0
    new_rep = max(0, old_rep - amount)
    await update_user(uid, "rep", new_rep)
    await update.message.reply_text(f"💀 *{target['name']}* потерял {amount} репутации!\nБыло: {old_rep}⭐ → Стало: {new_rep}⭐", parse_mode=ParseMode.MARKDOWN)

async def resetrep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /resetrep @username")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    target = await get_user(uid)
    old_rep = target["rep"] or 0
    await update_user(uid, "rep", 0)
    await update.message.reply_text(f"🔄 Репутация *{target['name']}* сброшена!\nБыло: {old_rep}⭐ → Стало: 0⭐", parse_mode=ParseMode.MARKDOWN)

async def resetuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /resetuser @username")
        return
    users = await get_all_users()
    uid = get_user_id_from_input(context.args[0], users)
    if not uid:
        await update.message.reply_text("❌ Пользователь не найден!")
        return
    target = await get_user(uid)
    await update_user(uid, "nickname", None)
    await update_user(uid, "role", 2)
    await update_user(uid, "warns", 0)
    await update_user(uid, "rep", 0)
    await update_user(uid, "spouse_id", None)
    await update_user(uid, "prefix", None)
    await update_user(uid, "mod_role", None)
    await update.message.reply_text(
        f"🔄 *ВСЕ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ СБРОШЕНЫ!*\n\n"
        f"👤 Пользователь: {target['name']}\n"
        f"✅ Никнейм удалён\n✅ Ранг сброшен до 2\n✅ Варны обнулены\n"
        f"✅ Репутация обнулена\n✅ Брак расторгнут\n✅ Модераторская роль снята",
        parse_mode=ParseMode.MARKDOWN)

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    import io
    users = await get_all_users()
    backup_text = f"# Бэкап NEVERMORE BOT\n# Дата: {datetime.now()}\n\n"
    backup_text += f"## USERS ({len(users)} записей)\n"
    for u in users:
        backup_text += f"{u}\n"
    bio = io.BytesIO(backup_text.encode('utf-8'))
    bio.name = f"nevermore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    await update.message.reply_document(document=bio, caption="📦 *Бэкап базы данных*", parse_mode=ParseMode.MARKDOWN)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    users = await get_all_users()
    mutes = await get_mutes_list()
    bans = await get_bans_list()
    weddings = await get_active_weddings()
    await update.message.reply_text(
        f"📊 *СТАТИСТИКА БОТА*\n\n"
        f"👥 Пользователей: {len(users)}\n"
        f"🔇 Активных мутов: {len(mutes)}\n"
        f"🔨 Активных банов: {len(bans)}\n"
        f"💍 Активных свадеб: {len(weddings)}",
        parse_mode=ParseMode.MARKDOWN)

async def sql(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔ Только для создателя!")
        return
    if not context.args:
        await update.message.reply_text("❌ /sql SELECT * FROM users")
        return
    query = ' '.join(context.args)
    try:
        conn = await get_db()
        if query.strip().upper().startswith('SELECT'):
            rows = await conn.fetch(query)
            if rows:
                text = "📊 *РЕЗУЛЬТАТ*\n\n"
                for row in rows[:10]:
                    text += f"• {dict(row)}\n"
                await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text("✅ Результат пуст")
        else:
            await conn.execute(query)
            await update.message.reply_text("✅ Запрос выполнен!")
        await conn.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ========== ВЕБ-СЕРВЕР ==========
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "bot": "Nevermore Bot"}).encode())
    def log_message(self, format, *args): pass

def start_web_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ Веб-сервер запущен на порту {port}")
    server.serve_forever()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 ЗАПУСК NEVERMORE FAMILY BOT...")
    
    # Запускаем веб-сервер
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    time.sleep(1)
    
    # Инициализация
    asyncio.run(init_db())
    
    # Создаём приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_message))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("info", info))
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
    app.add_handler(CommandHandler("setname", setname))
    app.add_handler(CommandHandler("setnick", setnick))
    app.add_handler(CommandHandler("setprefix", setprefix))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("giverep", giverep))
    app.add_handler(CommandHandler("setrole", setrole))
    app.add_handler(CommandHandler("role", role))
    app.add_handler(CommandHandler("giveaccess", giveaccess))
    app.add_handler(CommandHandler("nlist", nlist))
    app.add_handler(CommandHandler("grole", grole))
    app.add_handler(CommandHandler("roles", roles))
    app.add_handler(CommandHandler("all", all_command))
    app.add_handler(CommandHandler("editnick", editnick))
    app.add_handler(CommandHandler("setrank", setrank))
    app.add_handler(CommandHandler("delnick", delnick))
    app.add_handler(CommandHandler("setuser", setuser))
    app.add_handler(CommandHandler("creator", creator_panel))
    app.add_handler(CommandHandler("checkdb", check_db))
    app.add_handler(CommandHandler("checkmutes", check_mutes))
    app.add_handler(CommandHandler("checkbans", check_bans))
    app.add_handler(CommandHandler("checkweddings", check_weddings))
    app.add_handler(CommandHandler("takerep", takerep))
    app.add_handler(CommandHandler("resetrep", resetrep))
    app.add_handler(CommandHandler("resetuser", resetuser))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("sql", sql))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_auth))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, all_messages))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ БОТ ГОТОВ К ЗАПУСКУ! 🔥 FAM NEVERMORE ONLINE!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
