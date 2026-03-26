import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ========== КОНФИГ ==========
BOT_TOKEN = "8768445585:AAEV44NdL684Fi_NLBRmWk89LROJr15nUZ0"
ADMINS = {5695593671, 1784442476}  # Роли 10 (владельцы)
FAMILY_NAME = "Nevermore"
FAMILY_LINK = "https://t.me/famnevermore"
AUTH_LINK = "https://t.me/famnevermore/19467"
RULES_LINK = "https://t.me/famnevermore/26"

# ========== ХРАНИЛИЩА ==========
users = {}        # Все пользователи
mutes = {}        # Замученные
bans = {}         # Забаненные
weddings = []     # Свадьбы
logs = []         # Логи
pending_weddings = {}  # Ожидание свадьбы
reports = []      # Жалобы
cooldowns = {}    # Кулдауны
report_cooldowns = {}  # Кулдаун на отправку жалоб
report_votes = {}      # Голосование по жалобам
report_messages = {}   # Сообщения с жалобами
report_id_counter = 0  # Счетчик жалоб

# ========== РОЛИ (игровые ранги) ==========
game_ranks = {
    0: {"name": "⚠️ Заблокирован", "emoji": "🚫"},
    1: {"name": "Не используется", "emoji": "❌"},
    2: {"name": "Новичок", "emoji": "😭", "desc": "6 машин в автопарке, фри ранг в ДС"},
    3: {"name": "Любитель скорости", "emoji": "🏎", "desc": "Средний автопарк, свой тег, наёмный фермер"},
    4: {"name": "Образованный", "emoji": "💻", "desc": "Гайды по старту, ценам"},
    5: {"name": "Невермор", "emoji": "🎧", "desc": "Инвестиции, афк заработок, скрипты"},
    6: {"name": "Шарющий", "emoji": "📖", "desc": "Улучшенный автопарк, клады, тайники"},
    7: {"name": "Барыга", "emoji": "😎", "desc": "Ловля лавок на ЦР, конфиги"},
    8: {"name": "Премиум", "emoji": "🤩", "desc": "Весь автопарк, все гайды, анти-кик"},
    9: {"name": "Зам. лидера", "emoji": "👑", "desc": "Права модерации"},
    10: {"name": "Лидер", "emoji": "💎", "desc": "Полный доступ"}
}

# ========== МОДЕРАТОРСКИЕ РОЛИ ==========
mod_roles = [8, 9, 10]

# ========== ПРАВИЛА (УБРАНЫ ОСКОРБЛЕНИЯ) ==========
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

*Старайтесь не нарушать!* ⚠️
"""

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

def get_rank_name(role):
    return game_ranks.get(role, game_ranks[2])["name"]

def get_rank_emoji(role):
    return game_ranks.get(role, game_ranks[2])["emoji"]

def has_permission(user_id, required_role):
    """Проверка прав: 8-модер, 9-зам, 10-лидер"""
    if user_id not in users:
        return False
    user_role = users[user_id].get("mod_role", 0)
    return user_role >= required_role

def add_log(user_id, action, target=None, reason=None):
    logs.insert(0, {
        "time": datetime.now(),
        "user": user_id,
        "user_name": users.get(user_id, {}).get("nickname") or users.get(user_id, {}).get("name", str(user_id)),
        "action": action,
        "target": target,
        "reason": reason
    })
    if len(logs) > 200:
        logs.pop()

def init_user(user):
    if user.id not in users:
        users[user.id] = {
            "id": user.id,
            "name": user.first_name,
            "username": user.username,
            "nickname": None,
            "role": 2,
            "warns": 0,
            "rep": 0,
            "spouse": None,
            "last_online": datetime.now(),
            "msgs": 0,
            "joined": datetime.now(),
            "mod_role": None,
        }
    else:
        users[user.id]["last_online"] = datetime.now()
        users[user.id]["msgs"] += 1
    return users[user.id]

def is_muted(user_id):
    return user_id in mutes and mutes[user_id] > datetime.now()

def is_banned(user_id):
    return user_id in bans and bans[user_id] > datetime.now()

def is_moderator(user_id):
    return users.get(user_id, {}).get("mod_role", 0) >= 8

def get_user_id_from_input(input_str):
    """Получить user_id из username (@) или ID"""
    input_str = input_str.strip()
    
    if input_str.startswith('@'):
        username = input_str[1:].lower()
        for uid, u in users.items():
            if u.get("username") and u["username"].lower() == username:
                return uid
        return None
    
    try:
        return int(input_str)
    except:
        return None

def check_rule_violation(text):
    """Проверка нарушения правил"""
    text_lower = text.lower()
    violations = []
    
    # 18+ контент
    adult_words = ['порно', 'секс', '18+', 'голый', 'эротика']
    if any(w in text_lower for w in adult_words):
        violations.append(("adult", 120, "мут 120 минут за 18+ контент"))
    
    # Упоминание родителей
    parent_words = ['мать', 'отец', 'родители', 'мама', 'папа']
    if any(w in text_lower for w in parent_words):
        violations.append(("parent", 120, "мут 120 минут за упоминание родителей"))
    
    # Политика
    politics = ['путин', 'зеленский', 'политика', 'война', 'россия', 'украина']
    if any(w in text_lower for w in politics):
        violations.append(("politics", 60, "мут 60 минут за политику"))
    
    # Нацистская символика
    nazi = ['свастика', 'нацист', 'гитлер']
    if any(w in text_lower for w in nazi):
        violations.append(("nazi", 60, "мут 60 минут за нацистскую символику"))
    
    return violations

async def apply_punishment(update, user_id, duration, reason):
    """Применение наказания"""
    mutes[user_id] = datetime.now() + timedelta(minutes=duration)
    try:
        user = await update.message.chat.get_member(user_id)
        await update.message.reply_text(f"🔇 {user.user.first_name}, {reason}", parse_mode=ParseMode.MARKDOWN)
    except:
        pass
    add_log(0, "auto_mute", user_id, reason)

async def notify_admins(context, text):
    """Отправить уведомление всем админам"""
    for uid, u in users.items():
        if u.get("mod_role") in [8, 9, 10]:
            try:
                await context.bot.send_message(uid, text, parse_mode=ParseMode.MARKDOWN)
            except:
                pass

# ========== ПРИВЕТСТВИЕ ==========
async def welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        
        init_user(member)
        add_log(member.id, "joined")
        
        welcome_text = f"""
