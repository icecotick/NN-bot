import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
import random
import os
import sqlite3
import time

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('economy.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INT PRIMARY KEY, balance INT DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# Функции для работы с валютой
def get_balance(user_id):
    conn = sqlite3.connect('economy.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def update_balance(user_id, amount):
    conn = sqlite3.connect('economy.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

# Настройка бота
TOKEN = os.getenv("DISCORD_TOKEN")
ROLE_NAME = "Патриот"
CRIT_CHANCE = 5  # 5% шанс крита
SUCCESS_CHANCE = 20  # 20% общий шанс успеха

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Обработчик ошибок кулдауна
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

# Команда славитьпартиюнн с кулдауном 4 часа
@bot.command(name="славитьпартиюнн")
@commands.cooldown(rate=1, per=14400, type=commands.BucketType.user)  # 4 часа
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
        await ctx.send(f'💥 **КРИТ!** {user.mention}, ты получил роль + 1000 социального рейтинга! (Баланс: {balance + 1000})')

    elif roll <= SUCCESS_CHANCE:
        await user.add_roles(role)
        update_balance(user.id, 100)
        await ctx.send(f'🟥 {user.mention}, ты получил роль + 100 рейтинга! (Баланс: {balance + 100})')

    else:
        penalty = min(10, balance)
        update_balance(user.id, -penalty)
        await ctx.send(f'🕊 {user.mention}, -{penalty} рейтинга. Попробуй ещё! (Баланс: {balance - penalty})')

# Команда фарм с кулдауном 20 минут
@bot.command(name="фарм")
@commands.cooldown(rate=1, per=1200, type=commands.BucketType.user)  # 20 минут
async def farm(ctx):
    user = ctx.author
    role = discord.utils.get(user.roles, name=ROLE_NAME)

    if not role:
        await ctx.send("⛔ Эта команда доступна только для Патриотов.")
        return

    reward = random.randint(5, 15)
    update_balance(user.id, reward)
    balance = get_balance(user.id)

    await ctx.send(f"🌾 {user.mention}, вы заработали {reward} соц. кредитов! (Баланс: {balance})")

# Команда баланс с кулдауном 5 секунд
@bot.command(name="баланс")
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user)  # 5 секунд
async def balance(ctx):
    balance = get_balance(ctx.author.id)
    await ctx.send(f'💰 {ctx.author.mention}, ваш баланс: {balance}')

# Команда перевести (без кулдауна)
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

# Команда топ с кулдауном 5 секунд
@bot.command(name="топ")
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user)  # 5 секунд
async def top(ctx):
    conn = sqlite3.connect('economy.db')
    c = conn.cursor()
    c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
    top_users = c.fetchall()
    conn.close()

    if not top_users:
        await ctx.send("😔 Таблица пуста.")
        return

    leaderboard = ""
    for i, (user_id, balance) in enumerate(top_users, start=1):
        user = await bot.fetch_user(user_id)
        leaderboard += f"{i}. {user.name} — {balance} кредитов\n"

    await ctx.send(f"🏆 **Топ 10 Патриотов:**\n{leaderboard}")

# Команда помощь
@bot.command(name="помощь")
async def help_command(ctx):
    help_text = """
📜 **Команды бота:**

🔴 `!славитьпартиюнн` — попытка стать Патриотом и получить рейтинг. Шанс успеха 20%, шанс крита 5%.

🌾 `!фарм` — заработать немного соц. кредитов (только для Патриотов, раз в 20 минут).

💰 `!баланс` — показать ваш текущий рейтинг.

💸 `!перевести @пользователь сумма` — перевести соц. кредиты другому участнику.

🏆 `!топ` — топ-10 пользователей по рейтингу.

ℹ️ `!помощь` — показать список команд.
"""
    await ctx.send(help_text)

# Запуск бота
bot.run(TOKEN)
