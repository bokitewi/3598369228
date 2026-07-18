#!/usr/bin/env python3
"""Neutralize vanilla definition blocks that reference absent map titles.

County and barony compatibility shells are not safe in CK3 because they need
real province and de-jure structures.  For selected vanilla databases, keep
the public scripted keys registered while neutralizing only top-level
definitions that link to counties or baronies absent from the total
conversion map.
"""

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
LOCATION_RE = re.compile(
    r"Failed to fetch a valid landed title '([bc]_[A-Za-z0-9_-]+)'.*?"
    r"file: ([^']+?) line: [0-9]+ \(([A-Za-z0-9_.]+)"
)
TOP_LEVEL_BLOCK = re.compile(
    r"(?m)^(?:(scripted_effect|scripted_trigger)[ \t]+)?"
    r"([A-Za-z0-9_.]+)[ \t]*=[ \t]*\{"
)

TARGETS = {
    "common/scripted_triggers/10_tgp_japan_triggers.txt": "trigger",
    "common/scripted_modifiers/10_tgp_japan_modifiers.txt": "modifier",
    "common/scripted_effects/00_historical_characters_scripted_effects.txt": (
        "effect"
    ),
    "common/scripted_effects/00_tributary_setup_effects.txt": "effect",
    "common/scripted_effects/00_major_decisions_scripted_effects.txt": (
        "effect"
    ),
    "common/scripted_effects/06_dlc_ce1_legend_effects.txt": "effect",
    "common/scripted_effects/07_frankokratia_scripted_effects.txt": "effect",
    "common/script_values/02_religion_values.txt": "value",
    "events/dlc/ep3/ep3_emperor_yearly_2.txt": "event",
    "events/decisions_events/major_decisions_events.txt": "event",
    "events/dlc/fp2/fp2_yearly_events.txt": "event",
    "events/dlc/ep3/ep3_frankokratia_events.txt": "event",
    "events/dlc/ce1/epidemic_events.txt": "event",
    "events/bookmark_events.txt": "event",
    "events/dlc/fp3/fp3_story_cycle_zanj_rebellion_events.txt": "event",
    (
        "events/dlc/ep3/"
        "ep3_story_cycle_harrying_of_the_north_events.txt"
    ): "event",
    (
        "events/activities/coronation_activity/"
        "coronation_events_6.txt"
    ): "event",
    "events/dlc/tgp/tgp_silk_road_events.txt": "event",
    "common/scripted_triggers/tgp_silk_road_triggers.txt": "trigger",
    "common/on_action/activities/pilgrimage_on_actions.txt": "on_action",
    (
        "events/activities/pilgrimage_activity/"
        "pilgrimage_events.txt"
    ): "event",
    "events/activities/pilgrimage_activity/hajj_events.txt": "event",
    (
        "events/activities/pilgrimage_activity/"
        "pilgrimage_events_seasia.txt"
    ): "event",
    "events/religion_events/great_holy_war_events.txt": "event",
    (
        "events/activities/imperial_examination_activity/"
        "emperor_prep_phase_imperial_examination_events.txt"
    ): "event",
    "common/achievements/standard_achievements.txt": "achievement",
}
EVENT_EXCLUSIONS = {
    "events/dlc/tgp/tgp_silk_road_events.txt",
    "events/religion_events/great_holy_war_events.txt",
    "events/religion_events/local_shrine_events.txt",
}
EFFECT_EXCLUSIONS = {
    "common/scripted_effects/00_relation_effects.txt",
    "common/scripted_effects/09_dlc_mpo_scripted_effects.txt",
}


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


def replacement(
    declaration: str | None,
    key: str,
    kind: str,
    links: list[str],
    original_body: str,
) -> str:
    prefix = f"{declaration} " if declaration else ""
    comment = "\t# Absent vanilla-map title links isolated."
    if kind == "trigger":
        body = [comment, "\talways = no"]
    elif kind == "modifier":
        body = [comment, "\tmodifier = { add = 0 }"]
    elif kind == "effect":
        body = [comment]
    elif kind == "value":
        body = [comment, "\tvalue = 0"]
    elif kind == "event":
        if declaration == "scripted_trigger":
            body = [comment, "\talways = no"]
        elif declaration == "scripted_effect":
            body = [comment]
        else:
            event_type = re.search(
                r"(?m)^[ \t]*type[ \t]*=[ \t]*([A-Za-z0-9_]+)",
                original_body,
            )
            type_key = (
                event_type.group(1) if event_type else "character_event"
            )
            body = [
                comment,
                f"\ttype = {type_key}",
                "\thidden = yes",
                "\ttrigger = { always = no }",
            ]
    elif kind == "on_action":
        body = [comment, "\ttrigger = { always = no }"]
    elif kind == "achievement":
        body = [
            comment,
            "\tpossible = { always = no }",
            "\thappened = { always = no }",
        ]
    else:
        raise ValueError(f"Unknown target kind: {kind}")
    return f"{prefix}{key} = {{\n" + "\n".join(body) + "\n}"


def neutralize(
    text: str,
    missing: set[str],
    forced_keys: set[str],
    kind: str,
) -> tuple[str, int]:
    blocks: list[
        tuple[int, int, str | None, str, list[str], str]
    ] = []
    for match in TOP_LEVEL_BLOCK.finditer(text):
        end = block_end(text, match.end() - 1)
        body = text[match.end() : end - 1]
        links = sorted(
            key
            for key in missing
            if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(key)}(?![A-Za-z0-9_-])", body)
        )
        if links or match.group(2) in forced_keys:
            blocks.append(
                (
                    match.start(),
                    end,
                    match.group(1),
                    match.group(2),
                    links,
                    body,
                )
            )

    for start, end, declaration, key, links, body in reversed(blocks):
        text = (
            text[:start]
            + replacement(declaration, key, kind, links, body)
            + text[end:]
        )
    return text, len(blocks)


def main() -> None:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    log_text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    missing = set(MISSING_RE.findall(log_text))
    contexts_by_source: dict[str, set[str]] = {}
    for _title, source, context in LOCATION_RE.findall(log_text):
        contexts_by_source.setdefault(source.replace("\\", "/"), set()).add(
            context
        )
    print(f"missing_county_barony_keys={len(missing)}")

    targets = dict(TARGETS)
    for relative_path in contexts_by_source:
        vanilla_path = VANILLA / relative_path
        if not vanilla_path.exists():
            continue
        if (
            relative_path.startswith("events/")
            and relative_path not in EVENT_EXCLUSIONS
            and not relative_path.startswith(
                "events/activities/pilgrimage_activity/"
            )
            and not relative_path.startswith(
                "events/activities/imperial_examination_activity/"
            )
        ):
            targets.setdefault(relative_path, "event")
        elif (
            relative_path.startswith("common/scripted_effects/")
            and relative_path not in EFFECT_EXCLUSIONS
        ):
            targets.setdefault(relative_path, "effect")
        elif relative_path.startswith("common/scripted_triggers/"):
            targets.setdefault(relative_path, "trigger")

    for relative_path, kind in targets.items():
        destination = ROOT / relative_path
        source = destination if destination.exists() else VANILLA / relative_path
        text = source.read_text(encoding="utf-8-sig", errors="strict")
        generated, count = neutralize(
            text,
            missing,
            contexts_by_source.get(relative_path, set()),
            kind,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            generated, encoding="utf-8-sig", newline="\n"
        )
        print(f"{relative_path}: neutralized={count}")


if __name__ == "__main__":
    main()