👋 *@{member.username or member.first_name}*, добро пожаловать в группу *FAM {FAMILY_NAME}*!

📝 Напиши, пожалуйста, свой ник в авторизацию в течение 24 часов, иначе кик.
📖 Просим ознакомиться с правилами чата: {RULES_LINK}
🔑 Ссылка на авторизацию: {AUTH_LINK}

*Приятного общения!* ❤️
"""
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    init_user(user)
    add_log(user.id, "start")
    
    keyboard = [
        [InlineKeyboardButton("📜 Правила", callback_data="rules")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("⭐ Топ", callback_data="top")],
        [InlineKeyboardButton("💍 Свадьбы", callback_data="weddings")]
    ]
    
    await update.message.reply_text(
        f"🔥 *ДОБРО ПОЖАЛОВАТЬ В FAM {FAMILY_NAME}!* 🔥\n\n"
        f"Привет, {user.first_name}! 👋\n"
        f"🎮 Твой игровой ранг: {get_rank_emoji(users[user.id]['role'])} *{get_rank_name(users[user.id]['role'])}*\n"
        f"⭐ Репутация: {users[user.id]['rep']}\n"
        f"👑 Модераторская роль: {users[user.id].get('mod_role', 'Нет')}\n\n"
        f"Используй /help для списка команд!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_log(user.id, "help")
    
    help_text = f"""
🔥 *FAM {FAMILY_NAME} - КОМАНДЫ* 🔥

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
/kiss [reply] - Поцеловать 💋
/hug [reply] - Обнять 🤗
/slap [reply] - Ударить 👋
/me [действие] - Описать действие
/try [действие] - Попытать удачу 🎯
/gay - Гей дня 🏳️‍🌈
/clown - Клоун дня 🤡
/wish - Предсказание ✨

📊 *СТАТИСТИКА:*
/top - Топ участников
/online - Кто онлайн
/check [ник] - Проверить игрока

🔨 *МОДЕРАЦИЯ:*
/warn [reply] [причина] - Предупреждение
/mute [reply] [время] - Замутить
/unmute [reply] - Размутить
/ban [reply] [причина] - Забанить
/unban [user_id] - Разбанить
/warns [user] - Варны пользователя
/bans - Список забаненных
/mutelist - Список замученных
/logs - Логи действий
/clear [кол-во] - Очистить чат
/report [текст] - Пожаловаться

👑 *АДМИНИСТРИРОВАНИЕ:*
/setrole [user] [2-10] - Выдать роль
/role [user] [0-10] - Сменить роль (0-снять)
/giveaccess [user] [8-10] - Выдать доступ
/nlist - Список участников
/grole [user] [0-10] - Игровая роль
/gnick [user] [ник] - Дать ник
/roles - Все роли
/all - Призвать всех

📜 *ПРАВИЛА:*
/rules - Показать правила

📝 *ДРУГОЕ:*
/report [текст] - Жалоба
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(RULES, parse_mode=ParseMode.MARKDOWN)

