import logging
import json
import asyncio
import random
import re
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode
from telegram import Bot
from telegram.error import TelegramError

# --- Настройки ---
BOT_TOKEN = '8702619122:AAGkrADExDJjBl58r7w8e9mNm7MEOtBKANk'  # Токен бота
DB_CHANNEL_ID = -1003883431431  # ID канала для БД
ADMIN_IDS = [1784442476, 1389740970, 5695593671]  # ID админов
CHAT_ID = -1002501760414  # ID чата Nevermore (группа)

# Ранги (ключ: уровень, значение: название и описание)
RANKS = {
    2: {"name": "👶 Новичок", "description": "• У вас есть 6 машин в автопарке\n• фри ранг в дс с гайдами\n• советы для новичков\n• топ работы\n• скрипты\n• как расширить инвентарь"},
    3: {"name": "🏎 Любитель скорости", "description": "• Доступен средний автопарк\n• Можете выбрать себе любой тег\n• Карта с секретными персонажами\n• Получение наёмного фермера\n\nВы так же можете приобрести 3 ранг за смену фамилии на Nevermore, цена 20кк"},
    4: {"name": "🎓 Образованный", "description": "• Куда вложить первые деньги?\n• Что делать при старте игры?\n• Как узнать цену на любой товар?\n\nЦена 30кк"},
    5: {"name": "🌑 Невермор", "description": "• Полезные инвестиции, куда вложить чтобы сделать больше\n• Расскажем как зарабатывать афк\n• Открыт доступ к полезным скриптам\n\nЦена 40кк"},
    6: {"name": "💡 Шарющий", "description": "• Доступен улучшенный автопарк\n• Ответы на клады\n• Как получить тайник VC\n• Как заработать много денег\n• Как заработать азекоины\n\nЦена 60кк"},
    7: {"name": "💰 Барыга", "description": "• Доступ к гайдам:\n  - как ловить лавки на цр\n  - как барыжить на цр\n  - конфиги для скупки на цр\n\nЦена 70кк"},
    8: {"name": "💎 Премиум", "description": "• Доступен абсолютно весь автопарк\n• Доступны все гайды:\n  + мой опыт фарма\n• Любой тег\n• Чат с лидером семьи, отвечу на любые вопросы, в любое время\n• Как выбивать тачки с ларцов\n• Анти-кик с фамы (можете в ней находиться хоть год, вас не кикнут)\n• Как фармить новые клады\n\nЦена 100кк"},
    9: {"name": "👑 Зам. Лидера", "description": "Правая рука лидера."},
    10: {"name": "👑👑 Лидер", "description": "Глава семьи Nevermore."},
}

# Настройки модерации
WARNS_TO_BAN = 3
BAN_DAYS = 5
MUTE_DAYS = 1  # Стандартное время мута в днях, если не указано

# Смайлики для красоты
EMOJI = {
    "warn": "⚠️",
    "ban": "🔨",
    "mute": "🔇",
    "unmute": "🔊",
    "info": "ℹ️",
    "success": "✅",
    "error": "❌",
    "heart": "❤️",
    "crown": "👑",
    "game": "🎮",
    "profile": "👤",
    "list": "📜",
    "rules": "📏",
    "rep": "⭐",
    "online": "🟢",
    "offline": "⚫",
    "wedding": "💍",
    "gay": "🏳️‍🌈",
    "clown": "🤡",
    "wish": "✨",
}

