"""Remove unnamed one-pixel province noise from the CK3 province map.

The repair is deliberately narrow:

* only unnamed definition rows at or above province 4759 are considered;
* only colors occurring exactly once in provinces.png are removed;
* the pixel is replaced by the most common valid color in its 8-neighborhood;
* ties are resolved by province ID so the result is deterministic;
* the matching definition.csv row is removed.
"""

from __future__ import annotations

import csv
import os
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = ROOT / "map_data" / "definition.csv"
PROVINCES_PATH = ROOT / "map_data" / "provinces.png"
FIRST_UNNAMED_ID = 4759


def pack_color(rgb: tuple[int, int, int]) -> int:
	return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def unpack_color(code: int) -> tuple[int, int, int]:
	return ((code >> 16) & 255, (code >> 8) & 255, code & 255)


def main() -> None:
	with DEFINITION_PATH.open("r", encoding="utf-8", newline="") as stream:
		rows = list(csv.reader(stream, delimiter=";"))

	color_to_id: dict[int, int] = {}
	unnamed_codes: dict[int, int] = {}
	for row in rows:
		if len(row) < 5 or not row[0].isdigit():
			continue
		province_id = int(row[0])
		code = pack_color((int(row[1]), int(row[2]), int(row[3])))
		if code in color_to_id and code != 0:
			raise RuntimeError(
				f"Duplicate non-black definition color for provinces "
				f"{color_to_id[code]} and {province_id}"
			)
		color_to_id[code] = province_id
		if province_id >= FIRST_UNNAMED_ID and not row[4].strip():
			unnamed_codes[province_id] = code

	image = Image.open(PROVINCES_PATH).convert("RGB")
	pixels = np.array(image, dtype=np.uint8)
	codes = (
		(pixels[..., 0].astype(np.uint32) << 16)
		| (pixels[..., 1].astype(np.uint32) << 8)
		| pixels[..., 2].astype(np.uint32)
	)
	unique, counts = np.unique(codes, return_counts=True)
	color_counts = {int(code): int(count) for code, count in zip(unique, counts)}

	targets = {
		province_id: code
		for province_id, code in unnamed_codes.items()
		if color_counts.get(code, 0) == 1
	}
	if not targets:
		print("No unnamed one-pixel provinces found.")
		return

	normal_codes = {
		code
		for code, province_id in color_to_id.items()
		if province_id < FIRST_UNNAMED_ID
	}
	target_code_to_id = {code: province_id for province_id, code in targets.items()}
	target_mask = np.isin(codes, np.fromiter(target_code_to_id, dtype=np.uint32))
	ys, xs = np.where(target_mask)
	if len(ys) != len(targets):
		raise RuntimeError(
			f"Expected {len(targets)} target pixels but found {len(ys)}"
		)

	replacements: list[tuple[int, int, int, int]] = []
	for y, x in zip(ys, xs):
		code = int(codes[y, x])
		province_id = target_code_to_id[code]
		y0 = max(0, int(y) - 1)
		y1 = min(codes.shape[0], int(y) + 2)
		x0 = max(0, int(x) - 1)
		x1 = min(codes.shape[1], int(x) + 2)
		neighbors = Counter(
			int(value)
			for value in codes[y0:y1, x0:x1].ravel()
			if int(value) in normal_codes
		)
		if not neighbors:
			raise RuntimeError(
				f"Province {province_id} has no valid color in its 8-neighborhood"
			)
		best_count = max(neighbors.values())
		best_codes = [
			value for value, count in neighbors.items() if count == best_count
		]
		replacement = min(best_codes, key=lambda value: color_to_id[value])
		pixels[y, x] = unpack_color(replacement)
		replacements.append(
			(province_id, color_to_id[replacement], int(x), int(y))
		)

	target_ids = set(targets)
	new_rows = [
		row
		for row in rows
		if not (row and row[0].isdigit() and int(row[0]) in target_ids)
	]

	image_tmp = PROVINCES_PATH.with_suffix(".png.dm_tmp")
	definition_tmp = DEFINITION_PATH.with_suffix(".csv.dm_tmp")
	Image.fromarray(pixels, mode="RGB").save(image_tmp, format="PNG")
	with definition_tmp.open("w", encoding="utf-8", newline="") as stream:
		writer = csv.writer(stream, delimiter=";", lineterminator="\n")
		writer.writerows(new_rows)
	os.replace(image_tmp, PROVINCES_PATH)
	os.replace(definition_tmp, DEFINITION_PATH)

	for province_id, replacement_id, x, y in sorted(replacements):
		print(
			f"{province_id} -> {replacement_id} at ({x}, {y})"
		)
	print(f"Removed {len(replacements)} unnamed one-pixel provinces.")


if __name__ == "__main__":
	main()
