import os
import random
import json
import re
import asyncio
import traceback
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, RoleSelect
from groq import Groq
from dotenv import load_dotenv
from supabase import create_client, Client

from ac_recognise import check_proof

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))
CLIENT_ID = os.getenv("CLIENT_ID")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

MODEL = "llama-3.3-70b-versatile"
LOGIN_URL = "https://kingchat-ten.vercel.app"

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
active_conversations = {}

def load_ac_knowledge():
    try:
        with open("animal_company_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print("Error loading AC knowledge:", e)
        return "Animal Company is a free multiplayer VR survival game on Meta Quest."

AC_KNOWLEDGE = load_ac_knowledge()
client = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

SYSTEM_PROMPT = f"""
You are KingChat — a real person on Discord, not a bot.

Personality:
- Talk exactly like a normal Discord user
- Slightly selfish and a little mean, but not trying too hard
- When people insult you or annoy you, stay extremely chill and unbothered (use 🥱 often)
- Keep every reply short (1 sentence is perfect, max 2)
- Use casual language, slang, and emojis naturally
- Don’t sound helpful or formal
- Don’t explain things unless asked
- You can be arrogant in a lazy way

Examples of how you talk:
- "yea whatever 🥱"
- "lmao ok"
- "who asked"
- "damn aight"
- "not my problem"
- "bored already"

You know about Animal Company:
{AC_KNOWLEDGE}

Rules:
- Never say you are an AI or a bot
- Never write long messages
- Sound human
"""

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
            await interaction.response.send_message("Failed to send request.", ephemeral=True)

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
    try:
        supabase.table("users").delete().eq("discord_id", str(discord_id)).execute()
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
                    embed = discord.Embed(title="✅ KingChat Unlocked!", description="Your server is now unlocked again.", color=0x2ECC71)
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
                embed = discord.Embed(title="✅ KingChat Unlocked!", description="Your server is now unlocked.", color=0x2ECC71)
                await owner.send(embed=embed)
            except:
                pass
    except Exception as e:
        print("Error in try_unlock_server:", e)

@tasks.loop(seconds=30)
async def check_all_servers():
    for guild in bot.guilds:
        await try_unlock_server(guild)

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
        except:
            await interaction.response.send_message("Invalid number.", ephemeral=True)

class LevelRoleView(View):
    def __init__(self, guild_id: str, level: int):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.level = level

    @discord.ui.select(cls=RoleSelect, placeholder="Select role for this level", min_values=1, max_values=1)
    async def select_role(self, interaction: discord.Interaction, select: RoleSelect):
        role = select.values[0]
        if self.guild_id not in role_configs:
            role_configs[self.guild_id] = {}
        role_configs[self.guild_id][str(self.level)] = str(role.id)
        ac_enabled[self.guild_id] = True
        save_memory()
        await interaction.response.edit_message(content=f"✅ Level {self.level} → {role.mention}", view=None)

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
                    {"role": "system", "content": f"You know Animal Company well.\n{AC_KNOWLEDGE}\nGenerate one short realistic challenge. Only output the challenge."},
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
                    f"To unlock it, log in here:\n**{LOGIN_URL}**\n\n"
                    f"If you can’t log in, click the button below to request a manual unlock."
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

@bot.command(name="stop")
async def stop(ctx):
    if ctx.author.id != OWNER_ID:
        return
    toggles[str(ctx.guild.id)] = False
    save_memory()
    await ctx.send("🛑 Bot stopped in this server.")

@bot.command(name="start")
async def start(ctx):
    if ctx.author.id != OWNER_ID:
        return
    toggles[str(ctx.guild.id)] = True
    save_memory()
    await ctx.send("🟢 Bot started in this server.")

@bot.command(name="unlock")
async def unlock(ctx):
    if ctx.author.id != OWNER_ID:
        return
    unlocked_servers[str(ctx.guild.id)] = True
    force_locked[str(ctx.guild.id)] = False
    save_memory()
    await ctx.send("🔓 Server has been **unlocked** by the owner.")

@bot.command(name="lock")
async def lock(ctx):
    if ctx.author.id != OWNER_ID:
        return
    unlocked_servers[str(ctx.guild.id)] = False
    force_locked[str(ctx.guild.id)] = True
    save_memory()
    await clear_user_login(ctx.guild.owner_id)
    await ctx.send("🔒 Server has been **locked**. The owner must log in again.")

    try:
        owner = ctx.guild.owner or await bot.fetch_user(ctx.guild.owner_id)
        embed = discord.Embed(
            title="🔒 KingChat is Locked",
            description=(
                f"The bot has been locked in **{ctx.guild.name}**.\n\n"
                f"Log in here to unlock:\n**{LOGIN_URL}**\n\n"
                f"If you can’t log in, click the button below."
            ),
            color=0xE67E22
        )
        view = ManualUnlockView(ctx.guild.id, ctx.guild.name)
        await owner.send(embed=embed, view=view)
    except:
        pass

@bot.tree.command(name="toggle", description="Turn the bot on or off (Admins only)")
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction):
    if not is_server_unlocked(interaction.guild.id):
        return await interaction.response.send_message("Server is locked.", ephemeral=True)
    guild_id = str(interaction.guild.id)
    toggles[guild_id] = not toggles.get(guild_id, True)
    save_memory()
    status = "ON" if toggles[guild_id] else "OFF"
    await interaction.response.send_message(f"Bot is now **{status}**.", ephemeral=True)

