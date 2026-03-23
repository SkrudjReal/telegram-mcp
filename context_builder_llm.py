"""
context_builder_llm.py — LLM-саммари чатов и лично известных людей.

Логика:
- Чаты: саммари чата + краткое досье на ВСЕХ участников сразу (один блок)
- Люди: подробный профиль только если есть личка (chat_type=private)
"""

import json
import subprocess
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

CONTEXT_DIR = Path(__file__).parent / "context"
MESSAGES_FILE = CONTEXT_DIR / "messages.jsonl"
CHATS_DIR = CONTEXT_DIR / "chats"
PEOPLE_DIR = CONTEXT_DIR / "people"

CHATS_DIR.mkdir(parents=True, exist_ok=True)
PEOPLE_DIR.mkdir(parents=True, exist_ok=True)

OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID", "0"))
MAX_MSGS = 80
PAUSE = 8


def ask_claude(prompt: str) -> str:
    time.sleep(PAUSE)
    result = subprocess.run(
        ["openclaw", "agent", "--agent", "main", "--message", prompt, "--json"],
        capture_output=True, text=True, timeout=300
    )
    try:
        data = json.loads(result.stdout)
        return data["result"]["payloads"][0]["text"]
    except Exception:
        return result.stdout.strip() or "ошибка"


def fmt_msgs(msgs: list) -> str:
    lines = []
    for m in msgs[-MAX_MSGS:]:
        d = "→" if m.get("direction") == "out" else "←"
        name = m.get("sender_name", "?")
        text = (m.get("text") or "").strip()
        if not text:
            continue
        ts = m.get("ts", "")[:10]
        reply = f" [↩ {m['reply_to_text'][:40]}]" if m.get("reply_to_text") else ""
        lines.append(f"{d} {name} [{ts}]: {text}{reply}")
    return "\n".join(lines)


def load_messages():
    if not MESSAGES_FILE.exists():
        return []
    msgs = []
    with open(MESSAGES_FILE, encoding="utf-8") as f:
        for line in f:
            try:
                msgs.append(json.loads(line))
            except Exception:
                pass
    return msgs


def main():
    print("[llm_builder] Загружаю...")
    msgs = load_messages()
    if not msgs:
        print("[llm_builder] Нет сообщений.")
        return
    print(f"[llm_builder] {len(msgs)} записей")

    # Группируем по чатам
    chats = defaultdict(lambda: {"title": "", "type": "", "msgs": []})
    for m in msgs:
        cid = m.get("chat_id")
        chats[cid]["title"] = m.get("chat_title", str(cid))
        chats[cid]["type"] = m.get("chat_type", "")
        chats[cid]["msgs"].append(m)

    # Находим личные чаты (не с собой)
    private_chat_ids = set()
    for cid, info in chats.items():
        if info["type"] == "private" and cid != OWNER_ID:
            private_chat_ids.add(cid)

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Саммари групповых чатов
    for cid, info in chats.items():
        if info["type"] != "group":
            continue
        if len(info["msgs"]) < 5:
            continue

        print(f"[llm_builder] Чат: {info['title']}")
        text = fmt_msgs(info["msgs"])

        # Собираем участников (не owner)
        participants = defaultdict(list)
        for m in info["msgs"]:
            sid = m.get("sender_id")
            if sid and sid != OWNER_ID:
                name = m.get("sender_name", str(sid))
                t = (m.get("text") or "").strip()
                if t:
                    participants[name].append(t[:100])

        # Краткие характеристики участников
        people_summary = ""
        if participants:
            people_lines = []
            for name, texts in participants.items():
                sample = " / ".join(texts[:3])
                people_lines.append(f"- {name}: «{sample}»")
            people_summary = "\n".join(people_lines)

        prompt = f"""Чат "{info['title']}" (тип: {info['type']}). Последние сообщения (→ outgoing (owner), ← incoming):

{text}

Участники и примеры их сообщений:
{people_summary}

Дай структурированное резюме:
1. О чём этот чат и какова его атмосфера (2-3 предложения)
2. Краткое досье на каждого участника (1 строка: имя — кто такой, роль в чате)
3. Актуальные темы на сейчас

Максимум 200 слов, без лишней воды."""

        summary = ask_claude(prompt)

        chat_file = CHATS_DIR / f"{cid}.md"
        existing = chat_file.read_text(encoding="utf-8") if chat_file.exists() else ""
        if "## LLM Анализ" in existing:
            existing = existing[:existing.index("## LLM Анализ")]
        chat_file.write_text(
            existing.rstrip() + f"\n\n## LLM Анализ\n*{updated}*\n\n{summary}\n",
            encoding="utf-8"
        )

    # Профили людей только из личек
    for cid, info in chats.items():
        if cid not in private_chat_ids:
            continue
        if len(info["msgs"]) < 3:
            continue

        # Находим собеседника
        other_name = ""
        other_id = cid  # для личек chat_id = user_id собеседника
        for m in info["msgs"]:
            sid = m.get("sender_id")
            if sid and sid != OWNER_ID:
                other_name = m.get("sender_name", str(cid))
                other_id = sid
                break

        if not other_name:
            continue

        print(f"[llm_builder] Личка: {other_name}")
        text = fmt_msgs(info["msgs"])

        prompt = f"""Личная переписка between owner (→) и {other_name} (←):

{text}

Составь подробный профиль {other_name}:
1. Кто этот человек — возраст, характер, роль in owner's life
2. Как они общаются, какие темы
3. Что сейчас происходит у этого человека
4. Relationship with owner — близость, история, эмоциональный тон

Максимум 150 слов."""

        summary = ask_claude(prompt)

        person_file = PEOPLE_DIR / f"{other_id}.md"
        existing = person_file.read_text(encoding="utf-8") if person_file.exists() else ""
        if "## LLM Анализ" in existing:
            existing = existing[:existing.index("## LLM Анализ")]
        person_file.write_text(
            existing.rstrip() + f"\n\n## LLM Анализ (личка)\n*{updated}*\n\n{summary}\n",
            encoding="utf-8"
        )

    print("[llm_builder] Готово!")


if __name__ == "__main__":
    main()
