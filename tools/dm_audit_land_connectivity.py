#!/usr/bin/env python3
"""Audit CK3 land-province graph connectivity and nearest component bridges."""

from __future__ import annotations

import csv
import re
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "map_data"
TARGET_NAMES = {"WEI3", "YANGHU", "QIAN1", "YISHI1", "CHILI"}


class UnionFind:
	def __init__(self, values: set[int]) -> None:
		self.parent = {value: value for value in values}
		self.size = {value: 1 for value in values}

	def find(self, value: int) -> int:
		while self.parent[value] != value:
			self.parent[value] = self.parent[self.parent[value]]
			value = self.parent[value]
		return value

	def union(self, left: int, right: int) -> None:
		a = self.find(left)
		b = self.find(right)
		if a == b:
			return
		if self.size[a] < self.size[b]:
			a, b = b, a
		self.parent[b] = a
		self.size[a] += self.size[b]


def expand_default_map_ids(text: str, key: str) -> set[int]:
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
		rows = list(csv.reader(stream, delimiter=";"))
	id_to_color: dict[int, tuple[int, int, int]] = {}
	id_to_name: dict[int, str] = {}
	color_to_id: dict[int, int] = {}
	for row in rows:
		if len(row) < 5 or not row[0].isdigit():
			continue
		province_id = int(row[0])
		color = (int(row[1]), int(row[2]), int(row[3]))
		id_to_color[province_id] = color
		id_to_name[province_id] = row[4]
		color_to_id[(color[0] << 16) | (color[1] << 8) | color[2]] = province_id

	default_map = (MAP_DIR / "default.map").read_text(encoding="utf-8-sig")
	non_land: set[int] = set()
	for key in (
		"sea_zones",
		"river_provinces",
		"lakes",
		"impassable_mountains",
	):
		non_land.update(expand_default_map_ids(default_map, key))
	non_land.add(0)
	land_ids = set(id_to_color) - non_land
	union = UnionFind(land_ids)

	pixels = np.asarray(
		Image.open(MAP_DIR / "provinces.png").convert("RGB"),
		dtype=np.uint8,
	)
	codes = (
		(pixels[..., 0].astype(np.uint32) << 16)
		| (pixels[..., 1].astype(np.uint32) << 8)
		| pixels[..., 2].astype(np.uint32)
	)
	lookup_size = max(color_to_id) + 1
	code_lookup = np.full(lookup_size, -1, dtype=np.int32)
	for code, province_id in color_to_id.items():
		code_lookup[code] = province_id
	province_pixels = code_lookup[codes]

	all_edges: set[tuple[int, int]] = set()
	for left, right in (
		(province_pixels[:, :-1], province_pixels[:, 1:]),
		(province_pixels[:-1, :], province_pixels[1:, :]),
	):
		different = (left != right) & (left >= 0) & (right >= 0)
		pairs = np.unique(
			np.stack((left[different], right[different]), axis=1),
			axis=0,
		)
		for first, second in pairs:
			a = int(first)
			b = int(second)
			all_edges.add((min(a, b), max(a, b)))
			if a in land_ids and b in land_ids:
				union.union(a, b)

	with (MAP_DIR / "adjacencies.csv").open(
		"r",
		encoding="utf-8-sig",
		newline="",
	) as stream:
		for row in csv.reader(stream, delimiter=";"):
			if len(row) < 3 or not row[0].isdigit() or not row[1].isdigit():
				continue
			first = int(row[0])
			second = int(row[1])
			if first in land_ids and second in land_ids:
				union.union(first, second)

	components: dict[int, set[int]] = defaultdict(set)
	for province_id in land_ids:
		components[union.find(province_id)].add(province_id)
	ordered = sorted(components.values(), key=len, reverse=True)
	province_to_component = {
		province_id: index
		for index, component in enumerate(ordered)
		for province_id in component
	}
	print(
		f"Land provinces: {len(land_ids)}; connected components: {len(ordered)}; "
		f"sizes: {[len(component) for component in ordered[:20]]}"
	)
	name_to_id = {name: province_id for province_id, name in id_to_name.items()}
	for name in sorted(TARGET_NAMES):
		province_id = name_to_id[name]
		print(
			f"TARGET {name}: id={province_id} "
			f"component={province_to_component.get(province_id)}"
		)

	graph: dict[int, set[int]] = defaultdict(set)
	for first, second in all_edges:
		graph[first].add(second)
		graph[second].add(first)
	main_component = ordered[0]
	for index, component in enumerate(ordered[1:], start=1):
		if len(component) > 5:
			continue
		queue = deque(component)
		previous: dict[int, int | None] = {
			province_id: None for province_id in component
		}
		destination: int | None = None
		while queue and destination is None:
			current = queue.popleft()
			for neighbor in graph[current]:
				if neighbor in previous:
					continue
				previous[neighbor] = current
				if neighbor in main_component:
					destination = neighbor
					break
				queue.append(neighbor)
		if destination is None:
			print(f"BRIDGE component={index} size={len(component)} no pixel path")
			continue
		path = [destination]
		while previous[path[-1]] is not None:
			path.append(previous[path[-1]])  # type: ignore[arg-type]
		path.reverse()
		def kind(province_id: int) -> str:
			return "land" if province_id in land_ids else "barrier"
		print(
			f"BRIDGE component={index} size={len(component)} "
			+ " -> ".join(
				f"{province_id}:{id_to_name.get(province_id, '')}[{kind(province_id)}]"
				for province_id in path
			)
			+ " members="
			+ ",".join(
				f"{province_id}:{id_to_name[province_id]}"
				for province_id in sorted(component)
			)
		)


if __name__ == "__main__":
	main()
