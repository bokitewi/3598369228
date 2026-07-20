#!/usr/bin/env python3
"""Remove undefined external-mod building keys from holding allow-lists."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDING_DIR = ROOT / "common" / "buildings"
HOLDINGS = ROOT / "common" / "holdings" / "00_holdings.txt"


def main() -> None:
	defined: set[str] = set()
	for path in BUILDING_DIR.glob("*.txt"):
		text = path.read_text(encoding="utf-8-sig", errors="replace")
		defined.update(
			re.findall(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{", text)
		)

	lines = HOLDINGS.read_text(encoding="utf-8-sig").splitlines()
	output: list[str] = []
	in_buildings = False
	depth = 0
	removed: Counter[str] = Counter()
	for line in lines:
		stripped = line.strip()
		if not in_buildings and re.match(r"^buildings\s*=\s*\{$", stripped):
			in_buildings = True
			depth = 1
			output.append(line)
			continue
		if in_buildings:
			depth += line.count("{") - line.count("}")
			match = re.match(r"^([A-Za-z0-9_]+)(?:\s*#.*)?$", stripped)
			if match and match.group(1) not in defined:
				removed[match.group(1)] += 1
				if depth <= 0:
					in_buildings = False
				continue
			output.append(line)
			if depth <= 0:
				in_buildings = False
			continue
		output.append(line)
	HOLDINGS.write_text("\n".join(output) + "\n", encoding="utf-8-sig")
	print(
		f"Defined building keys: {len(defined)}; removed references: "
		f"{sum(removed.values())} ({len(removed)} unique)"
	)
	for key, count in removed.most_common():
		print(f"{count:2} {key}")


if __name__ == "__main__":
	main()