# --- Telegram Storage вместо SQLite ---
class TelegramDB:
    def __init__(self, token, channel_id):
        self.bot = Bot(token=token)
        self.channel_id = channel_id
        self.cache = None
        self.last_update_id = 0
        
    async def load(self):
        """Загружает базу данных из Telegram канала"""
        try:
            # Получаем последние сообщения из канала
            updates = await self.bot.get_updates(offset=self.last_update_id, limit=10)
            
            for update in updates:
                if update.message and update.message.text:
                    if update.message.text.startswith('DB_BACKUP'):
                        # Нашли бэкап
                        json_str = update.message.text[9:]  # Убираем 'DB_BACKUP'
                        self.cache = json.loads(json_str)
                        self.last_update_id = update.update_id + 1
                        print(f"✅ База данных загружена из Telegram. Записей: {len(self.cache.get('users', {}))}")
                        return self.cache
                        
            # Если ничего не нашли, создаем пустую БД
            print("⚠️ База данных не найдена, создаем новую")
            self.cache = {
                'users': {},
                'mutes': {},
                'bans': {},
                'warns': {},
                'weddings': [],
                'logs': [],
                'next_id': 1
            }
            await self.save()  # Сохраняем пустую БД
            return self.cache
            
        except Exception as e:
            print(f"❌ Ошибка загрузки БД: {e}")
            # Создаем пустую БД в памяти
            self.cache = {
                'users': {},
                'mutes': {},
                'bans': {},
                'warns': {},
                'weddings': [],
                'logs': [],
                'next_id': 1
            }
            return self.cache
    
    async def save(self):
        """Сохраняет базу данных в Telegram канал"""
        try:
            if not self.cache:
                return
                
            # Превращаем в JSON
            json_str = json.dumps(self.cache, ensure_ascii=False, indent=2, default=str)
            
            # Отправляем в канал
            message = await self.bot.send_message(
                chat_id=self.channel_id,
                text=f"DB_BACKUP{json_str}"
            )
            
            # Удаляем старые бэкапы (оставляем только последние 3)
            updates = await self.bot.get_updates(limit=20)
            backups = []
            
            for update in updates:
                if update.message and update.message.text and update.message.text.startswith('DB_BACKUP'):
                    backups.append((update.message.message_id, update.message.date))
            
            # Сортируем по дате (новые в начале)
            backups.sort(key=lambda x: x[1], reverse=True)
            
            # Удаляем старые (начиная с 4-го)
            for msg_id, _ in backups[3:]:
                try:
                    await self.bot.delete_message(chat_id=self.channel_id, message_id=msg_id)
                except:
                    pass
                    
            print(f"✅ База данных сохранена в Telegram. Сообщение ID: {message.message_id}")
            
        except Exception as e:
            print(f"❌ Ошибка сохранения БД: {e}")
    
    # --- Методы для работы с данными ---
    def get_user(self, user_id):
        return self.cache['users'].get(str(user_id))
    
    def update_user(self, user_id, data):
        self.cache['users'][str(user_id)] = data
        
    def add_user(self, user_id, username, first_name):
        if str(user_id) not in self.cache['users']:
            self.cache['users'][str(user_id)] = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'nickname': None,
                'rank': 2,
                'warns': 0,
                'reputation': 0,
                'joined_date': datetime.now().isoformat(),
                'spouse_id': None,
                'prefix': None,
                'last_online': datetime.now().isoformat()
            }
            return True
        return False
    
    def add_log(self, user_id, username, action):
        log_entry = {
            'id': self.cache.get('next_id', 1),
            'user_id': user_id,
            'username': username,
            'action': action,
            'timestamp': datetime.now().isoformat()
        }
        self.cache['logs'].append(log_entry)
        self.cache['next_id'] = self.cache.get('next_id', 1) + 1
        
        # Ограничиваем размер логов
        if len(self.cache['logs']) > 1000:
            self.cache['logs'] = self.cache['logs'][-1000:]
    
    def add_mute(self, user_id, muted_until, reason):
        self.cache['mutes'][str(user_id)] = {
            'user_id': user_id,
            'muted_until': muted_until.isoformat() if isinstance(muted_until, datetime) else muted_until,
            'reason': reason
        }
    
    def remove_mute(self, user_id):
        if str(user_id) in self.cache['mutes']:
            del self.cache['mutes'][str(user_id)]
    
    def get_mute(self, user_id):
        return self.cache['mutes'].get(str(user_id))
    
    def add_ban(self, user_id, banned_until, reason):
        self.cache['bans'][str(user_id)] = {
            'user_id': user_id,
            'banned_until': banned_until.isoformat() if isinstance(banned_until, datetime) else banned_until,
            'reason': reason
        }
    
    def remove_ban(self, user_id):
        if str(user_id) in self.cache['bans']:
            del self.cache['bans'][str(user_id)]
    
    def get_ban(self, user_id):
        return self.cache['bans'].get(str(user_id))
    
    def add_wedding(self, user1_id, user2_id):
        wedding = {
            'id': len(self.cache['weddings']) + 1,
            'user1_id': user1_id,
            'user2_id': user2_id,
            'date': datetime.now().isoformat()
        }
        self.cache['weddings'].append(wedding)
        return wedding
    
    def get_all_users(self):
        return list(self.cache['users'].values())
    
    def get_all_mutes(self):
        return list(self.cache['mutes'].values())
    
    def get_all_bans(self):
        return list(self.cache['bans'].values())
    
    def get_all_logs(self, limit=20):
        return self.cache['logs'][-limit:]
    
    def get_all_weddings(self):
        return self.cache['weddings']

# --- Инициализация БД ---
db = None

async def init_db():
    global db
    db = TelegramDB(BOT_TOKEN, DB_CHANNEL_ID)
    await db.load()

# --- Функции-помощники для работы с БД (адаптированные) ---
def get_user(user_id):
    return db.get_user(user_id)

def update_user_rank(user_id, new_rank):
    user = db.get_user(user_id)
    if user:
        user['rank'] = new_rank
        db.update_user(user_id, user)

def add_warn(user_id):
    user = db.get_user(user_id)
    if user:
        user['warns'] = user.get('warns', 0) + 1
        db.update_user(user_id, user)
        if user['warns'] >= WARNS_TO_BAN:
            return True  # Пора банить
    return False

def log_action(user_id, username, action):
    db.add_log(user_id, username, action)

def get_user_rank(user_id):
    user = db.get_user(user_id)
    return user['rank'] if user else 2

