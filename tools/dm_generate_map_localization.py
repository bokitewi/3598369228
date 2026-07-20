#!/usr/bin/env python3
"""Generate localization for intentionally split sea and lake map provinces."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "localization"
    / "simp_chinese"
    / "dm_generated_map_provinces_l_simp_chinese.yml"
)


def render() -> str:
    lines = [
        "l_simp_chinese:",
        ' lake_weiding:0 "渭定湖"',
    ]
    lines.extend(
        f' sea_bohai_bay_{index}:0 "渤海"'
        for index in range(1, 176)
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8-sig") if OUTPUT.exists() else None
        if current != expected:
            print(f"DRIFT: {OUTPUT.relative_to(ROOT)}")
            return 1
        print("map localization is up to date")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8-sig", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
