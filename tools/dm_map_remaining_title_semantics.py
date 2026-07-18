#!/usr/bin/env python3
"""Apply narrow fallbacks for remaining vanilla map-specific semantics."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
)

COUNCIL_FILES = (
    "common/council_tasks/00_kurultai_tasks.txt",
    "common/council_tasks/00_marshal_tasks.txt",
    "common/council_tasks/00_chancellor_tasks.txt",
    "common/council_tasks/00_steward_tasks.txt",
    "common/council_tasks/00_spymaster_tasks.txt",
    "common/council_tasks/00_court_chaplain_tasks.txt",
    "common/script_values/99_court_chaplain_values.txt",
    "common/script_values/99_marshal_values.txt",
    "common/script_values/99_chancellor_values.txt",
)


def load(relative_path: str) -> str:
    destination = ROOT / relative_path
    source = (
        VANILLA / relative_path
        if relative_path in COUNCIL_FILES
        else destination if destination.exists() else VANILLA / relative_path
    )
    return source.read_text(encoding="utf-8-sig", errors="strict")


def write(relative_path: str, text: str) -> None:
    destination = ROOT / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8-sig", newline="\n")


def main() -> None:
    council_replacements = 0
    for relative_path in COUNCIL_FILES:
        text = load(relative_path)
        text, count = re.subn(
            r"(?<![A-Za-z0-9_-])c_byzantion(?![A-Za-z0-9_-])",
            "c_zhu3",
            text,
        )
        if relative_path == "common/council_tasks/00_steward_tasks.txt":
            text = text.replace(
                "this = title:c_maragha",
                "always = no",
            )
        if count:
            write(relative_path, text)
            council_replacements += count
            print(f"{relative_path}: university_title_fallbacks={count}")

    hunt_path = "common/scripted_triggers/00_hunt_triggers.txt"
    hunt_text = load(hunt_path)
    hunt_count = 0
    for county in (
        "c_dahlak",
        "c_faereyar",
        "c_hormuz",
        "c_lesbos",
        "c_maldives",
        "c_malta",
        "c_naxos",
    ):
        pattern = re.compile(
            rf"(?m)^([ \t]*)county[ \t]*=[ \t]*title:{county}"
            r"[^\r\n]*$"
        )
        hunt_text, count = pattern.subn(r"\1always = no", hunt_text)
        hunt_count += count
    write(hunt_path, hunt_text)

    shrine_path = "events/religion_events/local_shrine_events.txt"
    shrine_text = load(shrine_path)
    shrine_text, shrine_count = re.subn(
        r"(?<![A-Za-z0-9_-])b_qianfeng(?![A-Za-z0-9_-])",
        "b_793_0",
        shrine_text,
    )
    write(shrine_path, shrine_text)

    print(
        f"council_fallbacks={council_replacements} "
        f"hunt_exclusions_removed={hunt_count} "
        f"local_shrine_links_mapped={shrine_count}"
    )


if __name__ == "__main__":
    main()
