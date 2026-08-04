
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
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

MODEL = "gpt-4o"

REPLY_CHANCE = 0.25
REACT_CHANCE = 0.30
REACTION_EMOJIS = ["😂", "💀", "🔥", "😭", "🤡", "💅", "🤨", "🙄", "✨", "👀", "🤣"]

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
You are KingChat, a highly responsive Discord personality.

Personality & Rules:
- Adapt your tone directly to the user's message:
  * IF THE USER IS NICE, COMPLIMENTARY, OR FRIENDLY: Be wholesome, genuinely friendly, sweet, and supportive back.
  * IF THE USER IS RUDE, CRINGE, MID, OR TOXIC: Roast them relentlessly, be savage, sarcastic, and put them in their place.
  * IF THE MESSAGE IS NEUTRAL: Give a witty or casual Discord-style reply.
- Keep every reply short (1-2 sentences max).
- Talk like a real person on Discord, using modern internet casual language.
- Never be racist, sexist, or attack protected characteristics.
"""

# Helper function to check owner permission
def is_owner():
    async def predicate(ctx: commands.Context):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

# ================= PREFIX COMMANDS (OWNER ONLY) =================
@bot.command(name="start")
@is_owner()
async def start_bot(ctx: commands.Context):
    if not ctx.guild:
        return
    guild_id = str(ctx.guild.id)
    toggles[guild_id] = True
    save_toggles(toggles)
    await ctx.reply("🟢 KingChat has been enabled in this server.")

@bot.command(name="stop")
@is_owner()
async def stop_bot(ctx: commands.Context):
    if not ctx.guild:
        return
    guild_id = str(ctx.guild.id)
    toggles[guild_id] = False
    save_toggles(toggles)
    await ctx.reply("🔴 KingChat has been disabled in this server.")

@start_bot.error
@stop_bot.error
async def owner_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ Only the bot owner can use this command.")

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

    # Always process bot commands first (!start, !stop, etc.)
    await bot.process_commands(message)

    guild_id = str(message.guild.id)
    if not toggles.get(guild_id, True):
        return

    content = message.content.lower()

    # Ignore messages that start with the command prefix to prevent double execution
    if content.startswith("!"):
        return

    is_called = re.search(r"\bkingchat\b", content) or bot.user.mentioned_in(message)
    should_reply = is_called or (random.random() < REPLY_CHANCE)

    # React only sometimes
    if random.random() < REACT_CHANCE:
        try:
            await message.add_reaction(random.choice(REACTION_EMOJIS))
        except Exception:
            pass

    if should_reply and message.content.strip():
        try:
            print(f"Responding to: {message.content[:80]}")

            # Get recent chat for context
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

Evaluate their tone: If nice, respond warmly. If mean/rude/cringe, roast them savagely."""
                        }
                    ],
                    max_tokens=90,
                    temperature=0.9
                )

                reply = response.choices[0].message.content.strip()

                if reply:
                    await message.reply(reply, mention_author=False)
                    print("✅ Response sent")
                else:
                    await message.reply("mid message tbh", mention_author=False)

        except Exception as e:
            print(f"❌ ERROR: {e}")

# ================= READY =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print(f"Model: {MODEL}")
    print("KingChat active")
    try:
        await bot.tree.sync()
        print("Slash commands synced")
    except Exception as e:
        print(e)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

```
