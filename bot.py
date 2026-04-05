import discord
from discord.ext import commands, tasks
import random
import json
import os
import asyncio
import time
from datetime import datetime, timedelta, timezone
import asyncpg

# --- Bot setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Files ---
CARDS_FILE = "cards.json"

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

RARITY_ORDER = {
    "mythic": 5,
    "legendary": 4,
    "epic": 3,
    "rare": 2,
    "common": 1
}

# Placeholder images for rarities
RARITY_PLACEHOLDER_IMAGES = {
    "common": "common_placeholder.png",
    "rare": "rare_placeholder.png",
    "epic": "epic_placeholder.png",
    "legendary": "legendary_placeholder.png",
    "mythic": "mythic_placeholder.png"
}

# --- Database ---
DB_URL = os.getenv("DATABASE_URL")  # Railway Postgres URL

async def init_db():
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            money INT DEFAULT 100,
            xp INT DEFAULT 0,
            level INT DEFAULT 1,
            last_claim BIGINT DEFAULT 0,
            cards TEXT DEFAULT '[]'
        )
    """)
    await conn.close()

asyncio.run(init_db())

# --- Load cards ---
def load_json(file_name, default):
    if not os.path.exists(file_name):
        return default
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

cards = load_json(CARDS_FILE, [])

# --- User functions ---
async def get_user(user_id: int):
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
    if row:
        user = dict(row)
        user["cards"] = json.loads(user["cards"])
    else:
        user = {
            "user_id": user_id,
            "money": 100,
            "xp": 0,
            "level": 1,
            "last_claim": 0,
            "cards": []
        }
        await conn.execute(
            "INSERT INTO users (user_id, money, xp, level, last_claim, cards) VALUES ($1,$2,$3,$4,$5,$6)",
            user_id, 100, 0, 1, 0, json.dumps([])
        )
    await conn.close()
    return user

async def save_user(user: dict):
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("""
        UPDATE users
        SET money=$1, xp=$2, level=$3, last_claim=$4, cards=$5
        WHERE user_id=$6
    """, user["money"], user["xp"], user["level"], user["last_claim"], json.dumps(user["cards"]), user["user_id"])
    await conn.close()

# --- XP and leveling ---
def xp_needed_for_level(level: int) -> int:
    return 100 + (level - 1) * 50

def make_progress_bar(current: int, maximum: int, size: int = 10) -> str:
    if maximum <= 0:
        return "⬜" * size
    ratio = current / maximum
    filled = int(ratio * size)
    filled = max(0, min(filled, size))
    empty = size - filled
    return "🟩" * filled + "⬜" * empty

def add_xp(user: dict, amount: int):
    if amount <= 0:
        return 0
    user["xp"] += amount
    level_ups = 0
    while user["xp"] >= xp_needed_for_level(user["level"]):
        need = xp_needed_for_level(user["level"])
        user["xp"] -= need
        user["level"] += 1
        level_ups += 1
    return level_ups

# --- Cards functions ---
def get_random_card():
    if not cards:
        return None
    total_chance = sum(float(card.get("chance", 0)) for card in cards)
    if total_chance <= 0:
        return random.choice(cards)
    roll = random.uniform(0, total_chance)
    current = 0
    for card in cards:
        current += float(card.get("chance", 0))
        if roll <= current:
            return card
    return random.choice(cards)

def get_card_by_name(name: str):
    for card in cards:
        if card.get("name") == name:
            return card
    return None

def make_card_embed(title, card, footer_text=None, extra_text=None, show_image=True):
    rarity = card.get("rarity", "common")
    chance = card.get("chance", 0)
    name = card.get("name", "Unknown")

    embed = discord.Embed(
        title=title,
        description=(
            f"🎴 **{name}**\n"
            f"🌈 Рідкість: **{rarity}**\n"
            f"🎲 Шанс: **{chance}%**"
        ),
        color=rarity_colors.get(rarity, 0xFFFFFF)
    )
    if extra_text:
        embed.add_field(name="Інформація", value=extra_text, inline=False)
    image = str(card.get("image", "")).strip()
    if show_image and image:
        embed.set_image(url=image)
    if footer_text:
        embed.set_footer(text=footer_text)
    return embed

def build_inventory_items(owned_cards: list):
    counts = {}
    for card_name in owned_cards:
        counts[card_name] = counts.get(card_name, 0) + 1
    items = []
    for card_name, count in counts.items():
        card = get_card_by_name(card_name)
        rarity = card.get("rarity", "common") if card else "common"
        chance = card.get("chance", 0) if card else 0
        image = card.get("image", "") if card else ""
        items.append({
            "name": card_name,
            "count": count,
            "rarity": rarity,
            "chance": chance,
            "image": image
        })
    return items

def get_leaderboard_embed(guild):
    return discord.Embed(title="🏆 Таблиця лідерів", description="Підтримка постгрес потребує async leaderboard", color=0xF1C40F)
