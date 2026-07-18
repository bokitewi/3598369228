#!/usr/bin/env python3
"""Map the vanilla nomad merchant-origin effect to Spring-Autumn cities."""

from __future__ import annotations

import re
from pathlib import Path

from dm_isolate_missing_title_links import block_end


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
    r"\common\scripted_effects\09_dlc_mpo_scripted_effects.txt"
)
TARGET = ROOT / "common/scripted_effects/09_dlc_mpo_scripted_effects.txt"
EFFECT_KEY = "mpo_find_suitable_merchant_effect"
MARKETS = (
    ("c_wangcheng", "b_793_0", "Wangcheng"),
    ("c_linzi", "b_8_0", "Linzi"),
    ("c_ying", "b_330_0", "Ying"),
    ("c_xianyang", "b_900_0", "Xianyang"),
    ("c_qufu", "b_444_0", "Qufu"),
    ("c_daliang", "b_645_0", "Daliang"),
    ("c_ji", "b_132_0", "Ji"),
    ("c_shangqiu", "b_533_0", "Shangqiu"),
    ("c_handan", "b_1191_0", "Handan"),
    ("c_gusu", "b_2110_0", "Gusu"),
    ("c_jinling", "b_2088_0", "Jinling"),
)


def generated_effect() -> str:
    lines = [
        f"{EFFECT_KEY} = {{",
        "\t# Spring-Autumn market origins; vanilla world titles are absent.",
        "\trandom_list = {",
    ]
    for county, barony, label in MARKETS:
        lines.extend(
            [
                f"\t\t1 = {{ # {label}",
                "\t\t\ttrigger = {",
                f"\t\t\t\ttitle:{county} = {{",
                "\t\t\t\t\texists = holder",
                "\t\t\t\t\tNOT = {",
                "\t\t\t\t\t\tholder.top_liege = {",
                (
                    "\t\t\t\t\t\t\tgovernment_has_flag = "
                    "government_is_nomadic"
                ),
                "\t\t\t\t\t\t}",
                "\t\t\t\t\t}",
                "\t\t\t\t}",
                "\t\t\t}",
                "\t\t\tmodifier = {",
                f"\t\t\t\tadd = title:{county}.development_level",
                "\t\t\t}",
                f"\t\t\ttitle:{barony} = {{",
                "\t\t\t\tsave_scope_as = merchant_origin",
                "\t\t\t}",
                "\t\t}",
            ]
        )
    lines.extend(["\t}", "}"])
    return "\n".join(lines)


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8-sig", errors="strict")
    match = re.search(
        rf"(?m)^{re.escape(EFFECT_KEY)}[ \t]*=[ \t]*\{{",
        text,
    )
    if not match:
        raise RuntimeError(f"Vanilla effect not found: {EFFECT_KEY}")
    end = block_end(text, match.end() - 1)
    text = text[: match.start()] + generated_effect() + text[end:]
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8-sig", newline="\n")
    print(f"Mapped {EFFECT_KEY} to {len(MARKETS)} Spring-Autumn markets")


if __name__ == "__main__":
    main()
