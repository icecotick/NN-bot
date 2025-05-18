import discord
from discord.ext import commands
import random
import os

TOKEN = os.getenv("DISCORD_TOKEN")
ROLE_NAME = "Патриот"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")

@bot.command(name="славитьпартиюнн")
async def slav_party(ctx):
    user = ctx.author
    guild = ctx.guild

    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if not role:
        await ctx.send(f'❌ Роль "{ROLE_NAME}" не найдена на сервере.')
        return

    if random.randint(1, 100) <= 20:
        await user.add_roles(role)
        await ctx.send(f'🟥 {user.mention}, ты получил звание **Патриот**! Слава партии НН!')
    else:
        await ctx.send(f'🕊 {user.mention}, сегодня не твой день. Продолжай славить партию НН!')

bot.run(TOKEN)
