import os
import random
import json
import re

import discord
from discord import app_commands
from discord.ext import commands
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ================= CONFIG =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = "gpt-4o"

REPLY_CHANCE = 0.22          # Chance to reply to normal messages
REACT_CHANCE = 0.28          # Chance to react
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "💅", "🤨", "🙄", "✨", "👀", "🤣", "💀"]

# ================= SETUP =================
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOGGLE_FILE = "toggles.json"

def load_toggles():
    if os.path.exists(TOGGLE_FILE):
        with open(TOGGLE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_toggles(data):
    with open(TOGGLE_FILE, "w") as f:
        json.dump(data, f, indent=2)

toggles = load_toggles()

SYSTEM_PROMPT = """
You are KingChat, a normal, chill, and slightly chaotic Discord bot.

Personality:
- Talk like a regular person in a Discord server
- Be casual and modern
- If people are nice → be friendly
- If people are rude → be blunt and roasting
- Keep replies very short (1-2 sentences max)
- Never sound formal, medieval, or like a fantasy character
"""

# ================= SLASH COMMAND =================
@bot.tree.command(name="toggle", description="Turn KingChat on or off")
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
    enabled = state.value == "on"
    toggles[guild_id] = enabled
    save_toggles(toggles)

    await interaction.response.send_message(f"KingChat is now {'🟢 ON' if enabled else '🔴 OFF'}")

# ================= MESSAGE HANDLER =================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    guild_id = str(message.guild.id)
    if not toggles.get(guild_id, True):
        return

    content = message.content.lower()

    # Always read the message
    is_called = re.search(r"\bkingchat\b", content) or bot.user.mentioned_in(message)
    should_reply = is_called or (random.random() < REPLY_CHANCE)

    # React only sometimes
    if random.random() < REACT_CHANCE:
        try:
            await message.add_reaction(random.choice(REACTION_EMOJIS))
        except:
            pass

    if should_reply and message.content.strip():
        try:
            print(f"Reading & replying to: {message.content[:80]}")

            # Get recent chat so the bot understands context
            history = []
            async for msg in message.channel.history(limit=10):
                if msg.id == message.id:
                    continue
                history.append(f"{msg.author.display_name}: {msg.content}")
            history.reverse()
            chat_context = "\n".join(history[-7:])

            async with message.channel.typing():
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"""Recent chat:
{chat_context}

Current message from {message.author.display_name}:
{message.content}

Reply naturally as KingChat:"""
                        }
                    ],
                    max_tokens=90,
                    temperature=0.85
                )

                reply = response.choices[0].message.content.strip()

                if reply:
                    await message.reply(reply, mention_author=False)
                    print("✅ Reply sent")
                else:
                    await message.reply("yeah?", mention_author=False)

        except Exception as e:
            print(f"❌ ERROR: {e}")

    await bot.process_commands(message)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Model: {MODEL}")
    print("Now reading every message in the channel")
    try:
        await bot.tree.sync()
        print("Slash commands synced")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