def is_muted(user_id):
    mute = db.get_mute(user_id)
    if mute:
        mute_until = datetime.fromisoformat(mute['muted_until'])
        if mute_until > datetime.now():
            return True
        else:
            db.remove_mute(user_id)
    return False

def is_banned(user_id):
    ban = db.get_ban(user_id)
    if ban:
        ban_until = datetime.fromisoformat(ban['banned_until'])
        if ban_until > datetime.now():
            return True
        else:
            db.remove_ban(user_id)
    return False

# --- Проверка прав ---
def has_permission(user_id, required_rank):
    """Проверяет, есть ли у пользователя ранг не ниже required_rank."""
    user_rank = get_user_rank(user_id)
    return user_rank >= required_rank

# --- Команды (с адаптацией под TelegramDB) ---

# 1. Приветствие новых участников
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        # Добавляем в БД
        db.add_user(member.id, member.username, member.first_name)
        
        welcome_text = (
            f"👋 {member.full_name}, добро пожаловать в группу Fam Nevermore!\n\n"
            f"📝 Напиши, пожалуйста, свой ник в авторизацию в течение 24 часов, иначе кик.\n"
            f"📖 Просим ознакомиться с правилами чата: https://t.me/famnevermore/26\n"
            f"🔑 Ссылка на авторизацию: https://t.me/famnevermore/19467\n\n"
            f"Приятного общения! {EMOJI['heart']}"
        )
        await update.message.reply_text(welcome_text)
        log_action(member.id, member.username, "joined the chat")
    
    # Сохраняем БД после изменений
    await db.save()

# 2. /mute
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 8):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы замутить его.")
        return

    target_user = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Не указана"
    mute_time = datetime.now() + timedelta(days=MUTE_DAYS)

    db.add_mute(target_user.id, mute_time, reason)

    await update.message.reply_text(
        f"{EMOJI['mute']} Пользователь {target_user.full_name} замучен до {mute_time.strftime('%Y-%m-%d %H:%M')}.\nПричина: {reason}"
    )
    log_action(update.effective_user.id, update.effective_user.username, f"muted {target_user.id}")
    await db.save()

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 8):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы размутить его.")
        return

    target_user = update.message.reply_to_message.from_user
    db.remove_mute(target_user.id)

    await update.message.reply_text(f"{EMOJI['unmute']} Пользователь {target_user.full_name} размучен.")
    log_action(update.effective_user.id, update.effective_user.username, f"unmuted {target_user.id}")
    await db.save()

# 3. /ban
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 8):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы забанить его.")
        return

    target_user = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Нарушение правил"
    ban_time = datetime.now() + timedelta(days=BAN_DAYS)

    db.add_ban(target_user.id, ban_time, reason)

    await update.message.reply_text(
        f"{EMOJI['ban']} Пользователь {target_user.full_name} забанен до {ban_time.strftime('%Y-%m-%d %H:%M')}.\nПричина: {reason}"
    )
    log_action(update.effective_user.id, update.effective_user.username, f"banned {target_user.id}")

    # Пытаемся кикнуть
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
    except:
        pass  # Если бот не админ в чате, просто логируем
    
    await db.save()

# 4. /warn
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 8):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы выдать предупреждение.")
        return

    target_user = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Нарушение правил"

    # Добавляем варн
    if add_warn(target_user.id):
        # 3 варна -> бан
        ban_time = datetime.now() + timedelta(days=BAN_DAYS)
        db.add_ban(target_user.id, ban_time, f"3 предупреждения: {reason}")
        await update.message.reply_text(
            f"{EMOJI['ban']} Пользователь {target_user.full_name} получил 3-е предупреждение и забанен на {BAN_DAYS} дней."
        )
        log_action(update.effective_user.id, update.effective_user.username, f"auto-banned {target_user.id} (3 warns)")
    else:
        user = get_user(target_user.id)
        warns_count = user['warns'] if user else 0
        await update.message.reply_text(
            f"{EMOJI['warn']} Пользователь {target_user.full_name} получил предупреждение ({warns_count}/{WARNS_TO_BAN}).\nПричина: {reason}"
        )
        log_action(update.effective_user.id, update.effective_user.username, f"warned {target_user.id}")
    
    await db.save()

# 5. /setname
async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 8):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы установить ему ник.")
        return

    target_user = update.message.reply_to_message.from_user
    new_nick = " ".join(context.args)
    if not new_nick:
        await update.message.reply_text("Укажи новый ник. Пример: /setname Diego_Retroware")
        return

    user = get_user(target_user.id)
    if user:
        user['nickname'] = new_nick
        db.update_user(target_user.id, user)
        await update.message.reply_text(f"{EMOJI['success']} Ник для {target_user.full_name} установлен: {new_nick}")
        log_action(update.effective_user.id, update.effective_user.username, f"setname {target_user.id} to {new_nick}")
        await db.save()

