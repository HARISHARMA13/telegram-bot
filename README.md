# All-in-One Telegram Group Management + Music Bot

Python 3.12, aiogram 3.x, PostgreSQL, Pyrogram + PyTgCalls for voice-chat music.

## Architecture

```
bot/
  config.py            Environment-driven settings (no hard-coded secrets)
  database/
    models.py           SQLAlchemy models (all persistent state)
    engine.py            Async engine/session + init_db()
    crud.py               Data-access functions, grouped by domain
  handlers/
    owner.py             /owner /settings /security /trustedadmin /trustedbot
                          /logs /permissions /status — all Owner-gated
    moderation.py        ban/kick/mute/warn/lock/filter/blacklist/antiflood/slowmode
    welcome.py            Welcome messages + join-request handling
    bot_protection.py    Unauthorized-bot detection (called from member_events)
    member_events.py     Single dispatch point for chat_member updates
    notes.py              /save /get /notes /clear
    pinned.py             /setinfo /pininfo /editinfo (rules/announcements + buttons)
    federation.py         /fnew /fjoin /fadmin /fban /funban
    cleanup.py            Configurable auto-delete of bot messages, by category
    guard.py              Passive enforcement: locks, filters, blacklist, anti-flood
    help.py               Categorized /help
  music/
    userbot.py            Pyrogram "assistant" client + PyTgCalls instance
    generate_session.py   One-time interactive script to produce a session string
    queue.py              Per-chat in-memory queue
    source.py             yt-dlp search / stream-URL resolution
    handlers.py           /play /pause /resume /skip /stop /queue /shuffle /volume /loop
  utils/
    filters.py             Permission hierarchy (Owner > Trusted Admin > Group Admin > All)
    security.py             Anti-clone/anti-takeover safeguards, secret redaction
    logger_service.py       Audit log (DB + optional log channel) and Owner alerts
    parsing.py               Duration parsing, target-user resolution
main.py                    Entrypoint: wires bot + database + userbot together
```

## 24/7 deployment

See `DEPLOY.md` for Docker/cloud deployment. The bot uses long polling and is designed to run as an always-on worker/container.

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in:
   - `BOT_TOKEN` from @BotFather
   - `OWNER_ID` — your numeric Telegram user ID (e.g. from @userinfobot)
   - `API_ID` / `API_HASH` from https://my.telegram.org — needed for the music userbot
   - `DATABASE_URL` pointing at a running PostgreSQL instance
4. Generate a reusable userbot session once: `python -m bot.music.generate_session`,
   then paste the printed string into `USERBOT_SESSION_STRING`. Use a dedicated
   Telegram account for this, not your personal one — it will visibly join
   voice chats as "assistant".
5. `python main.py`

Tables are created automatically on first run (`init_db()`); for real schema
migrations going forward, use Alembic against `bot/database/models.py`.

## Permission model

- **Owner** (fixed via `OWNER_ID` at startup, cannot be changed by any command):
  full override, and the only one who can touch security, trusted
  admins/bots, federation roots, and `/permissions` itself.
- **Trusted Admin**: Owner-appointed via `/trustedadmin add`, can be granted
  access to moderation/federation actions without needing Telegram
  group-admin rights.
- **Group Admin**: real Telegram admins of that specific group.
- **All members**: only for commands the Owner explicitly opens up via
  `/permissions <command> all`.

`/permissions` can reconfigure most moderation/note/music commands per
group, but never the security/bot/federation/owner command set — that's
enforced in code (`_PROTECTED_COMMANDS` in `owner.py`), not just by
default config, so it can't be loosened by mistake.

## Honest limitations (please read before deploying)

- **Anti-clone is best-effort.** Whoever holds `BOT_TOKEN` controls the bot
  account on Telegram's side — no code running *inside* the bot can stop a
  second instance from running with a copied token. What this project does
  do: verify Owner configuration at boot, log and alert on any Owner/trusted
  -only command attempted by someone else, and never print the token, API
  hash, DB URL, or userbot session anywhere reachable by a command.
- **Slow mode**: the Bot API has no endpoint to set Telegram's native
  per-chat slow mode. `/slowmode` stores the intent and the bot enforces its
  own per-user cooldown in `guard.py` instead.
- **Voice-chat music requires a second, real account** (the "userbot") in
  addition to the bot — this is a hard Telegram platform constraint, not a
  design choice. Keep that account's session string as secret as the bot
  token; anyone with it fully controls that account.
- **Audio sourcing**: `bot/music/source.py` uses yt-dlp to resolve a
  streamable URL and never downloads/stores copies of media. You are
  responsible for pointing it only at sources you're licensed to use in
  your community and for complying with those platforms' terms.
- **No payment system** is included anywhere, by design.
- `py-tgcalls`'s API shifts between versions; if you pin a version other
  than the one in `requirements.txt`, double-check `bot/music/handlers.py`
  and `userbot.py` against that version's docs.

## Extending

- New moderation command → add to `moderation.py`, gate it with
  `ConfigurablePermission("yourcommand")`, and add it to
  `_CONFIGURABLE_COMMANDS` in `owner.py` if the Owner should be able to
  reconfigure who can run it.
- New cleanup category → add to `CATEGORIES` in `cleanup.py` and call
  `maybe_autodelete(bot, chat_id, message_id, "your_category")` after
  sending the relevant message.
