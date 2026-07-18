#!/usr/bin/env python3
"""Repair obsolete dynasty cultures and generate CoAs for founderless families."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DYNASTIES = ROOT / "common" / "dynasties" / "00_baijia.txt"
HOUSES = (
	ROOT
	/ "common"
	/ "dynasty_houses"
	/ "00_baijia_dynasty_houses.txt"
)
COA_DIR = ROOT / "common" / "coat_of_arms" / "coat_of_arms"
TARGET = COA_DIR / "zz_dm_compat_generated_house_coa.txt"
COLORS = (
	"red",
	"blue",
	"yellow",
	"green",
	"black",
	"white",
	"orange",
	"purple",
)


def main() -> None:
	dynasty_text = DYNASTIES.read_text(encoding="utf-8-sig")
	mappings = {
		"ji": "zhou",
		"feng": "shennongshi",
		"diren": "beidi",
	}
	counts: dict[str, int] = {}
	for obsolete, current in mappings.items():
		old = f'culture = "{obsolete}"'
		counts[obsolete] = dynasty_text.count(old)
		dynasty_text = dynasty_text.replace(old, f'culture = "{current}"')
	DYNASTIES.write_text(dynasty_text, encoding="utf-8-sig")

	house_text = HOUSES.read_text(encoding="utf-8-sig")
	house_keys = set(
		re.findall(r"(?m)^(house_(?:baijia|xin)\d+)\s*=\s*\{", house_text)
	)
	dynasty_keys = set(
		re.findall(r"(?m)^((?:baijia|xin)\d+)\s*=\s*\{", dynasty_text)
	)
	family_keys = house_keys | dynasty_keys
	existing_keys: set[str] = set()
	for path in COA_DIR.glob("*.txt"):
		if path == TARGET:
			continue
		text = path.read_text(encoding="utf-8-sig", errors="replace")
		existing_keys.update(
			re.findall(
				r"(?m)^((?:house_)?(?:baijia|xin)\d+)\s*=\s*\{",
				text,
			)
		)
	missing = sorted(family_keys - existing_keys)

	lines = [
		"# Generated compatibility CoAs for scripted dynasties and houses.",
		"# Keeps family keys intact and prevents founderless CoA generation.",
		"",
	]
	for key in missing:
		digest = hashlib.sha256(key.encode("ascii")).digest()
		first = COLORS[digest[0] % len(COLORS)]
		second = COLORS[digest[1] % len(COLORS)]
		if second == first:
			second = COLORS[(COLORS.index(first) + 1) % len(COLORS)]
		lines.extend(
			(
				f"{key} = {{",
				'\tpattern = "pattern_solid.dds"',
				f'\tcolor1 = "{first}"',
				f'\tcolor2 = "{second}"',
				"}",
				"",
			)
		)
	TARGET.write_text("\n".join(lines), encoding="utf-8-sig")
	print(
		"Repaired obsolete dynasty cultures: "
		+ ", ".join(f"{key}={value}" for key, value in counts.items())
	)
	print(f"Wrote {TARGET} with {len(missing)} compatibility CoAs")


if __name__ == "__main__":
	main()
