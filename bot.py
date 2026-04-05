import discord
from discord.ext import commands, tasks
import random
import json
import os
import asyncio
import time
from datetime import datetime, timedelta, timezone

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"
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

# Тут шляхи до нових мінімалістичних знаків питання
# Поклади ці файли поруч з bot.py або зміни шляхи під себе
RARITY_PLACEHOLDER_IMAGES = {
    "common": "common_placeholder.png",
    "rare": "rare_placeholder.png",
    "epic": "epic_placeholder.png",
    "legendary": "legendary_placeholder.png",
    "mythic": "mythic_placeholder.png"
}


def load_json(file_name, default):
    if not os.path.exists(file_name):
        return default
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(file_name, data):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


data = load_json(DATA_FILE, {})
cards = load_json(CARDS_FILE, [])


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


def get_user(user_id: int):
    user_id = str(user_id)

    if user_id not in data:
        data[user_id] = {
            "money": 100,
            "cards": [],
            "last_claim": 0,
            "xp": 0,
            "level": 1
        }
        save_json(DATA_FILE, data)
    else:
        changed = False
        defaults = {
            "money": 100,
            "cards": [],
            "last_claim": 0,
            "xp": 0,
            "level": 1
        }

        for key, value in defaults.items():
            if key not in data[user_id]:
                data[user_id][key] = value
                changed = True

        if changed:
            save_json(DATA_FILE, data)

    return data[user_id]


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
        rarity = "common"
        chance = 0
        image = ""

        if card:
            rarity = card.get("rarity", "common")
            chance = card.get("chance", 0)
            image = card.get("image", "")

        items.append({
            "name": card_name,
            "count": count,
            "rarity": rarity,
            "chance": chance,
            "image": image
        })

    return items


def get_leaderboard_embed(guild):
    if not data:
        return discord.Embed(
            title="🏆 Таблиця лідерів",
            description="❌ Даних ще немає.",
            color=0xE74C3C
        )

    sorted_users = sorted(
        data.items(),
        key=lambda item: (item[1].get("level", 1), item[1].get("xp", 0)),
        reverse=True
    )

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    top_member = None

    for i, (user_id, user_data) in enumerate(sorted_users[:10], start=1):
        member = guild.get_member(int(user_id)) if guild else None

        if i == 1:
            top_member = member

        name = member.display_name if member else f"User {user_id}"
        lvl = user_data.get("level", 1)
        xp = user_data.get("xp", 0)

        icon = medals.get(i, f"**{i}.**")
        lines.append(f"{icon} **{name}** — Рівень **{lvl}** | XP **{xp}**")

    embed = discord.Embed(
        title="🏆 Таблиця лідерів",
        description="\n".join(lines),
        color=0xF1C40F
    )
    embed.set_footer(text="Топ 10 гравців сервера")

    if top_member:
        embed.set_thumbnail(url=top_member.display_avatar.url)

    return embed


async def send_panel(channel):
    embed = discord.Embed(
        title="🎰 Панель кейсів",
        description=(
            "Натискай кнопки нижче.\n\n"
            "Уся інформація відкривається особисто для гравця.\n"
            "Картинка випавшої картки видна тільки тому, хто її вибив."
        ),
        color=0x2ECC71
    )
    return await channel.send(embed=embed, view=CaseView())


@tasks.loop(minutes=10)
async def cleanup_panels():
    now = datetime.now(timezone.utc)
    limit_time = now - timedelta(hours=1)

    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                async for message in channel.history(limit=200):
                    if message.author != bot.user:
                        continue
                    if message.created_at >= limit_time:
                        continue
                    if not message.embeds:
                        continue

                    embed = message.embeds[0]
                    if embed.title == "🎰 Панель кейсів":
                        try:
                            await message.delete()
                        except Exception:
                            pass
            except Exception:
                pass


class InventorySearchModal(discord.ui.Modal, title="Пошук картки"):
    search_input = discord.ui.TextInput(
        label="Назва картки",
        placeholder="Наприклад: Naruto",
        required=True,
        max_length=100
    )

    def __init__(self, inventory_view):
        super().__init__()
        self.inventory_view = inventory_view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.inventory_view.owner_id:
            await interaction.response.send_message("❌ Це не твоє меню.", ephemeral=True)
            return

        self.inventory_view.search_query = str(self.search_input).strip()
        self.inventory_view.index = 0
        self.inventory_view.refresh_items()

        await interaction.response.edit_message(
            embed=self.inventory_view.get_current_embed(),
            view=self.inventory_view
        )


