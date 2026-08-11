import os
import random
import json
import re
import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, RoleSelect
from openai import OpenAI
from dotenv import load_dotenv

from ac_recognise import check_proof

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))
RACIST_PERSON = os.getenv("RACIST_PERSON")  # <-- Add this in .env

MODEL = "gpt-4o"

REACT_CHANCE = 0.22
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "💅", "🤨", "🙄", "✨", "👀", "🤣"]

NICKNAMES = {
    "happy": "Kingchat😁",
    "mad": "Kingchat😒",
    "neutral": "Kingchat😐"
}

toggles = {}
ac_enabled = {}
user_points = {}
active_quests = {}
role_configs = {}

POINTS_FILE = "points.json"
AC_FILE = "ac_settings.json"
ROLES_FILE = "roles.json"

def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return default

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

user_points = load_json(POINTS_FILE, {})
ac_enabled = load_json(AC_FILE, {})
role_configs = load_json(ROLES_FILE, {})

def load_ac_knowledge():
    try:
        with open("animal_company_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Animal Company is a popular free VR game on Meta Quest."

AC_KNOWLEDGE = load_ac_knowledge()

client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

SYSTEM_PROMPT = f"""
You are KingChat, a Discord bot with attitude.

Here is detailed knowledge about Animal Company:
{AC_KNOWLEDGE}

Personality:
- Be nice when people are nice
- Be mean (but not too far) when people are rude
- Keep replies short (1-2 sentences)
- Talk like a real Discord user
- Use your knowledge of Animal Company when relevant
"""

class RoleSetupView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.select(cls=RoleSelect, placeholder="Select 1–15 roles", min_values=1, max_values=15)
    async def select_roles(self, interaction: discord.Interaction, select: RoleSelect):
        roles = sorted(select.values, key=lambda r: r.position)
        role_configs[self.guild_id] = [str(r.id) for r in roles]
        save_json(ROLES_FILE, role_configs)
        ac_enabled[self.guild_id] = True
        save_json(AC_FILE, ac_enabled)
        mentions = ", ".join(r.mention for r in roles)
        await interaction.response.edit_message(content=f"✅ Roles set:\n{mentions}", view=None)

class QuestStartView(View):
    def __init__(self, user_id, guild_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your quest.", ephemeral=True)
        await interaction.response.defer()

        try:
            res = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": """You generate simple challenges for the VR game Animal Company.

Only use real things that exist in Animal Company.
Good examples:
- Dig 5 iron ore
- Kill an Angler Fish
- Sell 3 items
- Survive 60 seconds without dying
- Find and pick up a flashlight
- Kill a Smiley
- Collect 5 pieces of loot
- Use a walkie-talkie
- Enter the Mines
- Open your Stash

Never invent items that don't exist (no pine cones, no apples, etc.).
Only output the challenge, nothing else."""
                    },
                    {
                        "role": "user",
                        "content": "Generate one simple and real Animal Company challenge."
                    }
                ],
                max_tokens=40,
                temperature=0.7
            )
            task = res.choices[0].message.content.strip()
        except:
            task = "Dig 5 iron ore"

        active_quests[str(self.user_id)] = {"task": task, "guild_id": self.guild_id}
        embed = discord.Embed(
            title="🎯 Your AC Quest",
            description=f"**Challenge:**\n{task}\n\nSend a video or screenshot as proof in this DM.",
            color=discord.Color.green()
        )
        await interaction.edit_original_response(embed=embed, view=None)

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your quest.", ephemeral=True)
        await interaction.response.edit_message(content="Okay.", embed=None, view=None)

async def change_nickname(guild, mood):
    mood = mood.lower().strip()
    if mood not in NICKNAMES:
        mood = "neutral"
    try:
        me = guild.me
        if me and me.nick != NICKNAMES[mood]:
            await me.edit(nick=NICKNAMES[mood])
    except:
        pass

async def check_and_give_roles(member):
    guild_id = str(member.guild.id)
    if guild_id not in role_configs:
        return
    points = user_points.get(str(member.id), 0)
    for i, role_id in enumerate(role_configs[guild_id]):
        required = (i + 1) * 10
        role = member.guild.get_role(int(role_id))
        if not role:
            continue
        if points >= required and role not in member.roles:
            try:
                await member.add_roles(role)
            except:
                pass

@bot.command(name="stop")
async def stop(ctx):
    if ctx.author.id != OWNER_ID:
        return
    toggles[str(ctx.guild.id)] = False
    await ctx.send("🛑 Bot stopped.")

@bot.command(name="start")
async def start(ctx):
    if ctx.author.id != OWNER_ID:
        return
    toggles[str(ctx.guild.id)] = True
    await ctx.send("🟢 Bot started.")

@bot.tree.command(name="setup", description="Setup AC Quest roles")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    view = RoleSetupView(str(interaction.guild_id))
    await interaction.response.send_message("Select 1–15 roles:", view=view, ephemeral=True)

@bot.tree.command(name="points", description="Check your points")
async def points(interaction: discord.Interaction):
    pts = user_points.get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"You have **{pts}** points.", ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # ===== BLOCK RACIST PERSON =====
    if RACIST_PERSON and str(message.author.id) == str(RACIST_PERSON):
        try:
            await message.reply("I don’t talk to racist Ik what u did bum🥀", mention_author=False)
        except:
            pass
        return

    # Proof system
    if isinstance(message.channel, discord.DMChannel):
        user_id = str(message.author.id)
        if user_id in active_quests and message.attachments:
            att = message.attachments[0]
            quest = active_quests[user_id]["task"]

            await message.channel.send("Checking your proof... please wait.")

            is_valid, reason = await check_proof(att.url, quest, att.filename)

            if is_valid:
                user_points[user_id] = user_points.get(user_id, 0) + 5
                save_json(POINTS_FILE, user_points)

                guild_id = active_quests[user_id].get("guild_id")
                if guild_id and guild_id.isdigit():
                    guild = bot.get_guild(int(guild_id))
                    if guild:
                        member = guild.get_member(message.author.id)
                        if member:
                            await check_and_give_roles(member)

                del active_quests[user_id]
                await message.channel.send(
                    f"✅ **Proof accepted!** (+5 points)\nReason: {reason}\nTotal points: **{user_points[user_id]}**"
                )
            else:
                await message.channel.send(
                    f"❌ Proof rejected.\nReason: {reason}\nTry again."
                )
            return

    if not message.guild:
        return

    await bot.process_commands(message)

    if not toggles.get(str(message.guild.id), True):
        return

    content = message.content.lower()

    if re.search(r"\bac\s*quest\b", content) and ac_enabled.get(str(message.guild.id), False):
        try:
            embed = discord.Embed(
                title="🎮 AC Quest",
                description="You ready for your AC Quest?",
                color=discord.Color.blurple()
            )
            view = QuestStartView(message.author.id, str(message.guild.id))
            await message.author.send(embed=embed, view=view)
            await message.reply("Check your DMs!", mention_author=False)
        except:
            await message.reply("I can't DM you.", mention_author=False)
        return

    is_called = bot.user.mentioned_in(message) or "kingchat" in content or "king chat" in content
    if not is_called and random.random() > 0.18:
        return

    try:
        history = [f"{m.author.display_name}: {m.content}" async for m in message.channel.history(limit=7) if m.id != message.id]
        history.reverse()
        async with message.channel.typing():
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Recent chat:\n" + "\n".join(history) + f"\n\n{message.author.display_name}: {message.content}\n\nReply short as KingChat.\nFormat:\nMOOD: neutral\nREPLY: message"}
                ],
                max_tokens=80,
                temperature=0.9
            )
            full = response.choices[0].message.content.strip()
            mood, reply = "neutral", full
            for line in full.splitlines():
                if line.upper().startswith("MOOD:"):
                    mood = line.split(":", 1)[1].strip().lower()
                if line.upper().startswith("REPLY:"):
                    reply = line.split(":", 1)[1].strip()
            if reply:
                await message.reply(reply, mention_author=False)
                await change_nickname(message.guild, mood)
    except Exception as e:
        print(e)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
