
import os
import random
import json
import re
import io
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# ================= CONFIG =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

owner_id_env = os.getenv("OWNER_ID", "0")
OWNER_ID = int(owner_id_env) if owner_id_env.isdigit() else 0

MODEL = "gpt-4o"

REPLY_CHANCE = 0.25
REACT_CHANCE = 0.30
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "👋", "🤨", "🙄", "✨", "👀", "🤣"]

# Image paths for AI moods
AVATAR_PATHS = {
    "FRIENDLY": "avatars/happy.png",
    "SAVAGE": "avatars/savage.png",
    "NEUTRAL": "avatars/neutral.png"
}

current_mood = None 
server_memory = defaultdict(lambda: deque(maxlen=15))

# ================= SETUP =================
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOGGLE_FILE = "toggles.json"

def load_toggles():
    if os.path.exists(TOGGLE_FILE):
        try:
            with open(TOGGLE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading toggles: {e}")
            return {}
    return {}

def save_toggles(data):
    try:
        with open(TOGGLE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving toggles: {e}")

toggles = load_toggles()

SYSTEM_PROMPT = """
You are KingFrog, a highly responsive Discord personality.

Personality & Rules:
- Adapt your tone directly to the user's message:
  * IF THE USER IS NICE, COMPLIMENTARY, OR FRIENDLY: Be wholesome, genuinely friendly, sweet, and supportive back. Set MOOD: FRIENDLY.
  * IF THE USER IS RUDE, CRINGE, MID, OR TOXIC: Roast them relentlessly, be savage, sarcastic, and put them in their place. Set MOOD: SAVAGE.
  * IF THE MESSAGE IS NEUTRAL: Give a witty or casual Discord-style reply. Set MOOD: NEUTRAL.
- Keep every reply short (1-2 sentences max).
- Talk like a real person on Discord, using modern internet casual language.
- Never be racist, sexist, or attack protected characteristics.

OUTPUT FORMAT REQUIREMENTS:
Format your response exactly as:
MOOD: [FRIENDLY|SAVAGE|NEUTRAL]
REPLY: [Your actual reply here]
"""

async def update_avatar_for_mood(mood: str):
    global current_mood
    if mood == current_mood or mood not in AVATAR_PATHS:
        return

    filepath = AVATAR_PATHS[mood]
    if not os.path.exists(filepath):
        print(f"⚠️ Avatar image for '{mood}' not found at path: {filepath}")
        return

    try:
        with open(filepath, "rb") as image_file:
            avatar_bytes = image_file.read()
            await bot.user.edit(avatar=avatar_bytes)
            current_mood = mood
            print(f"🖼️ Updated profile picture to match mood: {mood}")
    except discord.HTTPException as e:
        print(f"⚠️ Discord avatar rate limit or HTTP error: {e}")
    except Exception as e:
        print(f"❌ Failed to update avatar: {e}")

def is_owner():
    async def predicate(ctx: commands.Context):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

# ================= PREFIX COMMANDS =================
@bot.command(name="start")
@is_owner()
async def start_bot(ctx: commands.Context):
    if not ctx.guild:
        return
    guild_id = str(ctx.guild.id)
    toggles[guild_id] = True
    save_toggles(toggles)
    await ctx.reply("🟢 KingFrog has been enabled in this server.")

@bot.command(name="stop")
@is_owner()
async def stop_bot(ctx: commands.Context):
    if not ctx.guild:
        return
    guild_id = str(ctx.guild.id)
    toggles[guild_id] = False
    save_toggles(toggles)
    await ctx.reply("🔴 KingFrog has been disabled in this server.")

@start_bot.error
@stop_bot.error
async def owner_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ Only the bot owner can use this command.")

# ================= SLASH COMMAND =================
@bot.tree.command(name="toggle", description="Turn KingFrog on or off")
@app_commands.describe(state="on or off")
@app_commands.choices(state=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def toggle(interaction: discord.Interaction, state: app_commands.Choice[str]):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    enabled = (state.value == "on")
    toggles[guild_id] = enabled
    save_toggles(toggles)

    await interaction.response.send_message(f"KingFrog is now {'🟢 ON' if enabled else '🔴 OFF'}")

# ================= MESSAGE HANDLER =================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    guild_id = str(message.guild.id)
    server_memory[guild_id].append(f"{message.author.display_name}: {message.content}")

    if not toggles.get(guild_id, True):
        return

    content = message.content.lower()
    is_called = re.search(r"\bkingfrog\b", content) or bot.user.mentioned_in(message)
    should_reply = is_called or (random.random() < REPLY_CHANCE)

    if random.random() < REACT_CHANCE:
        try:
            await message.add_reaction(random.choice(REACTION_EMOJIS))
        except Exception:
            pass

    if should_reply and message.content.strip():
        try:
            print(f"Responding in Server [{guild_id}]: {message.content[:80]}")

            recent_context = "\n".join(list(server_memory[guild_id])[-8:])

            async with message.channel.typing():
                response = await client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"Recent server chat context:\n{recent_context}\n\nCurrent message from {message.author.display_name}:\n{message.content}"
                        }
                    ],
                    max_tokens=120,
                    temperature=0.9
                )

                raw_text = response.choices[0].message.content.strip()

                mood_match = re.search(r"MOOD:\s*(FRIENDLY|SAVAGE|NEUTRAL)", raw_text, re.IGNORECASE)
                reply_match = re.search(r"REPLY:\s*(.*)", raw_text, re.DOTALL | re.IGNORECASE)

                detected_mood = mood_match.group(1).upper() if mood_match else "NEUTRAL"
                reply = reply_match.group(1).strip() if reply_match else raw_text

                await update_avatar_for_mood(detected_mood)

                if reply:
                    await message.reply(reply, mention_author=False)
                    server_memory[guild_id].append(f"KingFrog: {reply}")
                    print(f"✅ Response sent [{detected_mood}]")
                else:
                    await message.reply("mid message tbh", mention_author=False)

        except Exception as e:
            print(f"❌ ERROR: {e}")

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Model: {MODEL}")
    print("KingFrog active")
    try:
        await bot.tree.sync()
        print("Slash commands synced")
    except Exception as e:
        print(f"Sync error: {e}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
