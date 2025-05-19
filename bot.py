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
ADMIN_ROLES = ["создатель", "главный модер"]
ROB_CHANCE = 25  # Шанс успешной кражи
ROB_PERCENT = 20  # Процент кражи/штрафа
ROB_COOLDOWN = 3600  # 1 час кулдауна
CASINO_COOLDOWN = 60  # 1 минута кулдауна
CASINO_MULTIPLIERS = {
    2: 35,  # x2 (35% шанс)
    3: 10,  # x3 (10% шанс)
    5: 2,   # x5 (2% шанс)
    0: 53   # Проигрыш (53% шанс)
    # Константы для ивентов

}
# Константы для ивентов
EVENT_ACTIVE = False
EVENT_MULTIPLIER = 1.0
EVENT_TYPE = None
EVENT_END_TIME = 0
active_duels = {}

def is_admin(member: discord.Member) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return any(role.name.lower() in ADMIN_ROLES for role in member.roles)
# Система ивентов
async def check_events():
    while True:
        global EVENT_ACTIVE
        if EVENT_ACTIVE and time.time() > EVENT_END_TIME:
            EVENT_ACTIVE = False
            print("Ивент завершен")
        await asyncio.sleep(60)
        # Система дуэлей
async def duel_timeout(channel):
    await asyncio.sleep(120)
    if channel.id in active_duels:
        host_id = active_duels[channel.id]["host"]
        update_balance(host_id, active_duels[channel.id]["bet"])
        del active_duels[channel.id]
        await channel.send("🕒 Время дуэли вышло!")
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
            server_settings={'application_name': 'discord-bot'}
        )
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
        result = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
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
        return await conn.fetchrow("SELECT * FROM custom_roles WHERE user_id = $1", user_id)

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
        await ctx.send(f"⏳ Подождите {minutes}м {seconds}с перед повторным использованием!")
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
        await ctx.send(f'💥 **КРИТ!** {user.mention}, ты получил роль + 1000 кредитов! (Баланс: {await get_balance(user.id)})')
    elif roll <= SUCCESS_CHANCE:
        await user.add_roles(role)
        await update_balance(user.id, 100)
        await ctx.send(f'🟥 {user.mention}, ты получил роль + 100 кредитов! (Баланс: {await get_balance(user.id)})')
    else:
        penalty = min(10, balance)
        await update_balance(user.id, -penalty)
        await ctx.send(f'🕊 {user.mention}, -{penalty} кредитов. Попробуй ещё! (Баланс: {await get_balance(user.id)})')
        
@bot.command(name="фарм")
@commands.cooldown(rate=1, per=1200, type=commands.BucketType.user)
async def farm(ctx):
    if not discord.utils.get(ctx.author.roles, name=ROLE_NAME):
        await ctx.send("⛔ Только для Патриотов!")
        return

    base_reward = random.randint(5, 15)
    
    if EVENT_ACTIVE and EVENT_TYPE == "фарм":
        reward = int(base_reward * EVENT_MULTIPLIER)
        event_bonus = f" (Ивент x{EVENT_MULTIPLIER})"
    else:
        reward = base_reward
        event_bonus = ""
    
    update_balance(ctx.author.id, reward)
    await ctx.send(f"🌾 {ctx.author.mention}, вы получили {reward} кредитов{event_bonus}! Баланс: {get_balance(ctx.author.id)}")

@bot.command(name="баланс")
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
async def balance(ctx):
    bal = await get_balance(ctx.author.id)
    await ctx.send(f'💰 Ваш баланс: {bal} кредитов')

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
    await ctx.send(f'✅ {ctx.author.mention} перевел {amount} кредитов {member.mention}!')

@bot.command(name="топ")
@commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
async def top(ctx):
    async with bot.db.acquire() as conn:
        top_users = await conn.fetch("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")

    if not top_users:
        await ctx.send("😔 Таблица пуста.")
        return

    leaderboard = []
    for i, record in enumerate(top_users, start=1):
        try:
            user = await bot.fetch_user(record['user_id'])
            leaderboard.append(f"{i}. {user.name} — {record['balance']} кредитов")
        except:
            leaderboard.append(f"{i}. [Неизвестный] — {record['balance']} кредитов")

    await ctx.send("🏆 **Топ 10:**\n" + "\n".join(leaderboard))

@bot.command(name="допкредит")
async def add_credits(ctx, member: discord.Member, amount: int):
    if not is_admin(ctx.author):
        await ctx.send("❌ Только для администраторов!")
        return
    
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return
    
    await update_balance(member.id, amount)
    await ctx.send(f"✅ Админ {ctx.author.mention} добавил {amount} кредитов {member.mention}")

