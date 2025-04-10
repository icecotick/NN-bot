
import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
from discord import ButtonStyle
from discord.ui import Button, View
import yt_dlp

load_dotenv()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

queue = []
cenzor_words = []

# Загрузка стоп-слов
def load_cenzor_words():
    global cenzor_words
    if os.path.exists("cenzor_words.txt"):
        with open("cenzor_words.txt", "r", encoding="utf-8") as f:
            cenzor_words = [line.strip().lower() for line in f if line.strip()]

@bot.event
async def on_ready():
    print(f"Бот {bot.user} запущен!")
    load_cenzor_words()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    msg = message.content.lower()
    if any(word in msg for word in cenzor_words):
        await message.delete()
        await message.channel.send(f"{message.author.mention}, это слово запрещено!")
    await bot.process_commands(message)

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
    await ctx.send("Воспроизведение началось", view=MusicControls(vc))

class MusicControls(View):
    def __init__(self, vc):
        super().__init__()
        self.vc = vc

    @discord.ui.button(label="⏭ Пропустить", style=ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: Button):
        self.vc.stop()
        await interaction.response.send_message("Трек пропущен", ephemeral=True)

    @discord.ui.button(label="⏹ Стоп", style=ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: Button):
        await self.vc.disconnect()
        await interaction.response.send_message("Остановлено", ephemeral=True)

# Бан
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, duration: int = 0, *, reason="Нарушение правил"):
    await ctx.guild.ban(member, reason=reason)
    await ctx.send(f"{member} забанен. Причина: {reason}")
    if duration > 0:
        await asyncio.sleep(duration * 60)
        await ctx.guild.unban(member)
        await ctx.send(f"{member} разбанен после {duration} мин.")

# Мут
@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: int = 0):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await ctx.guild.create_role(name="Muted")
        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, speak=False)
    await member.add_roles(mute_role)
    await ctx.send(f"{member.mention} замучен")
    if duration > 0:
        await asyncio.sleep(duration * 60)
        await member.remove_roles(mute_role)
        await ctx.send(f"{member.mention} размучен")

# Пинг
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

bot.run(os.getenv(MTM0MDIzNjA4MzEyMzk4MjMzNw.G3Jl6f.j-iQhaCwzYlzb06-EK8gKgWcfZ_aUVpFFUspEo))
