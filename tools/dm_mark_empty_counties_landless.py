"""Mark county title shells without any barony as vanilla-supported landless titles.

The current Spring/Autumn title tree intentionally keeps a number of county
keys for localization and script compatibility even though their old baronies
have since moved elsewhere.  Restoring those obsolete barony blocks creates
duplicate title definitions, so the safe 1.19-compatible representation is a
landless county shell.
"""

from __future__ import annotations

import codecs
import re
from pathlib import Path

from dm_generate_history_compat import load_title_tree


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "common" / "landed_titles" / "00_DM_landed_titles.txt"
COUNTY_RE = re.compile(r"^(\s*)(c_[A-Za-z0-9_]+)\s*=\s*\{")
BARONY_RE = re.compile(r"^\s*b_[A-Za-z0-9_]+\s*=\s*\{", re.MULTILINE)
LANDLESS_RE = re.compile(r"^\s*landless\s*=\s*yes\b", re.MULTILINE)
CAPITAL_RE = re.compile(r"^\s*capital\s*=", re.MULTILINE)


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


def main() -> None:
	raw = TARGET.read_bytes()
	has_bom = raw.startswith(codecs.BOM_UTF8)
	payload = raw[len(codecs.BOM_UTF8) :] if has_bom else raw
	text = payload.decode("utf-8", errors="strict")
	newline = "\r\n" if "\r\n" in text else "\n"
	lines = text.splitlines()

	parent, children, _, barony_province, _ = load_title_tree()

	def descendant_has_province(title: str) -> bool:
		if title.startswith("b_"):
			return title in barony_province
		return any(descendant_has_province(child) for child in children.get(title, []))

	def descendant_real_counties(title: str) -> list[str]:
		result: list[str] = []
		for child in children.get(title, []):
			if child.startswith("c_") and descendant_has_province(child):
				result.append(child)
			elif not child.startswith("c_"):
				result.extend(descendant_real_counties(child))
		return result

	def fallback_capital(county: str) -> str:
		container = parent.get(county)
		while container:
			candidates = descendant_real_counties(container)
			if candidates:
				return candidates[0]
			container = parent.get(container)
		raise RuntimeError(f"No regional capital county found for {county}")

	insert_after: dict[int, list[str]] = {}
	counties: list[str] = []
	capitals_added: list[str] = []
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
				raise RuntimeError(f"Unclosed county block at line {index + 1}")
			depth += brace_delta(lines[end])
		block = newline.join(lines[index : end + 1])
		if not BARONY_RE.search(block):
			insertions: list[str] = []
			if not CAPITAL_RE.search(block):
				insertions.append(
					f"{match.group(1)}\tcapital = {fallback_capital(match.group(2))}"
				)
				capitals_added.append(match.group(2))
			if not LANDLESS_RE.search(block):
				insertions.append(f"{match.group(1)}\tlandless = yes")
				counties.append(match.group(2))
			if insertions:
				insert_after[index] = insertions
		index = end + 1

	output: list[str] = []
	for line_index, line in enumerate(lines):
		output.append(line)
		if line_index in insert_after:
			output.extend(insert_after[line_index])

	if insert_after:
		result = (newline.join(output) + newline).encode("utf-8")
		TARGET.write_bytes(codecs.BOM_UTF8 + result)

	print(f"Empty county shells marked landless: {len(counties)}")
	print(f"Landless county capitals added: {len(capitals_added)}")
	if counties:
		print(f"First: {counties[0]}; last: {counties[-1]}")


if __name__ == "__main__":
	main()
