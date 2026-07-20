#!/usr/bin/env python3
"""Disable visual/localization branches tied to absent vanilla titles."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dm_isolate_missing_title_links import block_end


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
)
DEFAULT_LOG = Path(
    r"C:\Users\15550\AppData\Local\Temp\dm_ck3_clean_userdir\logs\error.log"
)
ERROR_RE = re.compile(
    r"Failed to fetch a valid landed title '([bc]_[A-Za-z0-9_-]+)'"
    r".*?file: ([^']+?) line:"
)
TRIGGER_RE = re.compile(
    r"(?m)^([ \t]*)trigger[ \t]*=[ \t]*\{"
)
VISUAL_PREFIXES = (
    "common/event_backgrounds/",
    "common/event_themes/",
    "common/customizable_localization/",
    "gfx/interface/illustrations/scripted_illustrations/",
    "gfx/court_scene/",
)
FALLBACKS = {"b": "b_490_0", "c": "c_zhu3"}


def contains_key(text: str, keys: set[str]) -> bool:
    return any(
        re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(key)}"
            rf"(?![A-Za-z0-9_-])",
            text,
        )
        for key in keys
    )


def disable_trigger_blocks(
    text: str, missing: set[str]
) -> tuple[str, int]:
    selected: list[tuple[int, int, str]] = []
    for match in TRIGGER_RE.finditer(text):
        end = block_end(text, match.end() - 1)
        if any(start <= match.start() < old_end for start, old_end, _ in selected):
            continue
        block = text[match.start() : end]
        if contains_key(block, missing):
            selected.append((match.start(), end, match.group(1)))
    for start, end, indent in reversed(selected):
        text = (
            text[:start]
            + f"{indent}trigger = {{ always = no }}"
            + text[end:]
        )
    return text, len(selected)


def replace_residual_links(
    text: str, missing: set[str]
) -> tuple[str, int]:
    replaced = 0
    for key in sorted(missing, key=len, reverse=True):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(key)}(?![A-Za-z0-9_-])"
        )
        text, count = pattern.subn(FALLBACKS[key[0]], text)
        replaced += count
    return text, replaced


def main() -> None:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    log_text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    missing_by_source: dict[str, set[str]] = {}
    for key, source in ERROR_RE.findall(log_text):
        source = source.replace("\\", "/")
        if source.startswith(VISUAL_PREFIXES):
            missing_by_source.setdefault(source, set()).add(key)

    total_triggers = 0
    total_residual = 0
    for relative_path, missing in sorted(missing_by_source.items()):
        destination = ROOT / relative_path
        source = destination if destination.exists() else VANILLA / relative_path
        text = source.read_text(encoding="utf-8-sig", errors="strict")
        text, triggers = disable_trigger_blocks(text, missing)
        text, residual = replace_residual_links(text, missing)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8-sig", newline="\n")
        total_triggers += triggers
        total_residual += residual
        print(
            f"{relative_path}: triggers_disabled={triggers} "
            f"residual_links_redirected={residual}"
        )
    print(
        f"total_triggers_disabled={total_triggers} "
        f"total_residual_links_redirected={total_residual}"
    )


if __name__ == "__main__":
    main()