@bot.tree.command(name="setup", description="Setup AC Quest")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    if not is_server_unlocked(interaction.guild.id):
        return await interaction.response.send_message("Server is locked.", ephemeral=True)
    view = SetupView(str(interaction.guild_id))
    await interaction.response.send_message(embed=discord.Embed(title="⚙️ Setup", color=0x3498DB), view=view, ephemeral=True)

@bot.tree.command(name="points", description="Check your points")
async def points(interaction: discord.Interaction):
    pts = user_points.get(str(interaction.user.id), 0)
    await interaction.response.send_message(f"You have **{pts}** points.", ephemeral=True)

@bot.tree.command(name="invite", description="Get the invite link")
async def invite(interaction: discord.Interaction):
    invite_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&permissions=8&scope=bot%20applications.commands"
    embed = discord.Embed(title="Invite KingChat", description="Add KingChat to your server!", color=0x00FF85)
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Invite KingChat", url=invite_url, style=discord.ButtonStyle.link))
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="KingChat Help", color=0x1E90FF)
    embed.add_field(name="General", value="`/help` `/invite` `/points`", inline=False)
    embed.add_field(name="Admin", value="`/toggle` `/setup` `/serverblacklist` `/unblacklist`", inline=False)
    embed.add_field(name="Owner Only", value="`!unlock` `!lock` `!stop` `!start` `/globalblacklist`", inline=False)
    embed.set_footer(text="KingChat • Made by KingFrog")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="serverblacklist", description="Blacklist a user in this server")
@app_commands.describe(user="User to blacklist")
async def serverblacklist(interaction: discord.Interaction, user: discord.User):
    if not is_server_unlocked(interaction.guild.id):
        return await interaction.response.send_message("Server is locked.", ephemeral=True)
    if not (interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID):
        return await interaction.response.send_message("No permission.", ephemeral=True)
    try:
        supabase.table("users").upsert({
            "discord_id": str(user.id),
            "is_blacklisted": True,
            "is_global": False,
            "server_id": str(interaction.guild.id),
            "username": str(user)
        }).execute()
        await interaction.response.send_message(f"✅ **{user}** blacklisted.", ephemeral=True)
    except:
        await interaction.response.send_message("Failed.", ephemeral=True)

