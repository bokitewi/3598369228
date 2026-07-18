#!/usr/bin/env python3
"""Keep vanilla database keys while disabling absent-map project branches."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
)
DEFAULT_LOG = Path(
    r"C:\Users\15550\AppData\Local\Temp\dm_ck3_clean_userdir\logs\error.log"
)
MISSING_RE = re.compile(
    r"Failed to fetch a valid landed title '([bc]_[A-Za-z0-9_-]+)'"
)
FALLBACKS = {"b": "b_490_0", "c": "c_zhu3"}


def block_end(text: str, opening_brace: int) -> int:
    depth = 0
    in_quote = False
    escaped = False
    index = opening_brace
    while index < len(text):
        character = text[index]
        if in_quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_quote = False
        else:
            if character == '"':
                in_quote = True
            elif character == "#":
                newline = text.find("\n", index)
                if newline < 0:
                    return len(text)
                index = newline
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return index + 1
        index += 1
    raise RuntimeError(f"Unclosed block beginning at byte {opening_brace}")


def replace_direct_child(
    body: str, child_key: str, replacement_body: str
) -> str:
    match = re.search(
        rf"(?m)^\t{re.escape(child_key)}[ \t]*=[ \t]*\{{",
        body,
    )
    if not match:
        return body
    end = block_end(body, match.end() - 1)
    replacement = (
        f"\t{child_key} = {{\n"
        f"{replacement_body}"
        "\n\t}"
    )
    return body[: match.start()] + replacement + body[end:]


def replace_missing_links(
    body: str, missing: set[str]
) -> tuple[str, int]:
    replaced = 0
    for key in sorted(missing, key=len, reverse=True):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(key)}(?![A-Za-z0-9_-])"
        )
        body, count = pattern.subn(FALLBACKS[key[0]], body)
        replaced += count
    return body, replaced


def rewrite_object(
    text: str,
    object_key: str,
    missing: set[str],
    false_children: tuple[str, ...],
    hide_from_list: bool = False,
) -> tuple[str, int]:
    match = re.search(
        rf"(?m)^{re.escape(object_key)}[ \t]*=[ \t]*\{{",
        text,
    )
    if not match:
        raise RuntimeError(f"Object not found: {object_key}")
    end = block_end(text, match.end() - 1)
    block = text[match.start() : end]
    block, replaced = replace_missing_links(block, missing)
    for child_key in false_children:
        block = replace_direct_child(
            block, child_key, "\t\talways = no"
        )
    if hide_from_list:
        if re.search(r"(?m)^\tshow_in_list[ \t]*=", block):
            block = re.sub(
                r"(?m)^\tshow_in_list[ \t]*=[^\r\n#]*",
                "\tshow_in_list = no",
                block,
            )
        else:
            block = block[:-1] + "\tshow_in_list = no\n}"
    return text[: match.start()] + block + text[end:], replaced


def source_text(relative_path: str) -> str:
    destination = ROOT / relative_path
    source = destination if destination.exists() else VANILLA / relative_path
    return source.read_text(encoding="utf-8-sig", errors="strict")


def write(relative_path: str, text: str) -> None:
    destination = ROOT / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8-sig", newline="\n")


def main() -> None:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    log_text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    missing = set(MISSING_RE.findall(log_text))

    project_path = "common/great_projects/types/00_great_project_types.txt"
    project_text = source_text(project_path)
    project_replaced = 0
    for key in (
        "great_wall",
        "great_wall_extend_to_shanhai_pass",
        "great_wall_extend_to_liaodong",
    ):
        project_text, count = rewrite_object(
            project_text,
            key,
            missing,
            ("is_shown", "can_start_planning", "is_valid"),
            hide_from_list=True,
        )
        project_replaced += count
    write(project_path, project_text)

    decision_path = "common/decisions/80_major_decisions.txt"
    decision_text = source_text(decision_path)
    decision_text, decision_replaced = rewrite_object(
        decision_text,
        "found_university_decision",
        missing,
        ("is_shown", "is_valid", "ai_potential"),
    )
    write(decision_path, decision_text)

    print(
        f"great_wall_links_redirected={project_replaced} "
        f"university_links_redirected={decision_replaced}"
    )


if __name__ == "__main__":
    main()