@bot.command(name="минускредит")
async def remove_credits(ctx, member: discord.Member, amount: int):
    if not is_admin(ctx.author):
        await ctx.send("❌ Только для администраторов!")
        return
    
    if amount <= 0:
        await ctx.send("❌ Сумма должна быть положительной!")
        return
    
    current_balance = await get_balance(member.id)
    if current_balance < amount:
        await ctx.send(f"❌ У пользователя только {current_balance} кредитов!")
        return
    
    await update_balance(member.id, -amount)
    await ctx.send(f"✅ Админ {ctx.author.mention} снял {amount} кредитов у {member.mention}")
    # Дуэльная система
@bot.command(name="бакшот_хост")
@commands.cooldown(1, 300, commands.BucketType.user)
async def host_duel(ctx, bet: int):
    if bet < 100:
        await ctx.send("❌ Минимальная ставка: 100 кредитов!")
        return
    
    balance = get_balance(ctx.author.id)
    if balance < bet:
        await ctx.send("❌ Недостаточно средств!")
        return

    update_balance(ctx.author.id, -bet)
    active_duels[ctx.channel.id] = {
        "host": ctx.author.id,
        "bet": bet,
        "participant": None
    }
    
    embed = discord.Embed(
        title="💥 Дуэль создана!",
        description=f"{ctx.author.mention} ставит {bet} кредитов!\n"
                    f"Присоединяйся: `!бакшот_присоединиться`",
        color=0xff0000
    )
    await ctx.send(embed=embed)
    await duel_timeout(ctx.channel)

@bot.command(name="бакшот_присоединиться")
async def join_duel(ctx):
    if ctx.channel.id not in active_duels:
        await ctx.send("❌ Нет активных дуэлей!")
        return
        
    duel = active_duels[ctx.channel.id]
    if duel["participant"] or ctx.author.id == duel["host"]:
        await ctx.send("❌ Невозможно присоединиться!")
        return

    if get_balance(ctx.author.id) < duel["bet"]:
        await ctx.send(f"❌ Нужно {duel['bet']} кредитов!")
        return

    update_balance(ctx.author.id, -duel["bet"])
    duel["participant"] = ctx.author.id
    
    # Анимация дуэли
    msg = await ctx.send("🔫 Дуэль начинается... 3")
    for i in range(2, 0, -1):
        await asyncio.sleep(1)
        await msg.edit(content=f"🔫 Дуэль начинается... {i}")
    await asyncio.sleep(1)
    
    # Определение победителя
    winner_id = random.choice([duel["host"], duel["participant"]])
    update_balance(winner_id, duel["bet"]*2)
    winner = await bot.fetch_user(winner_id)
    
    embed = discord.Embed(
        title="🎉 Победитель дуэли!",
        description=f"{winner.mention} забирает {duel['bet']*2} кредитов!",
        color=0x00ff00
    )
    await ctx.send(embed=embed)
    del active_duels[ctx.channel.id]


@bot.command(name="ограбить")
@commands.cooldown(rate=1, per=ROB_COOLDOWN, type=commands.BucketType.user)
async def rob(ctx, member: discord.Member):
    thief = ctx.author
    victim = member
    
    if thief == victim:
        await ctx.send("❌ Нельзя грабить себя!")
        return
    
    thief_balance = await get_balance(thief.id)
    victim_balance = await get_balance(victim.id)
    
    if victim_balance < 10:
        await ctx.send(f"❌ У {victim.mention} слишком мало кредитов!")
        return
    
    steal_amount = max(1, int(victim_balance * (ROB_PERCENT / 100)))
    
    if random.randint(1, 100) <= ROB_CHANCE:
        await update_balance(victim.id, -steal_amount)
        await update_balance(thief.id, steal_amount)
        await ctx.send(
            f"💰 {thief.mention} ограбил {victim.mention} и украл {steal_amount} кредитов!\n"
            f"💸 Новый баланс: {await get_balance(thief.id)}"
        )
    else:
        penalty = max(1, int(thief_balance * (ROB_PERCENT / 100)))
        await update_balance(thief.id, -penalty)
        await ctx.send(
            f"🚨 {thief.mention} попался при попытке ограбить {victim.mention}!\n"
            f"💸 Штраф: {penalty} кредитов\n"
            f"💰 Новый баланс: {await get_balance(thief.id)}"
        )

@bot.command(name="везение")
@commands.cooldown(rate=1, per=CASINO_COOLDOWN, type=commands.BucketType.user)
async def casino(ctx, amount: int):
    user = ctx.author
    balance = await get_balance(user.id)
    
    if amount <= 0:
        await ctx.send("❌ Ставка должна быть положительной!")
        return
    
    if balance < amount:
        await ctx.send(f"❌ Недостаточно средств! Ваш баланс: {balance}")
        return
    
    multipliers = list(CASINO_MULTIPLIERS.keys())
    weights = list(CASINO_MULTIPLIERS.values())
    result = random.choices(multipliers, weights=weights, k=1)[0]
    
    if result == 0:
        await update_balance(user.id, -amount)
        await ctx.send(f"🎰 {user.mention} ставит {amount} и... проигрывает! 💸")
    else:
        win = amount * result
        await update_balance(user.id, win)
        await ctx.send(f"🎰 {user.mention} ставит {amount} и выигрывает x{result}! 🎉 +{win} кредитов!")
        
