#!/usr/bin/env python3
"""Audit tiny and one-pixel province-map components without changing the map."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = ROOT / "map_data" / "definition.csv"
PROVINCES_PATH = ROOT / "map_data" / "provinces.png"
CHUNK_ROWS = 256


def pack_color(rgb: tuple[int, int, int]) -> int:
	return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def main() -> None:
	with DEFINITION_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
		rows = list(csv.reader(stream, delimiter=";"))

	color_to_id: dict[int, int] = {}
	id_to_name: dict[int, str] = {}
	for row in rows:
		if len(row) < 4 or not row[0].isdigit():
			continue
		province_id = int(row[0])
		code = pack_color((int(row[1]), int(row[2]), int(row[3])))
		color_to_id[code] = province_id
		id_to_name[province_id] = row[4].strip() if len(row) > 4 else ""

	pixels = np.asarray(Image.open(PROVINCES_PATH).convert("RGB"), dtype=np.uint8)
	codes = (
		(pixels[..., 0].astype(np.uint32) << 16)
		| (pixels[..., 1].astype(np.uint32) << 8)
		| pixels[..., 2].astype(np.uint32)
	)
	unique, counts = np.unique(codes, return_counts=True)
	total_counts = {
		int(code): int(count)
		for code, count in zip(unique, counts, strict=True)
	}

	singletons: Counter[int] = Counter()
	first_coordinate: dict[int, tuple[int, int]] = {}
	height, width = codes.shape
	for y0 in range(0, height, CHUNK_ROWS):
		y1 = min(height, y0 + CHUNK_ROWS)
		block = codes[y0:y1]
		same = np.zeros(block.shape, dtype=bool)
		if y0 > 0:
			same |= block == codes[y0 - 1 : y1 - 1]
		if y1 < height:
			same |= block == codes[y0 + 1 : y1 + 1]
		same[:, 1:] |= block[:, 1:] == block[:, :-1]
		same[:, :-1] |= block[:, :-1] == block[:, 1:]
		isolated = ~same
		isolated_codes = block[isolated]
		if isolated_codes.size == 0:
			continue
		part_codes, part_counts = np.unique(isolated_codes, return_counts=True)
		for code, count in zip(part_codes, part_counts, strict=True):
			singletons[int(code)] += int(count)
		for local_y, x in zip(*np.where(isolated), strict=True):
			code = int(block[local_y, x])
			first_coordinate.setdefault(code, (int(x), y0 + int(local_y)))

	print(f"Image: {width}x{height}; definition colors: {len(color_to_id)}")
	unknown = [
		(code, count)
		for code, count in total_counts.items()
		if code not in color_to_id
	]
	print(f"Unknown colors: {len(unknown)} ({sum(count for _, count in unknown)} pixels)")

	tiny = sorted(
		(
			total_counts.get(code, 0),
			province_id,
			id_to_name.get(province_id, ""),
			singletons.get(code, 0),
		)
		for code, province_id in color_to_id.items()
		if total_counts.get(code, 0) <= 16
	)
	print(f"Province colors with <=16 total pixels: {len(tiny)}")
	for total, province_id, name, isolated_count in tiny:
		print(
			f"TINY id={province_id} total={total} isolated={isolated_count} "
			f"name={name!r}"
		)

	isolated_rows = sorted(
		(
			count,
			total_counts.get(code, 0),
			color_to_id.get(code),
			id_to_name.get(color_to_id.get(code, -1), ""),
			first_coordinate[code],
			code,
		)
		for code, count in singletons.items()
	)
	print(f"Colors with isolated 4-neighbor singleton components: {len(isolated_rows)}")
	print(f"Total isolated pixels: {sum(singletons.values())}")
	for count, total, province_id, name, coordinate, code in isolated_rows:
		print(
			f"SINGLETONS count={count} total={total} id={province_id} "
			f"name={name!r} first={coordinate} color=0x{code:06X}"
		)


if __name__ == "__main__":
	main()
