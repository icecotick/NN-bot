import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
import random
import os
import asyncpg
import sys
import asyncio
from typing import Optional

# Настройки
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:KoiwhbfRHSNZZfrsDHRsniDsoRonHDPx@ballast.proxy.rlwy.net:53277/railway"
ROLE_NAME = "Патриот"
CUSTOM_ROLE_PRICE = 2000
CRIT_CHANCE = 10
SUCCESS_CHANCE = 40
ADMIN_ROLES = ["создатель", "главный модер"]  # Роли администраторов

def is_admin(member: discord.Member) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return any(role.name.lower() in ADMIN_ROLES for role in member.roles)

# Проверка обязательных переменных
if not TOKEN:
    print("❌ Ошибка: Не установлен DISCORD_TOKEN")
    sys.exit(1)

if not DATABASE_URL:
    print("❌ Ошибка: Не установлен DATABASE_URL")
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def create_db_pool():
    try:
        print("⌛ Подключаюсь к базе данных...")
        pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=10,
            server_settings={
                'application_name': 'discord-bot'
            }
        )
        # Проверка соединения
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return pool
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")
        sys.exit(1)

@bot.event
async def on_ready():
    try:
        bot.db = await create_db_pool()
        
        # Создание таблиц если не существуют
        async with bot.db.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance INTEGER DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_roles (
                    user_id BIGINT PRIMARY KEY,
                    role_id BIGINT,
                    role_name TEXT,
                    role_color TEXT
                )
            """)
        
        print(f"✅ Бот запущен как {bot.user}")
        print(f"✅ Успешное подключение к базе данных")
        
    except Exception as e:
        print(f"❌ Критическая ошибка при запуске бота: {e}")
        await bot.close()

async def close_db():
    if hasattr(bot, 'db') and not bot.db.is_closed():
        await bot.db.close()
        print("✅ Соединение с базой данных закрыто")

@bot.event
async def on_disconnect():
    await close_db()

async def get_balance(user_id: int) -> int:
    async with bot.db.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id = $1", 
            user_id
        )
        return result["balance"] if result else 0

async def update_balance(user_id: int, amount: int):
    async with bot.db.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, balance)
            VALUES ($1, $2)
            ON CONFLICT (user_id)
            DO UPDATE SET balance = users.balance + $2
        """, user_id, amount)

async def get_custom_role(user_id: int):
    async with bot.db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM custom_roles WHERE user_id = $1",
            user_id
        )

async def create_custom_role(user_id: int, role_id: int, role_name: str, role_color: str):
    async with bot.db.acquire() as conn:
        await conn.execute("""
            INSERT INTO custom_roles (user_id, role_id, role_name, role_color)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id)
            DO UPDATE SET role_id = $2, role_name = $3, role_color = $4
        """, user_id, role_id, role_name, role_color)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandOnCooldown):
        seconds = int(error.retry_after)
        minutes = seconds // 60
        seconds = seconds % 60
        await ctx.send(f"⏳ Подождите {minutes}м {seconds}с, прежде чем использовать эту команду снова.")
    else:
        print(f"⚠ Ошибка команды: {error}")
        await ctx.send("❌ Произошла ошибка при выполнении команды")

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
    balance = await get_balance(user.id)

    if roll <= CRIT_CHANCE:
        await user.add_roles(role)
        await update_balance(user.id, 1000)
        await ctx.send(f'💥 **КРИТ!** {user.mention}, ты получил роль + 1000 социального рейтинга! (Баланс: {await get_balance(user.id)})')

    elif roll <= SUCCESS_CHANCE:
        await user.add_roles(role)
        await update_balance(user.id, 100)
        await ctx.send(f'🟥 {user.mention}, ты получил роль + 100 рейтинга! (Баланс: {await get_balance(user.id)})')

    else:
        penalty = min(10, balance)
        await update_balance(user.id, -penalty)
        await ctx.send(f'🕊 {user.mention}, -{penalty} рейтинга. Попробуй ещё! (Баланс: {await get_balance(user.id)})')

@bot.command(name="фарм")
@commands.cooldown(rate=1, per=1200, type=commands.BucketType.user)
async def farm(ctx):
    user = ctx.author
    role = discord.utils.get(ctx.guild.roles, name=ROLE_NAME)

    if not role or role not in user.roles:
        await ctx.send("⛔ Эта команда доступна только для Патриотов.")
        return

    reward = random.randint(5, 15)
    await update_balance(user.id, reward)
    await ctx.send(f"🌾 {user.mention}, вы заработали {reward} соц. кредитов! (Баланс: {await get_balance(user.id)})")

@bot.command(name="баланс")
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
async def balance(ctx):
    bal = await get_balance(ctx.author.id)
    await ctx.send(f'💰 {ctx.author.mention}, ваш баланс: {bal}')