# 6. /giveaccess (выдать ранг 8,9,10)
async def giveaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 10):
        await update.message.reply_text(f"{EMOJI['error']} Только лидер может выдавать высокие ранги.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы выдать ему ранг.")
        return

    target_user = update.message.reply_to_message.from_user
    if not context.args:
        await update.message.reply_text("Укажи ранг (8, 9 или 10). Пример: /giveaccess 8")
        return

    try:
        new_rank = int(context.args[0])
        if new_rank not in [8, 9, 10]:
            await update.message.reply_text("Ранг должен быть 8 (модер), 9 (зам) или 10 (лидер).")
            return
    except ValueError:
        await update.message.reply_text("Ранг должен быть числом.")
        return

    user = get_user(target_user.id)
    if user:
        user['rank'] = new_rank
        db.update_user(target_user.id, user)
        await update.message.reply_text(
            f"{EMOJI['crown']} Пользователь {target_user.full_name} теперь имеет ранг {new_rank}: {RANKS[new_rank]['name']}"
        )
        log_action(update.effective_user.id, update.effective_user.username, f"gave rank {new_rank} to {target_user.id}")
        await db.save()

# 7. /setprefix
async def setprefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 8):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы установить ему префикс.")
        return

    target_user = update.message.reply_to_message.from_user
    prefix = " ".join(context.args)
    if not prefix:
        await update.message.reply_text("Укажи префикс. Пример: /setprefix [Admin]")
        return

    user = get_user(target_user.id)
    if user:
        user['prefix'] = prefix
        db.update_user(target_user.id, user)
        await update.message.reply_text(f"{EMOJI['success']} Префикс для {target_user.full_name} установлен: {prefix}")
        log_action(update.effective_user.id, update.effective_user.username, f"setprefix for {target_user.id}")
        await db.save()

# 8. /nlist (список ников)
async def nlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    if not users:
        await update.message.reply_text("Список пуст.")
        return

    text = f"{EMOJI['list']} Список игроков:\n"
    for user in users:
        name = user.get('nickname') or user.get('username') or f"id{user['user_id']}"
        text += f"• {name} (ранг {user['rank']})\n"

    await update.message.reply_text(text[:4096])

# 9. /grank (дать игровую роль)
async def grank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 8):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы выдать ему ранг.")
        return

    target_user = update.message.reply_to_message.from_user
    if not context.args:
        await update.message.reply_text("Укажи ранг (2-10, кроме 1 и 9 если надо). Пример: /grank 5")
        return

    try:
        new_rank = int(context.args[0])
        if new_rank < 2 or new_rank > 10:
            await update.message.reply_text("Ранг должен быть от 2 до 10.")
            return
    except ValueError:
        await update.message.reply_text("Ранг должен быть числом.")
        return

    user = get_user(target_user.id)
    if user:
        user['rank'] = new_rank
        db.update_user(target_user.id, user)
        await update.message.reply_text(
            f"{EMOJI['game']} Пользователь {target_user.full_name} теперь имеет игровой ранг {new_rank}: {RANKS[new_rank]['name']}"
        )
        log_action(update.effective_user.id, update.effective_user.username, f"grank {new_rank} to {target_user.id}")
        await db.save()

# 10. /gnick (дать ник тг пользователю)
async def gnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 2):  # Все могут ставить себе ник
        return

    if not context.args:
        await update.message.reply_text("Укажи свой ник. Пример: /gnick Diego_Retroware")
        return

    new_nick = " ".join(context.args)
    user = get_user(update.effective_user.id)
    if user:
        user['nickname'] = new_nick
        db.update_user(update.effective_user.id, user)
        await update.message.reply_text(f"{EMOJI['success']} Твой ник установлен: {new_nick}")
        log_action(update.effective_user.id, update.effective_user.username, f"set own nick to {new_nick}")
        await db.save()

# 11. /ranks (показывает ранги)
async def ranks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"{EMOJI['list']} Доступные ранги в семье Nevermore:\n\n"
    for rank_num, rank_data in RANKS.items():
        if rank_num == 9 or rank_num == 10:
            text += f"<b>{rank_num}. {rank_data['name']}</b>\n{rank_data['description']}\n\n"
        else:
            text += f"<b>{rank_num}. {rank_data['name']}</b>\n{rank_data['description']}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# 12. /warns (показывает варны)
async def warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = [u for u in db.get_all_users() if u.get('warns', 0) > 0]
    users.sort(key=lambda x: x.get('warns', 0), reverse=True)
    
    if not users:
        await update.message.reply_text(f"{EMOJI['info']} Нет пользователей с предупреждениями.")
        return

    text = f"{EMOJI['warn']} Список предупреждений:\n"
    for user in users:
        name = user.get('nickname') or user.get('username') or f"id{user['user_id']}"
        text += f"• {name} — {user.get('warns', 0)} варн(ов)\n"
    await update.message.reply_text(text)

# 13. /bans (забаненные)
async def bans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bans_list = db.get_all_bans()
    if not bans_list:
        await update.message.reply_text(f"{EMOJI['info']} Нет забаненных пользователей.")
        return

    text = f"{EMOJI['ban']} Забаненные пользователи:\n"
    now = datetime.now()
    for ban in bans_list:
        ban_until = datetime.fromisoformat(ban['banned_until'])
        if ban_until > now:
            text += f"• id{ban['user_id']} — до {ban_until.strftime('%Y-%m-%d')}, причина: {ban['reason']}\n"
    await update.message.reply_text(text)

