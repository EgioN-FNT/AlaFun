"""Discord bot with global /d20 and /percent slash commands."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("d20-bot")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

DICE_MIN = 1
DICE_MAX = 20
COLOR_ROLE_TOP_ID = 1415779488528203799
COLOR_ROLE_BOTTOM_ID = 1415779353345658971
ROLL_COUNT = 8
EDIT_INTERVAL_S = 0.2
USER_COOLDOWN_S = 5.0

INITIAL_TEXT = "Императоры кинули ваш кубик судьбы..."
EMBED_COLOR = discord.Color.from_rgb(88, 101, 242)  # Discord blurple
EMBED_TITLE = "🎲 Кубик судьбы"

VIP_IDS = frozenset({743045383764049962, 1217457275225112626})
VIP_25_IDS = frozenset({
    1247639212073812063, 706168663329210449, 1513269139194773504,
    604944158142103587, 632893088146260005, 825639032074928128,
    1410260842708074507, 825340887596007464, 838294142072651796,
    1346116223749980181, 790325676468076574, 507502716155854848,
    1067644373036175400, 1093596791716450354,
})

VIP_50_IDS = frozenset({
    1270988863661146112, 1267060866554003577, 1527223954677436529,
})

VIP_69_IDS = frozenset({
    974999269004148746,
})

VIP_75_IDS = frozenset({
    533690155932844032, 981370062663483433, 740904136895102999,
    1247210866387062835,
})

TEXT_25 = (
    "За вашей спиной расправились белые крылья. Вы Ангел и на 25% {action}! 🕊️",
    "Императоры узрели в вас искру истинного света. Вы Ангел и на 25% {action}!",
)

TEXT_50 = (
    "Вы — верный клинок в руках Императоров. Вы Примарх и на 50% {action}! ⚔️",
    "Императоры увидели в тебе своего сына... Рады тебя видеть, Примарх. Вы на 50% {action}.",
)

TEXT_69 = (
    "Ваши помыслы туманны, но Императорам это нравится. Вы на 69% {action}.",
)

TEXT_75 = (
    "Вы почти Импераподобны, Архангел. Императоры довольны вами. Вы на 75% {action}! 👑",
    "Вы — самый верный слуга Императоров, Архангел. Вы на 75% {action}.",
)
EMPEROR_WORD = "император"

BASE_DIR = Path(__file__).resolve().parent
COUNTS_FILE = BASE_DIR / "counts.json"
REWARDS_FILE = BASE_DIR / "rewards.json"
DATA_LOCK = asyncio.Lock()
HISTORY_SCAN_MAX = 5000
HISTORY_SCAN_DEFAULT = 1000

PERCENT_TITLE = "🔮 Весы Императоров"
PERCENT_COLOR = discord.Color.purple()
PERCENT_INTRO = "Императоры изучают вашу душу"
PERCENT_DOT_FRAMES = (".", "..", "...")
PERCENT_DOT_CYCLES = 2
PERCENT_EDIT_INTERVAL_S = 0.4

# Inclusive (low, high) ranges mapped to flavor templates.
PERCENT_TIERS: tuple[tuple[int, int, tuple[str, ...]], ...] = (
    (
        0,
        0,
        (
            "Абсолютный ноль. Вы на 0% {action}.",
            "Императоры не нашли в вас этого. 0% {action}.",
        ),
    ),
    (
        1,
        15,
        (
            "Искра есть, но она едва тлеет. Вы на {percent}% {action}.",
            "Императоры едва заметили это. Вы на {percent}% {action}.",
        ),
    ),
    (
        16,
        35,
        (
            "Слабовато, но начало положено. Вы на {percent}% {action}.",
            "Императоры сомневаются, но дают вам шанс. {percent}% {action}.",
        ),
    ),
    (
        36,
        50,
        ("Вы на верном пути, но до идеала далеко. Вы на {percent}% {action}.",),
    ),
    (
        51,
        70,
        (
            "Императоры довольны вами. Вы на {percent}% {action}.",
            "Хороший результат! Вы на {percent}% {action}.",
        ),
    ),
    (
        71,
        84,
        (
            "Впечатляюще! Вы на {percent}% {action}.",
            "Императоры наблюдают за вами с одобрением. {percent}% {action}.",
        ),
    ),
    (
        85,
        99,
        (
            "Вы почти достигли совершенства. {percent}% {action}.",
            "Великолепно! Вы на {percent}% {action}.",
        ),
    ),
    (
        100,
        100,
        ("Императоры узрели абсолютную истину! Вы на 100% {action}! 🎉",),
    ),
)


def make_embed(
    description: str,
    *,
    title: str = EMBED_TITLE,
    color: discord.Color = EMBED_COLOR,
) -> discord.Embed:
    """Build a rich card for slash-command replies."""
    return discord.Embed(
        title=title,
        description=description,
        color=color,
    )


def animation_description(value: int) -> str:
    """Keep the intro line visible while the number changes on the next line."""
    return f"{INITIAL_TEXT}\n🎲 **{value}**"


def final_description(value: int) -> str:
    """Same card, with the last roll shown as a large markdown heading."""
    return f"{INITIAL_TEXT}\n\n## 🎲 Вам выпало **{value}**"


def lowercase_first(text: str) -> str:
    """Lowercase only the first character so the phrase fits mid-sentence."""
    stripped = text.strip()
    if not stripped:
        return stripped
    return stripped[0].lower() + stripped[1:]


def mentions_emperor(action: str) -> bool:
    return EMPEROR_WORD in action.casefold()


def pick_percent_phrase(percent: int, action: str) -> str:
    for low, high, templates in PERCENT_TIERS:
        if low <= percent <= high:
            template = random.choice(templates)
            return template.format(percent=percent, action=action)
    return f"Вы на {percent}% {action}."

def resolve_percent_result(user_id: int, raw_action: str) -> tuple[int, str]:
    """Return (percent, embed description) for the /percent command."""
    action = lowercase_first(raw_action)
    emperor = mentions_emperor(raw_action)

    if not emperor:
        percent = random.randint(0, 100)
        flavor = pick_percent_phrase(percent, action)
        heading = f"## Вы на {percent}% {action}!"
        return percent, f"{flavor}\n\n{heading}"

    if user_id in VIP_IDS:
        percent = 100
        text = f"Император посмотрел в зеркало. Вы на 100% {action}! 👑"
        return percent, f"## {text}"

    percent = 0
    templates = None

    if user_id in VIP_25_IDS:
        percent, templates = 25, TEXT_25
    elif user_id in VIP_50_IDS:
        percent, templates = 50, TEXT_50
    elif user_id in VIP_69_IDS:
        percent, templates = 69, TEXT_69
    elif user_id in VIP_75_IDS:
        percent, templates = 75, TEXT_75

    if templates:
        text = random.choice(templates).format(action=action)
        return percent, f"## {text}"

    text = f"Смертный, не смей равнять себя с Императорами. Вы на 0% {action}."
    return 0, f"## {text}"

def load_json_file(path: Path, default: Any) -> Any:
    """Read UTF-8 JSON; return default if missing or corrupted."""
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        log.warning("Failed to read %s: %s", path.name, exc)
        return default
    return data if data is not None else default


def save_json_file(path: Path, data: Any) -> bool:
    """Write UTF-8 JSON. Returns False if the write fails."""
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        log.error("Failed to write %s: %s", path.name, exc)
        return False


def load_counts() -> dict[str, int]:
    raw = load_json_file(COUNTS_FILE, {})
    if not isinstance(raw, dict):
        log.warning("counts.json is not an object; resetting to empty")
        return {}
    counts: dict[str, int] = {}
    for key, value in raw.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return counts


def load_rewards() -> list[dict[str, int]]:
    raw = load_json_file(REWARDS_FILE, [])
    if not isinstance(raw, list):
        log.warning("rewards.json is not a list; resetting to empty")
        return []
    rewards: list[dict[str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            rewards.append(
                {
                    "channel_id": int(item["channel_id"]),
                    "role_id": int(item["role_id"]),
                    "required_messages": int(item["required_messages"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return rewards

def find_rewards_for_channel(
    rewards: list[dict[str, int]], channel_id: int
) -> list[dict[str, int]]:
    """Возвращает список ВСЕХ наград для указанного канала."""
    return [reward for reward in rewards if reward["channel_id"] == channel_id]

class ColorRoleCleanupView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Очистить", 
        style=discord.ButtonStyle.primary, 
        custom_id="cleanup_color_roles_btn", 
        emoji="🧹"
    )
    async def cleanup_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        if guild is None:
            return

        top_role = guild.get_role(COLOR_ROLE_TOP_ID)
        bottom_role = guild.get_role(COLOR_ROLE_BOTTOM_ID)

        if not top_role or not bottom_role:
            await interaction.response.send_message("Ошибка: роли-маркеры не найдены на сервере.", ephemeral=True)
            return

        # Ищем роли, которые находятся СТРОГО между маркерами
        roles_to_remove = [
            role for role in interaction.user.roles
            if bottom_role.position < role.position < top_role.position
        ]

        if not roles_to_remove:
            await interaction.response.send_message("У вас нет цветовых ролей для удаления.", ephemeral=True)
            return

        # Создаем окно подтверждения (Discord Confirmation UI)
        confirm_view = discord.ui.View(timeout=60)
        
        async def confirm_callback(confirm_interaction: discord.Interaction):
            await confirm_interaction.response.defer(ephemeral=True)
            
            # Удаляем пачками по 10, чтобы Discord не выдал ошибку лимитов
            for i in range(0, len(roles_to_remove), 10):
                chunk = roles_to_remove[i:i+10]
                try:
                    await interaction.user.remove_roles(*chunk)
                    await asyncio.sleep(1.0)
                except discord.HTTPException as exc:
                    log.warning("Failed to remove some roles: %s", exc)
                    await confirm_interaction.followup.send("Произошла ошибка при удалении некоторых ролей.", ephemeral=True)
                    return

            await confirm_interaction.followup.send(f"Успешно удалено {len(roles_to_remove)} цветовых ролей!", ephemeral=True)

        async def cancel_callback(cancel_interaction: discord.Interaction):
            await cancel_interaction.response.send_message("Удаление ролей отменено.", ephemeral=True)

        confirm_button = discord.ui.Button(label="Да, удалить", style=discord.ButtonStyle.danger, emoji="🗑️")
        confirm_button.callback = confirm_callback
        
        cancel_button = discord.ui.Button(label="Отмена", style=discord.ButtonStyle.secondary)
        cancel_button.callback = cancel_callback

        confirm_view.add_item(confirm_button)
        confirm_view.add_item(cancel_button)

        await interaction.response.send_message(
            f"Вы уверены, что хотите удалить **{len(roles_to_remove)}** цветовых ролей? Это действие нельзя отменить.",
            view=confirm_view,
            ephemeral=True
        )

class FateBot(commands.Bot):
    def __init__(self) -> None:
        # Включаем интент для чтения сообщений
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)

    async def setup_hook(self) -> None:
        self.add_view(ColorRoleCleanupView())
        # Global sync. First-time global commands can take up to ~1 hour to appear.
        synced = await self.tree.sync()
        log.info("Synced %s global app command(s)", len(synced))


bot = FateBot()


@bot.event
async def on_ready() -> None:
    user = bot.user
    log.info("Logged in as %s (%s)", user, user.id if user else "?")


@bot.event
async def on_message(message: discord.Message) -> None:
    try:
        if message.author.bot:
            return
        if message.guild is None:
            return

        async with DATA_LOCK:
            rewards = load_rewards()
            # Получаем СПИСОК всех наград для этого канала
            channel_rewards = find_rewards_for_channel(rewards, message.channel.id)
            if not channel_rewards:
                return

            counts = load_counts()
            user_key = str(message.author.id)
            new_count = counts.get(user_key, 0) + 1
            counts[user_key] = new_count
            save_json_file(COUNTS_FILE, counts)

        # Проходимся по каждой награде в списке
        for reward in channel_rewards:
            if new_count != reward["required_messages"]:
                continue # Если количество не совпадает с этой наградой, пропускаем и проверяем следующую

            role = message.guild.get_role(reward["role_id"])
            if role is None:
                log.warning(
                    "Reward role %s not found in guild %s",
                    reward["role_id"],
                    message.guild.id,
                )
                continue # Если роли нет, идем к следующей награде
                
            if not isinstance(message.author, discord.Member):
                continue
                
            if role in message.author.roles:
                continue # Если роль уже есть, идем к следующей

            try:
                await message.author.add_roles(
                    role, reason=f"Награда за {new_count} сообщений"
                )
            except discord.HTTPException as exc:
                log.warning("Failed to add reward role %s: %s", role.id, exc)
    finally:
        await bot.process_commands(message)


@bot.tree.command(
    name="d20",
    description="Кинуть кубик судьбы (1-20)",
)
@app_commands.checks.cooldown(1, USER_COOLDOWN_S)
async def d20(interaction: discord.Interaction) -> None:
    """Animate eight 1–20 rolls on one embed, then lock in the last value."""
    await interaction.response.send_message(embed=make_embed(INITIAL_TEXT))
    message = await interaction.original_response()

    # Делаем ровно 8 прокруток
    for i in range(ROLL_COUNT):
        is_final = i == ROLL_COUNT - 1

        if is_final:
            final_number = random.randint(DICE_MIN, DICE_MAX)
            description = final_description(final_number)
        else:
            value = random.randint(DICE_MIN, DICE_MAX)
            description = animation_description(value)

        try:
            await message.edit(content=None, embed=make_embed(description))
        except discord.HTTPException as exc:
            log.warning("Failed to edit roll animation: %s", exc)
            await asyncio.sleep(0.5) # Небольшая пауза, если Discord затупил

        # Если это не финальный шаг, ждем 0.12 секунды перед следующим
        if not is_final:
            await asyncio.sleep(EDIT_INTERVAL_S)

    # Железобетонная отправка финала (на случай если прошлый edit не сработал)
    final_embed = make_embed(final_description(final_number))
    try:
        await message.edit(content=None, embed=final_embed)
    except discord.HTTPException as exc:
        log.warning("Сбой при отправке финала d20: %s", exc)
        await asyncio.sleep(1.0)
        try:
            await message.edit(content=None, embed=final_embed)
        except discord.HTTPException:
            await interaction.followup.send(embed=final_embed)


@bot.tree.command(
    name="percent",
    description="Насколько процентов я...",
)
@app_commands.describe(действие="Текст, который пойдет после 'Насколько процентов я...'")
@app_commands.checks.cooldown(1, USER_COOLDOWN_S)
async def percent(interaction: discord.Interaction, действие: str) -> None:
    """Weigh the user's claim and reveal a 0–100% verdict as an embed."""
    _percent, result_description = resolve_percent_result(
        interaction.user.id,
        действие,
    )

    await interaction.response.send_message(
        embed=make_embed(
            f"{PERCENT_INTRO}.",
            title=PERCENT_TITLE,
            color=PERCENT_COLOR,
        )
    )
    message = await interaction.original_response()

    frames = PERCENT_DOT_FRAMES * PERCENT_DOT_CYCLES
    for index, dots in enumerate(frames):
        # Если это последний кадр, мы не показываем точки, а сразу выходим из цикла
        if index == len(frames) - 1:
            break
            
        try:
            await message.edit(
                content=None,
                embed=make_embed(
                    f"{PERCENT_INTRO}{dots}",
                    title=PERCENT_TITLE,
                    color=PERCENT_COLOR,
                ),
            )
        except discord.HTTPException as exc:
            log.warning("Сбой анимации: %s", exc)
            await asyncio.sleep(1.0)

        await asyncio.sleep(0.5)

    # Отправляем финал ОДИН раз в самом конце
    final_embed = make_embed(result_description, title=PERCENT_TITLE, color=PERCENT_COLOR)
    try:
        await message.edit(content=None, embed=final_embed)
    except discord.HTTPException as exc:
        log.warning("Сбой при отправке финала: %s", exc)
        await asyncio.sleep(1.0)
        try:
            await message.edit(content=None, embed=final_embed)
        except discord.HTTPException:
            await interaction.followup.send(embed=final_embed)