@bot.command(name="ивент_старт")
@commands.has_permissions(administrator=True)
async def start_event(ctx, hours: int, multiplier: float, event_type: str = "фарм"):
    global EVENT_ACTIVE, EVENT_MULTIPLIER, EVENT_TYPE, EVENT_END_TIME
    
    EVENT_ACTIVE = True
    EVENT_MULTIPLIER = multiplier
    EVENT_TYPE = event_type.lower()
    EVENT_END_TIME = time.time() + hours * 3600
    
    embed = discord.Embed(
        title="🎊 ИВЕНТ АКТИВИРОВАН!",
        description=f"**{event_type.upper()}** дает x{multiplier} награды!\nДействует {hours} часов.",
        color=0xffd700
    )
    await ctx.send(embed=embed)

@bot.command(name="ивент_статус")
async def event_status(ctx):
    if EVENT_ACTIVE:
        remaining = int((EVENT_END_TIME - time.time()) // 60)
        embed = discord.Embed(
            title="📢 Активный ивент",
            description=f"**Тип:** {EVENT_TYPE}\n**Множитель:** x{EVENT_MULTIPLIER}\n**Осталось:** {remaining} минут",
            color=0x00ff00
        )
    else:
        embed = discord.Embed(
            title="ℹ️ Ивентов нет",
            description="Админы могут запустить командой `!ивент_старт`",
            color=0xff0000
        )
    await ctx.send(embed=embed)
    
@bot.command(name="магазин")
async def shop(ctx):
    shop_text = f"""
🛍 **Магазин:**

🎨 `!купитьроль "Название" #Цвет` - Кастомная роль ({CUSTOM_ROLE_PRICE} кредитов)
Пример: `!купитьроль "Богач" #ff0000`

💰 Ваш баланс: {await get_balance(ctx.author.id)} кредитов
"""
    await ctx.send(shop_text)

@bot.command(name="купитьроль")
async def buy_role(ctx, role_name: str, role_color: str):
    user = ctx.author
    balance = await get_balance(user.id)
    
    if balance < CUSTOM_ROLE_PRICE:
        await ctx.send(f"❌ Недостаточно средств! Нужно {CUSTOM_ROLE_PRICE} кредитов.")
        return
    
    existing_role = await get_custom_role(user.id)
    if existing_role:
        try:
            old_role = ctx.guild.get_role(existing_role['role_id'])
            if old_role:
                await old_role.delete()
        except:
            pass
    
    try:
        color = discord.Color.from_str(role_color)
        new_role = await ctx.guild.create_role(
            name=role_name,
            color=color,
            reason=f"Кастомная роль для {user.name}"
        )
        await user.add_roles(new_role)
        await create_custom_role(user.id, new_role.id, role_name, role_color)
        await update_balance(user.id, -CUSTOM_ROLE_PRICE)
        await ctx.send(f"✅ {user.mention}, вы купили роль {new_role.mention}!")
    except ValueError:
        await ctx.send("❌ Неверный формат цвета! Пример: `#ff0000`")
    except Exception as e:
        print(f"Ошибка: {e}")
        await ctx.send("❌ Ошибка при создании роли!")

@bot.command(name="помощь")
async def help_command(ctx):
    help_text = f"""
📜 **Команды бота:**

🔴 `!славанн` - Стать Патриотом (2ч кд)
🌾 `!фарм` - Заработок (20м кд)
💰 `!баланс` - Ваш баланс
💸 `!перевести @юзер сумма` - Перевод
🏆 `!топ` - Топ-10 игроков
🛍 `!магазин` - Магазин
🎨 `!купитьроль "Назв" #Цвет` - Купить роль
➕ `!допкредит @юзер сумма` - Добавить кредиты (админ)
➖ `!минускредит @юзер сумма` - Снять кредиты (админ)
🦹 `!ограбить @юзер` - Попытка кражи (1ч кд)
🎰 `!везение сумма` - Игра в везение (1м кд)
ℹ️ `!помощь` - Справка
📢 `!ивент_старт` - Стартует ивент для фарма (админ)
🎰 `!бакшот_хост сумма` - стартует игру "бакшот рулетку"
 `!бакшот_присоединиться` - присоеденение к раунду
Примеры:
`!купитьроль "Богач" #ff0000`
`!везение 500`
`!ограбить @Игрок`
`!ивент_старт ивент_старт 2 2.5 фарм` (2 часа, x2.5 к фарму)
"""
    await ctx.send(help_text)

def run_bot():
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(bot.start(TOKEN))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        if loop.is_running():
            loop.run_until_complete(close_db())
        loop.close()

if __name__ == "__main__":
    run_bot()
