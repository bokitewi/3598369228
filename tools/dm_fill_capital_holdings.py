"""Give logged county-capital baronies the minimum legal vanilla holding.

CK3 automatically gives a county holder its capital barony.  A capital whose
province history says ``holding = none`` then becomes an illegal held barony.
This tool consumes the engine's exact history errors and changes only those
reported capital provinces to ``castle_holding``.
"""

from __future__ import annotations

import argparse
import codecs
import os
import re
from collections import defaultdict
from pathlib import Path

from dm_generate_history_compat import ROOT, load_title_tree, strip_comments


PROVINCE_RE = re.compile(r"^\s*(\d+)\s*=\s*\{")
HOLDING_RE = re.compile(r"^(\s*)holding\s*=\s*([A-Za-z0-9_]+)(.*)$")
NO_HOLDING_RE = re.compile(
	r"Barony (b_[A-Za-z0-9_]+) does not have a holding"
)


def line_brace_delta(line: str) -> int:
	clean = strip_comments(line)
	clean = re.sub(r'"(?:\\.|[^"])*"', '""', clean)
	return clean.count("{") - clean.count("}")


def locate_province_blocks(
	lines: list[str],
) -> dict[int, tuple[int, int]]:
	result: dict[int, tuple[int, int]] = {}
	depth = 0
	index = 0
	while index < len(lines):
		match = PROVINCE_RE.match(strip_comments(lines[index])) if depth == 0 else None
		if not match:
			depth += line_brace_delta(lines[index])
			index += 1
			continue
		start = index
		block_depth = line_brace_delta(lines[index])
		while block_depth > 0:
			index += 1
			if index >= len(lines):
				raise RuntimeError(f"Unclosed province block at line {start + 1}")
			block_depth += line_brace_delta(lines[index])
		result[int(match.group(1))] = (start, index)
		index += 1
	return result


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--error-log", required=True, type=Path)
	args = parser.parse_args()

	_, _, _, barony_province, _ = load_title_tree()
	log_text = args.error_log.read_text(encoding="utf-8-sig", errors="replace")
	baronies = set(NO_HOLDING_RE.findall(log_text))
	unknown = sorted(baronies - set(barony_province))
	if unknown:
		raise RuntimeError(f"Unknown logged baronies: {unknown[:20]}")
	target_provinces = {barony_province[barony] for barony in baronies}

	by_file: dict[Path, set[int]] = defaultdict(set)
	all_blocks: dict[int, Path] = {}
	file_cache: dict[Path, tuple[bool, str, list[str]]] = {}
	for path in sorted((ROOT / "history" / "provinces").glob("*.txt")):
		raw = path.read_bytes()
		has_bom = raw.startswith(codecs.BOM_UTF8)
		payload = raw[len(codecs.BOM_UTF8) :] if has_bom else raw
		text = payload.decode("utf-8", errors="strict")
		newline = "\r\n" if "\r\n" in text else "\n"
		lines = text.splitlines()
		file_cache[path] = (has_bom, newline, lines)
		for province_id in locate_province_blocks(lines):
			if province_id in all_blocks:
				raise RuntimeError(
					f"Duplicate province history block {province_id}: "
					f"{all_blocks[province_id]} and {path}"
				)
			all_blocks[province_id] = path

	missing_blocks = sorted(target_provinces - set(all_blocks))
	if missing_blocks:
		raise RuntimeError(
			"Logged capital provinces lack history blocks: "
			f"{missing_blocks[:30]}"
		)
	for province_id in target_provinces:
		by_file[all_blocks[province_id]].add(province_id)

	replaced_none = 0
	inserted_missing = 0
	already_legal = 0
	for path, targets in by_file.items():
		has_bom, newline, lines = file_cache[path]
		blocks = locate_province_blocks(lines)
		for province_id in sorted(targets, reverse=True):
			start, end = blocks[province_id]
			depth = 1
			holding_line: int | None = None
			holding_value: str | None = None
			for line_index in range(start + 1, end):
				match = HOLDING_RE.match(strip_comments(lines[line_index]))
				if depth == 1 and match:
					holding_line = line_index
					holding_value = match.group(2)
					break
				depth += line_brace_delta(lines[line_index])
			if holding_line is None:
				indent = re.match(r"^(\s*)", lines[start]).group(1) + "\t"
				lines.insert(start + 1, f"{indent}holding = castle_holding")
				inserted_missing += 1
			elif holding_value == "none":
				match = HOLDING_RE.match(lines[holding_line])
				assert match is not None
				lines[holding_line] = (
					f"{match.group(1)}holding = castle_holding{match.group(3)}"
				)
				replaced_none += 1
			else:
				already_legal += 1

		payload = (newline.join(lines) + newline).encode("utf-8")
		temp = path.with_suffix(path.suffix + ".dm_tmp")
		temp.write_bytes(codecs.BOM_UTF8 + payload)
		os.replace(temp, path)

	print(f"Logged capital baronies: {len(baronies)}")
	print(f"Capital holding=none replaced: {replaced_none}")
	print(f"Missing capital holdings inserted: {inserted_missing}")
	print(f"Already legal holdings left unchanged: {already_legal}")


if __name__ == "__main__":
	main()
