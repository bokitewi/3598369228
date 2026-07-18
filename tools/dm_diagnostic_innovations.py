import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INNOVATION_DIR = ROOT / "common" / "culture" / "innovations"
FILES = (
    "dm_early_medieval_innovations.txt",
    "dm_high_medieval_innovations.txt",
    "dm_tribal_innovations.txt",
    "01_early_medieval_innovations_COPF.txt",
)
SUFFIX = ".diagnostic_disabled"


def disable() -> None:
    moved = 0
    for name in FILES:
        source = INNOVATION_DIR / name
        target = Path(str(source) + SUFFIX)
        if source.exists():
            if target.exists():
                raise RuntimeError(f"Refusing to overwrite {target}")
            source.replace(target)
            moved += 1
    print(f"Disabled {moved} custom innovation files for diagnosis.")


def restore() -> None:
    moved = 0
    for name in FILES:
        source = INNOVATION_DIR / name
        backup = Path(str(source) + SUFFIX)
        if backup.exists():
            if source.exists():
                raise RuntimeError(f"Refusing to overwrite {source}")
            backup.replace(source)
            moved += 1
    print(f"Restored {moved} custom innovation files.")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"disable", "restore"}:
        raise SystemExit("Usage: dm_diagnostic_innovations.py disable|restore")
    if sys.argv[1] == "disable":
        disable()
    else:
        restore()


if __name__ == "__main__":
    main()