@bot.tree.command(name="setup_cleanup", description="Отправить сообщение с кнопкой очистки ролей")
@app_commands.default_permissions(administrator=True)
async def setup_cleanup(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="Очистка цветовых ролей",
        description="Нажмите на кнопку ниже, чтобы удалить все цветовые роли.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=ColorRoleCleanupView())

@bot.tree.command(name="reward_add", description="Добавить или обновить награду за сообщения")
@app_commands.describe(
    channel="Канал, в котором считаются сообщения",
    role="Роль, которая выдаётся за достижение порога",
    messages="Сколько сообщений нужно набрать",
)
@app_commands.default_permissions(administrator=True)
async def reward_add(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role,
    messages: int,
) -> None:
    if messages < 1:
        await interaction.response.send_message(
            "Число сообщений должно быть не меньше 1.",
            ephemeral=True,
        )
        return

    async with DATA_LOCK:
        rewards = load_rewards()
        overwritten = False
        for item in rewards:
            if item["channel_id"] == channel.id:
                item["role_id"] = role.id
                item["required_messages"] = messages
                overwritten = True
                break
        if not overwritten:
            rewards.append(
                {
                    "channel_id": channel.id,
                    "role_id": role.id,
                    "required_messages": messages,
                }
            )
        saved = save_json_file(REWARDS_FILE, rewards)

    if not saved:
        await interaction.response.send_message(
            "Не удалось сохранить rewards.json.",
            ephemeral=True,
        )
        return

    action = "обновлена" if overwritten else "добавлена"
    await interaction.response.send_message(
        f"Награда {action}: канал {channel.mention}, роль {role.mention}, "
        f"сообщений: **{messages}**.",
        ephemeral=True,
    )


@bot.tree.command(name="reward_list", description="Показать все награды за сообщения")
@app_commands.default_permissions(administrator=True)
async def reward_list(interaction: discord.Interaction) -> None:
    async with DATA_LOCK:
        rewards = load_rewards()

    if not rewards:
        await interaction.response.send_message(
            "Награды ещё не настроены.",
            ephemeral=True,
        )
        return

    guild = interaction.guild
    lines: list[str] = []
    for item in rewards:
        channel = guild.get_channel(item["channel_id"]) if guild else None
        role = guild.get_role(item["role_id"]) if guild else None
        channel_label = f"#{channel.name}" if channel else f"#{item['channel_id']}"
        role_label = f"@{role.name}" if role else f"@{item['role_id']}"
        lines.append(
            f"Канал: {channel_label}, Роль: {role_label}, "
            f"Сообщений: {item['required_messages']}"
        )

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="reward_remove", description="Удалить награду за сообщения в канале")
@app_commands.describe(channel="Канал, настройку которого нужно удалить")
@app_commands.default_permissions(administrator=True)
async def reward_remove(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
) -> None:
    async with DATA_LOCK:
        rewards = load_rewards()
        remaining = [item for item in rewards if item["channel_id"] != channel.id]
        if len(remaining) == len(rewards):
            await interaction.response.send_message(
                f"Для канала {channel.mention} награда не найдена.",
                ephemeral=True,
            )
            return
        saved = save_json_file(REWARDS_FILE, remaining)

    if not saved:
        await interaction.response.send_message(
            "Не удалось сохранить rewards.json.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"Награда для канала {channel.mention} удалена.",
        ephemeral=True,
    )