# 14. /mutelist
async def mutelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mutes = db.get_all_mutes()
    if not mutes:
        await update.message.reply_text(f"{EMOJI['info']} Нет замученных пользователей.")
        return

    text = f"{EMOJI['mute']} Замученные пользователи:\n"
    now = datetime.now()
    for mute in mutes:
        mute_until = datetime.fromisoformat(mute['muted_until'])
        if mute_until > now:
            text += f"• id{mute['user_id']} — до {mute_until.strftime('%Y-%m-%d %H:%M')}, причина: {mute['reason']}\n"
    await update.message.reply_text(text)

# 15. /logs
async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 9):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    logs_list = db.get_all_logs(20)
    if not logs_list:
        await update.message.reply_text("Логов нет.")
        return

    text = f"{EMOJI['list']} Последние действия:\n"
    for log in logs_list:
        ts = log['timestamp'][:16] if len(log['timestamp']) > 16 else log['timestamp']
        text += f"• {log['username']} — {log['action']} ({ts})\n"
    await update.message.reply_text(text[:4096])

# 16. /all
async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 9):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    await update.message.reply_text(f"{EMOJI['info']} Внимание, семья! {update.effective_user.full_name} обращается ко всем!")

# 17. /wedding
async def wedding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 2):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы предложить ему/ей руку и сердце.")
        return

    user1 = update.effective_user
    user2 = update.message.reply_to_message.from_user

    if user1.id == user2.id:
        await update.message.reply_text("Нельзя жениться на самом себе!")
        return

    # Проверяем, не женаты ли уже
    weddings = db.get_all_weddings()
    for w in weddings:
        if w['user1_id'] == user1.id or w['user2_id'] == user1.id or w['user1_id'] == user2.id or w['user2_id'] == user2.id:
            await update.message.reply_text("Один из вас уже состоит в браке.")
            return

    # Создаем свадьбу
    db.add_wedding(user1.id, user2.id)
    
    user1_data = get_user(user1.id)
    user2_data = get_user(user2.id)
    
    if user1_data:
        user1_data['spouse_id'] = user2.id
        db.update_user(user1.id, user1_data)
    if user2_data:
        user2_data['spouse_id'] = user1.id
        db.update_user(user2.id, user2_data)

    await update.message.reply_text(
        f"{EMOJI['wedding']} Поздравляем! {user1.full_name} и {user2.full_name} теперь муж и жена! {EMOJI['heart']}"
    )
    log_action(user1.id, user1.username, f"married {user2.id}")
    await db.save()

# 18. /weddings (список свадеб)
async def weddings_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    weddings = db.get_all_weddings()
    if not weddings:
        await update.message.reply_text(f"{EMOJI['info']} Свадеб пока нет.")
        return

    text = f"{EMOJI['wedding']} Семейные пары:\n"
    for w in weddings:
        user1 = get_user(w['user1_id'])
        user2 = get_user(w['user2_id'])
        name1 = user1.get('nickname') or user1.get('username') or f"id{w['user1_id']}" if user1 else f"id{w['user1_id']}"
        name2 = user2.get('nickname') or user2.get('username') or f"id{w['user2_id']}" if user2 else f"id{w['user2_id']}"
        date = w['date'][:10]
        text += f"• {name1} + {name2} (с {date})\n"
    await update.message.reply_text(text)

# 19. /top
async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    users.sort(key=lambda x: x.get('reputation', 0), reverse=True)
    users = users[:10]
    
    if not users:
        await update.message.reply_text("Нет данных.")
        return

    text = f"{EMOJI['rep']} Топ по репутации:\n"
    for i, user in enumerate(users, 1):
        name = user.get('nickname') or user.get('username') or "Без имени"
        rep = user.get('reputation', 0)
        text += f"{i}. {name} — {rep} ⭐\n"
    await update.message.reply_text(text)

# 20. /me
async def me_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = " ".join(context.args)
    if not action:
        await update.message.reply_text("Напиши действие. Пример: /me поправил корону на голове")
        return
    user = update.effective_user
    text = f"<i>{user.full_name} {action}</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# 21. /try
async def try_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = " ".join(context.args)
    if not action:
        await update.message.reply_text("Напиши действие. Пример: /try запрыгнуть на крышу")
        return
    success = random.choice(["Удачно! ✅", "Неудачно... ❌", "Критический успех! 💥", "Эпик фейл! 💩"])
    user = update.effective_user
    text = f"<i>{user.full_name} пытается {action}...\n{success}</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# 22. /kiss
async def kiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы поцеловать его.")
        return
    user1 = update.effective_user
    user2 = update.message.reply_to_message.from_user
    text = f"{EMOJI['heart']} {user1.full_name} нежно поцеловал(а) {user2.full_name}!"
    await update.message.reply_text(text)

