#!/usr/bin/env python3
"""Replace selected European achievement files with inert registered shells."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III"
    r"\game\common\achievements"
)
FILES = (
    "fp1_achievements.txt",
    "fp2_achievements.txt",
    "ep3_achievements.txt",
)
TOP_KEY_RE = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*\{")


def top_level_keys(text: str) -> list[str]:
    keys: list[str] = []
    depth = 0
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0]
        if depth == 0:
            match = TOP_KEY_RE.match(line.strip())
            if match:
                keys.append(match.group(1))
        depth += line.count("{") - line.count("}")
        if depth < 0:
            raise ValueError("Unbalanced closing brace")
    if depth:
        raise ValueError(f"Unbalanced braces: depth={depth}")
    return keys


def main() -> None:
    out_dir = ROOT / "common/achievements"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in FILES:
        source = VANILLA / name
        keys = top_level_keys(source.read_text(encoding="utf-8-sig"))
        lines = [
            "# Deliberate total-conversion override.",
            "# IDs remain registered, but European achievement logic is disabled.",
            "",
        ]
        for key in keys:
            lines.extend(
                [
                    f"{key} = {{",
                    "\tpossible = { always = no }",
                    "\thappened = { always = no }",
                    "}",
                    "",
                ]
            )
        target = out_dir / name
        target.write_text("\n".join(lines), encoding="utf-8-sig", newline="\n")
        print(f"{name}: {len(keys)} inert achievements")
        total += len(keys)
    print(f"total={total}")


if __name__ == "__main__":
    main()
