#!/usr/bin/env python3
"""Preserve generic pilgrimage while isolating absent vanilla holy sites."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dm_isolate_absent_map_projects_decisions import replace_direct_child
from dm_isolate_missing_title_links import block_end


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
    r"\common\activities\activity_types\pilgrimage.txt"
)
TARGET = ROOT / "common/activities/activity_types/pilgrimage.txt"
DEFAULT_LOG = Path(
    r"C:\Users\15550\AppData\Local\Temp\dm_ck3_clean_userdir\logs\error.log"
)
MISSING_RE = re.compile(
    r"Failed to fetch a valid landed title '([bc]_[A-Za-z0-9_-]+)'"
    r".*?file: common/activities/activity_types/pilgrimage\.txt"
)
BACKGROUND_RE = re.compile(r"(?m)^[ \t]*background[ \t]*=[ \t]*\{")
FALLBACKS = {"b": "b_490_0", "c": "c_zhu3"}


def disable_absent_unique_backgrounds(
    text: str, missing: set[str]
) -> tuple[str, int]:
    blocks: list[tuple[int, int, str]] = []
    for match in BACKGROUND_RE.finditer(text):
        end = block_end(text, match.end() - 1)
        block = text[match.start() : end]
        if any(
            re.search(
                rf"(?<![A-Za-z0-9_-]){re.escape(key)}"
                rf"(?![A-Za-z0-9_-])",
                block,
            )
            for key in missing
        ):
            blocks.append((match.start(), end, block))
    for start, end, block in reversed(blocks):
        indent_match = re.match(r"^([ \t]*)", block)
        indent = indent_match.group(1) if indent_match else ""
        normalized = re.sub(
            rf"(?m)^{re.escape(indent)}",
            "",
            block,
        )
        normalized = replace_direct_child(
            normalized, "trigger", "\t\talways = no"
        )
        block = "\n".join(
            indent + line if line else line
            for line in normalized.splitlines()
        )
        text = text[:start] + block + text[end:]
    return text, len(blocks)


def main() -> None:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    log_text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    missing = set(MISSING_RE.findall(log_text))
    text = SOURCE.read_text(encoding="utf-8-sig", errors="strict")
    text, background_count = disable_absent_unique_backgrounds(
        text, missing
    )
    replaced = 0
    for key in sorted(missing, key=len, reverse=True):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(key)}(?![A-Za-z0-9_-])"
        )
        text, count = pattern.subn(FALLBACKS[key[0]], text)
        replaced += count
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8-sig", newline="\n")
    print(
        f"pilgrimage_links_redirected={replaced} "
        f"unique_backgrounds_disabled={background_count}"
    )


if __name__ == "__main__":
    main()
