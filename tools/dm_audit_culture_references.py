import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game")

TOP_LEVEL = re.compile(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{")
SINGLE_FIELDS = (
    "ethos",
    "heritage",
    "language",
    "martial_custom",
    "head_determination",
)


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


def keys_in(directory: Path):
    result = set()
    for path in directory.glob("*.txt"):
        result.update(key for key, _ in blocks(path))
    return result


def main() -> None:
    pillars = keys_in(ROOT / "common/culture/pillars")
    traditions = keys_in(VANILLA / "common/culture/traditions")
    traditions.update(keys_in(ROOT / "common/culture/traditions"))

    failures = []
    culture_count = 0
    for path in sorted((ROOT / "common/culture/cultures").glob("*.txt")):
        for culture, body in blocks(path):
            culture_count += 1
            for field in SINGLE_FIELDS:
                match = re.search(
                    rf"(?m)^\s*{field}\s*=\s*([A-Za-z0-9_]+)",
                    body,
                )
                if match and match.group(1) not in pillars:
                    failures.append(
                        (path.name, culture, field, match.group(1))
                    )
            tradition_block = re.search(
                r"(?ms)^\s*traditions\s*=\s*\{(.*?)^\s*\}",
                body,
            )
            if tradition_block:
                for tradition in re.findall(
                    r"\btradition_[A-Za-z0-9_]+\b",
                    tradition_block.group(1),
                ):
                    if tradition not in traditions:
                        failures.append(
                            (path.name, culture, "tradition", tradition)
                        )

    print(
        f"Audited {culture_count} cultures against "
        f"{len(pillars)} pillars and {len(traditions)} traditions."
    )
    for path, culture, field, value in failures:
        print(f"{path}: {culture}: missing {field} = {value}")
    print(f"Missing references: {len(failures)}")


if __name__ == "__main__":
    main()
