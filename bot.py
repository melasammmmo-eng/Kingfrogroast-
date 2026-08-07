import os
import random
import json
import re
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ================= CONFIG =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))

MODEL = "gpt-4o"

REACT_CHANCE = 0.22
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "💅", "🤨", "🙄", "✨", "👀", "🤣"]

# How long the bot stays in conversation mode after last interaction (in seconds)
CONVERSATION_TIMEOUT = 90

NICKNAMES = {
    "happy": "Kingchat😁",
    "mad": "Kingchat😒",
    "neutral": "Kingchat😐"
}

# ================= SETUP =================
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

TOGGLE_FILE = "toggles.json"
current_moods = {}
active_conversations = {}  # {channel_id: last_active_time}

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

# ================= CHANGE NICKNAME =================
async def change_nickname(guild, mood: str):
    mood = mood.lower().strip()
    if mood not in NICKNAMES:
        mood = "neutral"

    new_nick = NICKNAMES[mood]

    try:
        me = guild.me
        if me.nick != new_nick:
            await me.edit(nick=new_nick)
            current_moods[guild.id] = mood
            print(f"✅ Nickname changed to '{new_nick}' in {guild.name}")
    except Exception as e:
        print(f"❌ Failed to change nickname: {e}")

# ================= OWNER COMMANDS =================
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
    channel_id = message.channel.id
    now = datetime.utcnow()

    # Check if bot is being called
    is_called = (
        bot.user.mentioned_in(message)
        or "kingchat" in content
        or "king chat" in content
    )

    # Check if conversation is still active
    last_active = active_conversations.get(channel_id)
    in_conversation = last_active and (now - last_active) < timedelta(seconds=CONVERSATION_TIMEOUT)

    # Start or continue conversation
    if is_called:
        active_conversations[channel_id] = now
        should_reply = True
    elif in_conversation:
        # Still in conversation, reply sometimes so it feels natural
        should_reply = random.random() < 0.45
        if should_reply:
            active_conversations[channel_id] = now
    else:
        should_reply = False

    # React sometimes
    if random.random() < REACT_CHANCE:
        try:
            await message.add_reaction(random.choice(REACTION_EMOJIS))
        except:
            pass

    if not should_reply or not message.content.strip():
        return

    try:
        print(f"\nReplying in conversation: {message.content[:80]}")

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

Reply as KingChat.
Also decide your mood (happy, mad, or neutral).

You MUST reply in this exact format:
MOOD: happy
REPLY: your message here
"""
                    }
                ],
                max_tokens=110,
                temperature=0.9
            )

            full_reply = response.choices[0].message.content.strip()
            print("AI Response:", full_reply)

            mood = "neutral"
            reply = full_reply

            if "MOOD:" in full_reply.upper():
                for line in full_reply.splitlines():
                    line_upper = line.upper()
                    if line_upper.startswith("MOOD:"):
                        mood = line.split(":", 1)[1].strip().lower()
                    if line_upper.startswith("REPLY:"):
                        reply = line.split(":", 1)[1].strip()

            if mood not in ["happy", "mad", "neutral"]:
                mood = "neutral"

            if reply:
                await message.reply(reply, mention_author=False)
                await change_nickname(message.guild, mood)

    except Exception as e:
        print(f"❌ ERROR: {e}")

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Owner ID: {OWNER_ID}")
    print("Conversation mode active")
    print("Triggers: kingchat / king chat / ping")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
