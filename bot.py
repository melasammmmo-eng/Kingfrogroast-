import os
import random
import json
import re
import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client

from ac_recognise import check_proof

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))
RACIST_PERSON = os.getenv("RACIST_PERSON")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

MODEL = "gpt-4o"
LOGIN_URL = "https://kingchat-ten.vercel.app"

NICKNAMES = {
    "happy": "Kingchat😁",
    "mad": "Kingchat😒",
    "neutral": "Kingchat😐"
}

MEMORY_FILE = "/app/data/memory.json"

def load_memory():
    os.makedirs("/app/data", exist_ok=True)
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {
        "toggles": {},
        "ac_enabled": {},
        "user_points": {},
        "role_configs": {},
        "points_per_quest": {}
    }

def save_memory():
    os.makedirs("/app/data", exist_ok=True)
    data = {
        "toggles": toggles,
        "ac_enabled": ac_enabled,
        "user_points": user_points,
        "role_configs": role_configs,
        "points_per_quest": points_per_quest
    }
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

memory = load_memory()
toggles = memory.get("toggles", {})
ac_enabled = memory.get("ac_enabled", {})
user_points = memory.get("user_points", {})
role_configs = memory.get("role_configs", {})
points_per_quest = memory.get("points_per_quest", {})
active_quests = {}

