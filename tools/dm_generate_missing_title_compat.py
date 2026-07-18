#!/usr/bin/env python3
"""Generate inert landed-title compatibility shells from the current CK3 log.

The total-conversion map replaces vanilla landed titles, while global vanilla
databases still compile references to those keys.  These shells deliberately
have no province, de-jure parent, holder, history, or gameplay effects.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = Path(
    r"C:\Users\15550\AppData\Local\Temp\dm_ck3_clean_userdir\logs\error.log"
)
TITLE_OUT = ROOT / "common/landed_titles/zz_dm_compat_missing_titles.txt"
COA_OUT = (
    ROOT
    / "common/coat_of_arms/coat_of_arms/zz_dm_compat_missing_title_coa.txt"
)

MISSING_RE = re.compile(
    r"Failed to fetch a valid landed title '([ekdcbh]_[A-Za-z0-9_-]+)'.*?"
    r"file: ([^']+?) line:"
)
DEFINED_RE = re.compile(
    r"(?m)^[ \t]*([ekdcbh]_[A-Za-z0-9_-]+)[ \t]*=[ \t]*\{"
)
COLORS = ("blue", "red", "green", "yellow", "black", "white", "purple")
MASKED_SOURCES = {
    "common/achievements/ep3_achievements.txt",
    "common/achievements/fp1_achievements.txt",
    "common/achievements/fp2_achievements.txt",
    "common/decisions/00_major_decisions_east_europe.txt",
    "common/decisions/00_major_decisions_iberia_north_africa.txt",
    "common/decisions/80_major_decisions_british_isles.txt",
    "common/decisions/80_major_decisions_middle_europe.txt",
    "common/decisions/80_major_decisions_roman.txt",
    "common/decisions/dlc_decisions/03_fp2_decisions.txt",
    "common/decisions/dlc_decisions/ep3_decisions.txt",
    "common/decisions/dlc_decisions/fp_1/00_fp1_major_decisions.txt",
    "common/decisions/dlc_decisions/fp_1/00_fp1_other_decisions.txt",
}


def deterministic_rgb(key: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(key.encode("ascii")).digest()
    return tuple(48 + byte % 160 for byte in digest[:3])


def deterministic_coa_colors(key: str) -> tuple[str, str]:
    digest = hashlib.sha256(("coa:" + key).encode("ascii")).digest()
    first = COLORS[digest[0] % len(COLORS)]
    second = COLORS[digest[1] % len(COLORS)]
    if second == first:
        second = COLORS[(COLORS.index(first) + 1) % len(COLORS)]
    return first, second


def read_defined_titles() -> set[str]:
    result: set[str] = set()
    for path in (ROOT / "common/landed_titles").glob("*.txt"):
        if path in {TITLE_OUT}:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        result.update(DEFINED_RE.findall(text))
    return result


def main() -> None:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    log_text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    sources_by_key: dict[str, set[str]] = {}
    for key, source in MISSING_RE.findall(log_text):
        sources_by_key.setdefault(key, set()).add(source.replace("\\", "/"))
    missing = {
        key
        for key, sources in sources_by_key.items()
        if key[0] in {"e", "k", "d", "h"}
        and any(source not in MASKED_SOURCES for source in sources)
    }
    masked_only = set(sources_by_key) - missing
    defined = read_defined_titles()
    shells = sorted(missing - defined)

    title_lines = [
        "# Generated inert compatibility shells for vanilla title references.",
        "# No provinces, de-jure structure, holders, history, or map content.",
        "",
    ]
    coa_lines = [
        "# Generated pre-scripted CoAs for inert compatibility title shells.",
        "",
    ]

    for key in shells:
        red, green, blue = deterministic_rgb(key)
        title_lines.extend(
            [
                f"{key} = {{",
                f"\tcolor = {{ {red} {green} {blue} }}",
                "\tlandless = yes",
                "\tcapital = c_zhu3",
                "\tallow_domicile = no",
                "\tno_automatic_claims = yes",
                "\tde_jure_drift_disabled = yes",
                "\tcan_use_nomadic_naming = no",
                "\tcan_be_named_after_dynasty = no",
                "\tdefinite_form = yes",
                "\truler_uses_title_name = no",
                "}",
                "",
            ]
        )
        color1, color2 = deterministic_coa_colors(key)
        coa_lines.extend(
            [
                f"{key} = {{",
                '\tpattern = "pattern_solid.dds"',
                f'\tcolor1 = "{color1}"',
                f'\tcolor2 = "{color2}"',
                "}",
                "",
            ]
        )

    TITLE_OUT.write_text(
        "\n".join(title_lines), encoding="utf-8-sig", newline="\n"
    )
    COA_OUT.write_text(
        "\n".join(coa_lines), encoding="utf-8-sig", newline="\n"
    )
    print(
        f"log_missing={len(sources_by_key)} masked_only={len(masked_only)} "
        f"remaining={len(missing)} existing={len(missing & defined)}"
    )
    print(f"generated_shells={len(shells)}")
    print(TITLE_OUT)
    print(COA_OUT)


if __name__ == "__main__":
    main()
