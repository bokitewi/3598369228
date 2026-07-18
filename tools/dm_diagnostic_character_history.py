import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = ROOT / "history" / "characters"
TEST_FILE = HISTORY_DIR / "zz_dm_diagnostic_characters.txt"
SUFFIX = ".all_diagnostic_disabled"


def top_level_keys(path: Path):
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line and not line[0].isspace() and "= {" in line:
            key = line.split("=", 1)[0].strip()
            if key.replace("_", "").isalnum():
                yield key


def enable() -> None:
    characters = []
    sources = sorted(HISTORY_DIR.glob("*.txt"))
    for source in sources:
        if source == TEST_FILE:
            continue
        backup = Path(str(source) + SUFFIX)
        if backup.exists():
            raise RuntimeError(f"Refusing to overwrite {backup}")
        characters.extend(top_level_keys(source))
        source.replace(backup)
    entries = []
    for character in dict.fromkeys(characters):
        entries.append(
            f"{character} = {{\n"
            "\tname = \"Diagnostic\"\n"
            "\tculture = zhou\n"
            "\tfaith = dongzhouli\n"
            "\t3800.1.1 = { birth = yes }\n"
            "}\n"
        )
    TEST_FILE.write_text("\n".join(entries), encoding="utf-8-sig")
    print(
        f"Enabled minimal diagnostic history for "
        f"{len(entries)} character IDs."
    )


def restore() -> None:
    if TEST_FILE.exists():
        TEST_FILE.unlink()
    restored = 0
    for backup in sorted(HISTORY_DIR.glob(f"*.txt{SUFFIX}")):
        source = Path(str(backup).removesuffix(SUFFIX))
        if source.exists():
            raise RuntimeError(f"Refusing to overwrite {source}")
        backup.replace(source)
        restored += 1
    print(f"Restored {restored} character history files.")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"enable", "restore"}:
        raise SystemExit(
            "Usage: dm_diagnostic_character_history.py enable|restore"
        )
    if sys.argv[1] == "enable":
        enable()
    else:
        restore()


if __name__ == "__main__":
    main()
