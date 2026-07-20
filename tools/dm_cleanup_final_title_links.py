#!/usr/bin/env python3
"""Clean low-frequency absent-title links without adding fake counties."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dm_disable_absent_title_visual_branches import (
    disable_trigger_blocks,
)
from dm_isolate_absent_map_projects_decisions import (
    replace_direct_child,
)
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
    r".*?file: ([^']+?) line: [0-9]+ \(([A-Za-z0-9_.]+)"
)
FALLBACKS = {"b": "b_490_0", "c": "c_zhu3"}


def load(relative_path: str) -> str:
    destination = ROOT / relative_path
    source = destination if destination.exists() else VANILLA / relative_path
    return source.read_text(encoding="utf-8-sig", errors="strict")


def write(relative_path: str, text: str) -> None:
    destination = ROOT / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8-sig", newline="\n")


def contains_missing(text: str, missing: set[str]) -> bool:
    return any(
        re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(key)}"
            rf"(?![A-Za-z0-9_-])",
            text,
        )
        for key in missing
    )


def remove_named_blocks(
    text: str,
    missing: set[str],
    names: tuple[str, ...],
) -> tuple[str, int]:
    name_pattern = "|".join(re.escape(name) for name in names)
    block_re = re.compile(
        rf"(?m)^([ \t]*)(?:{name_pattern})[ \t]*=[ \t]*\{{"
    )
    selected: list[tuple[int, int, str]] = []
    for match in block_re.finditer(text):
        end = block_end(text, match.end() - 1)
        if any(start <= match.start() < old_end for start, old_end, _ in selected):
            continue
        block = text[match.start() : end]
        if contains_missing(block, missing):
            selected.append((match.start(), end, match.group(1)))
    for start, end, indent in reversed(selected):
        text = (
            text[:start]
            + f"{indent}# Absent vanilla-map branch removed."
            + text[end:]
        )
    return text, len(selected)


def remove_title_scope_blocks(
    text: str, missing: set[str]
) -> tuple[str, int]:
    keys = "|".join(re.escape(key) for key in sorted(missing))
    if not keys:
        return text, 0
    scope_re = re.compile(
        rf"(?m)^([ \t]*)title:(?:{keys})[ \t]*=[ \t]*\{{"
    )
    blocks: list[tuple[int, int, str]] = []
    for match in scope_re.finditer(text):
        end = block_end(text, match.end() - 1)
        blocks.append((match.start(), end, match.group(1)))
    for start, end, indent in reversed(blocks):
        text = (
            text[:start]
            + f"{indent}# Absent vanilla title scope removed."
            + text[end:]
        )
    return text, len(blocks)


def replace_residual(
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


def rewrite_top_object(
    text: str,
    object_key: str,
    missing: set[str],
    false_children: tuple[str, ...],
    empty_children: tuple[str, ...],
) -> tuple[str, int]:
    match = re.search(
        rf"(?m)^{re.escape(object_key)}[ \t]*=[ \t]*\{{",
        text,
    )
    if not match:
        raise RuntimeError(f"Object not found: {object_key}")
    end = block_end(text, match.end() - 1)
    block = text[match.start() : end]
    block, replaced = replace_residual(block, missing)
    for child in false_children:
        block = replace_direct_child(block, child, "\t\talways = no")
    for child in empty_children:
        block = replace_direct_child(block, child, "")
    return text[: match.start()] + block + text[end:], replaced


def main() -> None:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    log_text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    missing_by_source: dict[str, set[str]] = {}
    contexts_by_source: dict[str, set[str]] = {}
    for title, source, context in ERROR_RE.findall(log_text):
        source = source.replace("\\", "/")
        missing_by_source.setdefault(source, set()).add(title)
        contexts_by_source.setdefault(source, set()).add(context)

    for relative_path, missing in sorted(missing_by_source.items()):
        if relative_path.startswith("tests/"):
            write(
                relative_path,
                "# Vanilla-world automated test disabled for total conversion.\n",
            )
            print(f"{relative_path}: test disabled")
            continue

        text = load(relative_path)
        if relative_path.startswith("common/tutorial"):
            text, replaced = replace_residual(text, missing)
            write(relative_path, text)
            print(f"{relative_path}: tutorial fallbacks={replaced}")
            continue

        if relative_path.startswith("common/casus_belli_types/"):
            replaced = 0
            for key in sorted(contexts_by_source[relative_path]):
                text, count = rewrite_top_object(
                    text,
                    key,
                    missing,
                    ("can_use", "can_use_title", "can_use_target"),
                    ("on_victory",),
                )
                replaced += count
            write(relative_path, text)
            print(f"{relative_path}: CBs disabled links={replaced}")
            continue

        if relative_path.startswith("common/buildings/"):
            replaced = 0
            for key in sorted(contexts_by_source[relative_path]):
                text, count = rewrite_top_object(
                    text,
                    key,
                    missing,
                    ("can_construct_potential", "can_construct"),
                    (),
                )
                replaced += count
            write(relative_path, text)
            print(f"{relative_path}: buildings hidden links={replaced}")
            continue

        if relative_path.startswith("common/script_values/"):
            text, removed = remove_named_blocks(
                text, missing, ("if", "modifier")
            )
            text, residual = replace_residual(text, missing)
            write(relative_path, text)
            print(
                f"{relative_path}: value branches={removed} "
                f"residual={residual}"
            )
            continue

        if relative_path.startswith("common/on_action/"):
            text, removed = remove_named_blocks(
                text, missing, ("if", "trigger_if")
            )
            text, scopes = remove_title_scope_blocks(text, missing)
            text, residual = replace_residual(text, missing)
            write(relative_path, text)
            print(
                f"{relative_path}: on_action branches={removed} "
                f"scopes={scopes} residual={residual}"
            )
            continue

        if relative_path.startswith("common/activities/"):
            text, triggers = disable_trigger_blocks(text, missing)
            text, residual = replace_residual(text, missing)
            write(relative_path, text)
            print(
                f"{relative_path}: activity triggers={triggers} "
                f"residual={residual}"
            )
            continue

        if relative_path.startswith("common/story_cycles/"):
            replaced = 0
            for key in sorted(contexts_by_source[relative_path]):
                text, count = rewrite_top_object(
                    text, key, missing, ("trigger",), ()
                )
                replaced += count
            write(relative_path, text)
            print(f"{relative_path}: story cycles hidden links={replaced}")
            continue

        text, removed = remove_named_blocks(
            text,
            missing,
            (
                "if",
                "trigger_if",
                "modifier",
                "trigger",
                "on_invalidated",
            ),
        )
        text, scopes = remove_title_scope_blocks(text, missing)
        text, residual = replace_residual(text, missing)
        write(relative_path, text)
        print(
            f"{relative_path}: branches={removed} scopes={scopes} "
            f"residual={residual}"
        )


if __name__ == "__main__":
    main()
