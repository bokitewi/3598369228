"""Remove empty county shells and preserve an auditable migration table.

An empty county has no descendant barony with a province.  Such titles are not
legal landed counties in CK3 1.19.  The migration target is deterministic:

1. the valid capital county of the same duchy;
2. the nearest valid county in source order within the same duchy;
3. the valid capital county of the containing kingdom;
4. the nearest valid county in source order within that kingdom.

Only actual title/capital references are rewritten.  Province-history section
comments are updated for maintainability, obsolete county localization keys are
removed, and unrelated coat-of-arms designer assets with similar filenames are
left untouched.
"""

from __future__ import annotations

import argparse
import codecs
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from dm_generate_history_compat import load_title_tree


ROOT = Path(__file__).resolve().parents[1]
TITLE_PATH = ROOT / "common" / "landed_titles" / "00_DM_landed_titles.txt"
LOC_PATH = (
	ROOT
	/ "localization"
	/ "simp_chinese"
	/ "DM_custom_titles_l_simp_chinese.yml"
)
TABLE_PATH = ROOT / "tools" / "dm_empty_county_migration.json"
COUNTY_RE = re.compile(r"^(\s*)(c_[A-Za-z0-9_]+)\s*=\s*\{")
BARONY_RE = re.compile(r"(?m)^\s*b_[A-Za-z0-9_]+\s*=\s*\{")
LANDLESS_RE = re.compile(r"(?m)^\s*landless\s*=\s*yes\b")
CAPITAL_RE = re.compile(
	r"(?m)^(\s*capital\s*=\s*)(c_[A-Za-z0-9_]+)(\s*(?:#.*)?)$"
)


def strip_comment(line: str) -> str:
	quoted = False
	escaped = False
	for index, char in enumerate(line):
		if quoted:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
		elif char == '"':
			quoted = True
		elif char == "#":
			return line[:index]
	return line


def brace_delta(line: str) -> int:
	clean = strip_comment(line)
	clean = re.sub(r'"(?:\\.|[^"])*"', '""', clean)
	return clean.count("{") - clean.count("}")


def county_ranges(lines: list[str]) -> dict[str, tuple[int, int]]:
	result: dict[str, tuple[int, int]] = {}
	index = 0
	while index < len(lines):
		match = COUNTY_RE.match(strip_comment(lines[index]))
		if not match:
			index += 1
			continue
		depth = brace_delta(lines[index])
		end = index
		while depth > 0:
			end += 1
			if end >= len(lines):
				raise RuntimeError(
					f"Unclosed county block at line {index + 1}"
				)
			depth += brace_delta(lines[end])
		result[match.group(2)] = (index, end + 1)
		index = end + 1
	return result


def read_utf8(path: Path) -> tuple[str, bool, str]:
	raw = path.read_bytes()
	bom = raw.startswith(codecs.BOM_UTF8)
	if bom:
		raw = raw[len(codecs.BOM_UTF8) :]
	text = raw.decode("utf-8", errors="strict")
	newline = "\r\n" if "\r\n" in text else "\n"
	return text, bom, newline


def write_utf8(path: Path, text: str, bom: bool) -> None:
	payload = text.encode("utf-8")
	temp = path.with_suffix(path.suffix + ".dm_tmp")
	temp.write_bytes((codecs.BOM_UTF8 if bom else b"") + payload)
	os.replace(temp, path)


