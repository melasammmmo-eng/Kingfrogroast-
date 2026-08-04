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

SYSTEM_PROMPT = """
You are KingFrogBot (also called KingChat), a confident frog king.

- If the person is nice → be friendly and kind.
- If the person is rude → be mean and ruthless.
- Always reply in 1-2 short sentences only.
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

    await interaction.response.send_message(f"KingFrogBot is now {'🟢 ON' if enabled else '🔴 OFF'}")

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

    content = message.content.lower()

    # Reply if "kingchat" appears anywhere in the sentence
    if re.search(r"\bkingchat\b", content) or bot.user.mentioned_in(message):
        try:
            print(f"Triggered by message: {message.content}")

            async with message.channel.typing():
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"{message.author.display_name} said: {message.content}\n\nReply as KingFrogBot:"
                        }
                    ],
                    max_tokens=80,
                    temperature=0.9
                )

                reply = response.choices[0].message.content.strip()

                if reply:
                    await message.reply(reply, mention_author=False)
                    print("✅ Reply sent")
                else:
                    await message.reply("The frog king has nothing to say right now.", mention_author=False)

        except Exception as e:
            print(f"❌ ERROR: {e}")
            await message.reply("Something went wrong in the swamp 🐸", mention_author=False)

    await bot.process_commands(message)

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Model: {MODEL}")
    try:
        await bot.tree.sync()
        print("Slash commands synced")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
