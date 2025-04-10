
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import yt_dlp
import asyncio

# Загружаем переменные окружения
load_dotenv()

# Инициализация бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Получаем токен из переменных окружения
TOKEN = os.getenv("DISCORD_TOKEN")

# Загрузка стоп-слов
cenzor_words = []

def load_cenzor_words():
    global cenzor_words
    if os.path.exists("cenzor_words.txt"):
        with open("cenzor_words.txt", "r", encoding="utf-8") as f:
            cenzor_words = [line.strip().lower() for line in f if line.strip()]

# Музыка
@bot.command()
async def play(ctx, url):
    voice_channel = ctx.author.voice.channel
    vc = await voice_channel.connect() if not ctx.voice_client else ctx.voice_client
    with yt_dlp.YoutubeDL({'format': 'bestaudio', 'outtmpl': 'song.%(ext)s'}) as ydl:
        info = ydl.extract_info(url, download=False)
        url2 = info['url']
    vc.stop()
    vc.play(discord.FFmpegPCMAudio(url2), after=lambda e: print('Готово'))
    await ctx.send("Воспроизведение началось")

# Автоматическая фильтрация сообщений
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    msg = message.content.lower()
    if any(word in msg for word in cenzor_words):
        await message.delete()
        await message.channel.send(f"{message.author.mention}, это слово запрещено!")
    await bot.process_commands(message)

# Пример команды "ping"
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# Пример команды "ban"
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, reason=None):
    await ctx.guild.ban(member, reason=reason)
    await ctx.send(f"{member} был забанен по причине: {reason}")

# Пример команды "unban"
@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, member: discord.Member):
    await ctx.guild.unban(member)
    await ctx.send(f"{member} был разбанен.")

# Пример команды "mute"
@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: int = 0):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await ctx.guild.create_role(name="Muted")
        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, speak=False, send_messages=False)
    await member.add_roles(mute_role)
    await ctx.send(f"{member} был замучен.")
    if duration > 0:
        await asyncio.sleep(duration * 60)  # duration in minutes
        await member.remove_roles(mute_role)
        await ctx.send(f"{member} больше не замучен.")

# Пример команды "unmute"
@bot.command()
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role in member.roles:
        await member.remove_roles(mute_role)
        await ctx.send(f"{member} был размучен.")
    else:
        await ctx.send(f"{member} не замучен.")

# Запуск бота
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    load_cenzor_words()  # Загружаем стоп-слова при запуске

bot.run(TOKEN)
