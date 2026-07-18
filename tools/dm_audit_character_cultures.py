import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = (3850, 1, 1)
TOP_LEVEL = re.compile(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{")
DATE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def strip_comments(text: str) -> str:
    return re.sub(r"#.*", "", text)


def blocks(path: Path):
    text = strip_comments(path.read_text(encoding="utf-8-sig"))
    for match in TOP_LEVEL.finditer(text):
        depth = 0
        end = match.end()
        for index in range(match.end() - 1, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        yield match.group(1), text[match.start():end]


def culture_keys():
    result = set()
    directory = ROOT / "common/culture/cultures"
    for path in directory.glob("*.txt"):
        result.update(key for key, _ in blocks(path))
    return result


def event_dates(body: str, event: str):
    found = []
    direct = re.search(
        rf"(?m)^\s*{event}\s*=\s*(\d+\.\d+\.\d+)",
        body,
    )
    if direct:
        found.append(tuple(map(int, direct.group(1).split("."))))
    dated = re.finditer(
        rf"(?ms)^\s*(\d+\.\d+\.\d+)\s*=\s*\{{"
        rf".*?^\s*{event}\s*=\s*yes\b.*?^\s*\}}",
        body,
    )
    for match in dated:
        found.append(tuple(map(int, match.group(1).split("."))))
    return sorted(found)


def holder_ids():
    result = set()
    directory = ROOT / "history/titles"
    for path in directory.glob("*.txt"):
        text = strip_comments(path.read_text(encoding="utf-8-sig"))
        result.update(
            re.findall(r"(?m)^\s*holder\s*=\s*([A-Za-z0-9_]+)", text)
        )
    return result


def main() -> None:
    valid_cultures = culture_keys()
    holders = holder_ids()
    definitions = defaultdict(list)
    alive = []
    for path in sorted((ROOT / "history/characters").glob("*.txt")):
        for character, body in blocks(path):
            definitions[character].append((path.name, body))
            births = event_dates(body, "birth")
            deaths = event_dates(body, "death")
            is_alive = (
                (not births or births[0] <= START)
                and (not deaths or deaths[-1] > START)
            )
            if not is_alive:
                continue
            cultures = re.findall(
                r"(?m)^\s*culture\s*=\s*\"?([A-Za-z0-9_]+)\"?",
                body,
            )
            alive.append(
                (
                    character,
                    path.name,
                    cultures[-1] if cultures else None,
                    character in holders,
                    births[0] if births else None,
                    deaths[-1] if deaths else None,
                )
            )

    duplicates = {
        key: values for key, values in definitions.items() if len(values) > 1
    }
    missing = [row for row in alive if row[2] is None]
    invalid = [
        row for row in alive
        if row[2] is not None and row[2] not in valid_cultures
    ]
    holder_missing = [row for row in missing if row[3]]
    holder_invalid = [row for row in invalid if row[3]]
    missing_holder_definitions = sorted(holders - definitions.keys())

    print(
        f"definitions={len(definitions)} alive_at_start={len(alive)} "
        f"duplicate_ids={len(duplicates)}"
    )
    print(
        f"alive_missing_culture={len(missing)} "
        f"alive_invalid_culture={len(invalid)} "
        f"holder_missing={len(holder_missing)} "
        f"holder_invalid={len(holder_invalid)} "
        f"missing_holder_definitions={len(missing_holder_definitions)}"
    )
    for character in missing_holder_definitions[:300]:
        print(f"MISSING_HOLDER_DEFINITION {character}")
    for label, rows in (
        ("HOLDER_MISSING", holder_missing),
        ("HOLDER_INVALID", holder_invalid),
        ("ALIVE_MISSING", missing),
        ("ALIVE_INVALID", invalid),
    ):
        print(f"--- {label} ---")
        for row in rows[:300]:
            print(
                f"{row[1]}:{row[0]} culture={row[2]} "
                f"holder={row[3]} birth={row[4]} death={row[5]}"
            )
    print("--- DUPLICATE_IDS ---")
    for character, values in list(duplicates.items())[:300]:
        print(character, ", ".join(path for path, _ in values))


if __name__ == "__main__":
    main()
