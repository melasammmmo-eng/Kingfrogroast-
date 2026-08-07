import os
import random
import json
import re

import discord
from discord.ext import commands
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ================= CONFIG =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))   # Only you can use !start and !stop

MODEL = "gpt-4o"

REPLY_CHANCE = 0.15
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
You are KingChat, a Discord bot with attitude.

Personality rules:
- If someone is nice or friendly → be nice, chill, and friendly back.
- If someone is mean, rude, or toxic → be mean and roast them, but don't go too far.
- Keep replies short (1-2 sentences max).
- Talk like a real person in Discord.
- Never be extremely toxic, racist, or attack protected characteristics.
"""

# ================= CHANGE PROFILE PICTURE =================
async def change_avatar(mood: str):
    global current_mood
    if mood == current_mood:
        return

    for ext in [".png", ".jpg"]:
        path = f"moods/{mood}{ext}"
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    await bot.user.edit(avatar=f.read())
                current_mood = mood
                print(f"✅ Profile picture changed to: {mood}")
                return
            except Exception as e:
                print(f"Failed to change avatar: {e}")
                return

    print(f"❌ No image found for mood: {mood}")

# ================= OWNER ONLY COMMANDS =================
@bot.command(name="stop")
async def stop(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the owner can use this command.")
    
    guild_id = str(ctx.guild.id)
    toggles[guild_id] = False
    save_toggles(toggles)
    await ctx.send("🛑 Bot stopped in this server.")

@bot.command(name="start")
async def start(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the owner can use this command.")
    
    guild_id = str(ctx.guild.id)
    toggles[guild_id] = True
    save_toggles(toggles)
    await ctx.send("🟢 Bot started in this server.")

# ================= MESSAGE HANDLER =================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    await bot.process_commands(message)

    guild_id = str(message.guild.id)
    if not toggles.get(guild_id, True):
        return

    content = message.content.lower()

    is_called = re.search(r"\bkingchat\b", content) or bot.user.mentioned_in(message)
    should_reply = is_called or (random.random() < REPLY_CHANCE)

    if random.random() < REACT_CHANCE:
        try:
            await message.add_reaction(random.choice(REACTION_EMOJIS))
        except:
            pass

    if should_reply and message.content.strip():
        try:
            print(f"Thinking about: {message.content[:80]}")

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

Reply as KingChat.
Also decide your mood (happy, mad, or neutral).

Format exactly like this:
MOOD: neutral
REPLY: your message here
"""
                        }
                    ],
                    max_tokens=120,
                    temperature=0.9
                )

                full_reply = response.choices[0].message.content.strip()
                print(full_reply)

                mood = "neutral"
                reply = full_reply

                if "MOOD:" in full_reply and "REPLY:" in full_reply:
                    for line in full_reply.splitlines():
                        if line.startswith("MOOD:"):
                            mood = line.replace("MOOD:", "").strip().lower()
                        if line.startswith("REPLY:"):
                            reply = line.replace("REPLY:", "").strip()

                if mood not in ["happy", "mad", "neutral"]:
                    mood = "neutral"

                if reply:
                    await message.reply(reply, mention_author=False)
                    await change_avatar(mood)

        except Exception as e:
            print(f"❌ ERROR: {e}")

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Owner ID: {OWNER_ID}")
    print("Commands: !start | !stop (Owner only)")
    if os.path.exists("moods"):
        print("Moods folder found:", os.listdir("moods"))
    else:
        print("⚠️ 'moods' folder not found!")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
