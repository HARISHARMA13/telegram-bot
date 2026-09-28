# Run the Telegram bot 24/7

This project uses Telegram long polling, so it stays live as long as the Python process is running.
For a cloud deployment, use a service that supports an always-running worker/container (not a short-lived serverless function).

## Required environment variables

For the normal moderation/group-management bot:

```text
BOT_TOKEN=your-token-from-BotFather
OWNER_ID=your-numeric-telegram-user-id
DATABASE_URL=your-postgresql-connection-string
ENABLE_MUSIC=false
```

`API_ID`, `API_HASH`, and `USERBOT_SESSION_STRING` are only needed when `ENABLE_MUSIC=true`.

## Docker

Build and run:

```bash
docker build -t telegram-bot .
docker run --restart unless-stopped --env-file .env telegram-bot
```

The included `docker-compose.yml` also starts a local PostgreSQL database.

```bash
docker compose up -d --build
```

Check logs:

```bash
docker compose logs -f bot
```

## Cloud deployment

A simple setup is:

1. Create a PostgreSQL database with your cloud provider.
2. Create an always-on Docker/worker service from this repository.
3. Add the environment variables above.
4. Deploy the service.
5. Confirm the logs contain `Starting polling…`.
6. Open Telegram and send `/start` to the bot.

Do not put `.env`, Telegram bot tokens, API hashes, or userbot session strings into Git.

## Music

If voice-chat music is required:

1. Set `ENABLE_MUSIC=true`.
2. Create a dedicated Telegram assistant account.
3. Generate a session locally:

```bash
python -m bot.music.generate_session
```

4. Put the resulting value into `USERBOT_SESSION_STRING` as a secret environment variable.
5. Also provide `API_ID` and `API_HASH`.

A cloud server cannot perform the interactive phone/login flow on every restart, so the session string must be pre-generated.