# 23. /slap
async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы дать ему пощечину.")
        return
    variants = [
        "сильно, аж искры из глаз! ⚡",
        "любя, как родного 💕",
        "с размаху! 🤚",
        "мокрой тряпкой! 🧹",
        "газетой! 📰"
    ]
    user1 = update.effective_user
    user2 = update.message.reply_to_message.from_user
    text = f"{user1.full_name} дал пощечину {user2.full_name} {random.choice(variants)}"
    await update.message.reply_text(text)

# 24. /hug
async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы обнять его.")
        return
    user1 = update.effective_user
    user2 = update.message.reply_to_message.from_user
    text = f"{EMOJI['heart']} {user1.full_name} крепко обнял(а) {user2.full_name}!"
    await update.message.reply_text(text)

# 25. /rep+ и /rep-
async def rep_plus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы изменить его репутацию.")
        return
    target = update.message.reply_to_message.from_user
    if target.id == update.effective_user.id:
        await update.message.reply_text("Нельзя менять репутацию самому себе.")
        return
    
    user = get_user(target.id)
    if user:
        user['reputation'] = user.get('reputation', 0) + 1
        db.update_user(target.id, user)
        await update.message.reply_text(f"{EMOJI['rep']} Репутация {target.full_name} повышена!")
        await db.save()

async def rep_minus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение пользователя, чтобы изменить его репутацию.")
        return
    target = update.message.reply_to_message.from_user
    if target.id == update.effective_user.id:
        await update.message.reply_text("Нельзя менять репутацию самому себе.")
        return
    
    user = get_user(target.id)
    if user:
        user['reputation'] = user.get('reputation', 0) - 1
        db.update_user(target.id, user)
        await update.message.reply_text(f"{EMOJI['rep']} Репутация {target.full_name} понижена!")
        await db.save()

