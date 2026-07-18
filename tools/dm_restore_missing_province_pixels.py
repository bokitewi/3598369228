#!/usr/bin/env python3
"""Restore zero-pixel province definitions around their original map locators."""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = ROOT / "map_data" / "definition.csv"
PROVINCES_PATH = ROOT / "map_data" / "provinces.png"
LOCATORS_PATH = ROOT / "gfx/map/map_object_data/siege_locators.txt"

LAND_IDS = {1290, 1435, 3396, 3397, 3787, 3959, 4244}
MOUNTAIN_IDS = {
	2422,
	2423,
	2424,
	2425,
	2426,
	2427,
	2428,
	2429,
	2430,
	2668,
	2669,
	2670,
}
SEA_IDS = {4559, 4584, 4592, 4638, 4661, 4723, 4729, 4730}
TARGET_IDS = LAND_IDS | MOUNTAIN_IDS | SEA_IDS
RESET_HOST_ID = {
	1290: 589,
	1435: 589,
	2422: 589,
	2423: 589,
	2424: 589,
	2425: 589,
	2426: 589,
	2427: 589,
	2428: 589,
	2429: 589,
	2430: 589,
	2668: 0,
	2669: 0,
	2670: 0,
	3396: 4628,
	3397: 4630,
	3787: 4595,
	3959: 4594,
	4244: 589,
	4559: 589,
	4584: 589,
	4592: 589,
	4638: 589,
	4661: 589,
	4723: 589,
	4729: 589,
	4730: 589,
}
RADIUS_BY_TYPE = {
	"land": 14,
	"mountain": 9,
	"sea": 24,
}


def pack_color(rgb: tuple[int, int, int]) -> int:
	return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def unpack_color(code: int) -> tuple[int, int, int]:
	return ((code >> 16) & 255, (code >> 8) & 255, code & 255)


def province_type(province_id: int) -> str:
	if province_id in LAND_IDS:
		return "land"
	if province_id in MOUNTAIN_IDS:
		return "mountain"
	return "sea"


def main() -> None:
	with DEFINITION_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
		rows = list(csv.reader(stream, delimiter=";"))
	id_to_code = {
		int(row[0]): pack_color((int(row[1]), int(row[2]), int(row[3])))
		for row in rows
		if len(row) >= 4 and row[0].isdigit()
	}

	locator_text = LOCATORS_PATH.read_text(encoding="utf-8-sig")
	locators = {
		int(province_id): (round(float(x)), round(float(y)))
		for province_id, x, y in re.findall(
			r"id=(\d+)\s+position=\{\s*([\d.]+)\s+[\d.-]+\s+([\d.]+)",
			locator_text,
		)
	}

	image = Image.open(PROVINCES_PATH).convert("RGB")
	pixels = np.array(image, dtype=np.uint8)
	codes = (
		(pixels[..., 0].astype(np.uint32) << 16)
		| (pixels[..., 1].astype(np.uint32) << 8)
		| pixels[..., 2].astype(np.uint32)
	)

	# Undo this tool's earlier direct-Z placement before rebuilding with CK3's
	# bottom-up map coordinate convention. This also makes reruns deterministic.
	for province_id in sorted(TARGET_IDS):
		target_mask = codes == id_to_code[province_id]
		if not np.any(target_mask):
			continue
		host_code = id_to_code[RESET_HOST_ID[province_id]]
		pixels[target_mask] = unpack_color(host_code)
		codes[target_mask] = host_code

	unique, counts = np.unique(codes, return_counts=True)
	count_by_code = {
		int(code): int(count)
		for code, count in zip(unique, counts, strict=True)
	}

	missing = [
		province_id
		for province_id in sorted(TARGET_IDS)
		if count_by_code.get(id_to_code[province_id], 0) == 0
	]
	if not missing:
		print("All targeted provinces already have pixels.")
		return
	if set(missing) != TARGET_IDS:
		remaining = sorted(TARGET_IDS - set(missing))
		raise RuntimeError(
			f"Refusing a partial restore; already present target IDs: {remaining}"
		)

	assignments: dict[tuple[int, int], tuple[int, int]] = {}
	host_by_id: dict[int, int] = {}
	height, width = codes.shape
	for province_id in missing:
		if province_id not in locators:
			raise RuntimeError(f"Missing siege locator for province {province_id}")
		center_x, locator_z = locators[province_id]
		center_y = height - locator_z
		if not (0 <= center_x < width and 0 <= center_y < height):
			raise RuntimeError(
				f"Locator outside map for province {province_id}: "
				f"({center_x}, {locator_z})"
			)
		host_code = int(codes[center_y, center_x])
		host_by_id[province_id] = host_code
		radius = RADIUS_BY_TYPE[province_type(province_id)]
		for y in range(max(0, center_y - radius), min(height, center_y + radius + 1)):
			for x in range(max(0, center_x - radius), min(width, center_x + radius + 1)):
				distance_squared = (x - center_x) ** 2 + (y - center_y) ** 2
				if distance_squared > radius**2:
					continue
				if int(codes[y, x]) != host_code:
					continue
				current = assignments.get((y, x))
				candidate = (distance_squared, province_id)
				if current is None or candidate < current:
					assignments[(y, x)] = candidate

	painted_counts = {province_id: 0 for province_id in missing}
	for (y, x), (_, province_id) in assignments.items():
		pixels[y, x] = unpack_color(id_to_code[province_id])
		painted_counts[province_id] += 1

	too_small = {
		province_id: count
		for province_id, count in painted_counts.items()
		if count < 100
	}
	if too_small:
		raise RuntimeError(f"Restored provinces would be too small: {too_small}")

	tmp_path = PROVINCES_PATH.with_suffix(".png.dm_tmp")
	Image.fromarray(pixels, mode="RGB").save(tmp_path, format="PNG")
	os.replace(tmp_path, PROVINCES_PATH)

	code_to_id = {code: province_id for province_id, code in id_to_code.items()}
	for province_id in missing:
		print(
			f"{province_id}: type={province_type(province_id)} "
			f"locator={locators[province_id]} "
			f"pixel_center=({locators[province_id][0]}, "
			f"{height - locators[province_id][1]}) "
			f"host={code_to_id[host_by_id[province_id]]} "
			f"pixels={painted_counts[province_id]}"
		)
	print(f"Restored {len(missing)} zero-pixel provinces.")


if __name__ == "__main__":
	main()