# ========== ПРОФИЛЬ ==========
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = init_user(user)
    
    spouse_name = "Нет"
    for w in weddings:
        if (w["user1"] == user.id or w["user2"] == user.id) and not w.get("divorced"):
            spouse_id = w["user1"] if w["user2"] == user.id else w["user2"]
            if spouse_id in users:
                spouse_name = users[spouse_id]["nickname"] or users[spouse_id]["name"]
    
    mod_role_text = ""
    if u.get("mod_role"):
        mod_names = {8: "Модератор", 9: "Зам. лидера", 10: "Лидер"}
        mod_role_text = f"\n👑 Мод. роль: {mod_names.get(u['mod_role'], u['mod_role'])}"
    
    profile_text = (
        f"<b>{get_rank_emoji(u['role'])} ПРОФИЛЬ {get_rank_emoji(u['role'])}</b>\n\n"
        f"👤 Имя: <b>{u['name']}</b>\n"
        f"📝 Username: @{u['username'] or 'Нет'}\n"
        f"💫 Никнейм: {u['nickname'] or 'Не установлен'}\n"
        f"🏷️ Префикс: {u.get('prefix', 'Нет')}\n"
        f"🎮 Игровой ранг: <b>{get_rank_name(u['role'])}</b>{mod_role_text}\n\n"
        f"⭐ Репутация: <b>{u['rep']}</b>\n"
        f"⚠️ Варны: {u['warns']}/3\n"
        f"💬 Сообщений: {u['msgs']}\n"
        f"💍 Супруг(а): {spouse_name}\n\n"
        f"📅 В семье с: {u['joined'].strftime('%d.%m.%Y')}\n"
        f"🕐 Последний онлайн: {u['last_online'].strftime('%d.%m.%Y %H:%M')}"
    )
    
    await update.message.reply_text(profile_text, parse_mode=ParseMode.HTML)
    add_log(user.id, "view_profile")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leader = None
    for uid, u in users.items():
        if u.get("mod_role") == 10:
            leader = u
            break
    
    leader_text = f"@{leader['username'] or leader['name']}" if leader else "Не указан"
    
    info_text = f"""
ℹ️ *ИНФОРМАЦИЯ О СЕМЬЕ {FAMILY_NAME}* ℹ️

👑 *Лидер:* {leader_text}
📊 *Участников:* {len(users)}
⭐ *Общая репутация:* {sum(u['rep'] for u in users.values())}

📌 *Ссылки:*
• Правила: {RULES_LINK}
• Авторизация: {AUTH_LINK}
"""
    await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /setname [ник]")
        return
    
    user = update.effective_user
    u = init_user(user)
    nickname = ' '.join(context.args)[:50]
    u["nickname"] = nickname
    await update.message.reply_text(f"✅ Никнейм установлен: {nickname}")
    add_log(user.id, "set_name", reason=nickname)

async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /setprefix [префикс]")
        return
    
    user = update.effective_user
    u = init_user(user)
    prefix = ' '.join(context.args)[:20]
    u["prefix"] = prefix
    await update.message.reply_text(f"✅ Префикс установлен: {prefix}")
    add_log(user.id, "set_prefix", reason=prefix)

