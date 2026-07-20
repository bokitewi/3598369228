"""Restore province/barony mappings removed from empty county shells.

The canonical title file currently contains hundreds of counties with only a
color. The mod's own adjacent backup retains their authored barony/province
blocks. This script replaces only those empty county blocks; every non-empty
county and all other current title changes remain untouched.
"""

from __future__ import annotations

import codecs
import argparse
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "common" / "landed_titles" / "00_DM_landed_titles.txt"
BACKUP = ROOT / "common" / "landed_titles" / "00_DM_landed_titles.txt.bak"
COUNTY_RE = re.compile(r"^\s*(c_[A-Za-z0-9_]+)\s*=\s*\{")
BARONY_RE = re.compile(r"(?m)^\s*b_[A-Za-z0-9_]+\s*=\s*\{")
PROVINCE_RE = re.compile(r"(?m)^\s*province\s*=\s*(\d+)")


def strip_line(line: str) -> str:
	out: list[str] = []
	quoted = False
	escaped = False
	for char in line:
		if quoted:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
			continue
		if char == '"':
			quoted = True
		elif char == "#":
			break
		else:
			out.append(char)
	return "".join(out)


def block_ranges(lines: list[str]) -> dict[str, tuple[int, int]]:
	result: dict[str, tuple[int, int]] = {}
	for start, line in enumerate(lines):
		match = COUNTY_RE.match(line)
		if not match:
			continue
		depth = 0
		opened = False
		for end in range(start, len(lines)):
			clean = strip_line(lines[end])
			depth += clean.count("{")
			if "{" in clean:
				opened = True
			depth -= clean.count("}")
			if opened and depth == 0:
				result[match.group(1)] = (start, end + 1)
				break
		else:
			raise RuntimeError(f"Unclosed county block {match.group(1)}")
	return result


def decode(path: Path) -> tuple[str, str]:
	raw = path.read_bytes()
	if raw.startswith(codecs.BOM_UTF8):
		raw = raw[len(codecs.BOM_UTF8) :]
	text = raw.decode("utf-8", errors="strict")
	newline = "\r\n" if "\r\n" in text else "\n"
	return text, newline


def replace_blocks(
	current_lines: list[str],
	source_lines: list[str],
	restore: bool,
) -> tuple[list[str], int, set[int]]:
	current_ranges = block_ranges(current_lines)
	source_ranges = block_ranges(source_lines)
	replacements: dict[int, tuple[int, list[str]]] = {}
	provinces: set[int] = set()
	for county, (start, end) in current_ranges.items():
		current_block = "\n".join(current_lines[start:end])
		current_has_baronies = bool(BARONY_RE.search(current_block))
		if county not in source_ranges:
			continue
		source_start, source_end = source_ranges[county]
		source_block_lines = source_lines[source_start:source_end]
		source_block = "\n".join(source_block_lines)
		source_has_baronies = bool(BARONY_RE.search(source_block))
		if restore:
			replace = not current_has_baronies and source_has_baronies
		else:
			replace = current_has_baronies and not source_has_baronies
		if not replace:
			continue
		for value in PROVINCE_RE.findall(
			source_block if restore else current_block
		):
			province_id = int(value)
			if restore and province_id >= 4759:
				raise RuntimeError(
					f"{county} backup references removed province {province_id}"
				)
			provinces.add(province_id)
		replacements[start] = (end, source_block_lines)

	output: list[str] = []
	index = 0
	while index < len(current_lines):
		if index in replacements:
			end, replacement = replacements[index]
			output.extend(replacement)
			index = end
		else:
			output.append(current_lines[index])
			index += 1
	return output, len(replacements), provinces


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--diagnostic-disable",
		action="store_true",
		help="Temporarily return restored counties to their Git-baseline shells.",
	)
	args = parser.parse_args()
	current_text, current_newline = decode(CURRENT)
	current_lines = current_text.splitlines()
	if args.diagnostic_disable:
		source_text = subprocess.check_output(
			[
				"git",
				"show",
				"HEAD:common/landed_titles/00_DM_landed_titles.txt",
			],
			cwd=ROOT,
		).decode("utf-8-sig")
		source_lines = source_text.splitlines()
		output, replacement_count, provinces = replace_blocks(
			current_lines, source_lines, restore=False
		)
	else:
		backup_text, _ = decode(BACKUP)
		source_lines = backup_text.splitlines()
		output, replacement_count, provinces = replace_blocks(
			current_lines, source_lines, restore=True
		)

	if not replacement_count:
		print("No county blocks require this operation.")
		return

	payload = (current_newline.join(output) + current_newline).encode("utf-8")
	temp = CURRENT.with_suffix(CURRENT.suffix + ".dm_tmp")
	temp.write_bytes(codecs.BOM_UTF8 + payload)
	os.replace(temp, CURRENT)
	if args.diagnostic_disable:
		print(
			f"Diagnostic-disabled {replacement_count} restored counties "
			f"covering {len(provinces)} province mappings."
		)
	else:
		print(
			f"Restored {replacement_count} empty counties using "
			f"{len(provinces)} authored province mappings."
		)


if __name__ == "__main__":
	main()
