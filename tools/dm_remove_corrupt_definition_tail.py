"""Remove the corrupt unnamed province-definition tail from the CK3 map.

Province definitions 0..4758 are the authored map. Rows 4759 and above are
unnamed image-noise colors appended by an editor. CK3 requires definition IDs
to be contiguous, so deleting only some of those rows is invalid. This repair:

* keeps every authored definition from 0 through 4758 unchanged;
* merges every remaining non-black tail pixel into a bordering authored color;
* resolves larger tail regions by nearest-border propagation;
* removes every definition row at or above 4759;
* verifies that the resulting IDs are exactly 0..4758.
"""

from __future__ import annotations

import csv
import heapq
import os
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = ROOT / "map_data" / "definition.csv"
PROVINCES_PATH = ROOT / "map_data" / "provinces.png"
FIRST_CORRUPT_ID = 4759


def pack_color(rgb: tuple[int, int, int]) -> int:
	return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def unpack_color(code: int) -> tuple[int, int, int]:
	return ((code >> 16) & 255, (code >> 8) & 255, code & 255)


def main() -> None:
	with DEFINITION_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
		rows = list(csv.reader(stream, delimiter=";"))

	color_to_id: dict[int, int] = {}
	tail_codes: dict[int, int] = {}
	kept_rows: list[list[str]] = []
	kept_ids: list[int] = []
	for row in rows:
		if not row or not row[0].isdigit():
			kept_rows.append(row)
			continue
		province_id = int(row[0])
		code = pack_color((int(row[1]), int(row[2]), int(row[3])))
		if province_id < FIRST_CORRUPT_ID:
			kept_rows.append(row)
			kept_ids.append(province_id)
			if code in color_to_id and code != 0:
				raise RuntimeError(
					f"Duplicate authored color for provinces "
					f"{color_to_id[code]} and {province_id}"
				)
			color_to_id[code] = province_id
		else:
			tail_codes[province_id] = code

	expected_ids = list(range(FIRST_CORRUPT_ID))
	if kept_ids != expected_ids:
		raise RuntimeError(
			"Authored definition IDs are not exactly 0..4758; refusing repair"
		)
	if not tail_codes:
		print("No corrupt definition tail found.")
		return

	image = Image.open(PROVINCES_PATH).convert("RGB")
	pixels = np.array(image, dtype=np.uint8)
	codes = (
		(pixels[..., 0].astype(np.uint32) << 16)
		| (pixels[..., 1].astype(np.uint32) << 8)
		| pixels[..., 2].astype(np.uint32)
	)

	# Black is already the authored province-0 color, so the duplicate black
	# tail row has no uniquely attributable pixels and requires no image edit.
	target_codes = {code for code in tail_codes.values() if code != 0}
	target_mask = np.isin(codes, np.fromiter(target_codes, dtype=np.uint32))
	target_y, target_x = np.where(target_mask)
	target_pixels = {
		(int(y), int(x)) for y, x in zip(target_y.tolist(), target_x.tolist())
	}

	height, width = codes.shape
	valid_codes = set(color_to_id)
	valid_codes.discard(0)
	best: dict[tuple[int, int], tuple[int, int]] = {}
	queue: list[tuple[int, int, int, int]] = []

	# Border target pixels receive the locally dominant authored neighbor.
	# The province ID is included in the ordering to make ties deterministic.
	for y, x in target_pixels:
		neighbors = Counter()
		for dy in (-1, 0, 1):
			for dx in (-1, 0, 1):
				if dx == 0 and dy == 0:
					continue
				ny = y + dy
				nx = x + dx
				if 0 <= ny < height and 0 <= nx < width:
					code = int(codes[ny, nx])
					if code in valid_codes:
						neighbors[code] += 1
		if not neighbors:
			continue
		max_count = max(neighbors.values())
		replacement = min(
			(code for code, count in neighbors.items() if count == max_count),
			key=lambda code: color_to_id[code],
		)
		province_id = color_to_id[replacement]
		best[(y, x)] = (0, province_id)
		heapq.heappush(queue, (0, province_id, y, x))

	if target_pixels and not queue:
		raise RuntimeError("Corrupt tail pixels have no authored border colors")

	# Partition every larger corrupt block by distance from its authored
	# borders. This avoids replacing a long strip with one arbitrary province.
	while queue:
		distance, province_id, y, x = heapq.heappop(queue)
		if best.get((y, x)) != (distance, province_id):
			continue
		for dy, dx in ((-1, 0), (0, -1), (0, 1), (1, 0)):
			neighbor = (y + dy, x + dx)
			if neighbor not in target_pixels:
				continue
			candidate = (distance + 1, province_id)
			if neighbor not in best or candidate < best[neighbor]:
				best[neighbor] = candidate
				heapq.heappush(
					queue,
					(candidate[0], candidate[1], neighbor[0], neighbor[1]),
				)

	unresolved = target_pixels.difference(best)
	if unresolved:
		raise RuntimeError(
			f"{len(unresolved)} corrupt pixels could not reach an authored border"
		)

	for (y, x), (_, province_id) in best.items():
		replacement_code = next(
			code for code, candidate_id in color_to_id.items()
			if candidate_id == province_id
		)
		pixels[y, x] = unpack_color(replacement_code)

	image_tmp = PROVINCES_PATH.with_suffix(".png.dm_tmp")
	definition_tmp = DEFINITION_PATH.with_suffix(".csv.dm_tmp")
	Image.fromarray(pixels, mode="RGB").save(image_tmp, format="PNG")
	with definition_tmp.open("w", encoding="utf-8", newline="") as stream:
		writer = csv.writer(stream, delimiter=";", lineterminator="\n")
		writer.writerows(kept_rows)
	os.replace(image_tmp, PROVINCES_PATH)
	os.replace(definition_tmp, DEFINITION_PATH)

	counts = Counter(province_id for _, province_id in best.values())
	print(
		f"Removed {len(tail_codes)} corrupt definition rows and merged "
		f"{len(best)} pixels into {len(counts)} authored provinces."
	)
	for province_id, count in sorted(counts.items()):
		print(f"  province {province_id}: +{count} pixels")


if __name__ == "__main__":
	main()
