#!/usr/bin/env python3
"""Merge every isolated one-pixel map speck into a neighboring color block."""

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
CHUNK_ROWS = 256


def pack_color(rgb: tuple[int, int, int]) -> int:
	return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def unpack_color(code: int) -> tuple[int, int, int]:
	return ((code >> 16) & 255, (code >> 8) & 255, code & 255)


def main() -> None:
	with DEFINITION_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
		rows = list(csv.reader(stream, delimiter=";"))
	color_to_id = {
		pack_color((int(row[1]), int(row[2]), int(row[3]))): int(row[0])
		for row in rows
		if len(row) >= 4 and row[0].isdigit()
	}

	image = Image.open(PROVINCES_PATH).convert("RGB")
	pixels = np.array(image, dtype=np.uint8)
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

	height, _ = codes.shape
	coordinates: list[tuple[int, int]] = []
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
		for local_y, x in zip(*np.where(~same), strict=True):
			coordinates.append((y0 + int(local_y), int(x)))

	changes: Counter[tuple[int, int]] = Counter()
	for y, x in coordinates:
		old_code = int(codes[y, x])
		y0 = max(0, y - 1)
		y1 = min(codes.shape[0], y + 2)
		x0 = max(0, x - 1)
		x1 = min(codes.shape[1], x + 2)
		neighbors = Counter(
			int(code)
			for code in codes[y0:y1, x0:x1].ravel()
			if int(code) != old_code and int(code) in color_to_id
		)
		if not neighbors:
			raise RuntimeError(f"No defined neighboring color at ({x}, {y})")
		best_neighbor_count = max(neighbors.values())
		candidates = [
			code
			for code, count in neighbors.items()
			if count == best_neighbor_count
		]
		new_code = max(
			candidates,
			key=lambda code: (
				total_counts.get(code, 0),
				-color_to_id[code],
			),
		)
		pixels[y, x] = unpack_color(new_code)
		changes[(color_to_id[old_code], color_to_id[new_code])] += 1

	tmp_path = PROVINCES_PATH.with_suffix(".png.dm_tmp")
	Image.fromarray(pixels, mode="RGB").save(tmp_path, format="PNG")
	os.replace(tmp_path, PROVINCES_PATH)

	for (old_id, new_id), count in sorted(changes.items()):
		print(f"{old_id} -> {new_id}: {count} pixel(s)")
	print(f"Merged {len(coordinates)} isolated one-pixel components.")


if __name__ == "__main__":
	main()
