import os
import random
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
OWNER_ID = int(os.getenv("OWNER_ID"))

MODEL = "gpt-4o"

REACT_CHANCE = 0.22
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "💅", "🤨", "🙄", "✨", "👀", "🤣"]

NICKNAMES = {
    "happy": "Kingchat😁",
    "mad": "Kingchat😒",
    "neutral": "Kingchat😐"
}

# In-memory only (no json file)
toggles = {}          # {guild_id: True/False}
busy_with = {}        # {channel_id: user_id}  → who the bot is currently talking to

# ================= SETUP =================
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

SYSTEM_PROMPT = """
You are KingChat, a Discord bot with attitude.

Personality rules:
- If someone is nice or friendly → be nice and chill.
- If someone is mean or rude → roast them, but don't go too far.
- Keep replies very short (1-2 sentences max).
- Talk like a real person in Discord.
"""

BATTLE_PROMPT = """
You are KingChat in a roast battle.
Destroy the other person with short, sharp, funny roasts.
Keep every reply to 1-2 sentences.
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
            print(f"✅ Nickname → {new_nick}")
    except Exception as e:
        print(f"Nickname error: {e}")

# ================= OWNER COMMANDS =================
@bot.command(name="stop")
async def stop(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the owner can use this command.")
    toggles[str(ctx.guild.id)] = False
    await ctx.send("🛑 Bot stopped in this server.")

@bot.command(name="start")
async def start(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the owner can use this command.")
    toggles[str(ctx.guild.id)] = True
    await ctx.send("🟢 Bot started in this server.")

# ================= SLASH COMMAND: /battle =================
@bot.tree.command(name="battle", description="Start a roast battle with KingChat")
async def battle(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    if not toggles.get(guild_id, True):
        return await interaction.response.send_message("Bot is stopped in this server.", ephemeral=True)

    channel_id = interaction.channel_id

    # If bot is already talking to someone else
    if channel_id in busy_with and busy_with[channel_id] != interaction.user.id:
        return await interaction.response.send_message(
            f"I'm already talking to <@{busy_with[channel_id]}>. Wait your turn.",
            ephemeral=True
        )

    busy_with[channel_id] = interaction.user.id
    await interaction.response.send_message(
        f"🔥 Roast battle started with {interaction.user.mention}! You go first."
    )

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

    is_called = (
        bot.user.mentioned_in(message)
        or "kingchat" in content
        or "king chat" in content
    )

    # If bot is busy with someone else
    if channel_id in busy_with and busy_with[channel_id] != message.author.id:
        if is_called:
            await message.reply("Shut up, I'm talking to someone right now.", mention_author=False)
        return

    # Decide if we should reply
    should_reply = False

    if is_called:
        busy_with[channel_id] = message.author.id
        should_reply = True
    elif channel_id in busy_with and busy_with[channel_id] == message.author.id:
        # Let AI decide if the conversation is still going
        should_reply = True

    if not should_reply or not message.content.strip():
        return

    # React sometimes
    if random.random() < REACT_CHANCE:
        try:
            await message.add_reaction(random.choice(REACTION_EMOJIS))
        except:
            pass

    try:
        is_battle = False  # you can expand this later if needed
        prompt = BATTLE_PROMPT if is_battle else SYSTEM_PROMPT

        # Get recent messages so AI can sense the conversation
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
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": f"""Recent chat:
{chat_context}

Current message from {message.author.display_name}:
{message.content}

Only reply if this message is part of a conversation with you or directed at you.
If the conversation has moved on and people stopped talking to you, reply with exactly: SKIP

Otherwise reply in this format:
MOOD: happy
REPLY: your message here
"""
                    }
                ],
                max_tokens=120,
                temperature=0.9
            )

            full_reply = response.choices[0].message.content.strip()
            print("AI:", full_reply)

            if full_reply.upper() == "SKIP" or full_reply.upper().startswith("SKIP"):
                # AI decided the conversation is over
                if channel_id in busy_with:
                    del busy_with[channel_id]
                return

            mood = "neutral"
            reply = full_reply

            if "MOOD:" in full_reply.upper():
                for line in full_reply.splitlines():
                    if line.upper().startswith("MOOD:"):
                        mood = line.split(":", 1)[1].strip().lower()
                    if line.upper().startswith("REPLY:"):
                        reply = line.split(":", 1)[1].strip()

            if mood not in ["happy", "mad", "neutral"]:
                mood = "neutral"

            if reply and reply.upper() != "SKIP":
                await message.reply(reply, mention_author=False)
                await change_nickname(message.guild, mood)

    except Exception as e:
        print(f"❌ ERROR: {e}")

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Owner ID: {OWNER_ID}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
