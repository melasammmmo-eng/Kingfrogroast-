import os
import random
import json
import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
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
role_configs = {}  # {guild_id: [role_id1, role_id2, ...]}  (15 roles)

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

# ================= ANIMAL COMPANY KNOWLEDGE =================
AC_KNOWLEDGE = """
You know a lot about the VR game Animal Company (Meta Quest + SteamVR).

- Free multiplayer social VR survival game by Wooster Games
- Released July 2024, still Early Access
- Extremely popular on Quest
- Players are customizable thick-cheeked animals
- Adventure Mode (co-op survival + monsters + loot) and Arena Mode (6v6 PvP)
- Maps: haunted forests, labs, mines, lava caves, frozen lakes, nuclear zones
- Features: physics toys, gadgets, tech tree, crafting, proximity chat, cosmetics
- Very chaotic and memeable
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

# ================= VIEWS =================
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

        # AI generates a unique quest
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You generate short, fun, doable challenges for the VR game Animal Company. Keep it 1 sentence."},
                    {"role": "user", "content": "Generate one creative and fun challenge a player can do and record in Animal Company."}
                ],
                max_tokens=60,
                temperature=1.1
            )
            task = response.choices[0].message.content.strip()
        except:
            task = "Survive 2 minutes without dying and do a funny dance"

        active_quests[str(self.user_id)] = {
            "task": task,
            "guild_id": self.guild_id
        }

        embed = discord.Embed(
            title="🎯 Your AC Quest",
            description=f"**Your challenge:**\n{task}\n\nRecord yourself doing this, then click **Send Proof** and upload the video here.",
            color=discord.Color.green()
        )
        view = ProofView(self.user_id)
        await interaction.edit_original_response(embed=embed, view=view)

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
        required = (i + 1) * 10  # 10, 20, 30 ... 150
        role = member.guild.get_role(int(role_id))
        if not role:
            continue

        if points >= required:
            if role not in member.roles:
                try:
                    await member.add_roles(role)
                    print(f"Gave {role.name} to {member}")
                except:
                    pass
        else:
            if role in member.roles:
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

@bot.tree.command(name="setup", description="Setup the 15 AC Quest roles for this server")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Please send the **15 role IDs** in order (from lowest to highest), separated by spaces.\n"
        "Example: `123 456 789 ...` (exactly 15 IDs)\n\n"
        "You have 60 seconds.",
        ephemeral=True
    )

    def check(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        ids = msg.content.strip().split()
        if len(ids) != 15:
            return await interaction.followup.send("You must provide exactly 15 role IDs.", ephemeral=True)

        role_configs[str(interaction.guild_id)] = ids
        save_json(ROLES_FILE, role_configs)
        ac_enabled[str(interaction.guild_id)] = True
        save_json(AC_FILE, ac_enabled)

        await interaction.followup.send("✅ Successfully set up 15 roles + enabled AC Quests!", ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send("Timed out.", ephemeral=True)

# ================= MESSAGE HANDLER =================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # ===== Handle Proof Videos in DMs =====
    if isinstance(message.channel, discord.DMChannel):
        user_id = str(message.author.id)
        if user_id in active_quests and message.attachments:
            for att in message.attachments:
                if att.content_type and "video" in att.content_type:
                    user_points[user_id] = user_points.get(user_id, 0) + 10
                    save_json(POINTS_FILE, user_points)

                    # Try to give roles if we know the guild
                    guild_id = active_quests[user_id].get("guild_id")
                    if guild_id and guild_id != "dm":
                        guild = bot.get_guild(int(guild_id))
                        if guild:
                            member = guild.get_member(message.author.id)
                            if member:
                                await check_and_give_roles(member)

                    del active_quests[user_id]
                    await message.channel.send(
                        f"✅ Proof accepted! You earned **+10 points**.\n"
                        f"Total points: **{user_points[user_id]}**"
                    )
                    return

    if not message.guild:
        return

    await bot.process_commands(message)

    if not toggles.get(str(message.guild.id), True):
        return

    content = message.content.lower()

    # ===== AC QUEST TRIGGER =====
    if "ac quest" in content and ac_enabled.get(str(message.guild.id), False):
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
            await message.reply("I can't DM you. Enable DMs from server members.", mention_author=False)
        return

    # ===== Normal talking =====
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
                        "content": f"Recent chat:\n" + "\n".join(history) + f"\n\n{message.author.display_name}: {message.content}\n\nReply as KingChat (1-2 sentences). Also pick mood: happy/mad/neutral\n\nFormat:\nMOOD: neutral\nREPLY: your message"
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