class InventoryView(discord.ui.View):
    def __init__(self, owner_id: int, owned_cards: list):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.base_items = build_inventory_items(owned_cards)
        self.search_query = ""
        self.sort_mode = "rarity"
        self.index = 0
        self.filtered_items = []
        self.refresh_items()

    def refresh_items(self):
        items = self.base_items[:]

        if self.search_query:
            q = self.search_query.lower()
            items = [item for item in items if q in item["name"].lower()]

        if self.sort_mode == "rarity":
            items.sort(
                key=lambda x: (-RARITY_ORDER.get(x["rarity"], 0), -x["count"], x["name"].lower())
            )
        elif self.sort_mode == "count":
            items.sort(
                key=lambda x: (-x["count"], -RARITY_ORDER.get(x["rarity"], 0), x["name"].lower())
            )
        else:
            items.sort(key=lambda x: x["name"].lower())

        self.filtered_items = items

        if self.index >= len(self.filtered_items):
            self.index = 0

    def get_current_embed(self):
        if not self.filtered_items:
            return discord.Embed(
                title="🎒 Інвентар",
                description="❌ Нічого не знайдено.",
                color=0xE74C3C
            )

        item = self.filtered_items[self.index]

        card = {
            "name": item["name"],
            "rarity": item["rarity"],
            "chance": item["chance"],
            "image": item["image"]
        }

        extra_text = (
            f"Кількість: **{item['count']}**\n"
            f"Сортування: **{self.sort_mode}**"
        )
        if self.search_query:
            extra_text += f"\nПошук: **{self.search_query}**"

        return make_card_embed(
            "🎒 Інвентар",
            card,
            footer_text=f"Картка {self.index + 1} з {len(self.filtered_items)}",
            extra_text=extra_text,
            show_image=True
        )

    async def ensure_owner(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Це не твоє меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        if self.filtered_items:
            self.index = (self.index - 1) % len(self.filtered_items)
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        if self.filtered_items:
            self.index = (self.index + 1) % len(self.filtered_items)
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="🌈 По рідкості", style=discord.ButtonStyle.primary, row=1)
    async def sort_rarity_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        self.sort_mode = "rarity"
        self.index = 0
        self.refresh_items()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="🔢 По кількості", style=discord.ButtonStyle.primary, row=1)
    async def sort_count_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        self.sort_mode = "count"
        self.index = 0
        self.refresh_items()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)

    @discord.ui.button(label="🔍 Пошук", style=discord.ButtonStyle.success, row=2)
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        await interaction.response.send_modal(InventorySearchModal(self))

    @discord.ui.button(label="♻️ Скинути", style=discord.ButtonStyle.danger, row=2)
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        self.search_query = ""
        self.sort_mode = "rarity"
        self.index = 0
        self.refresh_items()
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self)


class CardsListView(discord.ui.View):
    def __init__(self, owner_id: int, card_list: list):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.card_list = card_list
        self.index = 0

    def get_current_embed_and_file(self):
        card = self.card_list[self.index]
        rarity = card.get("rarity", "common")

        fake_card = {
            "name": card.get("name"),
            "rarity": rarity,
            "chance": card.get("chance"),
            "image": ""
        }

        embed = make_card_embed(
            "📋 Список карток",
            fake_card,
            footer_text=f"Картка {self.index + 1} з {len(self.card_list)}",
            show_image=False
        )

        image_path = RARITY_PLACEHOLDER_IMAGES.get(rarity)
        if image_path and os.path.exists(image_path):
            file = discord.File(image_path, filename="rarity.png")
            embed.set_image(url="attachment://rarity.png")
            return embed, file

        return embed, None

    async def ensure_owner(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Це не твоє меню.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        self.index = (self.index - 1) % len(self.card_list)
        embed, file = self.get_current_embed_and_file()
        await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        self.index = (self.index + 1) % len(self.card_list)
        embed, file = self.get_current_embed_and_file()
        await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)


class CaseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📦 Відкрити кейс", style=discord.ButtonStyle.primary, custom_id="case_open", row=0)
    async def open_case(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)
        cost = 20

        if user["money"] < cost:
            await interaction.response.send_message("❌ Недостатньо грошей для відкриття кейсу.", ephemeral=True)
            return

        if not cards:
            await interaction.response.send_message("❌ У системі ще немає карток.", ephemeral=True)
            return

        user["money"] -= cost
        save_json(DATA_FILE, data)

        await interaction.response.send_message("🎰 Відкриваємо кейс...", ephemeral=True)
        private_msg = await interaction.original_response()

        near_mythic = random.choice([True, False, False])

        for i in range(4):
            fake = random.choice(cards)

            if near_mythic and i == 2:
                mythics = [c for c in cards if c.get("rarity") == "mythic"]
                if mythics:
                    fake = random.choice(mythics)

            embed = discord.Embed(
                title="🎲 Крутиться...",
                description=(
                    f"👤 **{interaction.user.name}** відкриває кейс...\n\n"
                    f"🎴 **{fake.get('name', 'Unknown')}**\n"
                    f"🌈 **{fake.get('rarity', 'common')}**"
                ),
                color=rarity_colors.get(fake.get("rarity", "common"), 0xFFFFFF)
            )

            image = str(fake.get("image", "")).strip()
            if image:
                embed.set_image(url=image)

            await private_msg.edit(content=None, embed=embed, view=None)
            await asyncio.sleep(0.8)

        card = get_random_card()
        if card is None:
            await private_msg.edit(content="❌ Не вдалося отримати картку.", embed=None, view=None)
            return

        user["cards"].append(card["name"])

        gained_xp = rarity_xp.get(card["rarity"], 0)
        level_ups = add_xp(user, gained_xp)
        save_json(DATA_FILE, data)

        need = xp_needed_for_level(user["level"])
        bar = make_progress_bar(user["xp"], need, 10)

        xp_text = ""
        if gained_xp > 0:
            xp_text = f"\n⭐ XP: **+{gained_xp}**\n{bar}\n**{user['xp']} / {need} XP**"

        level_text = ""
        if level_ups > 0:
            level_text = f"\n🆙 **{interaction.user.name}** підняв рівень до **{user['level']}**!"

        private_result = discord.Embed(
            title="🎉 Твоя картка",
            description=(
                f"🎴 **{card['name']}**\n"
                f"🌈 Рідкість: **{card['rarity']}**"
                f"{xp_text}{level_text}"
            ),
            color=rarity_colors.get(card["rarity"], 0xFFFFFF)
        )

        image = str(card.get("image", "")).strip()
        if image:
            private_result.set_image(url=image)

        await private_msg.edit(content=None, embed=private_result, view=None)

        public_title = "🎉 ВІДКРИТТЯ КЕЙСУ"
        public_color = rarity_colors.get(card["rarity"], 0xFFFFFF)
        public_content = None

        if card["rarity"] == "mythic":
            public_title = "💥 JACKPOT!!! 💥"
            public_color = rarity_colors["mythic"]
            public_content = "🔥 Випала міфічна картка!"

        public_embed = discord.Embed(
            title=public_title,
            description=(
                f"👤 **{interaction.user.name}** відкрив кейс!\n\n"
                f"🎴 Йому випало: **{card['name']}**\n"
                f"🌈 Рідкість: **{card['rarity']}**"
                f"{xp_text}{level_text}"
            ),
            color=public_color
        )

        public_embed.set_author(
            name=f"{interaction.user.display_name} відкрив кейс",
            icon_url=interaction.user.display_avatar.url
        )
        public_embed.set_footer(text="Історія відкриттів кейсів")

        await interaction.channel.send(content=public_content, embed=public_embed)
        await send_panel(interaction.channel)

    @discord.ui.button(label="💰 Баланс", style=discord.ButtonStyle.success, custom_id="case_balance", row=0)
    async def balance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)
        embed = discord.Embed(
            title="💰 Баланс",
            description=f"Монети: **{user['money']}**\nРівень: **{user['level']}**",
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎒 Інвентар", style=discord.ButtonStyle.secondary, custom_id="case_inventory", row=1)
    async def inventory_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)
        if not user["cards"]:
            await interaction.response.send_message("📭 У тебе поки немає карток.", ephemeral=True)
            return

        view = InventoryView(interaction.user.id, user["cards"])
        await interaction.response.send_message(embed=view.get_current_embed(), view=view, ephemeral=True)

    @discord.ui.button(label="📋 Картки", style=discord.ButtonStyle.secondary, custom_id="case_cards", row=1)
    async def cards_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not cards:
            await interaction.response.send_message("❌ У системі немає карток.", ephemeral=True)
            return

        view = CardsListView(interaction.user.id, cards)
        embed, file = view.get_current_embed_and_file()
        await interaction.response.send_message(
            embed=embed,
            file=file,
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="💸 Забрати 20 монет", style=discord.ButtonStyle.danger, custom_id="case_give", row=2)
    async def give_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)
        now = int(time.time())
        cooldown = 86400
        time_passed = now - user["last_claim"]

        if time_passed < cooldown:
            left = cooldown - time_passed
            hours = left // 3600
            minutes = (left % 3600) // 60

            await interaction.response.send_message(
                f"⏳ Ти вже забирав нагороду.\nСпробуй через **{hours} год {minutes} хв**.",
                ephemeral=True
            )
            return

        amount = 20
        user["money"] += amount
        user["last_claim"] = now
        save_json(DATA_FILE, data)

        embed = discord.Embed(
            title="💸 Щоденна нагорода",
            description=f"Ти отримав **{amount}** монет!\nТепер у тебе **{user['money']}** монет.",
            color=0xF1C40F
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏆 Лідерборд", style=discord.ButtonStyle.primary, custom_id="case_leaderboard", row=2)
    async def leaderboard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = get_leaderboard_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="👤 Профіль", style=discord.ButtonStyle.success, custom_id="case_profile", row=3)
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user(interaction.user.id)
        need = xp_needed_for_level(user["level"])
        bar = make_progress_bar(user["xp"], need, 12)

        embed = discord.Embed(
            title=f"👤 Профіль {interaction.user.name}",
            color=0x2ECC71
        )
        embed.add_field(name="🆙 Рівень", value=f"**{user['level']}**", inline=True)
        embed.add_field(name="💰 Монети", value=f"**{user['money']}**", inline=True)
        embed.add_field(name="🎴 Картки", value=f"**{len(user['cards'])}**", inline=True)
        embed.add_field(name="⭐ XP", value=f"{bar}\n**{user['xp']} / {need} XP**", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    bot.add_view(CaseView())
    if not cleanup_panels.is_running():
        cleanup_panels.start()
    print(f"✅ Бот запущений як {bot.user}")


@bot.command()
async def panel(ctx):
    await send_panel(ctx.channel)


@bot.command()
@commands.has_permissions(administrator=True)
async def addcard(ctx, name: str, chance: float, rarity: str, image: str = ""):
    rarity = rarity.lower().strip()

    if rarity not in rarity_colors:
        await ctx.send("❌ Рідкість має бути: common / rare / epic / legendary / mythic")
        return

    if chance <= 0:
        await ctx.send("❌ Шанс має бути більше 0.")
        return

    cards.append({
        "name": name,
        "chance": chance,
        "rarity": rarity,
        "image": image
    })

    save_json(CARDS_FILE, cards)
    await ctx.send(f"✅ Картка **{name}** додана.")
    await send_panel(ctx.channel)


@bot.command()
async def balance(ctx):
    user = get_user(ctx.author.id)
    embed = discord.Embed(
        title="💰 Баланс",
        description=f"Монети: **{user['money']}**\nРівень: **{user['level']}**",
        color=0x2ECC71
    )
    await ctx.send(embed=embed)
    await send_panel(ctx.channel)


@bot.command()
async def profile(ctx):
    user = get_user(ctx.author.id)
    need = xp_needed_for_level(user["level"])
    bar = make_progress_bar(user["xp"], need, 12)

    embed = discord.Embed(
        title=f"👤 Профіль {ctx.author.name}",
        color=0x2ECC71
    )
    embed.add_field(name="🆙 Рівень", value=f"**{user['level']}**", inline=True)
    embed.add_field(name="💰 Монети", value=f"**{user['money']}**", inline=True)
    embed.add_field(name="🎴 Картки", value=f"**{len(user['cards'])}**", inline=True)
    embed.add_field(name="⭐ XP", value=f"{bar}\n**{user['xp']} / {need} XP**", inline=False)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed)
    await send_panel(ctx.channel)


