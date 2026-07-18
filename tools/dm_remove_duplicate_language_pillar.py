from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "common" / "culture" / "pillars" / "01_language.txt"


def remove_top_level_block(text: str, key: str) -> str:
    marker = f"{key} = {{"
    start = text.find(marker)
    if start < 0:
        return text
    depth = 0
    end = start
    for index in range(start, len(text)):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    while end < len(text) and text[end] in "\r\n":
        end += 1
    return text[:start] + text[end:]


def main() -> None:
    original = TARGET.read_text(encoding="utf-8-sig")
    updated = remove_top_level_block(original, "language_chinese")
    if updated == original:
        print("language_chinese was already absent.")
        return
    TARGET.write_text(updated, encoding="utf-8-sig", newline="")
    print("Removed duplicate language_chinese from 01_language.txt.")


if __name__ == "__main__":
    main()
