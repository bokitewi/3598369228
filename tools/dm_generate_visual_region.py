#!/usr/bin/env python3
"""Generate one graphical region covering every Spring-and-Autumn land province."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "map_data"
TARGET = MAP_DIR / "geographical_regions" / "dm_visual_region.txt"


def expand_ids(text: str, key: str) -> set[int]:
	result: set[int] = set()
	for start, end in re.findall(
		rf"(?m)^\s*{re.escape(key)}\s*=\s*RANGE\s*\{{\s*(\d+)\s+(\d+)\s*\}}",
		text,
	):
		result.update(range(int(start), int(end) + 1))
	for values in re.findall(
		rf"(?m)^\s*{re.escape(key)}\s*=\s*LIST\s*\{{([^}}]*)\}}",
		text,
	):
		result.update(int(value) for value in re.findall(r"\d+", values))
	return result


def main() -> None:
	with (MAP_DIR / "definition.csv").open(
		"r",
		encoding="utf-8-sig",
		newline="",
	) as stream:
		province_ids = {
			int(row[0])
			for row in csv.reader(stream, delimiter=";")
			if row and row[0].isdigit() and int(row[0]) > 0
		}
	default_map = (MAP_DIR / "default.map").read_text(encoding="utf-8-sig")
	non_land: set[int] = set()
	for key in (
		"sea_zones",
		"river_provinces",
		"lakes",
		"impassable_mountains",
	):
		non_land.update(expand_ids(default_map, key))
	land_ids = sorted(province_ids - non_land)
	lines = [
		"# All playable Spring-and-Autumn land provinces use East Asian visuals.",
		"graphical_dm_huaxia = {",
		"\tgraphical = yes",
		"\tcolor = { 155 255 155 }",
		"\tprovinces = {",
	]
	for start in range(0, len(land_ids), 24):
		lines.append(
			"\t\t" + " ".join(str(value) for value in land_ids[start : start + 24])
		)
	lines.extend(("\t}", "}", ""))
	TARGET.parent.mkdir(parents=True, exist_ok=True)
	TARGET.write_text("\n".join(lines), encoding="utf-8-sig")
	print(f"Wrote {TARGET} with {len(land_ids)} land provinces")


if __name__ == "__main__":
	main()
