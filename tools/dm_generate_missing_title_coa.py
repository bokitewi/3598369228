#!/usr/bin/env python3
"""Generate deterministic CoAs for existing titles that cannot derive one."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG = Path(r"E:\documents\Paradox Interactive\Crusader Kings III\logs\error.log")
COA_DIR = ROOT / "common/coat_of_arms/coat_of_arms"
TARGET = COA_DIR / "zz_dm_compat_generated_title_coa.txt"
ERROR_RE = re.compile(
    r"Title '([ekdcbh]_[A-Za-z0-9_-]+)' needs one of the following "
    r"to generate a Coat of Arms"
)
KEY_RE = re.compile(
    r"(?m)^([ekdcbh]_[A-Za-z0-9_-]+)\s*=\s*\{"
)
COLORS = ("red", "blue", "yellow", "green", "black", "white", "purple")


def main() -> None:
    logged = set(
        ERROR_RE.findall(LOG.read_text(encoding="utf-8-sig", errors="replace"))
    )
    existing: set[str] = set()
    for path in COA_DIR.glob("*.txt"):
        if path == TARGET:
            continue
        existing.update(
            KEY_RE.findall(
                path.read_text(encoding="utf-8-sig", errors="replace")
            )
        )
    missing = sorted(logged - existing)
    lines = [
        "# Generated CoAs for existing titles without a derivation source.",
        "",
    ]
    for key in missing:
        digest = hashlib.sha256(("title:" + key).encode("ascii")).digest()
        first = COLORS[digest[0] % len(COLORS)]
        second = COLORS[digest[1] % len(COLORS)]
        if second == first:
            second = COLORS[(COLORS.index(first) + 1) % len(COLORS)]
        lines.extend(
            [
                f"{key} = {{",
                '\tpattern = "pattern_solid.dds"',
                f'\tcolor1 = "{first}"',
                f'\tcolor2 = "{second}"',
                "}",
                "",
            ]
        )
    TARGET.write_text("\n".join(lines), encoding="utf-8-sig", newline="\n")
    print(f"logged={len(logged)} existing={len(logged & existing)}")
    print(f"generated={len(missing)} target={TARGET}")


if __name__ == "__main__":
    main()
