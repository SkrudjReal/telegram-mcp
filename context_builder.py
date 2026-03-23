"""
context_builder.py — строит саммари по чатам и людям из messages.jsonl
БЕЗ LLM — чистая статистика и топ-фразы.

Запускать периодически: python3 context_builder.py
"""

import json
import os
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone

CONTEXT_DIR = Path(__file__).parent / "context"
MESSAGES_FILE = CONTEXT_DIR / "messages.jsonl"
CHATS_DIR = CONTEXT_DIR / "chats"
PEOPLE_DIR = CONTEXT_DIR / "people"

CHATS_DIR.mkdir(parents=True, exist_ok=True)
PEOPLE_DIR.mkdir(parents=True, exist_ok=True)

OWNER_ID = int(os.getenv("TELEGRAM_OWNER_ID", "0"))
MAX_SAMPLE = 20  # последних сообщений в саммари


def load_messages() -> list:
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


def top_words(texts: list, n=10) -> list:
    words = []
    for t in texts:
        for w in t.lower().split():
            w = w.strip(".,!?;:\"'()[]{}—-")
            if len(w) > 3 and w not in {"клав", "это", "что", "как", "для", "все", "там", "так", "тут", "нет", "ну"}:
                words.append(w)
    return [w for w, _ in Counter(words).most_common(n)]


def build_chat_md(chat_id, title, chat_type, msgs) -> str:
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    senders = Counter(m.get("sender_name", "?") for m in msgs)
    top_senders = senders.most_common(5)
    texts = [m.get("text", "") for m in msgs if m.get("text")]
    keywords = top_words(texts)
    last = msgs[-MAX_SAMPLE:]

    lines = [
        f"# Чат: {title}",
        f"**ID:** {chat_id} | **Тип:** {chat_type} | **Сообщений в базе:** {len(msgs)}",
        f"**Обновлено:** {updated}",
        "",
        "## Активные участники",
    ]
    for name, count in top_senders:
        lines.append(f"- {name}: {count} сообщ.")

    lines += ["", "## Ключевые слова", ", ".join(keywords) or "—", "", "## Последние сообщения"]
    for m in last:
        d = "→" if m.get("direction") == "out" else "←"
        name = m.get("sender_name", "?")
        text = (m.get("text") or "[медиа]")[:100]
        ts = m.get("ts", "")[:16].replace("T", " ")
        lines.append(f"[{ts}] {d} {name}: {text}")

    return "\n".join(lines)


def build_person_md(user_id, name, msgs_all) -> str:
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    chats_seen = Counter(m.get("chat_title", "?") for m in msgs_all)
    texts = [m.get("text", "") for m in msgs_all if m.get("text")]
    keywords = top_words(texts)
    last = msgs_all[-MAX_SAMPLE:]

    lines = [
        f"# {name} (user_id: {user_id})",
        f"**Сообщений:** {len(msgs_all)} | **Обновлено:** {updated}",
        "",
        "## Чаты где встречается",
    ]
    for chat, count in chats_seen.most_common():
        lines.append(f"- {chat}: {count} сообщ.")

    lines += ["", "## Ключевые слова", ", ".join(keywords) or "—", "", "## Последние сообщения"]
    for m in last:
        chat = m.get("chat_title", "?")
        text = (m.get("text") or "[медиа]")[:100]
        ts = m.get("ts", "")[:16].replace("T", " ")
        reply = f" ↩ \"{m['reply_to_text'][:40]}\"" if m.get("reply_to_text") else ""
        lines.append(f"[{ts}][{chat}]: {text}{reply}")

    return "\n".join(lines)


def main():
    print("[context_builder] Загружаю сообщения...")
    msgs = load_messages()
    if not msgs:
        print("[context_builder] Нет сообщений.")
        return
    print(f"[context_builder] Загружено {len(msgs)} записей")

    # Группируем по чатам
    chats: dict = defaultdict(lambda: {"title": "", "type": "", "msgs": []})
    for m in msgs:
        cid = m.get("chat_id")
        chats[cid]["title"] = m.get("chat_title", str(cid))
        chats[cid]["type"] = m.get("chat_type", "")
        chats[cid]["msgs"].append(m)

    # Группируем по людям (не owner)
    people: dict = defaultdict(lambda: {"name": "", "msgs": []})
    for m in msgs:
        sid = m.get("sender_id")
        if not sid or sid == OWNER_ID:
            continue
        people[sid]["name"] = m.get("sender_name", str(sid))
        people[sid]["msgs"].append(m)

    # Саммари по чатам
    for cid, info in chats.items():
        if len(info["msgs"]) < 3:
            continue
        print(f"[context_builder] Чат: {info['title']}")
        md = build_chat_md(cid, info["title"], info["type"], info["msgs"])
        (CHATS_DIR / f"{cid}.md").write_text(md, encoding="utf-8")

    # Саммари по людям
    for uid, info in people.items():
        if len(info["msgs"]) < 2:
            continue
        print(f"[context_builder] Человек: {info['name']}")
        md = build_person_md(uid, info["name"], info["msgs"])
        (PEOPLE_DIR / f"{uid}.md").write_text(md, encoding="utf-8")

    # Общий summary.md
    with open(CONTEXT_DIR / "summary.md", "w", encoding="utf-8") as f:
        f.write(f"# Контекст Март 7\n")
        f.write(f"*Обновлено: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n\n")
        f.write(f"**Всего записей:** {len(msgs)}\n\n")
        f.write("## Чаты\n")
        for cid, info in chats.items():
            if len(info["msgs"]) < 3:
                continue
            f.write(f"- [{info['title']}](chats/{cid}.md) — {len(info['msgs'])} сообщ.\n")
        f.write("\n## Люди\n")
        for uid, info in people.items():
            if len(info["msgs"]) < 2:
                continue
            f.write(f"- [{info['name']}](people/{uid}.md) — {len(info['msgs'])} сообщ.\n")

    print("[context_builder] Готово!")


if __name__ == "__main__":
    main()
