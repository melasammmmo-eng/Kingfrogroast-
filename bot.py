import os
import random
import re
import asyncio

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

REACT_CHANCE = 0.25
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "💅", "🤨", "🙄", "✨", "👀", "🤣"]

NICKNAMES = {
    "happy": "Kingchat😁",
    "mad": "Kingchat😒",
    "neutral": "Kingchat😐"
}

toggles = {}
busy_with = {}
in_battle = {}          # {channel_id: user_id}

# ================= SETUP =================
client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

SYSTEM_PROMPT = """
You are KingChat, a Discord bot with attitude.

Rules:
- If someone is nice → be nice and chill.
- If someone is mean → roast them (but not too hard).
- Keep replies very short (1-2 sentences max).
- Talk like a real person.
"""

BATTLE_PROMPT = """
You are KingChat in a full toxic roast battle.
Be extremely mean, ruthless, and career-ending with your roasts.
No mercy. No soft punches. Go for the throat.
Make them regret starting this.
Keep every reply short (1-2 sentences max).
Talk exactly like a toxic Discord user.
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

# ================= DELETE BATTLE MESSAGES =================
async def cleanup_battle_messages(channel, user_id):
    try:
        deleted = 0
        async for msg in channel.history(limit=50):
            if msg.author.id == bot.user.id or msg.author.id == user_id:
                try:
                    await msg.delete()
                    deleted += 1
                    await asyncio.sleep(0.35)
                except:
                    pass
        print(f"🧹 Deleted {deleted} battle messages")
    except Exception as e:
        print(f"Cleanup error: {e}")

# ================= OWNER COMMANDS =================
@bot.command(name="stop")
async def stop(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the owner can use this command.")
    toggles[str(ctx.guild.id)] = False
    await ctx.send("🛑 Bot stopped.")

@bot.command(name="start")
async def start(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the owner can use this command.")
    toggles[str(ctx.guild.id)] = True
    await ctx.send("🟢 Bot started.")

# ================= SLASH COMMAND =================
@bot.tree.command(name="battle", description="Start a toxic roast battle with KingChat")
async def battle(interaction: discord.Interaction):
    if not toggles.get(str(interaction.guild_id), True):
        return await interaction.response.send_message("Bot is stopped.", ephemeral=True)

    channel_id = interaction.channel_id

    if channel_id in busy_with and busy_with[channel_id] != interaction.user.id:
        return await interaction.response.send_message(
            f"I'm already talking to <@{busy_with[channel_id]}>.", ephemeral=True
        )

    busy_with[channel_id] = interaction.user.id
    in_battle[channel_id] = interaction.user.id

    await interaction.response.send_message(
        f"🔥 **ROAST BATTLE STARTED** between me and {interaction.user.mention}!\n"
        f"Say **give up** when you quit."
    )

# ================= HELPER: Detect if user gave up =================
def user_gave_up(text: str) -> bool:
    text = text.lower().strip()
    phrases = [
        "give up", "i give up", "you win", "fine you win", "i lose",
        "i surrender", "i quit", "gg you win", "ok you win", "okay you win",
        "you got me", "i'm done", "you win bro", "you win man"
    ]
    return any(p in text for p in phrases)

# ================= MESSAGE HANDLER =================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    await bot.process_commands(message)

    if not toggles.get(str(message.guild.id), True):
        return

    content = message.content.lower()
    channel_id = message.channel.id

    is_called = (
        bot.user.mentioned_in(message)
        or "kingchat" in content
        or "king chat" in content
    )

    # Busy with someone else
    if channel_id in busy_with and busy_with[channel_id] != message.author.id:
        if is_called:
            await message.reply("Shut up, I'm talking to someone right now.", mention_author=False)
        return

    # ===== BATTLE GIVE UP + CLEANUP =====
    if channel_id in in_battle and in_battle[channel_id] == message.author.id:
        if user_gave_up(message.content):
            await message.reply("Yeah I know. GG, easy win 😎", mention_author=False)

            # Delete the battle messages
            await cleanup_battle_messages(message.channel, message.author.id)

            # Clean up state
            del in_battle[channel_id]
            if channel_id in busy_with:
                del busy_with[channel_id]
            return

    should_reply = False
    is_battle = channel_id in in_battle and in_battle[channel_id] == message.author.id

    if is_called:
        busy_with[channel_id] = message.author.id
        should_reply = True
    elif channel_id in busy_with and busy_with[channel_id] == message.author.id:
        should_reply = True

    if not should_reply or not message.content.strip():
        return

    if random.random() < REACT_CHANCE:
        try:
            await message.add_reaction(random.choice(REACTION_EMOJIS))
        except:
            pass

    try:
        print(f"→ Generating reply for: {message.content[:70]}")

        history = []
        async for msg in message.channel.history(limit=10):
            if msg.id == message.id:
                continue
            history.append(f"{msg.author.display_name}: {msg.content}")
        history.reverse()
        chat_context = "\n".join(history[-7:])

        prompt = BATTLE_PROMPT if is_battle else SYSTEM_PROMPT

        async with message.channel.typing():
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": f"""Recent chat:
{chat_context}

{message.author.display_name} said: {message.content}

Reply as KingChat in 1-2 short sentences.
Also choose a mood: happy, mad, or neutral.

Answer in this exact format:
MOOD: mad
REPLY: your reply here"""
                    }
                ],
                max_tokens=100,
                temperature=0.95
            )

            full = response.choices[0].message.content.strip()
            print("AI returned:", full)

            mood = "neutral"
            reply = None

            for line in full.splitlines():
                if line.upper().startswith("MOOD:"):
                    mood = line.split(":", 1)[1].strip().lower()
                if line.upper().startswith("REPLY:"):
                    reply = line.split(":", 1)[1].strip()

            if not reply:
                reply = full

            if mood not in ["happy", "mad", "neutral"]:
                mood = "neutral"

            if reply:
                await message.reply(reply, mention_author=False)
                await change_nickname(message.guild, mood)
                print("✅ Reply sent")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        try:
            await message.reply("something went wrong", mention_author=False)
        except:
            pass

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
