import discord
from discord.ext import commands
import random
import json
import os
import asyncio
import time
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

# ================= CARDS =================
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
        cur.execute("INSERT INTO users (user_id) VALUES (%s) RETURNING *", (user_id,))
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
    cur.execute("SELECT card_name FROM user_cards WHERE user_id=%s", (user_id,))
    return [row[0] for row in cur.fetchall()]

def add_card(user_id, card_name):
    cur.execute("INSERT INTO user_cards (user_id, card_name) VALUES (%s, %s)", (user_id, card_name))

# ================= GAME LOGIC =================
def add_xp(user, amount):
    user["xp"] += amount
    while user["xp"] >= 100 + (user["level"] - 1) * 50:
        user["xp"] -= 100 + (user["level"] - 1) * 50
        user["level"] += 1

def get_random_card():
    return random.choice(cards) if cards else None


# ================= CASE SYSTEM =================
async def open_case_ui(interaction: discord.Interaction):
    user = get_user(interaction.user.id)

    if user["money"] < 20:
        await interaction.response.send_message("❌ Недостатньо грошей", ephemeral=True)
        return

    user["money"] -= 20
    update_user(user)

    await interaction.response.send_message("🎲 Крутиться...", ephemeral=True)
    msg = await interaction.original_response()

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
        return

    add_card(user["user_id"], card["name"])
    add_xp(user, rarity_xp.get(card["rarity"], 0))
    update_user(user)

    embed = discord.Embed(
        title="🎉 Твоя картка",
        description=f"{card['name']} ({card['rarity']})",
        color=rarity_colors.get(card["rarity"], 0xFFFFFF)
    )

    if card.get("image"):
        embed.set_image(url=card["image"])

    await msg.edit(embed=embed)


# ================= UI PANEL =================
class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎰 крутіть казіно", style=discord.ButtonStyle.green)
    async def case(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_case_ui(interaction)

    @discord.ui.button(label="💰 скіки в мене Гармакоїнів", style=discord.ButtonStyle.blurple)
    async def balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)
        await interaction.response.send_message(f"💰 {user['money']}", ephemeral=True)

    @discord.ui.button(label="🎒 пакажи маї карточкі", style=discord.ButtonStyle.gray)
    async def inventory(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)

        if not user["cards"]:
            await interaction.response.send_message("📭 нєту карточєк", ephemeral=True)
            return

        await interaction.response.send_message(
            "🎒 " + ", ".join(user["cards"][:25]),
            ephemeral=True
        )

    @discord.ui.button(label="🏆 хто самий крутий", style=discord.ButtonStyle.primary)
    async def leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):

        cur.execute("""
            SELECT user_id, level, xp
            FROM users
            ORDER BY level DESC, xp DESC
            LIMIT 10
        """)

        rows = cur.fetchall()

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        text = ""

        for i, (user_id, level, xp) in enumerate(rows, start=1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            icon = medals.get(i, f"{i}.")

            text += f"{icon} **{name}** — lvl {level} | xp {xp}\n"

        await interaction.response.send_message("🏆 Leaderboard\n\n" + text, ephemeral=True)

    @discord.ui.button(label="🎁 забрать дєньгі", style=discord.ButtonStyle.red)
    async def daily(self, interaction: discord.Interaction, button: discord.ui.Button):

        user = get_user(interaction.user.id)
        now = int(time.time())

        if now - user["last_claim"] < 86400:
            await interaction.response.send_message("⏳ Already claimed", ephemeral=True)
            return

        user["money"] += 20
        user["last_claim"] = now
        update_user(user)

        await interaction.response.send_message("💸 +20 coins", ephemeral=True)


# ================= PANEL COMMAND =================
@bot.command()
async def panel(ctx):
    embed = discord.Embed(
        title="🎮 іді нахкй",
        description="натискати знизу",
        color=0x2ECC71
    )

    await ctx.send(embed=embed, view=MainPanelView())


# ================= START =================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    bot.add_view(MainPanelView())


token = os.getenv("DISCORD_TOKEN")
bot.run(token)
