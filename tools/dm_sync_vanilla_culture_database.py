from pathlib import Path
from shutil import copy2


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game")


def sync_glob(relative_dir: Path, pattern: str) -> int:
    source_dir = VANILLA / relative_dir
    target_dir = ROOT / relative_dir
    copied = 0
    for source in sorted(source_dir.glob(pattern)):
        if source.is_file():
            target = target_dir / source.name
            copy2(source, target)
            print(f"{source.relative_to(VANILLA)} -> {target.relative_to(ROOT)}")
            copied += 1
    return copied


def main() -> None:
    culture_count = sync_glob(
        Path("common/culture/cultures"),
        "00_*.txt",
    )
    pillar_count = sync_glob(
        Path("common/culture/pillars"),
        "00_*.txt",
    )
    legacy_duplicate_pillars = (
        "01_ethos.txt",
        "01_head_determination.txt",
        "01_martial_custom.txt",
    )
    isolated = 0
    pillar_dir = ROOT / "common" / "culture" / "pillars"
    for name in legacy_duplicate_pillars:
        source = pillar_dir / name
        target = source.with_suffix(source.suffix + ".disabled")
        if source.exists():
            if target.exists():
                target.unlink()
            source.replace(target)
            print(f"{source.relative_to(ROOT)} -> {target.name}")
            isolated += 1
    print(
        f"Synchronized {culture_count} vanilla culture files and "
        f"{pillar_count} vanilla pillar files; isolated "
        f"{isolated} legacy duplicate pillar files."
    )


if __name__ == "__main__":
    main()
