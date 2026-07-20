#!/usr/bin/env python3
"""Generate Simplified Chinese labels for custom Chinese portrait entries.

Tiger derives the concrete PORTRAIT_MODIFIER keys from portrait templates.  This
tool consumes a Tiger JSON report so the generated localization follows the
entries that the current CK3 build actually exposes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "localization"
    / "simp_chinese"
    / "dm_generated_chinese_portraits_l_simp_chinese.yml"
)
KEY_PREFIX = "PORTRAIT_MODIFIER_chinese_"
MESSAGE_PREFIXES = (
    "missing localization key ",
    "missing simp_chinese localization key ",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def extract_keys(report: Path) -> list[str]:
    diagnostics = json.loads(report.read_text(encoding="utf-8-sig"))
    keys: set[str] = set()
    for diagnostic in diagnostics:
        message = diagnostic.get("message", "")
        for prefix in MESSAGE_PREFIXES:
            if message.startswith(prefix):
                key = message.removeprefix(prefix)
                if key.startswith(KEY_PREFIX):
                    keys.add(key)
                break
    return sorted(keys)


def ordinal(number: str) -> str:
    return {
        "01": "一",
        "02": "二",
        "03": "三",
        "04": "四",
        "05": "五",
        "1": "一",
        "2": "二",
        "3": "三",
        "4": "四",
        "5": "五",
        "6": "六",
    }.get(number, number)


def label_for(key: str) -> str:
    if key == "PORTRAIT_MODIFIER_chinese_clothes":
        return "中式服饰"
    if key == "PORTRAIT_MODIFIER_chinese_hair":
        return "中式发型"
    if key == "PORTRAIT_MODIFIER_chinese_headgear":
        return "中式冠帽"
    if key == "PORTRAIT_MODIFIER_chinese_legwear":
        return "中式下装"

    category = next(
        name for name in ("clothes", "hair", "headgear", "legwear") if f"_{name}_" in key
    )
    gender = "女式" if f"_{category}_f_" in key else "男式"
    category_name = {
        "clothes": "服饰",
        "hair": "发式",
        "headgear": "冠帽",
        "legwear": "下装",
    }[category]
    rank_name = ""
    for token, name in (
        ("buddhist_devoted", "佛门"),
        ("taoist_priest", "道门"),
        ("war_nob", "武官"),
        ("hi_nob", "高等贵族"),
        ("_imp_", "帝王"),
        ("_roy_", "王室"),
        ("_nob_", "贵族"),
        ("_com_", "庶民"),
    ):
        if token in key:
            rank_name = name
            break

    suffix = ""
    tail = key.rsplit("_", 1)[-1]
    if category == "hair" and tail in {"01", "02", "03", "04", "05"}:
        suffix = ordinal(tail)
    elif tail.startswith("m") and tail[1:].isdigit():
        suffix = f"·式样{ordinal(tail[1:])}"
    elif tail == "common":
        suffix = "·常服"
    elif tail == "hi":
        suffix = "·高阶"
    elif tail == "lo":
        suffix = "·简式"
    elif tail == "mask":
        suffix = "·覆面"
    elif tail in {"01", "02"}:
        suffix = f"·式样{ordinal(tail)}"

    return f"{gender}{rank_name}{category_name}{suffix}"


def render(keys: list[str]) -> str:
    lines = ["l_simp_chinese:"]
    lines.extend(f' {key}:0 "{label_for(key)}"' for key in keys)
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    content = render(extract_keys(args.input))
    current = OUTPUT.read_text(encoding="utf-8-sig") if OUTPUT.exists() else None
    if args.check:
        if current != content:
            print(f"DRIFT: {OUTPUT.relative_to(ROOT)}")
            return 1
        print(f"portrait localization OK: {content.count(chr(10)) - 1} keys")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8-sig", newline="\n")
    print(f"WROTE: {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