def load_ac_knowledge():
    try:
        with open("animal_company_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Animal Company is a free multiplayer VR survival game."

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

You have deep knowledge of Animal Company:
{AC_KNOWLEDGE}

Personality:
- Be nice when people are nice
- Be mean (but not too far) when people are rude
- Keep replies short (1-2 sentences)
- Talk like a real Discord user
"""

# ================= BLACKLIST + OWNER CHECK =================

async def has_owner_logged_in(guild: discord.Guild) -> bool:
    """Check if the server owner has logged in on the website"""
    try:
        owner_id = str(guild.owner_id)
        result = supabase.table("users").select("discord_id").eq("discord_id", owner_id).execute()
        return len(result.data) > 0
    except:
        return False

async def is_blacklisted(user_id: int, guild_id: int = None) -> bool:
    try:
        # Global blacklist
        result = supabase.table("users").select("*").eq("discord_id", str(user_id)).eq("is_blacklisted", True).eq("is_global", True).execute()
        if result.data:
            return True

        # Per-server blacklist
        if guild_id:
            result = supabase.table("users").select("*").eq("discord_id", str(user_id)).eq("is_blacklisted", True).eq("server_id", str(guild_id)).execute()
            if result.data:
                return True
    except Exception as e:
        print("Blacklist check error:", e)
    return False

async def blacklist_user(user_id: int, guild_id: int = None, global_ban: bool = False):
    data = {
        "discord_id": str(user_id),
        "is_blacklisted": True,
        "is_global": global_ban,
        "server_id": None if global_ban else str(guild_id)
    }
    try:
        supabase.table("users").upsert(data, on_conflict="discord_id").execute()
        return True
    except Exception as e:
        print("Blacklist error:", e)
        return False

# ================= VIEWS =================

class PointsModal(Modal, title="Set Points Per Quest"):
    points_input = TextInput(label="How many points per quest?", placeholder="Example: 5", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.points_input.value)
            if value < 1:
                return await interaction.response.send_message("Must be at least 1.", ephemeral=True)
            points_per_quest[str(interaction.guild_id)] = value
            save_memory()
            await interaction.response.send_message(f"✅ Each quest now gives **{value} points**.", ephemeral=True)
        except:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)

class SetupView(View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.button(label="Set Points Per Quest", style=discord.ButtonStyle.blurple)
    async def set_points(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PointsModal())

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
                    {"role": "system", "content": f"You are an expert on Animal Company.\n\n{AC_KNOWLEDGE}\n\nGenerate one short realistic challenge. Only output the challenge."},
                    {"role": "user", "content": "Generate one realistic Animal Company challenge."}
                ],
                max_tokens=40,
                temperature=0.8
            )
            task = res.choices[0].message.content.strip()
        except:
            task = "Dig some iron ore"

        active_quests[str(self.user_id)] = {"task": task, "guild_id": self.guild_id}
        embed = discord.Embed(title="🎯 Your AC Quest", description=f"**Challenge:**\n{task}\n\nSend proof in this DM.", color=0x9B59B6)
        await interaction.edit_original_response(embed=embed, view=None)

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your quest.", ephemeral=True)
        await interaction.response.edit_message(content="Okay.", embed=None, view=None)

# ================= EVENTS =================

@bot.event
async def on_guild_join(guild: discord.Guild):
    """When the bot joins a new server, DM the owner"""
    try:
        owner = guild.owner
        if owner:
            embed = discord.Embed(
                title="Thanks for adding KingChat!",
                description=(
                    f"To activate **owner features** (including `/blacklist`), please log in here:\n\n"
                    f"**{LOGIN_URL}**\n\n"
                    f"After you log in, the blacklist system will be unlocked for your server."
                ),
                color=0x9B59B6
            )
            await owner.send(embed=embed)
    except Exception as e:
        print("Could not DM server owner:", e)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()

# ================= COMMANDS =================

@bot.command(name="stop")
async def stop(ctx):
    if ctx.author.id != OWNER_ID:
        return
    toggles[str(ctx.guild.id)] = False
    save_memory()
    await ctx.send("🛑 Bot stopped.")

@bot.command(name="start")
async def start(ctx):
    if ctx.author.id != OWNER_ID:
        return
    toggles[str(ctx.guild.id)] = True
    save_memory()
    await ctx.send("🟢 Bot started.")

@bot.tree.command(name="setup", description="Setup AC Quest")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    view = SetupView(str(interaction.guild_id))
    await interaction.response.send_message("Setup menu:", view=view, ephemeral=True)

@bot.tree.command(name="points", description="Check your points")
async def points(interaction: discord.Interaction):
    pts = user_points.get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"You have **{pts}** points.", ephemeral=True)

@bot.tree.command(name="blacklist", description="Blacklist a user")
@app_commands.describe(user="User to blacklist")
async def blacklist(interaction: discord.Interaction, user: discord.Member):
    is_owner = interaction.user.id == OWNER_ID
    is_admin = interaction.user.guild_permissions.administrator

    if not (is_owner or is_admin):
        return await interaction.response.send_message("Only admins and the bot owner can use this.", ephemeral=True)

    # Check if server owner has logged in (unless it's the bot owner using the command)
    if not is_owner:
        if not await has_owner_logged_in(interaction.guild):
            return await interaction.response.send_message(
                f"The server owner must log in first at {LOGIN_URL} before blacklist can be used.",
                ephemeral=True
            )

    global_ban = is_owner
    success = await blacklist_user(user.id, interaction.guild.id, global_ban)

    if success:
        try:
            embed = discord.Embed(
                title="🚫 You have been blacklisted",
                description=f"You are blacklisted from KingChat.\n\nLog in here: {LOGIN_URL}",
                color=0xE74C3C
            )
            await user.send(embed=embed)
        except:
            pass

        scope = "globally" if global_ban else "in this server"
        await interaction.response.send_message(f"✅ {user.mention} blacklisted {scope}.", ephemeral=True)
    else:
        await interaction.response.send_message("Failed to blacklist.", ephemeral=True)

@bot.tree.command(name="unblacklist", description="Remove blacklist")
@app_commands.describe(user="User to unblacklist")
async def unblacklist(interaction: discord.Interaction, user: discord.Member):
    is_owner = interaction.user.id == OWNER_ID
    is_admin = interaction.user.guild_permissions.administrator

    if not (is_owner or is_admin):
        return await interaction.response.send_message("No permission.", ephemeral=True)

    try:
        supabase.table("users").update({
            "is_blacklisted": False,
            "is_global": False
        }).eq("discord_id", str(user.id)).execute()
        await interaction.response.send_message(f"✅ {user.mention} has been unblacklisted.", ephemeral=True)
    except:
        await interaction.response.send_message("Failed.", ephemeral=True)

# ================= MESSAGE HANDLER =================

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    guild_id = message.guild.id if message.guild else None
    if await is_blacklisted(message.author.id, guild_id):
        return

    if RACIST_PERSON and str(message.author.id) == str(RACIST_PERSON):
        try:
            await message.reply("I don’t talk to racist Ik what u did bum🥀", mention_author=False)
        except:
            pass
        return

    if isinstance(message.channel, discord.DMChannel):
        user_id = str(message.author.id)
        if user_id in active_quests and message.attachments:
            att = message.attachments[0]
            quest = active_quests[user_id]["task"]
            guild_id = active_quests[user_id]["guild_id"]

            await message.channel.send("Checking your proof...")
            is_valid, reason = await check_proof(att.url, quest, att.filename)

            if is_valid:
                pts_to_add = points_per_quest.get(guild_id, 5)
                user_points[user_id] = user_points.get(user_id, 0) + pts_to_add
                save_memory()
                del active_quests[user_id]
                await message.channel.send(f"✅ Proof accepted! +{pts_to_add} points")
            else:
                await message.channel.send(f"❌ Rejected: {reason}")
            return

    if not message.guild:
        return

    await bot.process_commands(message)

    if not toggles.get(str(message.guild.id), True):
        return

    content = message.content.lower()

    if re.search(r"\bac\s*quest\b", content) and ac_enabled.get(str(message.guild.id), False):
        try:
            view = QuestStartView(message.author.id, str(message.guild.id))
            await message.author.send(embed=discord.Embed(title="🎮 AC Quest", description="Ready?", color=0x9B59B6), view=view)
            await message.reply("Check your DMs!", mention_author=False)
        except:
            await message.reply("I can't DM you.", mention_author=False)
        return

    is_called = bot.user.mentioned_in(message) or "kingchat" in content or "king chat" in content
    if not is_called and random.random() > 0.18:
        return

    try:
        history = [f"{m.author.display_name}: {m.content}" async for m in message.channel.history(limit=6) if m.id != message.id]
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

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
