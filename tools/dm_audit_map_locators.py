#!/usr/bin/env python3
"""Audit province-based map-object locator coverage and placement."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
LOCATOR_DIR = ROOT / "gfx/map/map_object_data"
LOCATOR_FILES = (
	"activities.txt",
	"building_locators.txt",
	"combat_locators.txt",
	"other_stack_locators.txt",
	"player_stack_locators.txt",
	"siege_locators.txt",
)
OBJECT_PATTERN = re.compile(
	r"\{\s*"
	r"id=(\d+)\s*"
	r"position=\{\s*([\d.-]+)\s+[\d.-]+\s+([\d.-]+)\s*\}\s*"
	r"rotation=\{[^}]+\}\s*"
	r"scale=\{[^}]+\}\s*"
	r"\}",
	re.MULTILINE,
)


def pack_color(rgb: tuple[int, int, int]) -> int:
	return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def main() -> None:
	with (ROOT / "map_data/definition.csv").open(
		"r",
		encoding="utf-8-sig",
		newline="",
	) as stream:
		rows = list(csv.reader(stream, delimiter=";"))
	id_to_code = {
		int(row[0]): pack_color((int(row[1]), int(row[2]), int(row[3])))
		for row in rows
		if len(row) >= 4 and row[0].isdigit()
	}
	required_ids = set(id_to_code)

	pixels = np.asarray(
		Image.open(ROOT / "map_data/provinces.png").convert("RGB"),
		dtype=np.uint8,
	)
	codes = (
		(pixels[..., 0].astype(np.uint32) << 16)
		| (pixels[..., 1].astype(np.uint32) << 8)
		| pixels[..., 2].astype(np.uint32)
	)
	height, width = codes.shape

	for filename in LOCATOR_FILES:
		path = LOCATOR_DIR / filename
		text = path.read_text(encoding="utf-8-sig")
		objects = [
			(int(province_id), round(float(x)), round(float(z)))
			for province_id, x, z in OBJECT_PATTERN.findall(text)
		]
		present_ids = {province_id for province_id, _, _ in objects}
		duplicates = len(objects) - len(present_ids)
		missing = sorted(required_ids - present_ids)
		extra = sorted(present_ids - required_ids)
		invalid: list[tuple[int, int, int]] = []
		for province_id, x, z in objects:
			if province_id not in id_to_code:
				continue
			y = height - z
			if not (0 <= x < width and 0 <= y < height):
				invalid.append((province_id, x, z))
				continue
			if int(codes[y, x]) != id_to_code[province_id]:
				invalid.append((province_id, x, z))
		print(
			f"{filename}: objects={len(objects)} duplicate_ids={duplicates} "
			f"missing={len(missing)} extra={len(extra)} invalid={len(invalid)}"
		)
		if missing:
			print(f"  missing sample: {missing[:20]}")
		if extra:
			print(f"  extra sample: {extra[:20]}")
		if invalid:
			print(f"  invalid sample: {invalid[:20]}")


if __name__ == "__main__":
	main()
