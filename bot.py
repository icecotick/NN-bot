import discord
from discord.ext import commands
from discord.ext.commands import CommandOnCooldown
import random
import os
import asyncpg
import sys
import asyncio
import time
from typing import Optional
from datetime import datetime, timedelta

# Настройки
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:KoiwhbfRHSNZZfrsDHRsniDsoRonHDPx@ballast.proxy.rlwy.net:53277/railway"
ROLE_NAME = "Патриот"
CUSTOM_ROLE_PRICE = 2000
CRIT_CHANCE = 10
SUCCESS_CHANCE = 40
ADMIN_ROLES = ["создатель", "главный модер"]
ROB_CHANCE = 25
ROB_PERCENT = 20
ROB_COOLDOWN = 3600
CASINO_COOLDOWN = 60
BUCKSHOT_COOLDOWN = 1800
CASINO_MULTIPLIERS = {
    2: 35,
    3: 10,
    5: 2,
    0: 53
}

# Константы для ивентов
EVENT_ACTIVE = False
EVENT_MULTIPLIER = 1.0
EVENT_TYPE = None
EVENT_END_TIME = 0

# Глобальные переменные для бакшота
active_buckshots = {}
BUCKSHOT_GIF = "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExb21peDBuYWEzazhhb2EweWhzazd3NjkydnZ0dHI5M2x6b3d5aHdtdSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/DQb9xdHQwFl9fvJ1ls/giphy.gif"

def is_admin(member: discord.Member) -> bool:
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
            server_settings={'application_name': 'discord-bot'}
        )
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
            # Создаем таблицы (ФИКС ОТСТУПОВ В SQL-ЗАПРОСЕ)
            await conn.execute("""
CREATE TABLE IF NOT EXISTS profiles (
    user_id BIGINT PRIMARY KEY,
    bio TEXT DEFAULT '',
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    achievements TEXT[] DEFAULT ARRAY[]::TEXT[],
    last_daily TIMESTAMP DEFAULT NULL
);
            """)
            await conn.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    balance INTEGER DEFAULT 0
);
            """)
            await conn.execute("""
CREATE TABLE IF NOT EXISTS custom_roles (
    user_id BIGINT PRIMARY KEY,
    role_id BIGINT,
    role_name TEXT,
    role_color TEXT
);
            """)
            await conn.execute("""
