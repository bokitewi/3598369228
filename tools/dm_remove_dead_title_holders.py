#!/usr/bin/env python3
"""Remove title-holder assignments that predate or postdate the holder's life."""

from __future__ import annotations

import argparse
import codecs
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVALID: dict[str, set[str]] = {
    "history/titles/k_baoguo.txt": {"holder = baosuishi1"},
    "history/titles/k_bingguo.txt": {"holder = zixingbinguo1"},
    "history/titles/k_chenguo.txt": {"holder = han1183"},
    "history/titles/k_daiguo.txt": {"holder = song1276"},
    "history/titles/k_dongguo.txt": {"holder = dongxinghuanlongshi1"},
    "history/titles/k_feiguo.txt": {"holder = luguo6"},
    "history/titles/k_geguo1.txt": {
        "holder = han1389",
        "holder = han1391",
        "holder = han1406",
    },
    "history/titles/k_jiguo3.txt": {"holder = han5880"},
    "history/titles/k_moguo.txt": {"holder = han34"},
    "history/titles/k_pengguo.txt": {"holder = pengzu15"},
    "history/titles/k_weiguo.txt": {"holder = han179", "holder = han184"},
    "history/titles/k_xuguo1.txt": {"holder = han1144"},
    "history/titles/k_xuyanrong.txt": {"holder = xuyanrong6"},
    "history/titles/k_yangguo1.txt": {"holder = han34"},
    "history/titles/k_yiqu.txt": {"holder = han2924"},
    "history/titles/k_zhuguo.txt": {"holder = han851"},
    "history/titles/k_zhuguo1.txt": {"holder = zhuguo2"},
}


def cleaned(path: Path, invalid: set[str]) -> bytes:
    raw = path.read_bytes()
    bom = raw.startswith(codecs.BOM_UTF8)
    text = raw.decode("utf-8-sig")
    kept = [
        line
        for line in text.splitlines(keepends=True)
        if line.strip() not in invalid
    ]
    text = "".join(kept)
    newline = "\r\n" if "\r\n" in text else "\n"
    empty_date = re.compile(
        rf"(?m)^[ \t]*\d+\.\d+\.\d+[ \t]*=[ \t]*\{{[ \t]*{re.escape(newline)}"
        rf"(?:[ \t]*{re.escape(newline)})*"
        rf"^[ \t]*\}}[ \t]*(?:{re.escape(newline)}|$)"
    )
    text = empty_date.sub("", text)
    payload = text.encode("utf-8")
    return (codecs.BOM_UTF8 if bom else b"") + payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    drift: list[str] = []
    for relative, invalid in INVALID.items():
        path = ROOT / relative
        expected = cleaned(path, invalid)
        if expected != path.read_bytes():
            drift.append(relative)
            if not args.check:
                path.write_bytes(expected)
    if drift and args.check:
        print("invalid historical holders remain:")
        for item in drift:
            print(f"  {item}")
        return 1
    if drift:
        print(f"removed invalid holder assignments from {len(drift)} files")
    else:
        print("historical holder cleanup is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
