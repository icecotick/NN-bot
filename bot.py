import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
import random
import os
import sqlite3
import time
from contextlib import closing

# Инициализация базы данных
def init_db():
    with closing(sqlite3.connect('economy.db')) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY, 
                      balance INTEGER DEFAULT 0)''')
        conn.commit()

init_db()

# Функции для работы с валютой
def get_balance(user_id):
    with closing(sqlite3.connect('economy.db')) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

def update_balance(user_id, amount):
    with closing(sqlite3.connect('economy.db')) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        conn.commit()

# Настройка бота
TOKEN = os.getenv("DISCORD_TOKEN")
ROLE_NAME = "Патриот"
CRIT_CHANCE = 10  # 5% шанс крита
SUCCESS_CHANCE = 40  # 20% общий шанс успеха

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Обработчик ошибок
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandOnCooldown):
        seconds = int(error.retry_after)
        minutes = seconds // 60
        seconds = seconds % 60
        await ctx.send(f"⏳ Подождите {minutes}м {seconds}с, прежде чем использовать эту команду снова.")
    else:
        raise error

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")

@bot.command(name="славанн")
@commands.cooldown(rate=1, per=7200, type=commands.BucketType.user)
async def slav_party(ctx):
    user = ctx.author
    role = discord.utils.get(ctx.guild.roles, name=ROLE_NAME)

    if not role:
        await ctx.send('❌ Роль не найдена!')
        return

    if role in user.roles:
        await ctx.send(f'🟥 {user.mention}, ты уже Патриот!')
        return

    roll = random.randint(1, 100)
    balance = get_balance(user.id)

    if roll <= CRIT_CHANCE:
        await user.add_roles(role)
        update_balance(user.id, 1000)
        await ctx.send(f'💥 **КРИТ!** {user.mention}, ты получил роль + 1000 социального рейтинга! (Баланс: {get_balance(user.id)})')

    elif roll <= SUCCESS_CHANCE:
        await user.add_roles(role)
        update_balance(user.id, 100)
        await ctx.send(f'🟥 {user.mention}, ты получил роль + 100 рейтинга! (Баланс: {get_balance(user.id)})')

    else:
        penalty = min(10, balance)
        update_balance(user.id, -penalty)
        await ctx.send(f'🕊 {user.mention}, -{penalty} рейтинга. Попробуй ещё! (Баланс: {get_balance(user.id)})')

@bot.command(name="фарм")
@commands.cooldown(rate=1, per=1200, type=commands.BucketType.user)
async def farm(ctx):
    user = ctx.author
    role = discord.utils.get(ctx.guild.roles, name=ROLE_NAME)

    if not role or role not in user.roles:
        await ctx.send("⛔ Эта команда доступна только для Патриотов.")
        return

    reward = random.randint(5, 15)
    update_balance(user.id, reward)
    await ctx.send(f"🌾 {user.mention}, вы заработали {reward} соц. кредитов! (Баланс: {get_balance(user.id)})")

@bot.command(name="баланс")
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
async def balance(ctx):
    balance = get_balance(ctx.author.id)
    await ctx.send(f'💰 {ctx.author.mention}, ваш баланс: {balance}')

@bot.command(name="перевести")
async def transfer(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return
    
    sender_balance = get_balance(ctx.author.id)
    if sender_balance < amount:
        await ctx.send("❌ Недостаточно средств!")
        return

    update_balance(ctx.author.id, -amount)
    update_balance(member.id, amount)
    await ctx.send(f'✅ {ctx.author.mention} перевел {amount} рейтинга {member.mention}!')

@bot.command(name="топ")
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
async def top(ctx):
    with closing(sqlite3.connect('economy.db')) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        top_users = cursor.fetchall()

    if not top_users:
        await ctx.send("😔 Таблица пуста.")
        return

    leaderboard = []
    for i, (user_id, balance) in enumerate(top_users, start=1):
        try:
            user = await bot.fetch_user(user_id)
            leaderboard.append(f"{i}. {user.name} — {balance} кредитов")
        except:
            leaderboard.append(f"{i}. [Неизвестный пользователь] — {balance} кредитов")

    await ctx.send(f"🏆 **Топ 10 Патриотов:**\n" + "\n".join(leaderboard))

@bot.command(name="помощь")
async def help_command(ctx):
    help_text = """
📜 **Команды бота:**

🔴 `!славанн` — попытка стать Патриотом (2ч кд)
🌾 `!фарм` — заработать кредиты (20м кд, только для Патриотов)
💰 `!баланс` — показать ваш баланс (5с кд)
💸 `!перевести @юзер сумма` — перевод кредитов
🏆 `!топ` — топ-10 по балансу (5с кд)
ℹ️ `!помощь` — это сообщение
"""
    await ctx.send(help_text)

bot.run(TOKEN)
