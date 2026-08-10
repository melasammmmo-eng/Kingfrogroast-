import os
import random
import json
import asyncio
import re

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, RoleSelect
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ================= CONFIG =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))

MODEL = "gpt-4o"

REACT_CHANCE = 0.25
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "💅", "🤨", "🙄", "✨", "👀", "🤣"]

NICKNAMES = {
    "happy": "Kingchat😁",
    "mad": "Kingchat😒",
    "neutral": "Kingchat😐"
}

# ================= DATA =================
toggles = {}
ac_enabled = {}
user_points = {}
active_quests = {}
role_configs = {}  # {guild_id: [role_id1, role_id2, ...]}

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

# ================= SETUP =================
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

AC_KNOWLEDGE = """
You know a lot about the VR game Animal Company (Meta Quest + SteamVR).
- Free multiplayer social VR survival game by Wooster Games
- Players are customizable thick-cheeked animals
- Adventure Mode (survival + monsters) and Arena Mode (6v6 PvP)
- Very chaotic, memeable, and popular on Quest
"""

SYSTEM_PROMPT = f"""
You are KingChat, a Discord bot with attitude.

{AC_KNOWLEDGE}

Personality:
- Be nice when people are nice
- Be mean (but not too far) when people are rude
- Keep replies short (1-2 sentences)
- Talk like a real Discord user
"""

# ================= ROLE SELECT VIEW =================
class RoleSetupView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.select(
        cls=RoleSelect,
        placeholder="Select up to 15 roles (lowest → highest)",
        min_values=1,
        max_values=15
    )
    async def role_select(self, interaction: discord.Interaction, select: RoleSelect):
        roles = select.values
        # Sort roles by position (lowest first)
        roles = sorted(roles, key=lambda r: r.position)

        role_ids = [str(r.id) for r in roles]
        role_configs[self.guild_id] = role_ids
        save_json(ROLES_FILE, role_configs)

        ac_enabled[self.guild_id] = True
        save_json(AC_FILE, ac_enabled)

        role_mentions = ", ".join([r.mention for r in roles])
        await interaction.response.edit_message(
            content=f"✅ Setup complete!\n\n**Roles in order:**\n{role_mentions}\n\nAC Quests are now enabled.",
            view=None
        )

# ================= QUEST VIEWS =================
class QuestStartView(View):
    def __init__(self, user_id, guild_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your quest.", ephemeral=True)

        await interaction.response.defer()

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "Generate one short, fun, doable challenge for the VR game Animal Company. Only reply with the challenge sentence."},
                    {"role": "user", "content": "Generate a creative Animal Company challenge."}
                ],
                max_tokens=50,
                temperature=1.2
            )
            task = response.choices[0].message.content.strip()
        except:
            task = "Survive 2 minutes and do something funny"

        active_quests[str(self.user_id)] = {
            "task": task,
            "guild_id": self.guild_id
        }

        embed = discord.Embed(
            title="🎯 Your AC Quest",
            description=f"**Challenge:**\n{task}\n\nRecord it, then click **Send Proof** and upload the video here.",
            color=discord.Color.green()
        )
        await interaction.edit_original_response(embed=embed, view=ProofView(self.user_id))

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your quest.", ephemeral=True)
        await interaction.response.edit_message(content="Alright, maybe next time.", embed=None, view=None)

class ProofView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Send Proof", style=discord.ButtonStyle.blurple)
    async def proof_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your quest.", ephemeral=True)
        await interaction.response.send_message("Now send the video in this DM.", ephemeral=True)

# ================= HELPERS =================
async def change_nickname(guild, mood: str):
    mood = mood.lower().strip()
    if mood not in NICKNAMES:
        mood = "neutral"
    try:
        me = guild.me
        if me and me.nick != NICKNAMES[mood]:
            await me.edit(nick=NICKNAMES[mood])
    except:
        pass

async def check_and_give_roles(member: discord.Member):
    guild_id = str(member.guild.id)
    if guild_id not in role_configs:
        return

    points = user_points.get(str(member.id), 0)
    roles = role_configs[guild_id]

    for i, role_id in enumerate(roles):
        required = (i + 1) * 10
        role = member.guild.get_role(int(role_id))
        if not role:
            continue

        if points >= required and role not in member.roles:
            try:
                await member.add_roles(role)
            except:
                pass
        elif points < required and role in member.roles:
            try:
                await member.remove_roles(role)
            except:
                pass

# ================= COMMANDS =================
@bot.command(name="stop")
async def stop(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the owner can use this.")
    toggles[str(ctx.guild.id)] = False
    await ctx.send("🛑 Bot stopped.")

@bot.command(name="start")
async def start(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the owner can use this.")
    toggles[str(ctx.guild.id)] = True
    await ctx.send("🟢 Bot started.")

@bot.tree.command(name="setup", description="Setup AC Quest roles (1-15 roles)")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    view = RoleSetupView(str(interaction.guild_id))
    await interaction.response.send_message(
        "Select **1 to 15 roles** from the dropdown below (order = lowest to highest reward):",
        view=view,
        ephemeral=True
    )

# ================= MESSAGE HANDLER =================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Handle proof videos in DMs
    if isinstance(message.channel, discord.DMChannel):
        user_id = str(message.author.id)
        if user_id in active_quests and message.attachments:
            for att in message.attachments:
                if att.content_type and "video" in att.content_type:
                    user_points[user_id] = user_points.get(user_id, 0) + 10
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
                        f"✅ Proof accepted! **+10 points**\nTotal: **{user_points[user_id]}**"
                    )
                    return

    if not message.guild:
        return

    await bot.process_commands(message)

    if not toggles.get(str(message.guild.id), True):
        return

    content = message.content.lower()

    # Flexible AC Quest trigger
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
        except discord.Forbidden:
            await message.reply("I can't DM you. Please enable DMs.", mention_author=False)
        return

    # Normal reply logic
    is_called = (
        bot.user.mentioned_in(message)
        or "kingchat" in content
        or "king chat" in content
    )

    if not is_called and random.random() > 0.18:
        return

    try:
        history = []
        async for msg in message.channel.history(limit=8):
            if msg.id != message.id:
                history.append(f"{msg.author.display_name}: {msg.content}")
        history.reverse()

        async with message.channel.typing():
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Recent chat:\n" + "\n".join(history) + f"\n\n{message.author.display_name}: {message.content}\n\nReply as KingChat (1-2 sentences).\n\nFormat:\nMOOD: neutral\nREPLY: your message"
                    }
                ],
                max_tokens=90,
                temperature=0.9
            )

            full = response.choices[0].message.content.strip()
            mood = "neutral"
            reply = full

            for line in full.splitlines():
                if line.upper().startswith("MOOD:"):
                    mood = line.split(":", 1)[1].strip().lower()
                if line.upper().startswith("REPLY:"):
                    reply = line.split(":", 1)[1].strip()

            if reply:
                await message.reply(reply, mention_author=False)
                await change_nickname(message.guild, mood)

    except Exception as e:
        print(f"Error: {e}")

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