# ========== СВАДЬБЫ С СОГЛАСИЕМ ==========
async def wedding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💍 Ответь на сообщение того, кому хочешь предложить брак!")
        return
    
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя жениться на себе!")
        return
    
    for w in weddings:
        if (w["user1"] == user.id or w["user2"] == user.id) and not w.get("divorced"):
            await update.message.reply_text("❌ Вы уже в браке!")
            return
        if (w["user1"] == target.id or w["user2"] == target.id) and not w.get("divorced"):
            await update.message.reply_text("❌ Этот пользователь уже в браке!")
            return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, согласен", callback_data=f"wedding_accept_{user.id}_{target.id}")],
        [InlineKeyboardButton("❌ Нет, не согласен", callback_data=f"wedding_decline_{user.id}_{target.id}")]
    ])
    
    await update.message.reply_text(
        f"💍 *{user.first_name}* предлагает брак *{target.first_name}*!\n\n"
        f"У вас есть 120 секунд, чтобы ответить!",
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
    user = update.effective_user
    init_user(user)
    
    if not users[user.id].get("spouse"):
        await update.message.reply_text("❌ Вы не состоите в браке!")
        return
    
    spouse_id = users[user.id]["spouse"]
    
    for w in weddings:
        if (w["user1"] == user.id or w["user2"] == user.id) and not w.get("divorced"):
            w["divorced"] = True
            break
    
    users[user.id]["spouse"] = None
    if spouse_id in users:
        users[spouse_id]["spouse"] = None
    
    await update.message.reply_text(f"💔 *{user.first_name}* развелся(ась)!", parse_mode=ParseMode.MARKDOWN)
    add_log(user.id, "divorce", spouse_id)

async def weddings_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = [w for w in weddings if not w.get("divorced")]
    
    if not active:
        await update.message.reply_text("💔 Пока нет ни одной свадьбы")
        return
    
    text = "💍 *АКТИВНЫЕ БРАКИ* 💍\n\n"
    for w in active:
        name1 = users[w["user1"]]["nickname"] or users[w["user1"]]["name"] if w["user1"] in users else str(w["user1"])
        name2 = users[w["user2"]]["nickname"] or users[w["user2"]]["name"] if w["user2"] in users else str(w["user2"])
        date = w["date"].strftime('%d.%m.%Y')
        text += f"❤️ {name1} + {name2}\n📅 {date}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== РЕПУТАЦИЯ ==========
async def rep_plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("⭐ Ответь на сообщение!")
        return
    
    user = update.effective_user
    target = update.message.reply_to_message.from_user
    
    if user.id == target.id:
        await update.message.reply_text("❌ Нельзя себе!")
        return
    
    init_user(target)
    users[target.id]["rep"] += 1
    
    await update.message.reply_text(
        f"⭐ *{user.first_name}* +1 репутации *{target.first_name}*!\nТеперь: {users[target.id]['rep']}⭐",
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
    
    init_user(target)
    users[target.id]["rep"] -= 1
    
    await update.message.reply_text(
        f"💀 *{user.first_name}* -1 репутации *{target.first_name}*!\nТеперь: {users[target.id]['rep']}⭐",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user.id, "rep_minus", target.id)

# ========== МОДЕРАЦИЯ (с уведомлениями админов) ==========
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    moderator = update.effective_user
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    
    init_user(target)
    users[target.id]["warns"] += 1
    warns = users[target.id]["warns"]
    
    await update.message.reply_text(
        f"⚠️ *{target.first_name}* получил предупреждение!\n"
        f"📝 Причина: {reason}\n"
        f"⚠️ Предупреждений: {warns}/3",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await notify_admins(
        context,
        f"⚠️ *ВЫДАНО ПРЕДУПРЕЖДЕНИЕ*\n\n"
        f"👤 Модератор: {moderator.first_name}\n"
        f"🔨 Нарушитель: {target.first_name}\n"
        f"📝 Причина: {reason}\n"
        f"⚠️ Всего варнов: {warns}/3"
    )
    
    add_log(moderator.id, "warn", target.id, reason)
    
    if warns >= 3:
        mutes[target.id] = datetime.now() + timedelta(days=1)
        await update.message.reply_text(f"🔇 {target.first_name} замучен на 1 день за 3 предупреждения!")
        await notify_admins(
            context,
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
    
    moderator = update.effective_user
    target = update.message.reply_to_message.from_user
    duration = context.args[0] if context.args else "60"
    reason = ' '.join(context.args[1:]) or "Нарушение правил"
    
    try:
        minutes = int(duration)
    except:
        minutes = 60
    
    mutes[target.id] = datetime.now() + timedelta(minutes=minutes)
    
    await update.message.reply_text(
        f"🔇 *{target.first_name}* замучен!\n"
        f"⏱️ Длительность: {minutes} минут\n"
        f"📝 Причина: {reason}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await notify_admins(
        context,
        f"🔇 *ВЫДАН МУТ*\n\n"
        f"👤 Модератор: {moderator.first_name}\n"
        f"🔨 Нарушитель: {target.first_name}\n"
        f"⏱️ Длительность: {minutes} минут\n"
        f"📝 Причина: {reason}"
    )
    
    add_log(moderator.id, "mute", target.id, f"{minutes}мин - {reason}")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    target = update.message.reply_to_message.from_user
    if target.id in mutes:
        del mutes[target.id]
    
    await update.message.reply_text(f"🔊 *{target.first_name}* размучен!", parse_mode=ParseMode.MARKDOWN)
    add_log(update.effective_user.id, "unmute", target.id)

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответь на сообщение!")
        return
    
    moderator = update.effective_user
    target = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) or "Нарушение правил"
    
    bans[target.id] = datetime.now() + timedelta(days=365)
    
    await update.message.reply_text(
        f"🔨 *{target.first_name}* забанен!\n"
        f"📝 Причина: {reason}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await notify_admins(
        context,
        f"🔨 *ВЫДАН БАН*\n\n"
        f"👤 Модератор: {moderator.first_name}\n"
        f"🔨 Нарушитель: {target.first_name}\n"
        f"📝 Причина: {reason}\n"
        f"⏱️ Длительность: Навсегда"
    )
    
    add_log(moderator.id, "ban", target.id, reason)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Разбанить пользователя"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if not context.args:
        await update.message.reply_text("❌ /unban [@username или user_id]\n\nПример: /unban @username")
        return
    
    target_input = context.args[0]
    target_id = get_user_id_from_input(target_input)
    
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    if target_id in bans:
        del bans[target_id]
        await update.message.reply_text(f"🔓 Пользователь {target_input} разбанен!")
        add_log(update.effective_user.id, "unban", target_id)
    else:
        await update.message.reply_text(f"❌ Пользователь {target_input} не в бане!")

async def warns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать варны пользователя"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    target = None
    
    if context.args:
        target_input = context.args[0]
        target_id = get_user_id_from_input(target_input)
        
        if target_id and target_id in users:
            target = users[target_id]
        else:
            await update.message.reply_text(f"❌ Пользователь {target_input} не найден")
            return
    elif update.message.reply_to_message:
        tid = update.message.reply_to_message.from_user.id
        if tid in users:
            target = users[tid]
    
    if not target:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    await update.message.reply_text(f"⚠️ *{target['name']}* имеет {target['warns']}/3 предупреждений", parse_mode=ParseMode.MARKDOWN)

async def bans_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if not bans:
        await update.message.reply_text("🔨 Нет активных банов")
        return
    
    text = "🔨 *Активные баны:*\n\n"
    for uid, until in bans.items():
        if until > datetime.now():
            name = users[uid]["nickname"] or users[uid]["name"] if uid in users else str(uid)
            text += f"• {name} — до {until.strftime('%d.%m.%Y')}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    active = {uid: until for uid, until in mutes.items() if until > datetime.now()}
    
    if not active:
        await update.message.reply_text("🔇 Нет активных мутов")
        return
    
    text = "🔇 *Активные муты:*\n\n"
    for uid, until in active.items():
        name = users[uid]["nickname"] or users[uid]["name"] if uid in users else str(uid)
        text += f"• {name} — до {until.strftime('%d.%m.%Y %H:%M')}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if not logs:
        await update.message.reply_text("Нет логов")
        return
    
    text = "📋 *Последние действия:*\n\n"
    for log in logs[:15]:
        text += f"• {log['time'].strftime('%H:%M %d.%m')} — {log['user_name']}: {log['action']}\n"
        if len(text) > 4000:
            break
    
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

# ========== НОВАЯ СИСТЕМА ЖАЛОБ С ГОЛОСОВАНИЕМ ==========
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Жалоба с системой голосования"""
    if not context.args:
        await update.message.reply_text("❌ /report [текст жалобы]\n\nПример: /report Оскорбление участника")
        return
    
    user = update.effective_user
    user_id = user.id
    
    # Проверяем кулдаун
    if user_id in report_cooldowns and report_cooldowns[user_id] > datetime.now():
        remaining = int((report_cooldowns[user_id] - datetime.now()).total_seconds() / 3600)
        await update.message.reply_text(f"⏱️ Вы слишком часто отправляете жалобы! Следующая жалоба через {remaining} часов.")
        return
    
    reason = ' '.join(context.args)
    global report_id_counter
    report_id_counter += 1
    report_id = report_id_counter
    
    # Сохраняем жалобу
    report_data = {
        "id": report_id,
        "user": user_id,
        "user_name": user.first_name,
        "reason": reason,
        "time": datetime.now(),
        "status": "pending",
        "votes": {"approve": 0, "deny": 0, "offtopic": 0},
        "voters": []
    }
    report_votes[report_id] = report_data
    
    # Создаем кнопки
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобренно", callback_data=f"report_approve_{report_id}"),
            InlineKeyboardButton("❌ Отказанно", callback_data=f"report_deny_{report_id}"),
            InlineKeyboardButton("📝 Оффтоп", callback_data=f"report_offtopic_{report_id}")
        ]
    ])
    
    # Отправляем жалобу всем модераторам
    sent_count = 0
    for uid, u in users.items():
        if u.get("mod_role") in [8, 9, 10]:
            try:
                msg = await context.bot.send_message(
                    uid,
                    f"📢 *НОВАЯ ЖАЛОБА #{report_id}!*\n\n"
                    f"👤 От: {user.first_name}\n"
                    f"📝 Текст: {reason}\n"
                    f"🕐 Время: {datetime.now().strftime('%H:%M %d.%m')}\n\n"
                    f"*Голосуйте:*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
                report_messages[report_id] = msg.message_id
                sent_count += 1
            except:
                pass
    
    if sent_count > 0:
        await update.message.reply_text(f"✅ Жалоба #{report_id} отправлена {sent_count} модераторам!")
        add_log(user.id, "report", reason=reason)
    else:
        await update.message.reply_text("❌ Нет доступных модераторов!")

async def handle_report_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосов по жалобам"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # Проверяем, что голосующий - модератор
    if users.get(user_id, {}).get("mod_role", 0) < 8:
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
    
    # Проверяем, голосовал ли уже этот модератор
    if user_id in report["voters"]:
        await query.answer("❌ Вы уже голосовали по этой жалобе!", show_alert=True)
        return
    
    # Добавляем голос
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
    
    # Обновляем сообщение
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ {report['votes']['approve']}", callback_data=f"report_approve_{report_id}"),
            InlineKeyboardButton(f"❌ {report['votes']['deny']}", callback_data=f"report_deny_{report_id}"),
            InlineKeyboardButton(f"📝 {report['votes']['offtopic']}", callback_data=f"report_offtopic_{report_id}")
        ]
    ])
    
    try:
        await query.message.edit_reply_markup(reply_markup=keyboard)
    except:
        pass
    
    # Проверяем, не набралось ли 3 голоса оффтоп
    if report["votes"]["offtopic"] >= 3:
        report["status"] = "offtopic_punished"
        reporter_id = report["user"]
        report_cooldowns[reporter_id] = datetime.now() + timedelta(hours=6)
        
        await query.message.edit_text(
            f"📢 *ИТОГ ЖАЛОБЫ #{report_id}*\n\n"
            f"👤 От: {report['user_name']}\n"
            f"📝 Текст: {report['reason']}\n\n"
            f"⚖️ *РЕШЕНИЕ:* Жалоба признана оффтопом (3+ голосов)\n"
            f"⏱️ *НАКАЗАНИЕ:* {report['user_name']} не может отправлять жалобы 6 часов!",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            await context.bot.send_message(
                reporter_id,
                f"⚠️ *Ваша жалоба #{report_id} признана оффтопом!*\n\n"
                f"📝 Текст: {report['reason']}\n"
                f"⏱️ Вы не можете отправлять жалобы 6 часов!",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        
        del report_votes[report_id]
    
    # Проверяем, не набралось ли 3 голоса "отказанно"
    elif report["votes"]["deny"] >= 3:
        report["status"] = "denied"
        reporter_id = report["user"]
        report_cooldowns[reporter_id] = datetime.now() + timedelta(hours=6)
        
        await query.message.edit_text(
            f"📢 *ИТОГ ЖАЛОБЫ #{report_id}*\n\n"
            f"👤 От: {report['user_name']}\n"
            f"📝 Текст: {report['reason']}\n\n"
            f"⚖️ *РЕШЕНИЕ:* Жалоба отклонена (3+ голосов)\n"
            f"⏱️ *НАКАЗАНИЕ:* {report['user_name']} не может отправлять жалобы 6 часов!",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            await context.bot.send_message(
                reporter_id,
                f"⚠️ *Ваша жалоба #{report_id} отклонена!*\n\n"
                f"📝 Текст: {report['reason']}\n"
                f"⏱️ Вы не можете отправлять жалобы 6 часов!",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        
        del report_votes[report_id]

# ========== АДМИНИСТРАТИВНЫЕ КОМАНДЫ ==========
async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать игровую роль (2-10)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS and users.get(user_id, {}).get("mod_role", 0) < 8:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+ (Модератор)")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /setrole [@username или user_id] [2-10]\n\nПример: /setrole @username 5")
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
    
    if target_id not in users:
        try:
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, target_id)
            init_user(chat_member.user)
        except:
            await update.message.reply_text("❌ Пользователь не найден в чате!")
            return
    
    users[target_id]["role"] = role
    await update.message.reply_text(
        f"✅ *{users[target_id]['name']}* получил игровой ранг: {get_rank_name(role)}",
        parse_mode=ParseMode.MARKDOWN
    )
    add_log(user_id, "set_role", target_id, f"ранг {role}")

async def role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать/снять модераторскую роль (0-10, 0-снять)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS and users.get(user_id, {}).get("mod_role", 0) != 10:
        await update.message.reply_text("⛔ Нет прав! Только лидер может выдавать модераторские роли!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /role [@username или user_id] [0-10]\n\n0 - снять роль\n8 - Модератор\n9 - Зам. лидера\n10 - Лидер\n\nПример: /role @username 8")
        return
    
    target_input = context.args[0]
    try:
        mod_role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат роли!")
        return
    
    if mod_role < 0 or mod_role > 10:
        await update.message.reply_text("❌ Роль должна быть от 0 до 10")
        return
    
    target_id = get_user_id_from_input(target_input)
    
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    if target_id not in users:
        try:
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, target_id)
            init_user(chat_member.user)
        except:
            await update.message.reply_text(f"❌ Пользователь {target_input} не найден в чате!")
            return
    
    role_names = {8: "🛡️ Модератор", 9: "👑 Зам. лидера", 10: "💎 Лидер"}
    
    if mod_role == 0:
        users[target_id]["mod_role"] = None
        await update.message.reply_text(f"✅ У *{users[target_id]['name']}* снята модераторская роль", parse_mode=ParseMode.MARKDOWN)
        add_log(user_id, "role_removed", target_id)
    else:
        if mod_role not in role_names:
            await update.message.reply_text("❌ Роль может быть: 8, 9, 10")
            return
        
        users[target_id]["mod_role"] = mod_role
        await update.message.reply_text(f"✅ *{users[target_id]['name']}* получил роль: {role_names[mod_role]}", parse_mode=ParseMode.MARKDOWN)
        add_log(user_id, "role_granted", target_id, f"роль {mod_role}")
        
        try:
            await context.bot.send_message(
                target_id,
                f"🎉 *Поздравляем!*\n\nТы получил роль: {role_names[mod_role]}\n\nТеперь ты можешь использовать команды модерации!",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass

async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдать доступ (8-модер, 9-зам, 10-лидер)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS and users.get(user_id, {}).get("mod_role", 0) != 10:
        await update.message.reply_text("⛔ Нет прав! Только лидер может выдавать доступ!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /giveaccess [@username или user_id] [8-10]\n\n8 - Модератор\n9 - Зам. лидера\n10 - Лидер\n\nПример: /giveaccess @username 8")
        return
    
    target_input = context.args[0]
    try:
        level = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат уровня!")
        return
    
    if level not in [8, 9, 10]:
        await update.message.reply_text("❌ Уровень доступа: 8-модер, 9-зам, 10-лидер")
        return
    
    target_id = get_user_id_from_input(target_input)
    
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    if target_id not in users:
        try:
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, target_id)
            init_user(chat_member.user)
        except:
            await update.message.reply_text("❌ Пользователь не найден в чате!")
            return
    
    role_names = {8: "🛡️ Модератор", 9: "👑 Зам. лидера", 10: "💎 Лидер"}
    users[target_id]["mod_role"] = level
    
    await update.message.reply_text(f"✅ *{users[target_id]['name']}* получил доступ: {role_names[level]}", parse_mode=ParseMode.MARKDOWN)
    add_log(user_id, "give_access", target_id, f"уровень {level}")
    
    try:
        await context.bot.send_message(
            target_id,
            f"🎉 *Поздравляем!*\n\nТы получил роль: {role_names[level]}\n\nТеперь ты можешь использовать команды модерации!",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список участников с их ролями"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS and users.get(user_id, {}).get("mod_role", 0) < 8:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if not users:
        await update.message.reply_text("📋 Список пуст")
        return
    
    text = "📋 *СПИСОК УЧАСТНИКОВ*\n\n"
    for uid, u in list(users.items())[:50]:
        mod_role = ""
        mod_role_num = u.get("mod_role", 0)
        if mod_role_num == 8:
            mod_role = " [🛡️Мод]"
        elif mod_role_num == 9:
            mod_role = " [👑Зам]"
        elif mod_role_num == 10:
            mod_role = " [💎Лид]"
        
        text += f"• {u['nickname'] or u['name']} ({uid}){mod_role} — ранг {u['role']}\n"
        if len(text) > 4000:
            text += "\n... и другие"
            break
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def grole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Игровая роль (0-10)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS and users.get(user_id, {}).get("mod_role", 0) < 8:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /grole [@username или user_id] [0-10]\n\n0 - сбросить до 2 ранга\n\nПример: /grole @username 5")
        return
    
    target_input = context.args[0]
    try:
        role = int(context.args[1])
    except:
        await update.message.reply_text("❌ Неверный формат роли!")
        return
    
    if role < 0 or role > 10:
        await update.message.reply_text("❌ Роль должна быть от 0 до 10")
        return
    
    target_id = get_user_id_from_input(target_input)
    
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    if target_id not in users:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    if role == 0:
        users[target_id]["role"] = 2
        await update.message.reply_text(f"✅ У *{users[target_id]['name']}* игровая роль сброшена до Новичка")
    else:
        users[target_id]["role"] = role
        await update.message.reply_text(f"✅ *{users[target_id]['name']}* получил игровой ранг: {get_rank_name(role)}", parse_mode=ParseMode.MARKDOWN)
    
    add_log(user_id, "grole", target_id, f"ранг {role}")

async def gnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Дать ник пользователю"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS and users.get(user_id, {}).get("mod_role", 0) < 8:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /gnick [@username или user_id] [ник]\n\nПример: /gnick @username Крутой_Чел")
        return
    
    target_input = context.args[0]
    nickname = ' '.join(context.args[1:])[:50]
    
    target_id = get_user_id_from_input(target_input)
    
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь {target_input} не найден!")
        return
    
    if target_id not in users:
        await update.message.reply_text("❌ Пользователь не найден")
        return
    
    users[target_id]["nickname"] = nickname
    await update.message.reply_text(f"✅ *{users[target_id]['name']}* получил ник: {nickname}", parse_mode=ParseMode.MARKDOWN)
    add_log(user_id, "gnick", target_id, nickname)

async def roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает роли всех участников"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS and users.get(user_id, {}).get("mod_role", 0) < 8:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    if not users:
        await update.message.reply_text("Нет участников")
        return
    
    text = "👑 *РОЛИ УЧАСТНИКОВ*\n\n"
    for uid, u in list(users.items())[:50]:
        mod_text = ""
        mod_role = u.get("mod_role", 0)
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
    """Призвать всех (push)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMINS and users.get(user_id, {}).get("mod_role", 0) < 8:
        await update.message.reply_text("⛔ Нет прав! Требуется роль 8+")
        return
    
    mentions = []
    for uid, u in users.items():
        if u.get("username"):
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
    
    add_log(user_id, "all_push")

# ========== ТОП И СТАТИСТИКА ==========
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(users.values(), key=lambda x: x["msgs"], reverse=True)[:10]
    
    text = "📊 *ТОП ПО СООБЩЕНИЯМ* 📊\n\n"
    for i, u in enumerate(sorted_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        name = u["nickname"] or u["name"]
        text += f"{medal} {name} — {u['msgs']} сообщений\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    online_users = []
    offline_users = []
    
    for uid, u in users.items():
        if (now - u["last_online"]).seconds < 300:
            online_users.append(u)
        else:
            offline_users.append(u)
    
    text = f"🟢 *ОНЛАЙН ({len(online_users)}):*\n\n"
    for u in online_users[:20]:
        text += f"• {u['nickname'] or u['name']} ({get_rank_emoji(u['role'])} ранг {u['role']})\n"
    
    text += f"\n⚫ *ОФФЛАЙН ({len(offline_users)}):*\n\n"
    for u in offline_users[:10]:
        last = u["last_online"].strftime('%H:%M %d.%m')
        text += f"• {u['nickname'] or u['name']} — был {last}\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check [ник]")
        return
    
    nickname = ' '.join(context.args).lower()
    found = None
    
    for uid, u in users.items():
        if u.get("nickname") and u["nickname"].lower() == nickname:
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
        if found.get("mod_role") == 8:
            mod_text = " | 🛡️ Модер"
        elif found.get("mod_role") == 9:
            mod_text = " | 👑 Зам"
        elif found.get("mod_role") == 10:
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

# ========== РАЗВЛЕЧЕНИЯ ==========
async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("💋 Ответь на сообщение!")
        return
    
    user, target = update.effective_user, update.message.reply_to_message.from_user
    if user.id == target.id:
        await update.message.reply_text("😳 Нельзя себя!")
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
        await update.message.reply_text("🤗 Обними кого-то!")
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
        await update.message.reply_text("😅 Нельзя себя!")
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
        await update.message.reply_text("❓ /me [действие]")
        return
    
    action = ' '.join(context.args)
    await update.message.reply_text(f"* {update.effective_user.first_name} {action}")
    add_log(update.effective_user.id, f"me: {action}")

async def try_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❓ /try [действие]")
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
    if users:
        target = random.choice(list(users.values()))
        name = target["nickname"] or target["name"]
        await update.message.reply_text(f"🏳️‍🌈 *Гей дня:* {name}! 🏳️‍🌈", parse_mode=ParseMode.MARKDOWN)

async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if users:
        target = random.choice(list(users.values()))
        name = target["nickname"] or target["name"]
        await update.message.reply_text(f"🤡 *Клоун дня:* {name}! 🤡", parse_mode=ParseMode.MARKDOWN)

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

# ========== КНОПКИ ==========
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
                weddings.append({
                    "user1": user1,
                    "user2": user2,
                    "date": datetime.now(),
                    "divorced": False
                })
                try:
                    user1_obj = await context.bot.get_chat_member(query.message.chat.id, user1)
                    user2_obj = await context.bot.get_chat_member(query.message.chat.id, user2)
                    init_user(user1_obj.user)
                    init_user(user2_obj.user)
                    users[user1]["spouse"] = user2
                    users[user2]["spouse"] = user1
                except:
                    pass
                
                await query.message.edit_text(
                    f"💍 *ПОЗДРАВЛЯЕМ!*\n\n"
                    f"Брак между {users[user1]['name']} и {users[user2]['name']} заключен! 🎉",
                    parse_mode=ParseMode.MARKDOWN
                )
                del pending_weddings[key]
            else:
                await query.answer("✅ Ожидание ответа второй стороны...")
                await query.message.edit_text(
                    f"💍 *{users[user1]['name']}* предлагает брак *{users[user2]['name']}*\n\n"
                    f"✅ {query.from_user.first_name} согласился(ась)!\n"
                    f"⏳ Ожидание второй стороны...",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Да, согласен", callback_data=f"wedding_accept_{user1}_{user2}"),
                         InlineKeyboardButton("❌ Нет, не согласен", callback_data=f"wedding_decline_{user1}_{user2}")]
                    ])
                )
        else:
            await query.answer("❌ Предложение устарело!", show_alert=True)
    
    elif data.startswith("wedding_decline"):
        parts = data.split("_")
        user1 = int(parts[2])
        user2 = int(parts[3])
        key = f"{user1}_{user2}"
        
        if key in pending_weddings:
            del pending_weddings[key]
            await query.message.edit_text(f"💔 Брак отклонен {query.from_user.first_name}!", parse_mode=ParseMode.MARKDOWN)
            await query.answer("❌ Вы отклонили предложение")
        else:
            await query.answer("❌ Предложение устарело!", show_alert=True)

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
async def all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user = update.effective_user
    
    if user.id in bans and bans[user.id] > datetime.now():
        try:
            await update.message.delete()
        except:
            pass
        return
    
    if user.id in mutes and mutes[user.id] > datetime.now():
        try:
            await update.message.delete()
        except:
            pass
        return
    
    init_user(user)
    
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
def main():
    print("🚀 ЗАПУСК NEVERMORE FAMILY BOT...")
    print("🔥 ВСЕ МОДУЛИ АКТИВИРОВАНЫ!")
    print("📝 50+ КОМАНД ГОТОВЫ К РАБОТЕ!")
    
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
    print("🤖 ВСЕ КОМАНДЫ ГОТОВЫ К ИСПОЛЬЗОВАНИЮ!")
    print("🔥 FAM NEVERMORE ONLINE!")
    
    app.run_polling()

if __name__ == "__main__":
    main()