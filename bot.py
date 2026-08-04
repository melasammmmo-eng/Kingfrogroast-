import os
import random
import json
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ================= CONFIG =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = "gpt-4o"          # Changed to a more reliable model (change later if you want)

REPLY_CHANCE = 0.65       # High chance so it actually types
MIN_SECONDS_BETWEEN_REPLIES = 8

REACTION_EMOJIS = ["🐸", "👑", "💀", "🔥", "😈", "😭", "🤡", "💅", "🤨", "🙄", "💥", "✨"]

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
last_reply_time = {}

# ================= FIXED PERSONALITY =================
SYSTEM_PROMPT = """
You are KingFrogBot, a confident and dramatic frog king.

Personality rules:
- If the person is nice, friendly, or respectful → be warm, kind, supportive and playful.
- If the person is rude, toxic, mocking or disrespectful → be mean, ruthless, savage and roasting.
- Always reply in 1-2 short sentences only.
- Never be racist, sexist, or attack protected characteristics.
- Stay in character as a frog king.
"""

# ================= SLASH COMMAND =================
@bot.tree.command(name="toggle", description="Turn KingFrogBot on or off")
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

    status = "🟢 ON" if enabled else "🔴 OFF"
    await interaction.response.send_message(f"KingFrogBot is now {status}")

# ================= MESSAGE HANDLER =================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    guild_id = str(message.guild.id)
    if not toggles.get(guild_id, True):
        return

    # Always react
    try:
        await message.add_reaction(random.choice(REACTION_EMOJIS))
    except:
        pass

    # Reply logic
    if random.random() < REPLY_CHANCE and message.content.strip():
        channel_id = message.channel.id
        now = datetime.utcnow()

        last = last_reply_time.get(channel_id)
        if last and (now - last) < timedelta(seconds=MIN_SECONDS_BETWEEN_REPLIES):
            return

        last_reply_time[channel_id] = now

        try:
            print(f"Generating reply for: {message.content[:60]}")

            async with message.channel.typing():
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"Username: {message.author.display_name}\nMessage: {message.content}\n\nReply as KingFrogBot:"
                        }
                    ],
                    max_tokens=100,
                    temperature=0.9
                )

                reply = response.choices[0].message.content.strip()

                if reply:
                    await message.reply(reply, mention_author=False)
                    print("✅ Successfully sent reply")
                else:
                    print("⚠️ AI returned empty reply")

        except Exception as e:
            print(f"❌ ERROR WHILE REPLYING: {e}")

    await bot.process_commands(message)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Using model: {MODEL}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