CREATE TABLE IF NOT EXISTS command_cooldowns (
    user_id BIGINT,
    command_name TEXT,
    cooldown_end TIMESTAMP,
    PRIMARY KEY (user_id, command_name)
);
            """)
        return pool
    except Exception as e:
        print(f"❌ Ошибка подключения к базе данных: {e}")
        sys.exit(1)

async def get_cooldown(user_id: int, command_name: str) -> Optional[datetime]:
    async with bot.db.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT cooldown_end FROM command_cooldowns WHERE user_id = $1 AND command_name = $2",
            user_id, command_name
        )
        return result["cooldown_end"] if result else None

async def set_cooldown(user_id: int, command_name: str, cooldown_end: datetime):
    async with bot.db.acquire() as conn:
        await conn.execute("""
            INSERT INTO command_cooldowns (user_id, command_name, cooldown_end)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, command_name)
            DO UPDATE SET cooldown_end = $3
        """, user_id, command_name, cooldown_end)

def persistent_cooldown(rate, per, type):
    async def predicate(ctx):
        cooldown_end = await get_cooldown(ctx.author.id, ctx.command.name)
        if cooldown_end and cooldown_end > datetime.now():
            remaining = cooldown_end - datetime.now()
            raise CommandOnCooldown(
                ctx.command, 
                remaining.total_seconds(), 
                commands.BucketType.user
            )
        return True
    
    def decorator(command):
        command._buckets = commands.CooldownMapping(commands.Cooldown(rate, per, type))
        
        if not hasattr(command, '_before_invoke'):
            command._before_invoke = predicate
        else:
            old_before = command._before_invoke
            async def new_before(ctx):
                await predicate(ctx)
                await old_before(ctx)
            command._before_invoke = new_before
            
        old_callback = command.callback
        async def new_callback(ctx, *args, **kwargs):
            try:
                await old_callback(ctx, *args, **kwargs)
            finally:
                cooldown_end = datetime.now() + timedelta(seconds=per)
                await set_cooldown(ctx.author.id, ctx.command.name, cooldown_end)
                
        command.callback = new_callback
        return command
    
    return decorator

@bot.event
async def on_ready():
    try:
        bot.db = await create_db_pool()
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

async def get_profile(user_id: int):
    async with bot.db.acquire() as conn:
        profile = await conn.fetchrow("SELECT * FROM profiles WHERE user_id = $1", user_id)
        if not profile:
            await conn.execute("INSERT INTO profiles (user_id) VALUES ($1)", user_id)
            profile = await conn.fetchrow("SELECT * FROM profiles WHERE user_id = $1", user_id)
        return profile

async def update_profile(user_id: int, **kwargs):
    """Обновляет данные профиля пользователя"""
    if not kwargs:  # Если нет полей для обновления
        return
        
    async with bot.db.acquire() as conn:
        # Создаем список полей для обновления
        set_clause = ", ".join([f"{field} = ${i+1}" 
                              for i, field in enumerate(kwargs.keys())])
        
        # Формируем список значений
        values = list(kwargs.values()) + [user_id]
        
        # Формируем SQL запрос
        query = f"""
            UPDATE profiles
            SET {set_clause}
            WHERE user_id = ${len(kwargs) + 1}
        """
        
        await conn.execute(query, *values)

async def add_xp(user_id: int, xp_amount: int):
    profile = await get_profile(user_id)
    new_xp = profile['xp'] + xp_amount
    new_level = profile['level']
    
    if new_xp >= new_level * 100:
        new_level += 1
        new_xp = 0
    
    await update_profile(user_id, xp=new_xp, level=new_level)
    return new_level > profile['level']

set_clause = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(kwargs.keys())])
        values = [user_id] + list(kwargs.values())
        await conn.execute(f"""
            UPDATE profiles
            SET {set_clause}
            WHERE user_id = $1
        """, *values)

async def add_xp(user_id: int, xp_amount: int):
    profile = await get_profile(user_id)
    new_xp = profile['xp'] + xp_amount
    new_level = profile['level']
    
    if new_xp >= new_level * 100:
        new_level += 1
        new_xp = 0
    
    await update_profile(user_id, xp=new_xp, level=new_level)
    return new_level > profile['level']

@bot.command(name="профиль")
async def profile(ctx, member: discord.Member = None):
    """Показывает профиль пользователя"""
    user = member or ctx.author
    profile_data = await get_profile(user.id)
    balance = await get_balance(user.id)
    custom_role = await get_custom_role(user.id)
    
    embed = discord.Embed(
        title=f"📊 Профиль {user.display_name}",
        color=user.color
    )
    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)
    
    embed.add_field(name="💵 Баланс", value=f"{balance} кредитов", inline=True)
    embed.add_field(name="📊 Уровень", value=f"{profile_data['level']}", inline=True)
    embed.add_field(name="🌟 Опыт", value=f"{profile_data['xp']}/{profile_data['level'] * 100}", inline=True)
    
    bio = profile_data['bio'] or "Пока ничего не написано"
    embed.add_field(name="📝 О себе", value=bio, inline=False)
    
    if custom_role:
        embed.add_field(
            name="🎭 Кастомная роль", 
            value=f"Имя: {custom_role['role_name']}\nЦвет: {custom_role['role_color']}", 
            inline=False
        )
    
    achievements = profile_data['achievements'] or []
    if achievements:
        embed.add_field(name="🏆 Ачивки", value="\n".join(f"• {ach}" for ach in achievements), inline=False)
    else:
        embed.add_field(name="🏆 Ачивки", value="Пока нет ачивок", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="био")
async def set_bio(ctx, *, bio: str):
    """Установить биографию в профиль"""
    if len(bio) > 200:
        await ctx.send("❌ Биография слишком длинная (макс. 200 символов)")
        return
    
    await update_profile(ctx.author.id, bio=bio)
    await ctx.send("✅ Ваша биография успешно обновлена!")

@bot.command(name="ежедневная")
@persistent_cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
    """Получить ежедневную награду"""
    reward = random.randint(50, 150)
    level_up = await add_xp(ctx.author.id, 20)
    
    await update_balance(ctx.author.id, reward)
    await update_profile(ctx.author.id, last_daily=datetime.now())
    
    msg = f"🎁 {ctx.author.mention}, вы получили {reward} кредитов и 20 опыта!"
    if level_up:
        profile = await get_profile(ctx.author.id)
        msg += f"\n🎉 Поздравляем! Новый уровень: {profile['level']}"
    
    await ctx.send(msg)

@bot.command(name="бакшот")
@persistent_cooldown(1, BUCKSHOT_COOLDOWN, commands.BucketType.user)
async def buckshot(ctx, bet: int):
    if bet < 100:
        await ctx.send("❌ Минимальная ставка - 100 кредитов!")
        return
    
    balance = await get_balance(ctx.author.id)
    if balance < bet:
        await ctx.send("❌ Недостаточно средств!")
        return

    if ctx.channel.id in active_buckshots:
        await ctx.send("❌ В этом канале уже есть активная дуэль!")
        return

    await update_balance(ctx.author.id, -bet)
    active_buckshots[ctx.channel.id] = {
        "host": ctx.author.id,
        "bet": bet,
        "participant": None,
        "message": None,
        "current_chamber": 0,
        "live_bullet_position": random.randint(0, 5),
        "current_player": None
    }

embed = discord.Embed(
        title="💥 Бакшот-дуэль начата!",
        description=f"{ctx.author.mention} ставит {bet} кредитов!\n"
                    f"Первый, кто напишет !присоединиться, сразится с ним.\n"
                    f"Победитель забирает {bet*2} кредитов!\n\n"
                    f"🔫 Правила:\n"
                    f"- В барабане 6 патронов\n"
                    f"- Только 1 боевой патрон\n"
                    f"- Выбирайте, стрелять в себя или соперника",
        color=0xff0000
    )
    embed.set_image(url=BUCKSHOT_GIF)
    msg = await ctx.send(embed=embed)
    active_buckshots[ctx.channel.id]["message"] = msg

    await asyncio.sleep(240)
    if ctx.channel.id in active_buckshots and active_buckshots[ctx.channel.id]["participant"] is None:
        await update_balance(ctx.author.id, bet)
        del active_buckshots[ctx.channel.id]
        await ctx.send("🕒 Время вышло! Дуэль отменена.")

@bot.command(name="присоединиться")
async def join_buckshot(ctx):
    if ctx.channel.id not in active_buckshots:
        await ctx.send("❌ В этом канале нет активных дуэлей!")
        return
    
    duel = active_buckshots[ctx.channel.id]
    
    if duel["participant"] is not None:
        await ctx.send("❌ Кто-то уже присоединился к дуэли!")
        return
    
    if ctx.author.id == duel["host"]:
        await ctx.send("❌ Нельзя присоединиться к своей дуэли!")
        return
    
    balance = await get_balance(ctx.author.id)
    if balance < duel["bet"]:
        await ctx.send(f"❌ Для участия нужно {duel['bet']} кредитов!")
        return

    await update_balance(ctx.author.id, -duel["bet"])
    duel["participant"] = ctx.author.id
    duel["current_player"] = duel["host"]
    
    host = await bot.fetch_user(duel["host"])
    participant = await bot.fetch_user(duel["participant"])
    
    view = BuckshotView(duel)
    embed = discord.Embed(
        title="🔫 Бакшот-дуэль!",
        description=f"Игроки:\n"
                    f"{host.mention} (Ход)\n"
                    f"{participant.mention}\n\n"
                    f"Ставка: {duel['bet']*2} кредитов\n"
                    f"Текущий патрон: {duel['current_chamber']+1}/6\n"
                    f"Боевой патрон на позиции: ❓",
        color=0xff0000
    )
    embed.set_image(url=BUCKSHOT_GIF)
    await duel["message"].edit(embed=embed, view=view)

class BuckshotView(discord.ui.View):
    def init(self, duel_data):
        super().init(timeout=180)
        self.duel = duel_data
    
    async def update_embed(self, interaction: discord.Interaction, description: str):
        host = await interaction.guild.fetch_member(self.duel["host"])
        participant = await interaction.guild.fetch_member(self.duel["participant"])
        
        current_player = host if self.duel["current_player"] == self.duel["host"] else participant
        opponent = participant if current_player == host else host
        
        embed = discord.Embed(
            title="🔫 Бакшот-дуэль!",
            description=f"{description}\n\n"
                        f"Игроки:\n"
                        f"{host.mention} {'(Ход)' if current_player == host else ''}\n"
                        f"{participant.mention} {'(Ход)' if current_player == participant else ''}\n\n"
                        f"Ставка: {self.duel['bet']*2} кредитов\n"
                        f"Текущий патрон: {self.duel['current_chamber']+1}/6\n"
                        f"Боевой патрон на позиции: ❓",
            color=0xff0000
        )
        embed.set_image(url=BUCKSHOT_GIF)
        await interaction.message.edit(embed=embed)
    
    @discord.ui.button(label="Выстрелить в себя", style=discord.ButtonStyle.red, emoji="💀")
    async def shoot_self(self, interaction: discord.Interaction, button: discord.ui.Button):

if interaction.user.id != self.duel["current_player"]:
            await interaction.response.send_message("❌ Сейчас не ваш ход!", ephemeral=True)
            return
        
        if self.duel["current_chamber"] == self.duel["live_bullet_position"]:
            winner_id = self.duel["host"] if interaction.user.id == self.duel["participant"] else self.duel["participant"]
            winner = await interaction.guild.fetch_member(winner_id)
            
            total_pot = self.duel["bet"] * 2
            await update_balance(winner_id, total_pot)
            
            embed = discord.Embed(
                title="💀 Выстрел в себя!",
                description=f"🔫 БАХ! {interaction.user.mention} выстрелил в себя и проиграл!\n"
                            f"💥 Это был боевой патрон на позиции {self.duel['current_chamber']+1}\n"
                            f"🎉 Победитель: {winner.mention}\n"
                            f"💰 Выигрыш: {total_pot} кредитов!",
                color=0x00ff00
            )
            embed.set_image(url=BUCKSHOT_GIF)
            await interaction.message.edit(embed=embed, view=None)
            del active_buckshots[interaction.channel.id]
        else:
            self.duel["current_chamber"] += 1
            self.duel["current_player"] = self.duel["host"] if interaction.user.id == self.duel["participant"] else self.duel["participant"]
            await self.update_embed(
                interaction,
                f"💨 {interaction.user.mention} выстрелил в себя - холостой патрон!\n"
                f"🔫 Следующий патрон: {self.duel['current_chamber']+1}/6\n"
                f"Теперь ход противника."
            )
        
        await interaction.response.defer()
    
    @discord.ui.button(label="Выстрелить в соперника", style=discord.ButtonStyle.green, emoji="🎯")
    async def shoot_opponent(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.duel["current_player"]:
            await interaction.response.send_message("❌ Сейчас не ваш ход!", ephemeral=True)
            return
        
        if self.duel["current_chamber"] == self.duel["live_bullet_position"]:
            total_pot = self.duel["bet"] * 2
            await update_balance(interaction.user.id, total_pot)
            
            opponent_id = self.duel["host"] if interaction.user.id == self.duel["participant"] else self.duel["participant"]
            opponent = await interaction.guild.fetch_member(opponent_id)
            
            embed = discord.Embed(
                title="🎯 Выстрел в соперника!",
                description=f"🔫 БАХ! {interaction.user.mention} выстрелил в {opponent.mention} и победил!\n"
                            f"💥 Это был боевой патрон на позиции {self.duel['current_chamber']+1}\n"
                            f"💰 Выигрыш: {total_pot} кредитов!",
                color=0x00ff00
            )
            embed.set_image(url=BUCKSHOT_GIF)
            await interaction.message.edit(embed=embed, view=None)
            del active_buckshots[interaction.channel.id]
        else:
            self.duel["current_chamber"] += 1
            self.duel["current_player"] = self.duel["host"] if interaction.user.id == self.duel["participant"] else self.duel["participant"]
            await self.update_embed(
                interaction,
                f"💨 {interaction.user.mention} выстрелил в соперника - холостой патрон!\n"
                f"🔫 Следующий патрон: {self.duel['current_chamber']+1}/6\n"
                f"Теперь ход противника."
            )
        
        await interaction.response.defer()
    
    async def on_timeout(self):
        if self.duel["message"].channel.id in active_buckshots:
            host = await self.duel["message"].guild.fetch_member(self.duel["host"])

participant = await self.duel["message"].guild.fetch_member(self.duel["participant"])
            
            await update_balance(self.duel["host"], self.duel["bet"])
            await update_balance(self.duel["participant"], self.duel["bet"])
            
            embed = discord.Embed(
                title="🕒 Время вышло!",
                description=f"Дуэль между {host.mention} и {participant.mention} отменена из-за бездействия.",
                color=0xff0000
            )
            await self.duel["message"].edit(embed=embed, view=None)
            del active_buckshots[self.duel["message"].channel.id]

@bot.command(name="славанн")
@persistent_cooldown(1, 7200, commands.BucketType.user)
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
        await ctx.send(f'💥 КРИТ! {user.mention}, ты получил роль + 1000 кредитов! (Баланс: {await get_balance(user.id)})')
    elif roll <= SUCCESS_CHANCE:
        await user.add_roles(role)
        await update_balance(user.id, 100)
        await ctx.send(f'🟥 {user.mention}, ты получил роль + 100 кредитов! (Баланс: {await get_balance(user.id)})')
    else:
        penalty = min(10, balance)
        await update_balance(user.id, -penalty)
        await ctx.send(f'🕊 {user.mention}, -{penalty} кредитов. Попробуй ещё! (Баланс: {await get_balance(user.id)})')
        
@bot.command(name="фарм")
@persistent_cooldown(1, 1200, commands.BucketType.user)
async def farm(ctx):
    if not discord.utils.get(ctx.author.roles, name=ROLE_NAME):
        await ctx.send("⛔ Только для Патриотов!")
        return

    base_reward = random.randint(20, 50)
    
    if EVENT_ACTIVE and EVENT_TYPE == "фарм":
        reward = int(base_reward * EVENT_MULTIPLIER)
        event_bonus = f" (Ивент x{EVENT_MULTIPLIER})"
    else:
        reward = base_reward
        event_bonus = ""
    
    level_up = await add_xp(ctx.author.id, 5)
    await update_balance(ctx.author.id, reward)
    
    msg = f"🌾 {ctx.author.mention}, вы получили {reward} кредитов и 5 опыта{event_bonus}!"
    if level_up:
        profile = await get_profile(ctx.author.id)
        msg += f"\n🎉 Новый уровень: {profile['level']}"
    
    await ctx.send(msg)

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

await ctx.send("🏆 Топ 10:\n" + "\n".join(leaderboard))

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

@bot.command(name="ограбить")
@persistent_cooldown(rate=1, per=ROB_COOLDOWN, type=commands.BucketType.user)
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
@persistent_cooldown(rate=1, per=CASINO_COOLDOWN, type=commands.BucketType.user)
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
        description=f"{event_type.upper()} дает x{multiplier} награды!\nДействует {hours} часов.",
        color=0xffd700
    )
    await ctx.send(embed=embed)

@bot.command(name="ивент_статус")
async def event_status(ctx):
    if EVENT_ACTIVE:
        remaining = int((EVENT_END_TIME - time.time()) // 60)
        embed = discord.Embed(
            title="📢 Активный ивент",
            description=f"Тип: {EVENT_TYPE}\nМножитель: x{EVENT_MULTIPLIER}\nОсталось: {remaining} минут",
            color=0x00ff00
        )
    else:
        embed = discord.Embed(
            title="ℹ️ Ивентов нет",
            description="Админы могут запустить командой !ивент_старт",
            color=0xff0000
        )
    await ctx.send(embed=embed)
    
@bot.command(name="магазин")
async def shop(ctx):
    shop_text = f"""
