# d20 Discord bot

A small [discord.py](https://discordpy.readthedocs.io/) bot that exposes a global `/d20` slash command. The bot posts a fate-roll message, animates random values from **0–20** for about three seconds, then locks the last number as the result.

## Features

- Global `/d20` slash command
- Animated in-place edits (`message.edit`), not a flood of new messages
- Throttled updates (`asyncio.sleep(0.12)`) to stay under Discord rate limits
- 5-second per-user cooldown to limit spam
- Token loaded from `DISCORD_TOKEN` (never hardcoded)

## Create the Discord application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and create an application.
2. Open **Bot** and create a bot user. Copy the **token**.
3. Under **OAuth2 → URL Generator**:
   - Scopes: `bot` and `applications.commands`
   - Bot permissions: `Send Messages` and `Embed Links` (optional but useful)
4. Open the generated invite URL and add the bot to your server.

Privileged intents are **not** required. This bot only uses slash commands.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
```

Edit `.env` and set `DISCORD_TOKEN` to the bot token from the Developer Portal.

## Run

```bash
python bot.py
```

On first login the bot syncs `/d20` globally. Global slash commands can take **up to about an hour** to appear in every server. After that, type `/d20` in Discord.

## How the roll works

1. The bot replies with `Императоры кинули ваш кубик судьбы...`
2. It edits that same message about every 120 ms, showing a random integer `0`–`20`.
3. After ~3 seconds it stops and shows `## 🎲 Вам выпало **{n}**`, where `{n}` is the last animated value.

English fallbacks used in the spec:

- “The Emperors have cast your dice of fate...”
- “You rolled **{final_number}**”
