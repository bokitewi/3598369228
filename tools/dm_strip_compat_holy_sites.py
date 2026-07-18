#!/usr/bin/env python3
"""Remove map-bearing holy-site links from metadata-only compatibility faiths."""

from __future__ import annotations

import codecs
import re
from pathlib import Path


HOLY_SITE_LINE = re.compile(r"^\s*holy_site\s*=")


def main() -> None:
	mod_root = Path(__file__).resolve().parents[1]
	religion_dir = mod_root / "common" / "religion" / "religion_types"
	total = 0
	changed = 0
	for path in sorted(religion_dir.glob("dm_compat_*.txt")):
		raw = path.read_bytes()
		has_bom = raw.startswith(codecs.BOM_UTF8)
		text = raw.decode("utf-8-sig")
		lines = text.splitlines()
		kept = [line for line in lines if not HOLY_SITE_LINE.match(line)]
		removed = len(lines) - len(kept)
		if not removed:
			continue
		payload = ("\n".join(kept) + "\n").encode("utf-8")
		path.write_bytes(codecs.BOM_UTF8 + payload)
		total += removed
		changed += 1
		print(f"{path.name}: removed {removed}")
	print(f"Removed {total} holy-site links from {changed} compatibility files")


if __name__ == "__main__":
	main()
