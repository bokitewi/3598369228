from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CULTURE_DIR = ROOT / "common" / "culture" / "cultures"


def main() -> None:
    moved = 0
    for source in sorted(CULTURE_DIR.glob("00_*.txt")):
        target = source.with_suffix(source.suffix + ".disabled")
        if target.exists():
            raise RuntimeError(f"Refusing to overwrite {target}")
        source.replace(target)
        print(f"{source.relative_to(ROOT)} -> {target.name}")
        moved += 1
    print(f"Isolated {moved} unused vanilla culture files.")


if __name__ == "__main__":
    main()
