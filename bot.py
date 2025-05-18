import discord
from discord.ext import commands
import random
import os
import sqlite3
import asyncio
import time  # для антиспама


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

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")

# Основная команда
@bot.command(name="славитьпартиюнн")
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

    # Крит
    if roll <= CRIT_CHANCE:
        await user.add_roles(role)
        update_balance(user.id, 1000)
        await ctx.send(f'💥 **КРИТ!** {user.mention}, ты получил роль + 1000 социального рейтинга! (Баланс: {balance + 1000})')
    
    # Обычный успех
    elif roll <= SUCCESS_CHANCE:
        await user.add_roles(role)
        update_balance(user.id, 100)
        await ctx.send(f'🟥 {user.mention}, ты получил роль + 100 рейтинга! (Баланс: {balance + 100})')
    
    # Неудача
    else:
        penalty = min(10, balance)  # Не уходим в минус
        update_balance(user.id, -penalty)
        await ctx.send(f'🕊 {user.mention}, -{penalty} рейтинга. Попробуй ещё! (Баланс: {balance - penalty})')

# Команды экономики
@bot.command(name="баланс")
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

# Запуск бота
bot.run(TOKEN)
