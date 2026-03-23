"""
parse_chat.py — универсальный парсер чатов через telegram-mcp MCP.

Использование:
  python3 parse_chat.py <chat_id> [--limit 1000] [--out output.jsonl]

Примеры:
  python3 parse_chat.py 123456789                         # личка
  python3 parse_chat.py -100123456789 --limit 500        # группа
  python3 parse_chat.py 123456789 --out dm.jsonl         # в файл
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

CONTEXT_DIR = Path(__file__).parent / "context"
CHATS_DIR = CONTEXT_DIR / "chats"
PEOPLE_DIR = CONTEXT_DIR / "people"

PAGE_SIZE = 100   # сообщений за раз
PAUSE = 1.5       # пауза между запросами (сек)


def mcporter_call(tool: str, **kwargs) -> list[dict]:
    """Вызывает MCP-инструмент через mcporter, возвращает список распарсенных сообщений."""
    args = ["mcporter", "call", f"telegram.{tool}"]
    for k, v in kwargs.items():
        args.append(f"{k}={v}")

    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"mcporter error: {result.stderr.strip()}")

    # Парсим текстовый вывод вида "ID: 123 | Name | Date: ... | Message: text"
    messages = []
    for line in result.stdout.splitlines():
        if not line.startswith("ID:"):
            continue
        parts = line.split("|")
        try:
            msg_id = int(parts[0].replace("ID:", "").strip())
            sender = parts[1].strip() if len(parts) > 1 else ""
            date = parts[2].replace("Date:", "").strip() if len(parts) > 2 else ""
            text = ""
            reply_to = None

            for p in parts[2:]:
                if "Message:" in p:
                    text = p.split("Message:", 1)[1].strip()
                if "reply to" in p:
                    try:
                        reply_to = int(p.split("reply to")[1].strip())
                    except Exception:
                        pass

            messages.append({
                "id": msg_id,
                "sender": sender,
                "date": date,
                "text": text,
                "reply_to": reply_to,
            })
        except Exception:
            continue

    return messages


def parse_messages_output(raw: str) -> list[dict]:
    """Парсит текстовый вывод iter_all_messages."""
    messages = []
    for line in raw.splitlines():
        if not line.startswith("ID:"):
            continue
        parts = line.split("|")
        try:
            msg_id = int(parts[0].replace("ID:", "").strip())
            sender = parts[1].strip() if len(parts) > 1 else ""
            date = parts[2].replace("Date:", "").strip() if len(parts) > 2 else ""
            text = ""
            reply_to = None
            for p in parts[2:]:
                if "Message:" in p:
                    text = p.split("Message:", 1)[1].strip()
                if "reply to" in p:
                    try:
                        reply_to = int(p.strip().split("reply to")[1].strip())
                    except Exception:
                        pass
            messages.append({"id": msg_id, "sender": sender, "date": date, "text": text, "reply_to": reply_to})
        except Exception:
            continue
    return messages


def parse_chat(chat_id: int, limit: int = 5000, out_file: str = None) -> list[dict]:
    """Парсит чат через iter_all_messages с пагинацией по offset_id."""
    all_messages = []
    offset_id = 0
    total = 0
    batch = min(PAGE_SIZE * 5, 500)  # 500 за раз

    print(f"[parse_chat] Парсю чат {chat_id}, лимит: {limit}")

    while total < limit:
        fetch = min(batch, limit - total)
        print(f"[parse_chat] Запрос {fetch} сообщений (offset_id={offset_id})...")

        args = ["mcporter", "call", "telegram.iter_all_messages",
                f"chat_id={chat_id}", f"limit={fetch}"]
        if offset_id:
            args.append(f"offset_id={offset_id}")

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            raw = result.stdout
            # убираем stderr строки
            clean = "\n".join(l for l in raw.splitlines() if not l.startswith("[mcporter]"))
            msgs = parse_messages_output(clean)
        except Exception as e:
            print(f"[parse_chat] Ошибка: {e}")
            break

        if not msgs:
            print(f"[parse_chat] Пусто — конец чата.")
            break

        all_messages.extend(msgs)
        total += len(msgs)
        print(f"[parse_chat] Получено: {len(msgs)} | Всего: {total}")

        if len(msgs) < fetch:
            print(f"[parse_chat] Последняя партия.")
            break

        # offset_id = самый старый ID для следующей итерации
        offset_id = min(m["id"] for m in msgs)
        time.sleep(PAUSE)

    print(f"[parse_chat] Итого: {total} сообщений")

    # Сохраняем
    if out_file:
        out = Path(out_file)
    else:
        out = CONTEXT_DIR / f"raw_{chat_id}.jsonl"

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for msg in all_messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    print(f"[parse_chat] Сохранено в: {out}")

    # Дописываем в messages.jsonl (глобальный лог)
    messages_log = CONTEXT_DIR / "messages.jsonl"
    # Загружаем существующие ID чтобы не дублировать
    existing_ids = set()
    if messages_log.exists():
        with open(messages_log, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    existing_ids.add(json.loads(line)["id"])
                except Exception:
                    pass

    new_count = 0
    with open(messages_log, "a", encoding="utf-8") as f:
        for msg in all_messages:
            if msg["id"] not in existing_ids:
                f.write(json.dumps({**msg, "chat_id": chat_id}, ensure_ascii=False) + "\n")
                new_count += 1

    print(f"[parse_chat] Добавлено в messages.jsonl: {new_count} новых записей")

    return all_messages


def print_summary(messages: list[dict]):
    """Выводит краткую статистику."""
    senders = {}
    for m in messages:
        s = m.get("sender", "?")
        senders[s] = senders.get(s, 0) + 1

    print("\n=== Участники ===")
    for name, count in sorted(senders.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count} сообщений")

    if messages:
        print(f"\nПервое: {messages[-1].get('date', '?')}")
        print(f"Последнее: {messages[0].get('date', '?')}")


def main():
    parser = argparse.ArgumentParser(description="Парсер чатов через telegram-mcp")
    parser.add_argument("chat_id", type=int, help="ID чата или пользователя")
    parser.add_argument("--limit", type=int, default=1000, help="Макс. кол-во сообщений (default: 1000)")
    parser.add_argument("--out", type=str, help="Путь к выходному файлу (.jsonl)")
    parser.add_argument("--stats", action="store_true", help="Показать статистику")
    args = parser.parse_args()

    messages = parse_chat(args.chat_id, args.limit, args.out)

    if args.stats or not args.out:
        print_summary(messages)


if __name__ == "__main__":
    main()
