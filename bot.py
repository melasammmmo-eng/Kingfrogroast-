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

MODEL = "gpt-5"          # You can change this later if needed

ROAST_CHANCE = 0.55      # Increased so it replies more often
MIN_SECONDS_BETWEEN_ROASTS = 12

REACTION_EMOJIS = [
    "🐸", "👑", "💀", "🔥", "😈", "😭", "🤡", "💅", "🤨", "🙄",
    "💥", "🤢", "🤮", "🥱", "✨", "🐸", "👑"
]

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
last_roast_time = {}

# ================= AI PERSONALITY =================
async def generate_dynamic_system_prompt():
    meta_prompt = """
You are creating a unique system prompt for a Discord bot named KingFrogBot.

Core identity:
- Your name is KingFrogBot.
- You are a frog king — confident, dramatic, and full of personality.
- You are highly adaptive:
  • When someone is nice, friendly, or respectful → be warm, supportive, and kind.
  • When someone is rude, toxic, or disrespectful → become mean, ruthless, and savage.
- Always reply in 1-2 short sentences maximum.
- Never stay neutral.
- Never be racist, sexist, or attack protected characteristics.

Write ONLY the system prompt. No extra text.
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": meta_prompt}],
        max_tokens=400,
        temperature=1.1
    )
    return response.choices[0].message.content.strip()

# ================= SLASH COMMAND =================
@bot.tree.command(name="toggle", description="Turn KingFrogBot on or off")
@app_commands.describe(state="on or off")
@app_commands.choices(state=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def toggle(interaction: discord.Interaction, state: app_commands.Choice[str]):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need **Manage Server** permission.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    enabled = state.value == "on"
    toggles[guild_id] = enabled
    save_toggles(toggles)

    status = "🟢 **ON**" if enabled else "🔴 **OFF**"
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
    except Exception as e:
        print(f"Reaction error: {e}")

    # Try to reply
    if random.random() < ROAST_CHANCE and message.content.strip():
        channel_id = message.channel.id
        now = datetime.utcnow()

        last = last_roast_time.get(channel_id)
        if last and (now - last) < timedelta(seconds=MIN_SECONDS_BETWEEN_ROASTS):
            return

        last_roast_time[channel_id] = now

        try:
            print(f"Trying to reply to: {message.content[:50]}...")

            async with message.channel.typing():
                dynamic_system = await generate_dynamic_system_prompt()

                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": dynamic_system},
                        {
                            "role": "user",
                            "content": f"""Respond as KingFrogBot.

Username: {message.author.display_name}
Message: "{message.content}"

If they are nice → be kind.
If they are rude → be ruthless.
Keep it to 1-2 sentences only."""
                        }
                    ],
                    max_tokens=100,
                    temperature=0.95
                )

                reply = response.choices[0].message.content.strip()
                if reply:
                    await message.reply(reply, mention_author=False)
                    print("Successfully replied!")
                else:
                    print("Empty reply from AI")

        except Exception as e:
            print(f"REPLY ERROR: {e}")   # This will show the real problem in console

    await bot.process_commands(message)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"Using model: {MODEL}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