@bot.tree.command(name="globalblacklist", description="Blacklist a user everywhere (Owner only)")
@app_commands.describe(user="User to blacklist")
async def globalblacklist(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only.", ephemeral=True)
    try:
        supabase.table("users").upsert({
            "discord_id": str(user.id),
            "is_blacklisted": True,
            "is_global": True,
            "username": str(user)
        }).execute()
        await interaction.response.send_message(f"✅ **{user}** globally blacklisted.", ephemeral=True)
    except:
        await interaction.response.send_message("Failed.", ephemeral=True)

@bot.tree.command(name="unblacklist", description="Remove blacklist")
@app_commands.describe(user="User to unblacklist")
async def unblacklist(interaction: discord.Interaction, user: discord.User):
    if not (interaction.user.guild_permissions.administrator or interaction.user.id == OWNER_ID):
        return await interaction.response.send_message("No permission.", ephemeral=True)
    try:
        supabase.table("users").update({"is_blacklisted": False, "is_global": False}).eq("discord_id", str(user.id)).execute()
        await interaction.response.send_message(f"✅ **{user}** unblacklisted.", ephemeral=True)
    except:
        await interaction.response.send_message("Failed.", ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    try:
        if message.author.bot:
            return

        if message.guild and not is_server_unlocked(message.guild.id):
            if message.author.id != OWNER_ID:
                return

        guild_id = message.guild.id if message.guild else None
        if await is_blacklisted(message.author.id, guild_id):
            return

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

        if not is_server_unlocked(message.guild.id):
            return
        if not toggles.get(str(message.guild.id), True):
            return

        content = message.content.lower()
        channel_id = message.channel.id

        if re.search(r"\bac\s*quest\b", content) and ac_enabled.get(str(message.guild.id), False):
            try:
                view = QuestStartView(message.author.id, str(message.guild.id))
                await message.author.send(embed=discord.Embed(title="🎮 AC Quest", description="Ready?", color=0x9B59B6), view=view)
                await message.reply("Check your DMs!", mention_author=False)
            except:
                await message.reply("I can't DM you.", mention_author=False)
            return

        # ===== TALKING SYSTEM =====
        is_mentioned = (
            bot.user.mentioned_in(message) or 
            "kingchat" in content or 
            "king chat" in content
        )
        
        is_active = channel_id in active_conversations

        current_time = time.time()
        to_remove = [cid for cid, ts in active_conversations.items() if current_time - ts > 150]
        for cid in to_remove:
            del active_conversations[cid]

        should_reply = False

        if is_mentioned:
            should_reply = True
            active_conversations[channel_id] = current_time
        elif is_active:
            should_reply = True
            active_conversations[channel_id] = current_time
        else:
            if random.random() < 0.05:
                should_reply = True
                active_conversations[channel_id] = current_time

        if not should_reply:
            return

        history = []
        async for m in message.channel.history(limit=6):
            if m.id == message.id:
                continue
            history.append(f"{m.author.display_name}: {m.content}")
        history.reverse()

        reply = None

        try:
            async with message.channel.typing():
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": "Recent chat:\n" + "\n".join(history) + f"\n\n{message.author.display_name}: {message.content}\n\nReply as KingChat (short and human):"}
                    ],
                    max_tokens=60,
                    temperature=0.9
                )
                reply = response.choices[0].message.content.strip()

        except Exception as e:
            print("=== AI ERROR ===")
            print(e)
            traceback.print_exc()
            if channel_id in active_conversations:
                del active_conversations[channel_id]
            return

        if reply:
            try:
                await message.reply(reply, mention_author=False)

                if random.random() < 0.4:
                    emojis = ["🥱", "😒", "💀", "😂", "🙄", "😎"]
                    try:
                        await message.add_reaction(random.choice(emojis))
                    except:
                        pass
            except Exception as e:
                print("Failed to send reply:", e)
        else:
            print("Empty reply from AI")
            if channel_id in active_conversations:
                del active_conversations[channel_id]

    except Exception as e:
        print("on_message error:", e)
        traceback.print_exc()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