# 26. /profile
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id)
    if not data:
        await update.message.reply_text("Ты не зарегистрирован. Напиши что-нибудь в чат.")
        return

    spouse_name = "Нет"
    if data.get('spouse_id'):
        spouse = get_user(data['spouse_id'])
        if spouse:
            spouse_name = spouse.get('nickname') or spouse.get('username') or f"id{data['spouse_id']}"

    rank_name = RANKS.get(data['rank'], {}).get('name', 'Неизвестно')
    text = (
        f"{EMOJI['profile']} <b>Профиль {data.get('nickname') or data.get('username') or data.get('first_name')}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👤 Ранг: {rank_name} ({data['rank']})\n"
        f"{EMOJI['rep']} Репутация: {data.get('reputation', 0)}\n"
        f"{EMOJI['warn']} Варны: {data.get('warns', 0)}\n"
        f"{EMOJI['wedding']} Супруг(а): {spouse_name}\n"
        f"📅 В семье с: {data.get('joined_date', '')[:10]}\n"
        f"🏷 Префикс: {data.get('prefix') or 'Нет'}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# 27. /info
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"{EMOJI['info']} <b>Семья Nevermore</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👑 Лидер: @username_leader (замени)\n"
        f"💬 Дискорд: https://discord.gg/...\n"
        f"📢 Новости: https://t.me/famnevermore/...\n"
        f"📖 Правила: https://t.me/famnevermore/26\n"
        f"🔑 Авторизация: https://t.me/famnevermore/19467\n\n"
        f"Бот создан для уюта и порядка в семье. Не забывай про уважение!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# 28. /report
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответь на сообщение, на которое хочешь пожаловаться.")
        return

    reason = " ".join(context.args) if context.args else "Причина не указана"
    bad_msg = update.message.reply_to_message
    bad_user = bad_msg.from_user
    reporter = update.effective_user

    # Найти всех админов (ранг 9 и 10)
    admins = [u for u in db.get_all_users() if u.get('rank', 0) in [9, 10]]
    
    text = (
        f"🚨 <b>Жалоба</b>\n"
        f"От: {reporter.full_name} (@{reporter.username})\n"
        f"На: {bad_user.full_name} (@{bad_user.username})\n"
        f"Причина: {reason}\n"
        f"Сообщение: {bad_msg.text or bad_msg.caption or '[Не текст]'}\n"
        f"[Перейти к сообщению]({bad_msg.link})"
    )

    sent = False
    for admin in admins:
        try:
            await context.bot.send_message(admin['user_id'], text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            sent = True
        except:
            pass

    if sent:
        await update.message.reply_text(f"{EMOJI['success']} Жалоба отправлена администрации.")
    else:
        await update.message.reply_text(f"{EMOJI['error']} Не удалось отправить жалобу (админы недоступны).")

# 29. /check
async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, 8):
        await update.message.reply_text(f"{EMOJI['error']} Недостаточно прав.")
        return

    if not context.args:
        await update.message.reply_text("Укажи ник или имя. Пример: /check Diego_Retroware")
        return

    query = " ".join(context.args).lower()
    
    # Ищем по нику или юзернейму
    found_user = None
    for user in db.get_all_users():
        nickname = user.get('nickname', '').lower() if user.get('nickname') else ''
        username = user.get('username', '').lower() if user.get('username') else ''
        
        if query in nickname or query in username:
            found_user = user
            break

    if not found_user:
        await update.message.reply_text("Пользователь не найден в базе.")
        return

    text = (
        f"🔍 <b>Результат поиска:</b>\n"
        f"ID: {found_user['user_id']}\n"
        f"Username: @{found_user.get('username', 'Нет')}\n"
        f"Ник: {found_user.get('nickname', 'Нет')}\n"
        f"Ранг: {found_user.get('rank', 2)}\n"
        f"Варны: {found_user.get('warns', 0)}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# 30. /online
async def online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    online_users = []
    offline_users = []
    now = datetime.now()

    for user in users:
        last_seen_str = user.get('last_online')
        if last_seen_str:
            last_seen = datetime.fromisoformat(last_seen_str)
        else:
            last_seen = now - timedelta(days=999)
            
        name = user.get('nickname') or user.get('username') or f"id{user['user_id']}"
        
        if (now - last_seen) < timedelta(hours=1):  # Онлайн, если был в чате менее часа назад
            online_users.append(f"{EMOJI['online']} {name} (ранг {user.get('rank', 2)})")
        else:
            offline_users.append(f"{EMOJI['offline']} {name} (был {last_seen.strftime('%Y-%m-%d %H:%M')})")

    text = f"<b>Онлайн ({len(online_users)}):</b>\n"
    text += "\n".join(online_users) if online_users else "Никого нет онлайн\n"
    text += f"\n\n<b>Оффлайн ({len(offline_users)}):</b>\n"
    text += "\n".join(offline_users[:10])  # Показываем только 10 оффлайн
    if len(offline_users) > 10:
        text += f"\n... и еще {len(offline_users)-10}"

    await update.message.reply_text(text[:4096], parse_mode=ParseMode.HTML)

# 31. /gay (гей дня)
async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    if not users:
        await update.message.reply_text("Нет участников в базе.")
        return
    
    gay_of_day = random.choice(users)
    name = gay_of_day.get('nickname') or gay_of_day.get('username') or f"id{gay_of_day['user_id']}"
    await update.message.reply_text(
        f"{EMOJI['gay']} Сегодняшний Гей дня — {name}! Поздравляем! 🎉"
    )

# 32. /clown
async def clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    if not users:
        await update.message.reply_text("Нет участников в базе.")
        return
    
    clown_of_day = random.choice(users)
    name = clown_of_day.get('nickname') or clown_of_day.get('username') or f"id{clown_of_day['user_id']}"
    await update.message.reply_text(
        f"{EMOJI['clown']} Сегодняшний Клоун дня — {name}! Цирк уехал, клоун остался! 🎪"
    )

# 33. /wish
async def wish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wishes = [
        "🍀 Сегодня тебе повезёт в делах!",
        "💵 Ожидай неожиданную прибыль.",
        "❤️ Тебя ждёт романтическая встреча.",
        "😴 Отдохни сегодня, ты заслужил.",
        "🚀 Твой рейтинг скоро взлетит!",
        "🍔 Сегодня лучший день для вкусной еды.",
        "🎮 Удачной игры и фарма!",
        "🤝 Кто-то нуждается в твоей помощи."
    ]
    await update.message.reply_text(f"{EMOJI['wish']} {random.choice(wishes)}")

# 34. /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_rank = get_user_rank(update.effective_user.id)
    commands = {
        2: [
            "/profile - твоя карточка",
            "/info - информация о семье",
            "/gnick <ник> - установить ник",
            "/top - топ репутации",
            "/me - действие от 3-го лица",
            "/try - попытаться сделать что-то",
            "/kiss - поцеловать",
            "/hug - обнять",
            "/slap - дать пощечину",
            "/gay - гей дня",
            "/clown - клоун дня",
            "/wish - пожелание",
            "/rep+ /rep- - репутация",
            "/ranks - список рангов",
            "/nlist - список ников",
            "/wedding - предложить брак",
            "/weddings - список браков",
            "/report - пожаловаться",
        ],
        8: [  # Модератор
            "/mute <причина> - замутить",
            "/unmute - размутить",
            "/warn <причина> - варн",
            "/ban <причина> - бан",
            "/setname <ник> - сменить ник юзеру",
            "/setprefix <префикс> - дать префикс",
            "/grank <ранг> - выдать игровой ранг (2-8)",
            "/check - проверить пользователя",
            "/logs - логи действий",
        ],
        9: [  # Зам
            "/giveaccess <8,9,10> - выдать админку",
            "/all - обратиться ко всем",
        ],
        10: [  # Лидер
            "/giveaccess <8,9,10> - выдать админку",
            "/all - обратиться ко всем",
        ],
    }

    text = f"{EMOJI['info']} <b>Доступные команды (твой ранг: {user_rank}):</b>\n\n"
    shown = set()
    for r in range(2, user_rank + 1):
        if r in commands:
            for cmd in commands[r]:
                if cmd not in shown:
                    text += cmd + "\n"
                    shown.add(cmd)

    if user_rank == 10:
        text += "\n<i>Ты видишь все команды как лидер.</i>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# --- Автоматическая проверка сообщений на нарушения ---
async def check_message_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text.lower()

    # Проверяем, не в муте ли пользователь
    if is_muted(user_id):
        try:
            await update.message.delete()
        except:
            pass
        return

    # Простые правила (можно расширять)
    forbidden_patterns = [
        (r'(ху[йи]|пизд|бля|ебать|сука|пидор)', 60, "Оскорбления"),
        (r'(18\+|порно|секс|эротика|голая)', 120, "Контент 18+"),
        (r'(твою мать|мама|папа|родители)', 120, "Упоминание родителей"),
        (r'(политик|война|путин|зеленский|сша|россия|украина)', 60, "Политика"),
    ]

    for pattern, mute_minutes, rule_name in forbidden_patterns:
        if re.search(pattern, text):
            mute_time = datetime.now() + timedelta(minutes=mute_minutes)
            db.add_mute(user_id, mute_time, f"Нарушение: {rule_name}")
            await update.message.reply_text(
                f"{EMOJI['mute']} {update.effective_user.full_name}, вы замучены на {mute_minutes} минут за нарушение правил ({rule_name}).\n"
                f"Правила: https://t.me/famnevermore/26"
            )
            log_action(user_id, update.effective_user.username, f"auto-muted for {rule_name}")
            try:
                await update.message.delete()
            except:
                pass
            await db.save()
            break

# --- Обновление времени последнего онлайна ---
async def update_last_online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and not update.effective_user.is_bot:
        user = get_user(update.effective_user.id)
        if not user:
            db.add_user(update.effective_user.id, update.effective_user.username, update.effective_user.first_name)
            user = get_user(update.effective_user.id)
        
        if user:
            user['last_online'] = datetime.now().isoformat()
            user['username'] = update.effective_user.username
            db.update_user(update.effective_user.id, user)
            await db.save()

# --- Обработка команды /start в личке ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Привет! Я бот семьи Nevermore. {EMOJI['heart']}\n"
        f"Добавь меня в группу и выдай права администратора для полноценной работы.\n"
        f"В группе используй /help, чтобы узнать доступные команды."
    )

# --- Главная функция для GitHub Actions ---
async def main():
    global db
    print("🚀 Бот запускается...")
    
    # Инициализируем БД
    await init_db()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("warn", warn))
    application.add_handler(CommandHandler("setname", setname))
    application.add_handler(CommandHandler("giveaccess", giveaccess))
    application.add_handler(CommandHandler("setprefix", setprefix))
    application.add_handler(CommandHandler("nlist", nlist))
    application.add_handler(CommandHandler("grank", grank))
    application.add_handler(CommandHandler("gnick", gnick))
    application.add_handler(CommandHandler("ranks", ranks))
    application.add_handler(CommandHandler("warns", warns))
    application.add_handler(CommandHandler("bans", bans))
    application.add_handler(CommandHandler("mutelist", mutelist))
    application.add_handler(CommandHandler("logs", logs))
    application.add_handler(CommandHandler("all", all_command))
    application.add_handler(CommandHandler("wedding", wedding))
    application.add_handler(CommandHandler("weddings", weddings_list))
    application.add_handler(CommandHandler("top", top))
    application.add_handler(CommandHandler("me", me_action))
    application.add_handler(CommandHandler("try", try_action))
    application.add_handler(CommandHandler("kiss", kiss))
    application.add_handler(CommandHandler("slap", slap))
    application.add_handler(CommandHandler("hug", hug))
    application.add_handler(CommandHandler("repplus", rep_plus))
    application.add_handler(CommandHandler("repminus", rep_minus))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CommandHandler("check", check_user))
    application.add_handler(CommandHandler("online", online))
    application.add_handler(CommandHandler("gay", gay))
    application.add_handler(CommandHandler("clown", clown))
    application.add_handler(CommandHandler("wish", wish))

    # Обработчик новых участников
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    # Обработчик всех сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, update_last_online), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message_rules), group=2)

    # Запускаем polling (но он будет работать только пока выполняется GitHub Action)
    print("✅ Бот готов к работе. Начинаем polling...")
    
    # Устанавливаем вебхук (для GitHub Actions лучше использовать polling)
    await application.initialize()
    await application.start()
    
    # Запускаем polling с таймаутом
    await application.updater.start_polling(timeout=30)
    
    # Держим бота запущенным 5 минут (время выполнения GitHub Action)
    await asyncio.sleep(290)  # 5 минут - 10 секунд запас
    
    # Сохраняем БД перед выключением
    print("💾 Сохраняем базу данных...")
    await db.save()
    
    # Останавливаем бота
    print("🛑 Останавливаем бота...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    
    print("👋 Бот завершил работу.")

if __name__ == '__main__':
    asyncio.run(main())