@bot.command()
async def level(ctx):
    user = get_user(ctx.author.id)
    need = xp_needed_for_level(user["level"])
    bar = make_progress_bar(user["xp"], need, 15)

    embed = discord.Embed(
        title=f"🆙 Рівень {ctx.author.name}",
        description=(
            f"**Рівень:** {user['level']}\n"
            f"**XP:** {user['xp']} / {need}\n\n"
            f"{bar}"
        ),
        color=0x3498DB
    )

    await ctx.send(embed=embed)
    await send_panel(ctx.channel)


@bot.command()
async def leaderboard(ctx):
    embed = get_leaderboard_embed(ctx.guild)
    await ctx.send(embed=embed)
    await send_panel(ctx.channel)


@bot.command()
async def inventory(ctx):
    user = get_user(ctx.author.id)

    if not user["cards"]:
        await ctx.send("📭 У тебе поки немає карток.")
        await send_panel(ctx.channel)
        return

    view = InventoryView(ctx.author.id, user["cards"])
    await ctx.send(embed=view.get_current_embed(), view=view)
    await send_panel(ctx.channel)


@bot.command()
async def cardslist(ctx):
    if not cards:
        await ctx.send("❌ У системі немає карток.")
        await send_panel(ctx.channel)
        return

    view = CardsListView(ctx.author.id, cards)
    embed, file = view.get_current_embed_and_file()
    await ctx.send(embed=embed, file=file, view=view)
    await send_panel(ctx.channel)


import os

token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("❌ Переменная окружения DISCORD_TOKEN не установлена!")

bot.run(token)