@bot.command(name="перевести")
async def transfer(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return

    sender_balance = await get_balance(ctx.author.id)
    if sender_balance < amount:
        await ctx.send("❌ Недостаточно средств!")
        return

    await update_balance(ctx.author.id, -amount)
    await update_balance(member.id, amount)
    await ctx.send(f'✅ {ctx.author.mention} перевел {amount} рейтинга {member.mention}!')

@bot.command(name="топ")
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
async def top(ctx):
    async with bot.db.acquire() as conn:
        top_users = await conn.fetch(
            "SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10"
        )

    if not top_users:
        await ctx.send("😔 Таблица пуста.")
        return

    leaderboard = []
    for i, record in enumerate(top_users, start=1):
        try:
            user = await bot.fetch_user(record['user_id'])
            leaderboard.append(f"{i}. {user.name} — {record['balance']} кредитов")
        except:
            leaderboard.append(f"{i}. [Неизвестный пользователь] — {record['balance']} кредитов")

    await ctx.send("🏆 **Топ 10 Патриотов:**\n" + "\n".join(leaderboard))

@bot.command(name="допкредит")
async def add_credits(ctx, member: discord.Member, amount: int):
    """Добавляет кредиты указанному пользователю (только для админов)"""
    if not is_admin(ctx.author):
        await ctx.send("❌ Эта команда доступна только для администраторов!")
        return
    
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return
    
    await update_balance(member.id, amount)
    new_balance = await get_balance(member.id)
    await ctx.send(f"✅ Администратор {ctx.author.mention} добавил {amount} кредитов пользователю {member.mention}\n"
                   f"💰 Новый баланс: {new_balance} кредитов")

@bot.command(name="минускредит")
async def remove_credits(ctx, member: discord.Member, amount: int):
    """Удаляет кредиты у указанного пользователя (только для админов)"""
    if not is_admin(ctx.author):
        await ctx.send("❌ Эта команда доступна только для администраторов!")
        return
    
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return
    
    current_balance = await get_balance(member.id)
    if current_balance < amount:
        await ctx.send(f"❌ У пользователя только {current_balance} кредитов, нельзя снять {amount}!")
        return
    
    await update_balance(member.id, -amount)
    new_balance = await get_balance(member.id)
    await ctx.send(f"✅ Администратор {ctx.author.mention} снял {amount} кредитов у пользователя {member.mention}\n"
                   f"💰 Новый баланс: {new_balance} кредитов")

@bot.command(name="помощь")
async def help_command(ctx):
    help_text = f"""
📜 **Команды бота:**

🔴 `!славанн` — попытка стать Патриотом (2ч кд)
🌾 `!фарм` — заработать кредиты (20м кд, только для Патриотов)
💰 `!баланс` — показать ваш баланс (5с кд)
💸 `!перевести @юзер сумма` — перевод кредитов
🏆 `!топ` — топ-10 по балансу (5с кд)
🛍 `!магазин` — просмотреть доступные товары
🎨 `!купитьроль "Название" #Цвет` — купить кастомную роль ({CUSTOM_ROLE_PRICE} кредитов)
➕ `!допкредит @юзер сумма` — добавить кредиты (только для админов)
➖ `!минускредит @юзер сумма` — снять кредиты (только для админов)
ℹ️ `!помощь` — это сообщение

Примеры:
`!купитьроль "Богач" #ff0000`
`!допкредит @Пользователь 500`
`!минускредит @Пользователь 200`
"""
    await ctx.send(help_text)

@bot.command(name="магазин")
async def shop(ctx):
    shop_text = f"""
🛍 **Магазин социального кредита:**

🎨 `!купитьроль "Название" #Цвет` - Купить кастомную роль ({CUSTOM_ROLE_PRICE} кредитов)
Пример: `!купитьроль "Богач" #ff0000`

💰 Ваш баланс: {await get_balance(ctx.author.id)} кредитов
"""
    await ctx.send(shop_text)

@bot.command(name="купитьроль")
async def buy_role(ctx, role_name: str, role_color: str):
    user = ctx.author
    balance = await get_balance(user.id)
    
    if balance < CUSTOM_ROLE_PRICE:
        await ctx.send(f"❌ Недостаточно средств! Нужно {CUSTOM_ROLE_PRICE} кредитов, у вас {balance}.")
        return
    
    # Проверяем, есть ли уже кастомная роль у пользователя
    existing_role = await get_custom_role(user.id)
    if existing_role:
        try:
            old_role = ctx.guild.get_role(existing_role['role_id'])
            if old_role:
                await old_role.delete()
        except:
            pass
    
    # Создаем новую роль
    try:
        # Парсим цвет
        color = discord.Color.from_str(role_color)
        
        # Создаем роль
        new_role = await ctx.guild.create_role(
            name=role_name,
            color=color,
            reason=f"Кастомная роль для {user.name}"
        )
        
        # Даем роль пользователю
        await user.add_roles(new_role)
        
        # Сохраняем в базу данных
        await create_custom_role(user.id, new_role.id, role_name, role_color)
        
        # Списываем деньги
        await update_balance(user.id, -CUSTOM_ROLE_PRICE)
        
        await ctx.send(f"✅ {user.mention}, вы успешно купили роль {new_role.mention} за {CUSTOM_ROLE_PRICE} кредитов!")
    except ValueError:
        await ctx.send("❌ Неверный формат цвета! Используйте HEX формат, например: `#ff0000`")
    except Exception as e:
        print(f"Ошибка при создании роли: {e}")
        await ctx.send("❌ Произошла ошибка при создании роли. Попробуйте позже.")

def run_bot():
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(bot.start(TOKEN))
    except discord.errors.LoginFailure:
        print("❌ Ошибка авторизации Discord. Проверьте токен.")
    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал прерывания, завершаю работу...")
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
    finally:
        if loop.is_running():
            loop.run_until_complete(close_db())
        loop.close()

if __name__ == "__main__":
    run_bot()
