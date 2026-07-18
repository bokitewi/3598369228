#!/usr/bin/env python3
"""Hide vanilla decisions whose required map titles do not exist."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dm_isolate_absent_map_projects_decisions import (
    replace_direct_child,
    replace_missing_links,
)
from dm_isolate_missing_title_links import block_end


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
)
DEFAULT_LOG = Path(
    r"C:\Users\15550\AppData\Local\Temp\dm_ck3_clean_userdir\logs\error.log"
)
LOCATION_RE = re.compile(
    r"Failed to fetch a valid landed title '([bc]_[A-Za-z0-9_-]+)'.*?"
    r"file: (common/decisions/[^']+?) line: [0-9]+ "
    r"\(([A-Za-z0-9_.]+)"
)


def rewrite_decision(
    text: str,
    decision_key: str,
    missing: set[str],
) -> tuple[str, int]:
    match = re.search(
        rf"(?m)^{re.escape(decision_key)}[ \t]*=[ \t]*\{{",
        text,
    )
    if not match:
        raise RuntimeError(f"Decision not found: {decision_key}")
    end = block_end(text, match.end() - 1)
    block = text[match.start() : end]
    block, replaced = replace_missing_links(block, missing)
    for child_key in (
        "is_shown",
        "is_valid",
        "is_valid_showing_failures_only",
        "ai_potential",
    ):
        block = replace_direct_child(
            block, child_key, "\t\talways = no"
        )
    block = replace_direct_child(block, "effect", "")
    block = replace_direct_child(block, "ai_will_do", "\t\tvalue = 0")
    return text[: match.start()] + block + text[end:], replaced


def main() -> None:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    log_text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    keys_by_source: dict[str, set[str]] = {}
    missing_by_source: dict[str, set[str]] = {}
    for title, source, context in LOCATION_RE.findall(log_text):
        source = source.replace("\\", "/")
        if "_M_COPF" in source:
            continue
        keys_by_source.setdefault(source, set()).add(context)
        missing_by_source.setdefault(source, set()).add(title)

    decision_count = 0
    link_count = 0
    for relative_path, keys in sorted(keys_by_source.items()):
        destination = ROOT / relative_path
        source = destination if destination.exists() else VANILLA / relative_path
        if not source.exists():
            print(f"SKIP missing source: {relative_path}")
            continue
        text = source.read_text(encoding="utf-8-sig", errors="strict")
        for key in sorted(keys):
            text, replaced = rewrite_decision(
                text, key, missing_by_source[relative_path]
            )
            decision_count += 1
            link_count += replaced
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8-sig", newline="\n")
        print(f"{relative_path}: disabled={len(keys)}")
    print(f"decisions_disabled={decision_count} links_redirected={link_count}")


if __name__ == "__main__":
    main()