🛍 Магазин:

🎨 !купитьроль "Название" #Цвет - Кастомная роль ({CUSTOM_ROLE_PRICE} кредитов)
Пример: !купитьроль "Богач" #ff0000

🎮 !бакшот сумма - Дуэль 1v1 (30м кд)
🎰 !везение сумма - Классическое казино

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
        await ctx.send("❌ Неверный формат цвета! Пример: #ff0000")
    except Exception as e:
        print(f"Ошибка: {e}")
        await ctx.send("❌ Ошибка при создании роли!")

@bot.command(name="помощь")
async def help_command(ctx):
    help_text = f"""
📜 Команды бота:

📊 Профиль:
!профиль [@юзер] - Посмотреть профиль
!био текст - Установить биографию
!ежедневная - Получить ежедневную награду (24ч кд)

🎮 Игровые:
!славанн - Стать Патриотом (2ч кд)
!фарм - Заработок (20м кд)
!бакшот сумма - Дуэль 1v1 (30м кд)
`!везение сумма` - игра в везение (1м кд)
`!ограбить @юзер` - Попытка кражи (1ч кд)

💰 Экономика:
`!баланс` - Ваш баланс
`!перевести @юзер сумма` - Перевод
`!топ` - Топ-10 игроков
`!магазин` - Магазин
`!купитьроль "Назв" #Цвет` - Купить роль

🛠 Админ:
`!допкредит @юзер сумма` - Добавить кредиты
`!минускредит @юзер сумма` - Снять кредиты
`!ивент_старт` - Старт ивента

Примеры:
`!профиль @Игрок`
`!био Люблю играть в бакшот!`
`!купитьроль "Богач" #ff0000`
`!бакшот 1000`
`!ивент_старт 2 2.5 фарм` (2 часа, x2.5 к фарму)
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