def build_migration() -> dict[str, str]:
	text, _, _ = read_utf8(TITLE_PATH)
	lines = text.splitlines()
	ranges = county_ranges(lines)
	empty = {
		county
		for county, (start, end) in ranges.items()
		if (
			not BARONY_RE.search("\n".join(lines[start:end]))
			and not LANDLESS_RE.search("\n".join(lines[start:end]))
		)
	}
	if len(empty) != 223:
		raise RuntimeError(
			f"Expected exactly 223 empty counties, found {len(empty)}"
		)

	parent, children, capital, barony_province, _ = load_title_tree()

	@lru_cache(maxsize=None)
	def has_province(title: str) -> bool:
		if title.startswith("b_"):
			return title in barony_province
		return any(has_province(child) for child in children.get(title, []))

	@lru_cache(maxsize=None)
	def descendant_valid_counties(title: str) -> tuple[str, ...]:
		result: list[str] = []
		for child in children.get(title, []):
			if child.startswith("c_"):
				if child not in empty and has_province(child):
					result.append(child)
			else:
				result.extend(descendant_valid_counties(child))
		return tuple(result)

	def nearest_sibling(county: str, container: str) -> str | None:
		order = [
			child
			for child in children.get(container, [])
			if child.startswith("c_")
		]
		if county not in order:
			return None
		index = order.index(county)
		candidates = [
			item
			for item in order
			if item not in empty and has_province(item)
		]
		if not candidates:
			return None
		return min(candidates, key=lambda item: (abs(order.index(item) - index), order.index(item)))

	def valid_capital(container: str) -> str | None:
		value = capital.get(container)
		if (
			value
			and value.startswith("c_")
			and value not in empty
			and has_province(value)
		):
			return value
		return None

	def containing(county: str, prefix: str) -> str | None:
		item = parent.get(county)
		while item:
			if item.startswith(prefix):
				return item
			item = parent.get(item)
		return None

	migration: dict[str, str] = {}
	for county in sorted(empty):
		duchy = containing(county, "d_")
		kingdom = containing(county, "k_")
		target = valid_capital(duchy) if duchy else None
		if not target and duchy:
			target = nearest_sibling(county, duchy)
		if not target and kingdom:
			target = valid_capital(kingdom)
		if not target and kingdom:
			candidates = descendant_valid_counties(kingdom)
			target = candidates[0] if candidates else None
		if not target:
			raise RuntimeError(f"No valid migration target for {county}")
		migration[county] = target
	return migration


def remove_counties(migration: dict[str, str]) -> None:
	text, bom, newline = read_utf8(TITLE_PATH)
	lines = text.splitlines()
	ranges = county_ranges(lines)
	remove_at = {
		ranges[county][0]: ranges[county][1]
		for county in migration
		if county in ranges
	}
	output: list[str] = []
	index = 0
	while index < len(lines):
		if index in remove_at:
			index = remove_at[index]
			continue
		output.append(lines[index])
		index += 1
	result = newline.join(output) + newline
	result = CAPITAL_RE.sub(
		lambda match: (
			match.group(1)
			+ migration.get(match.group(2), match.group(2))
			+ match.group(3)
		),
		result,
	)
	write_utf8(TITLE_PATH, result, bom)


def update_province_comments(migration: dict[str, str]) -> None:
	pattern = re.compile(
		r"(?m)^(\s*#+\s*)("
		+ "|".join(re.escape(key) for key in sorted(migration, key=len, reverse=True))
		+ r")(\s*)$"
	)
	for path in sorted((ROOT / "history" / "provinces").glob("*.txt")):
		text, bom, _ = read_utf8(path)
		updated = pattern.sub(
			lambda match: (
				match.group(1) + migration[match.group(2)] + match.group(3)
			),
			text,
		)
		if updated != text:
			write_utf8(path, updated, bom)


def remove_obsolete_localization(migration: dict[str, str]) -> None:
	text, bom, newline = read_utf8(LOC_PATH)
	keys = set(migration) | {f"{key}_adj" for key in migration}
	line_re = re.compile(
		r"^\s*(" + "|".join(re.escape(key) for key in sorted(keys, key=len, reverse=True)) + r"):\d*\s"
	)
	lines = [
		line
		for line in text.splitlines()
		if not line_re.match(line)
	]
	write_utf8(LOC_PATH, newline.join(lines) + newline, bom)


def audit(migration: dict[str, str]) -> None:
	text, _, _ = read_utf8(TITLE_PATH)
	definitions = set(
		re.findall(r"(?m)^\s*(c_[A-Za-z0-9_]+)\s*=\s*\{", text)
	)
	remaining = sorted(set(migration) & definitions)
	if remaining:
		raise RuntimeError(f"Removed counties still defined: {remaining[:10]}")
	for source, target in migration.items():
		if target not in definitions:
			raise RuntimeError(f"{source} maps to undefined target {target}")
		if re.search(
			rf"(?m)^\s*capital\s*=\s*{re.escape(source)}\b", text
		):
			raise RuntimeError(f"Capital still references removed {source}")


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--check", action="store_true")
	args = parser.parse_args()

	if args.check:
		migration = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
		audit(migration)
		print(
			f"empty county migration audit OK: {len(migration)} removed counties"
		)
		return

	migration = build_migration()
	TABLE_PATH.write_text(
		json.dumps(migration, ensure_ascii=False, indent=2) + "\n",
		encoding="utf-8",
	)
	remove_counties(migration)
	update_province_comments(migration)
	remove_obsolete_localization(migration)
	audit(migration)
	print(
		f"Removed {len(migration)} empty county shells; migration table written "
		f"to {TABLE_PATH.relative_to(ROOT)}"
	)


if __name__ == "__main__":
	main()
