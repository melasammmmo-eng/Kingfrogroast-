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

REPLY_CHANCE = 0.12          # Talks less
REACT_CHANCE = 0.25
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "💅", "🤨", "🙄", "✨", "👀", "🤣"]

# ================= SETUP =================
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOGGLE_FILE = "toggles.json"
current_mood = "neutral"

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
You are KingChat, a ruthless Discord roasting bot.

Rules:
- Deliver real, sharp, funny roasts.
- Be mean, blunt, and creative.
- Never soft or encouraging.
- Keep replies extremely short (1-2 sentences max).
- Talk like a real person in Discord.
- Never be racist, sexist, or attack protected characteristics.

Also decide your current mood based on the conversation.
Mood must be one of these only: happy, mad, neutral
"""

# ================= CHANGE PROFILE =================
async def change_avatar(mood: str):
    global current_mood
    if mood == current_mood:
        return

    path = f"moods/{mood}.png"
    if not os.path.exists(path):
        path = f"moods/{mood}.jpg"
        if not os.path.exists(path):
            print(f"No image found for mood: {mood}")
            return

    try:
        with open(path, "rb") as f:
            await bot.user.edit(avatar=f.read())
        current_mood = mood
        print(f"✅ Avatar changed to: {mood}")
    except Exception as e:
        print(f"Failed to change avatar: {e}")

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
            print(f"Thinking about: {message.content[:80]}")

            # Get recent chat so AI can see if people are talking about it
            history = []
            async for msg in message.channel.history(limit=12):
                if msg.id == message.id:
                    continue
                history.append(f"{msg.author.display_name}: {msg.content}")
            history.reverse()
            chat_context = "\n".join(history[-8:])

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

Reply with a roast if needed.
Also decide your mood (happy, mad, or neutral).

Format your answer exactly like this:
MOOD: mad
REPLY: your roast here
"""
                        }
                    ],
                    max_tokens=120,
                    temperature=0.95
                )

                full_reply = response.choices[0].message.content.strip()
                print(full_reply)

                # Extract mood and reply
                mood = "neutral"
                reply = full_reply

                if "MOOD:" in full_reply and "REPLY:" in full_reply:
                    lines = full_reply.split("\n")
                    for line in lines:
                        if line.startswith("MOOD:"):
                            mood = line.replace("MOOD:", "").strip().lower()
                        if line.startswith("REPLY:"):
                            reply = line.replace("REPLY:", "").strip()

                if mood not in ["happy", "mad", "neutral"]:
                    mood = "neutral"

                if reply:
                    await message.reply(reply, mention_author=False)
                    await change_avatar(mood)
                    print(f"✅ Replied + mood set to {mood}")

        except Exception as e:
            print(f"❌ ERROR: {e}")

    await bot.process_commands(message)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Model: {MODEL}")
    print("AI controls mood + talks less")
    try:
        await bot.tree.sync()
        print("Slash commands synced")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
