import os
import random
import json
import re
import asyncio
import traceback

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, RoleSelect
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client

from ac_recognise import check_proof

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))
CLIENT_ID = os.getenv("CLIENT_ID")

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
    try:
        os.makedirs("/app/data", exist_ok=True)
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        print("Error loading memory:", e)
    return {
        "toggles": {},
        "ac_enabled": {},
        "user_points": {},
        "role_configs": {},
        "points_per_quest": {},
        "unlocked_servers": {},
        "force_locked": {}
    }

def save_memory():
    try:
        os.makedirs("/app/data", exist_ok=True)
        data = {
            "toggles": toggles,
            "ac_enabled": ac_enabled,
            "user_points": user_points,
            "role_configs": role_configs,
            "points_per_quest": points_per_quest,
            "unlocked_servers": unlocked_servers,
            "force_locked": force_locked
        }
        with open(MEMORY_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("Error saving memory:", e)

memory = load_memory()
toggles = memory.get("toggles", {})
ac_enabled = memory.get("ac_enabled", {})
user_points = memory.get("user_points", {})
role_configs = memory.get("role_configs", {})
points_per_quest = memory.get("points_per_quest", {})
unlocked_servers = memory.get("unlocked_servers", {})
force_locked = memory.get("force_locked", {})
active_quests = {}

def load_ac_knowledge():
    try:
        with open("animal_company_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print("Error loading AC knowledge:", e)
        return "Animal Company is a free multiplayer VR survival game on Meta Quest."

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

# ================= MANUAL UNLOCK VIEW =================

class ManualUnlockView(View):
    def __init__(self, guild_id: int, guild_name: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.guild_name = guild_name

    @discord.ui.button(label="Request Manual Unlock", style=discord.ButtonStyle.red, custom_id="manual_unlock_btn")
    async def request_unlock(self, interaction: discord.Interaction, button: Button):
        try:
            owner = await bot.fetch_user(OWNER_ID)
            embed = discord.Embed(
                title="🔓 Manual Unlock Request",
                description=(
                    f"**Server:** {self.guild_name}\n"
                    f"**Server ID:** `{self.guild_id}`\n\n"
                    f"**Requested by:** {interaction.user} (`{interaction.user.id}`)\n\n"
                    f"Use `!unlock` in that server to unlock it."
                ),
                color=0xE74C3C
            )
            await owner.send(embed=embed)
            await interaction.response.send_message("✅ Your request has been sent to the bot owner.", ephemeral=True)
        except Exception as e:
            print("Manual unlock request error:", e)
            await interaction.response.send_message("Failed to send request. Please try again later.", ephemeral=True)

# ================= LOCK + BLACKLIST =================

def is_server_unlocked(guild_id: int) -> bool:
    if force_locked.get(str(guild_id), False):
        return False
    return unlocked_servers.get(str(guild_id), False)

async def has_logged_in(discord_id: int) -> bool:
    try:
        result = supabase.table("users").select("discord_id").eq("discord_id", str(discord_id)).execute()
        return bool(result.data)
    except Exception as e:
        print("Error checking login:", e)
        return False

async def clear_user_login(discord_id: int):
    """Remove the user from the users table so they must log in again."""
    try:
        supabase.table("users").delete().eq("discord_id", str(discord_id)).execute()
        print(f"Cleared login for user {discord_id}")
    except Exception as e:
        print("Error clearing user login:", e)

async def is_blacklisted(user_id: int, guild_id: int = None) -> bool:
    try:
        res = supabase.table("users").select("*").eq("discord_id", str(user_id)).eq("is_blacklisted", True).eq("is_global", True).execute()
        if res.data:
            return True
        if guild_id:
            res = supabase.table("users").select("*").eq("discord_id", str(user_id)).eq("is_blacklisted", True).eq("server_id", str(guild_id)).execute()
            if res.data:
                return True
    except Exception as e:
        print("Blacklist check error:", e)
    return False

async def try_unlock_server(guild: discord.Guild):
    try:
        if force_locked.get(str(guild.id), False):
            if await has_logged_in(guild.owner_id):
                force_locked[str(guild.id)] = False
                unlocked_servers[str(guild.id)] = True
                save_memory()
                try:
                    owner = guild.owner or await bot.fetch_user(guild.owner_id)
                    embed = discord.Embed(
                        title="✅ KingChat Unlocked!",
                        description="Your server is now unlocked again.",
                        color=0x2ECC71
                    )
                    await owner.send(embed=embed)
                except:
                    pass
            return

        if is_server_unlocked(guild.id):
            return

        if await has_logged_in(guild.owner_id):
            unlocked_servers[str(guild.id)] = True
            save_memory()
            try:
                owner = guild.owner or await bot.fetch_user(guild.owner_id)
                embed = discord.Embed(
                    title="✅ KingChat Unlocked!",
                    description="Your server is now unlocked.\nYou can use `/serverblacklist`.",
                    color=0x2ECC71
                )
                await owner.send(embed=embed)
            except:
                pass
    except Exception as e:
        print("Error in try_unlock_server:", e)

@tasks.loop(seconds=30)
async def check_all_servers():
    for guild in bot.guilds:
        await try_unlock_server(guild)

# ================= SETUP =================

class PointsModal(Modal, title="Set Points Per Quest"):
    points_input = TextInput(label="How many points per quest?", placeholder="5", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.points_input.value)
            if value < 1:
                return await interaction.response.send_message("Must be at least 1.", ephemeral=True)
            points_per_quest[str(interaction.guild_id)] = value
            save_memory()
            await interaction.response.send_message(f"✅ Each quest now gives **{value} points**.", ephemeral=True)
        except Exception as e:
            print("PointsModal error:", e)
            await interaction.response.send_message("Invalid number.", ephemeral=True)

class LevelRoleView(View):
    def __init__(self, guild_id: str, level: int):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.level = level

    @discord.ui.select(cls=RoleSelect, placeholder="Select role for this level", min_values=1, max_values=1)
    async def select_role(self, interaction: discord.Interaction, select: RoleSelect):
        try:
            role = select.values[0]
            if self.guild_id not in role_configs:
                role_configs[self.guild_id] = {}
            role_configs[self.guild_id][str(self.level)] = str(role.id)
            ac_enabled[self.guild_id] = True
            save_memory()
            await interaction.response.edit_message(content=f"✅ Level {self.level} → {role.mention}", view=None)
        except Exception as e:
            print("LevelRoleView error:", e)
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

class SetupView(View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    @discord.ui.button(label="Set Points Per Quest", style=discord.ButtonStyle.blurple)
    async def set_points(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PointsModal())

    @discord.ui.select(
        placeholder="Choose a level...",
        options=[discord.SelectOption(label=f"Level {i}", value=str(i)) for i in range(1, 16)]
    )
    async def select_level(self, interaction: discord.Interaction, select: discord.ui.Select):
        level = int(select.values[0])
        view = LevelRoleView(self.guild_id, level)
        await interaction.response.send_message(f"Select role for **Level {level}**:", view=view, ephemeral=True)

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
                max_tokens=45,
                temperature=0.8
            )
            task = res.choices[0].message.content.strip()
        except Exception as e:
            print("Quest generation error:", e)
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
    try:
        unlocked_servers[str(guild.id)] = False
        force_locked[str(guild.id)] = False
        save_memory()

        owner = guild.owner
        if owner:
            embed = discord.Embed(
                title="🔒 KingChat is Locked",
                description=(
                    f"Thanks for adding **KingChat**!\n\n"
                    f"The bot is currently **locked**.\n\n"
                    f"To unlock it, log in with your Discord or Google account here:\n"
                    f"**{LOGIN_URL}**\n\n"
                    f"It will automatically unlock within 30 seconds after you log in.\n\n"
                    f"If you can’t log in with Discord or Google, click the button below to request a **manual unlock**."
                ),
                color=0xE67E22
            )
            view = ManualUnlockView(guild.id, guild.name)
            await owner.send(embed=embed, view=view)
    except Exception as e:
        print("Error in on_guild_join:", e)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        bot.add_view(ManualUnlockView(0, "placeholder"))
        check_all_servers.start()
        for guild in bot.guilds:
            await try_unlock_server(guild)
    except Exception as e:
        print("Error in on_ready:", e)

# ================= COMMANDS =================

@bot.command(name="stop")
async def stop(ctx):
    if ctx.author.id != OWNER_ID:
        return
    try:
        toggles[str(ctx.guild.id)] = False
        save_memory()
        await ctx.send("🛑 Bot stopped in this server.")
    except Exception as e:
        print("Stop command error:", e)

@bot.command(name="start")
async def start(ctx):
    if ctx.author.id != OWNER_ID:
        return
    try:
        toggles[str(ctx.guild.id)] = True
        save_memory()
        await ctx.send("🟢 Bot started in this server.")
    except Exception as e:
        print("Start command error:", e)

@bot.command(name="unlock")
async def unlock(ctx):
    if ctx.author.id != OWNER_ID:
        return
    try:
        unlocked_servers[str(ctx.guild.id)] = True
        force_locked[str(ctx.guild.id)] = False
        save_memory()
        await ctx.send("🔓 Server has been **unlocked** by the owner.")
        print(f"✅ Unlocked server: {ctx.guild.name} ({ctx.guild.id})")
    except Exception as e:
        print("Unlock command error:", e)
        await ctx.send("Failed to unlock the server.")

@bot.command(name="lock")
async def lock(ctx):
    if ctx.author.id != OWNER_ID:
        return
    try:
        unlocked_servers[str(ctx.guild.id)] = False
        force_locked[str(ctx.guild.id)] = True
        save_memory()

        # Clear the server owner's login so they must log in again
        await clear_user_login(ctx.guild.owner_id)

        await ctx.send("🔒 Server has been **locked**. The owner must log in again to unlock it.")

        # Send the locked embed to the server owner
        try:
            owner = ctx.guild.owner or await bot.fetch_user(ctx.guild.owner_id)
            embed = discord.Embed(
                title="🔒 KingChat is Locked",
                description=(
                    f"The bot has been **locked** in **{ctx.guild.name}**.\n\n"
                    f"To unlock it, log in with your Discord or Google account here:\n"
                    f"**{LOGIN_URL}**\n\n"
                    f"It will automatically unlock within 30 seconds after you log in.\n\n"
                    f"If you can’t log in with Discord or Google, click the button below to request a **manual unlock**."
                ),
                color=0xE67E22
            )
            view = ManualUnlockView(ctx.guild.id, ctx.guild.name)
            await owner.send(embed=embed, view=view)
        except Exception as e:
            print("Could not DM server owner on lock:", e)

        print(f"🔒 Locked server: {ctx.guild.name} ({ctx.guild.id})")
    except Exception as e:
        print("Lock command error:", e)
        await ctx.send("Failed to lock the server.")

@bot.tree.command(name="toggle", description="Turn the bot on or off in this server (Admins only)")
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction):
    try:
        if not is_server_unlocked(interaction.guild.id):
            return await interaction.response.send_message("Server is still locked. Owner must log in first.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        current = toggles.get(guild_id, True)
        toggles[guild_id] = not current
        save_memory()

        if toggles[guild_id]:
            await interaction.response.send_message("🟢 Bot is now **ON** in this server.", ephemeral=True)
        else:
            await interaction.response.send_message("🛑 Bot is now **OFF** in this server.", ephemeral=True)
    except Exception as e:
        print("Toggle error:", e)
        await interaction.response.send_message("Something went wrong.", ephemeral=True)

@bot.tree.command(name="setup", description="Setup AC Quest")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    try:
        if not is_server_unlocked(interaction.guild.id):
            return await interaction.response.send_message("Server is locked.", ephemeral=True)
        view = SetupView(str(interaction.guild_id))
        await interaction.response.send_message(embed=discord.Embed(title="⚙️ Setup", color=0x3498DB), view=view, ephemeral=True)
    except Exception as e:
        print("Setup error:", e)
        await interaction.response.send_message("Something went wrong.", ephemeral=True)

@bot.tree.command(name="points", description="Check your points")
async def points(interaction: discord.Interaction):
    try:
        pts = user_points.get(str(interaction.user.id), 0)
        await interaction.response.send_message(f"You have **{pts}** points.", ephemeral=True)
    except Exception as e:
        print("Points error:", e)
        await interaction.response.send_message("Something went wrong.", ephemeral=True)

@bot.tree.command(name="invite", description="Get the invite link for KingChat")
async def invite(interaction: discord.Interaction):
    try:
        invite_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&permissions=8&scope=bot%20applications.commands"
        
        embed = discord.Embed(
            title="Invite KingChat",
            description="Click the button below to add **KingChat** to your server!",
            color=0x00FF85
        )
        embed.set_footer(text="Thanks for supporting KingChat!")
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Invite KingChat", url=invite_url, style=discord.ButtonStyle.link))
        
        await interaction.response.send_message(embed=embed, view=view)
    except Exception as e:
        print("Invite error:", e)
        await interaction.response.send_message("Something went wrong.", ephemeral=True)

@bot.tree.command(name="help", description="Show all KingChat commands")
async def help_command(interaction: discord.Interaction):
    try:
        embed = discord.Embed(
            title="KingChat Help",
            description="Here are all the available commands:",
            color=0x1E90FF
        )
        
        embed.add_field(
            name="General",
            value=(
                "`/help` - Show this help message\n"
                "`/invite` - Get the bot invite link\n"
                "`/points` - Check your AC Quest points"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Admin Commands",
            value=(
                "`/toggle` - Turn the bot on/off in this server\n"
                "`/setup` - Setup AC Quest roles & points\n"
                "`/serverblacklist` - Blacklist a user in this server\n"
                "`/unblacklist` - Remove a user from blacklist"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Owner Only",
            value=(
                "`!unlock` - Force unlock the server\n"
                "`!lock` - Force lock the server (requires login again)\n"
                "`!stop` / `!start` - Stop or start the bot\n"
                "`/globalblacklist` - Blacklist a user everywhere"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Features",
            value=(
                "• Say **ac quest** to get a challenge\n"
                "• Mention **KingChat** or say the name to talk to it\n"
                "• Server locks until the owner logs in"
            ),
            inline=False
        )
        
        embed.set_footer(text="KingChat • Made by KingFrog")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        print("Help error:", e)
        await interaction.response.send_message("Something went wrong.", ephemeral=True)

@bot.tree.command(name="serverblacklist", description="Blacklist a user in this server only")
@app_commands.describe(user="User to blacklist")
async def serverblacklist(interaction: discord.Interaction, user: discord.User):
    try:
        if not is_server_unlocked(interaction.guild.id):
            return await interaction.response.send_message("Server is locked.", ephemeral=True)
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID):
            return await interaction.response.send_message("Only admins can use this.", ephemeral=True)

        supabase.table("users").upsert({
            "discord_id": str(user.id),
            "is_blacklisted": True,
            "is_global": False,
            "server_id": str(interaction.guild.id),
            "username": str(user)
        }).execute()

        try:
            embed = discord.Embed(
                title="🚫 You have been blacklisted",
                description=f"You have been blacklisted in **{interaction.guild.name}**.\n\nLog in here:\n**{LOGIN_URL}**",
                color=0xE74C3C
            )
            await user.send(embed=embed)
        except:
            pass

        await interaction.response.send_message(f"✅ **{user}** has been blacklisted in this server.", ephemeral=True)
    except Exception as e:
        print("Serverblacklist error:", e)
        await interaction.response.send_message("Failed.", ephemeral=True)

@bot.tree.command(name="globalblacklist", description="Blacklist a user everywhere (Bot Owner only)")
@app_commands.describe(user="User to blacklist globally")
async def globalblacklist(interaction: discord.Interaction, user: discord.User):
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Only the bot owner can use this.", ephemeral=True)

        supabase.table("users").upsert({
            "discord_id": str(user.id),
            "google_email": None,
            "is_blacklisted": True,
            "is_global": True,
            "server_id": None,
            "username": str(user)
        }).execute()

        try:
            embed = discord.Embed(
                title="🚫 You have been globally blacklisted",
                description=(
                    f"**{user}** has been blacklisted from KingChat everywhere.\n\n"
                    f"Log in here if you want to appeal:\n**{LOGIN_URL}**"
                ),
                color=0xE74C3C
            )
            await user.send(embed=embed)
        except:
            pass

        await interaction.response.send_message(
            f"✅ **{user}** (`{user.id}`) has been globally blacklisted.",
            ephemeral=True
        )
    except Exception as e:
        print("Globalblacklist error:", e)
        await interaction.response.send_message("Failed to blacklist user.", ephemeral=True)

@bot.tree.command(name="unblacklist", description="Remove blacklist")
@app_commands.describe(user="User to unblacklist")
async def unblacklist(interaction: discord.Interaction, user: discord.User):
    try:
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID):
            return await interaction.response.send_message("No permission.", ephemeral=True)

        supabase.table("users").update({
            "is_blacklisted": False,
            "is_global": False,
            "server_id": None
        }).eq("discord_id", str(user.id)).execute()
        await interaction.response.send_message(f"✅ **{user}** has been unblacklisted.", ephemeral=True)
    except Exception as e:
        print("Unblacklist error:", e)
        await interaction.response.send_message("Failed.", ephemeral=True)

# ================= MESSAGE HANDLER =================

@bot.event
async def on_message(message: discord.Message):
    try:
        if message.author.bot:
            return

        # ========== HARD LOCK ==========
        # Allow the OWNER to still use commands even when locked
        if message.guild and not is_server_unlocked(message.guild.id):
            if message.author.id != OWNER_ID:
                return
        # ===============================

        # BLACKLIST CHECK
        guild_id = message.guild.id if message.guild else None
        if await is_blacklisted(message.author.id, guild_id):
            return

        # Proof system
        if isinstance(message.channel, discord.DMChannel):
            user_id = str(message.author.id)
            if user_id in active_quests and message.attachments:
                att = message.attachments[0]
                quest = active_quests[user_id]["task"]
                g_id = active_quests[user_id]["guild_id"]
                await message.channel.send("Checking your proof...")
                is_valid, reason = await check_proof(att.url, quest, att.filename)
                if is_valid:
                    pts = points_per_quest.get(g_id, 5)
                    user_points[user_id] = user_points.get(user_id, 0) + pts
                    save_memory()
                    del active_quests[user_id]
                    await message.channel.send(f"✅ Proof accepted! +{pts} points")
                else:
                    await message.channel.send(f"❌ Rejected: {reason}")
                return

        if not message.guild:
            return

        await bot.process_commands(message)

        # After processing commands, if server is still locked, don't talk
        if not is_server_unlocked(message.guild.id):
            return

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
                try:
                    me = message.guild.me
                    if me and mood in NICKNAMES:
                        await me.edit(nick=NICKNAMES[mood])
                except:
                    pass
    except Exception as e:
        print("on_message error:", e)
        traceback.print_exc()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
