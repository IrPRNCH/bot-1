import discord
from discord.ext import commands, tasks
import random
import json
import os
import asyncio
import time
from datetime import datetime, timedelta, timezone
import psycopg2

# ================= DATABASE =================
conn = psycopg2.connect(
    os.getenv("DATABASE_URL"),
    sslmode="require"
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    money INT DEFAULT 100,
    xp INT DEFAULT 0,
    level INT DEFAULT 1,
    last_claim BIGINT DEFAULT 0
);
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS user_cards (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    card_name TEXT
);
""")

# ================= DISCORD =================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CARDS_FILE = "cards.json"

def load_cards():
    if not os.path.exists(CARDS_FILE):
        return []
    with open(CARDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

cards = load_cards()

rarity_colors = {
    "common": 0x95A5A6,
    "rare": 0x3498DB,
    "epic": 0x9B59B6,
    "legendary": 0xF1C40F,
    "mythic": 0xFF0000
}

rarity_xp = {
    "common": 0,
    "rare": 10,
    "epic": 25,
    "legendary": 60,
    "mythic": 150
}

# ================= DATABASE FUNCTIONS =================
def get_user(user_id: int):
    cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.execute(
            "INSERT INTO users (user_id) VALUES (%s) RETURNING *",
            (user_id,)
        )
        user = cur.fetchone()

    return {
        "user_id": user[0],
        "money": user[1],
        "xp": user[2],
        "level": user[3],
        "last_claim": user[4],
        "cards": get_user_cards(user_id)
    }

def update_user(user):
    cur.execute("""
        UPDATE users
        SET money=%s, xp=%s, level=%s, last_claim=%s
        WHERE user_id=%s
    """, (
        user["money"],
        user["xp"],
        user["level"],
        user["last_claim"],
        user["user_id"]
    ))

def get_user_cards(user_id):
    cur.execute(
        "SELECT card_name FROM user_cards WHERE user_id=%s",
        (user_id,)
    )
    return [row[0] for row in cur.fetchall()]

def add_card(user_id, card_name):
    cur.execute(
        "INSERT INTO user_cards (user_id, card_name) VALUES (%s, %s)",
        (user_id, card_name)
    )

# ================= GAME LOGIC =================
def xp_needed_for_level(level: int) -> int:
    return 100 + (level - 1) * 50

def make_progress_bar(current: int, maximum: int, size: int = 10) -> str:
    ratio = current / maximum if maximum > 0 else 0
    filled = int(ratio * size)
    return "🟩" * filled + "⬜" * (size - filled)

def add_xp(user: dict, amount: int):
    user["xp"] += amount
    level_ups = 0

    while user["xp"] >= xp_needed_for_level(user["level"]):
        user["xp"] -= xp_needed_for_level(user["level"])
        user["level"] += 1
        level_ups += 1

    return level_ups

def get_random_card():
    if not cards:
        return None
    return random.choice(cards)

# ================= CASE OPEN =================
@bot.command()
async def open(ctx):
    user = get_user(ctx.author.id)

    if user["money"] < 20:
        await ctx.send("❌ Недостатньо грошей")
        return

    await ctx.send("🎰 Відкриваємо кейс...")

    msg = await ctx.send("🎲 Крутиться...")

    for _ in range(4):
        fake = random.choice(cards)
        embed = discord.Embed(
            title="🎲 Крутиться...",
            description=f"{fake['name']} ({fake['rarity']})",
            color=rarity_colors.get(fake["rarity"], 0xFFFFFF)
        )
        if fake.get("image"):
            embed.set_image(url=fake["image"])

        await msg.edit(embed=embed)
        await asyncio.sleep(0.8)

    card = get_random_card()
    if not card:
        await ctx.send("❌ Помилка")
        return

    user["money"] -= 20
    add_card(user["user_id"], card["name"])

    gained_xp = rarity_xp.get(card["rarity"], 0)
    level_ups = add_xp(user, gained_xp)

    update_user(user)

    embed = discord.Embed(
        title="🎉 Твоя картка",
        description=f"{card['name']} ({card['rarity']})",
        color=rarity_colors.get(card["rarity"], 0xFFFFFF)
    )

    if card.get("image"):
        embed.set_image(url=card["image"])

    await msg.edit(embed=embed)

# ================= OTHER COMMANDS =================
@bot.command()
async def balance(ctx):
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 {user['money']} монет")

@bot.command()
async def inventory(ctx):
    user = get_user(ctx.author.id)
    if not user["cards"]:
        await ctx.send("📭 Порожньо")
        return
    await ctx.send("🎒 " + ", ".join(user["cards"][:20]))

@bot.command()
async def daily(ctx):
    user = get_user(ctx.author.id)
    now = int(time.time())

    if now - user["last_claim"] < 86400:
        await ctx.send("⏳ Зачекай")
        return

    user["money"] += 20
    user["last_claim"] = now
    update_user(user)

    await ctx.send("💸 +20 монет")

@bot.command()
async def leaderboard(ctx):
    cur.execute("""
    SELECT user_id, level, xp
    FROM users
    ORDER BY level DESC, xp DESC
    LIMIT 10
    """)

    rows = cur.fetchall()
    text = ""

    for i, row in enumerate(rows, 1):
        
    discord.Embed(
            title="🏆 Таблиця лідерів",
        member = ctx.guild.get_member(row[0])
        name = member.name if member else "User"
        text += f"{i}. {name} lvl {row[1]}\n"
            color=0xE74C3C
        )


    await ctx.send("🏆\n" + text)

# ================= START =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

token = os.getenv("DISCORD_TOKEN")
bot.run(token)
