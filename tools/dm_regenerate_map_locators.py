#!/usr/bin/env python3
"""Regenerate province-based map-object locators from provinces.png."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = ROOT / "map_data/definition.csv"
PROVINCES_PATH = ROOT / "map_data/provinces.png"
LOCATOR_DIR = ROOT / "gfx/map/map_object_data"
CHUNK_ROWS = 256
HEADERS = {
	"activities.txt": (
		"activities",
		"no",
		"activities_layer",
	),
	"building_locators.txt": (
		"buildings",
		"no",
		"building_layer",
	),
	"combat_locators.txt": (
		"combat",
		"no",
		"unit_layer",
	),
	"other_stack_locators.txt": (
		"unit_stack_other_owner",
		"yes",
		"unit_layer",
	),
	"player_stack_locators.txt": (
		"unit_stack_player_owned",
		"yes",
		"unit_layer",
	),
	"siege_locators.txt": (
		"siege",
		"no",
		"unit_layer",
	),
}


def pack_color(rgb: tuple[int, int, int]) -> int:
	return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def closest_pixel(
	codes: np.ndarray,
	code: int,
	centroid_x: float,
	centroid_y: float,
) -> tuple[int, int]:
	height, width = codes.shape
	center_x = min(width - 1, max(0, round(centroid_x)))
	center_y = min(height - 1, max(0, round(centroid_y)))
	if int(codes[center_y, center_x]) == code:
		candidate_x, candidate_y = center_x, center_y
	else:
		candidate_x = candidate_y = -1
		for radius in (8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192):
			x0 = max(0, center_x - radius)
			x1 = min(width, center_x + radius + 1)
			y0 = max(0, center_y - radius)
			y1 = min(height, center_y + radius + 1)
			local_y, local_x = np.where(codes[y0:y1, x0:x1] == code)
			if local_x.size == 0:
				continue
			absolute_x = local_x + x0
			absolute_y = local_y + y0
			distances = (
				(absolute_x.astype(np.float64) - centroid_x) ** 2
				+ (absolute_y.astype(np.float64) - centroid_y) ** 2
			)
			best = int(np.argmin(distances))
			candidate_x = int(absolute_x[best])
			candidate_y = int(absolute_y[best])
			break
		if candidate_x < 0:
			raise RuntimeError(f"Could not locate province color 0x{code:06X}")

	# Move toward the deepest nearby interior pixel so the transform does not
	# sit on a one-pixel border or coastal corner.
	radius = 32
	x0 = max(0, candidate_x - radius)
	x1 = min(width, candidate_x + radius + 1)
	y0 = max(0, candidate_y - radius)
	y1 = min(height, candidate_y + radius + 1)
	mask = codes[y0:y1, x0:x1] == code
	best_mask = mask
	for _ in range(8):
		eroded = np.zeros_like(best_mask)
		eroded[1:-1, 1:-1] = (
			best_mask[1:-1, 1:-1]
			& best_mask[:-2, 1:-1]
			& best_mask[2:, 1:-1]
			& best_mask[1:-1, :-2]
			& best_mask[1:-1, 2:]
		)
		if not np.any(eroded):
			break
		best_mask = eroded
	local_y, local_x = np.where(best_mask)
	absolute_x = local_x + x0
	absolute_y = local_y + y0
	distances = (
		(absolute_x.astype(np.float64) - centroid_x) ** 2
		+ (absolute_y.astype(np.float64) - centroid_y) ** 2
	)
	best = int(np.argmin(distances))
	return int(absolute_x[best]), int(absolute_y[best])


def render_locator(
	name: str,
	clamp_to_water_level: str,
	layer: str,
	points: dict[int, tuple[int, int]],
	height: int,
) -> str:
	lines = [
		"game_object_locator={",
		f'\tname="{name}"',
		"\trender_pass=Map",
		f"\tclamp_to_water_level={clamp_to_water_level}",
		"\tgenerated_content=no",
		f'\tlayer="{layer}"',
		"\tinstances={",
	]
	for province_id, (x, image_y) in sorted(points.items()):
		locator_z = height - image_y
		lines.extend(
			(
				"\t\t{",
				f"\t\t\tid={province_id}",
				f"\t\t\tposition={{ {x:.6f} 0.000000 {locator_z:.6f} }}",
				"\t\t\trotation={ 0.000000 0.000000 0.000000 1.000000 }",
				"\t\t\tscale={ 1.000000 1.000000 1.000000 }",
				"\t\t}",
			)
		)
	lines.extend(("\t}", "}", ""))
	return "\n".join(lines)


def main() -> None:
	with DEFINITION_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
		rows = list(csv.reader(stream, delimiter=";"))
	id_to_code = {
		int(row[0]): pack_color((int(row[1]), int(row[2]), int(row[3])))
		for row in rows
		if len(row) >= 4 and row[0].isdigit()
	}
	max_id = max(id_to_code)
	if set(id_to_code) != set(range(max_id + 1)):
		raise RuntimeError("Province definition IDs must be contiguous")

	pixels = np.asarray(Image.open(PROVINCES_PATH).convert("RGB"), dtype=np.uint8)
	codes = (
		(pixels[..., 0].astype(np.uint32) << 16)
		| (pixels[..., 1].astype(np.uint32) << 8)
		| pixels[..., 2].astype(np.uint32)
	)
	height, width = codes.shape

	lookup = np.full(1 << 24, max_id + 1, dtype=np.uint16)
	for province_id, code in id_to_code.items():
		lookup[code] = province_id

	counts = np.zeros(max_id + 1, dtype=np.int64)
	sum_x = np.zeros(max_id + 1, dtype=np.float64)
	sum_y = np.zeros(max_id + 1, dtype=np.float64)
	x_values = np.arange(width, dtype=np.float64)
	for y0 in range(0, height, CHUNK_ROWS):
		y1 = min(height, y0 + CHUNK_ROWS)
		province_ids = lookup[codes[y0:y1]]
		if np.any(province_ids > max_id):
			raise RuntimeError("provinces.png contains an undefined color")
		flat_ids = province_ids.ravel()
		counts += np.bincount(flat_ids, minlength=max_id + 1)
		x_weights = np.broadcast_to(
			x_values,
			province_ids.shape,
		).ravel()
		y_weights = np.broadcast_to(
			np.arange(y0, y1, dtype=np.float64)[:, None],
			province_ids.shape,
		).ravel()
		sum_x += np.bincount(
			flat_ids,
			weights=x_weights,
			minlength=max_id + 1,
		)
		sum_y += np.bincount(
			flat_ids,
			weights=y_weights,
			minlength=max_id + 1,
		)

	if np.any(counts == 0):
		raise RuntimeError(
			f"Zero-pixel provinces remain: {np.where(counts == 0)[0].tolist()}"
		)

	points: dict[int, tuple[int, int]] = {}
	for province_id in range(max_id + 1):
		centroid_x = sum_x[province_id] / counts[province_id]
		centroid_y = sum_y[province_id] / counts[province_id]
		points[province_id] = closest_pixel(
			codes,
			id_to_code[province_id],
			centroid_x,
			centroid_y,
		)

	for filename, (name, clamp, layer) in HEADERS.items():
		target = LOCATOR_DIR / filename
		tmp = target.with_suffix(".txt.dm_tmp")
		tmp.write_text(
			render_locator(name, clamp, layer, points, height),
			encoding="utf-8-sig",
		)
		os.replace(tmp, target)
		print(f"Wrote {target}: {len(points)} locators")


if __name__ == "__main__":
	main()
