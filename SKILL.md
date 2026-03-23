---
name: telegram-mcp
description: "Telegram MTProto MCP server with userbot watcher, chat/DM parser, context builders, criminal analysis and personality profiling. Use for reading Telegram messages, parsing chat history, criminal analysis, and psychological profiles."
---

# Telegram MCP — Watcher, Parser & Analysis

Full-featured Telegram MTProto MCP server. Connects to Telegram as a userbot and exposes message reading, sending, and parsing as MCP tools.

## Features

- **Userbot watcher** — monitors all messages, triggers AI agent on keyword
- **Chat/DM parser** — paginated parsing of any chat or DM via `parse_chat.py`
- **Context builders** — stats, top words, LLM summaries, people profiles
- **Criminal analysis** — detects CSAM, fraud, NCA violations, hate speech
- **Personality profiling** — psychological portrait from message history

## Setup

```bash
cp .env.example .env
# Fill in API_ID, API_HASH, SESSION_NAME, OWNER_ID from https://my.telegram.org/apps
pip install -r requirements.txt
python3 session_string_generator.py  # authorize session once
```

## Run watcher as systemd service

```bash
sudo cp tg-watcher.service /etc/systemd/system/
sudo systemctl enable --now tg-watcher
```

## MCP Tools (via mcporter)

- `send_message` — send message to chat
- `reply_to_message` — reply to specific message
- `iter_all_messages` — paginated message fetch
- `iter_messages_by_user` — messages from specific user
- and 90+ more Telegram API methods

## Important notes

See `CLAUDE.md` for full list of gotchas. Key ones:
- Use `\n` not `<br>` in HTML messages
- `iter_all_messages` for DMs, not `list_messages`
- Semaphore required for parallel agent calls

## Source

GitHub: https://github.com/SkrudjReal/telegram-mcp