@bot.tree.command(name="count_stats", description="Статистика сообщений в отслеживаемых каналах")
@app_commands.describe(user="Участник (если не указан — сумма по всем)")
@app_commands.default_permissions(administrator=True)
async def count_stats(
    interaction: discord.Interaction,
    user: discord.Member | None = None,
) -> None:
    async with DATA_LOCK:
        counts = load_counts()

    if user is None:
        total = sum(counts.values())
        await interaction.response.send_message(
            f"Всего сообщений в отслеживаемых каналах: **{total}**.",
            ephemeral=True,
        )
        return

    total = counts.get(str(user.id), 0)
    await interaction.response.send_message(
        f"У {user.mention} **{total}** сообщений в отслеживаемых каналах.",
        ephemeral=True,
    )


@bot.tree.command(
    name="count_history",
    description="Просканировать историю канала и добавить сообщения в статистику",
)
@app_commands.describe(
    channel="Канал, историю которого нужно просканировать",
    limit="Сколько сообщений просмотреть (по умолчанию 1000, максимум 5000)",
)
@app_commands.default_permissions(administrator=True)
async def count_history(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    limit: int = HISTORY_SCAN_DEFAULT,
) -> None:
    scan_limit = min(max(limit, 1), HISTORY_SCAN_MAX)

    try:
        async with DATA_LOCK:
            rewards = load_rewards()
    except Exception as exc:
        log.warning("Failed to load rewards.json for history scan: %s", exc)
        await interaction.response.send_message(
            "Не удалось прочитать rewards.json.",
            ephemeral=True,
        )
        return

    if not find_rewards_for_channel(rewards, channel.id):
        await interaction.response.send_message(
            f"Канал {channel.mention} не в списке отслеживания.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        "Начинаю сканирование истории... Это может занять некоторое время.",
        ephemeral=True,
    )

    new_counts: dict[str, int] = {}
    try:
        async for message in channel.history(limit=scan_limit):
            if message.author.bot:
                continue
            user_key = str(message.author.id)
            new_counts[user_key] = new_counts.get(user_key, 0) + 1
    except discord.Forbidden:
        await interaction.followup.send(
            f"Нет прав на чтение истории сообщений в канале {channel.mention}.",
            ephemeral=True,
        )
        return
    except discord.HTTPException as exc:
        log.warning("History scan failed in #%s: %s", channel.id, exc)
        await interaction.followup.send(
            "Не удалось просканировать историю канала.",
            ephemeral=True,
        )
        return

    try:
        async with DATA_LOCK:
            counts = load_counts()
            for user_key, extra in new_counts.items():
                counts[user_key] = counts.get(user_key, 0) + extra
            saved = save_json_file(COUNTS_FILE, counts)
    except Exception as exc:
        log.warning("Failed to update counts.json after history scan: %s", exc)
        await interaction.followup.send(
            "Не удалось сохранить counts.json.",
            ephemeral=True,
        )
        return

    if not saved:
        await interaction.followup.send(
            "Не удалось сохранить counts.json.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        f"Сканирование завершено! Обработано {scan_limit} сообщений. Статистика обновлена.",
        ephemeral=True,
    )


async def handle_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    if isinstance(error, app_commands.CommandOnCooldown):
        text = (
            f"Подождите ещё {error.retry_after:.1f} с. "
            f"/ Wait {error.retry_after:.1f}s."
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.HTTPException as exc:
            log.warning("Failed to send cooldown notice: %s", exc)
        return

    log.exception("Unhandled error in /%s: %s", interaction.command, error)
    try:
        notice = "Не удалось выполнить команду. / The command failed. Try again."
        if interaction.response.is_done():
            await interaction.followup.send(notice, ephemeral=True)
        else:
            await interaction.response.send_message(notice, ephemeral=True)
    except discord.HTTPException:
        pass


d20.error(handle_app_command_error)
percent.error(handle_app_command_error)
reward_add.error(handle_app_command_error)
reward_list.error(handle_app_command_error)
reward_remove.error(handle_app_command_error)
count_stats.error(handle_app_command_error)
count_history.error(handle_app_command_error)


def main() -> None:
    if not DISCORD_TOKEN:
        log.error(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and add your bot token."
        )
        sys.exit(1)
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
