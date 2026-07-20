#!/usr/bin/env python3
"""Integrate the approved Desktop kingdom subtrees into the live title file.

Only the explicitly registered kingdom blocks are replaced.  Existing empire
restoration work and every unrelated dirty-worktree map edit are preserved.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = Path.home() / "Desktop/landed_titles/00_DM_landed_titles.txt"
TARGET_PATH = ROOT / "common/landed_titles/00_DM_landed_titles.txt"

KINGDOMS = (
	"k_chaoxianguo",
	"k_zhenfanguo",
	"k_zhoutou",
	"k_gaoyi",
	"k_moren",
	"k_qingqiu",
	"k_huiren",
	"k_yilv",
	"k_donghu",
	"k_tuheguo",
	"k_guzhuguo",
	"k_yuren",
	"k_danlan",
	"k_shanrong",
	"k_wuzhongguo",
	"k_lingzhiguo",
)

# The restored e_chaoxian subtree already owns the populated c_yusinei.  The
# Desktop source predates that recovery and contains only an empty duplicate
# placeholder under k_zhenfanguo, so the placeholder must not be reintroduced.
OMIT_SOURCE_SUBTREES = {"k_zhenfanguo": ("c_yusinei",)}
OMIT_SOURCE_NESTED_SUBTREES = {
	"k_huiren": {
		# The Desktop file contains b_3849_0 twice.  Its approved and populated
		# location is c_quechuan; discard only the stale copy in c_ermian.
		"c_ermian": ("b_3849_0",),
	},
}


def find_block(
	text: str,
	key: str,
	start: int = 0,
	end: int | None = None,
) -> tuple[int, int]:
	limit = len(text) if end is None else end
	match = re.search(
		rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=[ \t]*\{{",
		text[start:limit],
	)
	if not match:
		raise ValueError(f"missing title block: {key}")
	block_start = start + match.start()
	open_at = start + match.end() - 1
	depth = 0
	quoted = False
	escaped = False
	comment = False
	for index in range(open_at, limit):
		char = text[index]
		if comment:
			if char in "\r\n":
				comment = False
			continue
		if quoted:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
			continue
		if char == "#":
			comment = True
		elif char == '"':
			quoted = True
		elif char == "{":
			depth += 1
		elif char == "}":
			depth -= 1
			if depth == 0:
				block_end = index + 1
				while block_end < limit and text[block_end] in "\r\n":
					block_end += 1
				return block_start, block_end
	raise ValueError(f"unterminated title block: {key}")


def immediate_children(block: str, prefix: str) -> list[str]:
	open_at = block.index("{")
	depth = 0
	quoted = False
	escaped = False
	comment = False
	line_start = 0
	result: list[str] = []
	for index, char in enumerate(block):
		if char in "\r\n":
			line_start = index + 1
			comment = False
			continue
		if comment:
			continue
		if quoted:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
			continue
		if char == "#":
			comment = True
		elif char == '"':
			quoted = True
		elif char == "{":
			if index != open_at and depth == 1:
				line = block[line_start:index]
				match = re.search(
					rf"\b({re.escape(prefix)}_[A-Za-z0-9_]+)[ \t]*=[ \t]*$",
					line,
				)
				if match:
					result.append(match.group(1))
			depth += 1
		elif char == "}":
			depth -= 1
	return result


def prepare_source_block(source: str, kingdom: str) -> str:
	start, end = find_block(source, kingdom)
	block = source[start:end].rstrip("\r\n")
	for child in OMIT_SOURCE_SUBTREES.get(kingdom, ()):
		child_start, child_end = find_block(block, child)
		block = block[:child_start] + block[child_end:]
	for parent, children in OMIT_SOURCE_NESTED_SUBTREES.get(kingdom, {}).items():
		parent_start, parent_end = find_block(block, parent)
		parent_block = block[parent_start:parent_end]
		for child in children:
			child_start, child_end = find_block(parent_block, child)
			parent_block = parent_block[:child_start] + parent_block[child_end:]
		block = block[:parent_start] + parent_block + block[parent_end:]
	return block.rstrip()


def reindent(block: str, indent: str) -> str:
	lines = block.splitlines()
	source_indent = re.match(r"[ \t]*", lines[0]).group(0)
	result: list[str] = []
	for line in lines:
		if not line.strip():
			result.append("")
		elif line.startswith(source_indent):
			result.append(indent + line[len(source_indent):])
		else:
			result.append(indent + line.lstrip())
	return "\n".join(result)


def normalized(block: str) -> str:
	return block.replace("\r\n", "\n").rstrip()


def definition_counts(text: str) -> Counter[str]:
	return Counter(
		re.findall(
			r"(?m)^[ \t]*([ekdcb]_[A-Za-z0-9_]+)[ \t]*=[ \t]*\{",
			text,
		)
	)


def province_counts(text: str) -> Counter[int]:
	return Counter(
		int(value)
		for value in re.findall(r"\bprovince[ \t]*=[ \t]*(\d+)", text)
	)


def ensure_no_new_duplicates(before: str, after: str) -> None:
	before_titles = definition_counts(before)
	after_titles = definition_counts(after)
	new_title_duplicates = [
		key
		for key, count in after_titles.items()
		if count > 1 and count > before_titles[key]
	]
	if new_title_duplicates:
		raise ValueError(
			"integration introduces duplicate titles: "
			+ ", ".join(sorted(new_title_duplicates))
		)

	before_provinces = province_counts(before)
	after_provinces = province_counts(after)
	new_province_duplicates = [
		province
		for province, count in after_provinces.items()
		if count > 1 and count > before_provinces[province]
	]
	if new_province_duplicates:
		raise ValueError(
			"integration introduces duplicate provinces: "
			+ ", ".join(map(str, sorted(new_province_duplicates)))
		)


def build_integrated_text(source: str, target: str) -> str:
	replacements: list[tuple[int, int, str]] = []
	huaxia_start, huaxia_end = find_block(target, "e_huaxia")
	huaxia_block = target[huaxia_start:huaxia_end]
	current_kingdoms = set(immediate_children(huaxia_block, "k"))
	for kingdom in KINGDOMS:
		if kingdom not in current_kingdoms:
			raise ValueError(f"{kingdom} is not an immediate child of e_huaxia")
		source_block = prepare_source_block(source, kingdom)
		start, end = find_block(target, kingdom, huaxia_start, huaxia_end)
		target_indent = re.match(r"[ \t]*", target[start:end]).group(0)
		replacements.append((start, end, reindent(source_block, target_indent) + "\n"))

	result = target
	for start, end, replacement in sorted(replacements, reverse=True):
		result = result[:start] + replacement + result[end:]
	ensure_no_new_duplicates(target, result)
	return result.rstrip() + "\n"


def audit(source: str, target: str) -> None:
	huaxia_start, huaxia_end = find_block(target, "e_huaxia")
	huaxia = target[huaxia_start:huaxia_end]
	immediate = set(immediate_children(huaxia, "k"))
	errors: list[str] = []
	for kingdom in KINGDOMS:
		if kingdom not in immediate:
			errors.append(f"{kingdom} is not directly under e_huaxia")
			continue
		source_block = prepare_source_block(source, kingdom)
		target_start, target_end = find_block(target, kingdom, huaxia_start, huaxia_end)
		target_block = target[target_start:target_end]
		target_indent = re.match(r"[ \t]*", target_block).group(0)
		expected = reindent(source_block, target_indent)
		if normalized(target_block) != normalized(expected):
			errors.append(f"{kingdom} differs from the approved Desktop subtree")
	for child in OMIT_SOURCE_SUBTREES["k_zhenfanguo"]:
		zhenfan_start, zhenfan_end = find_block(target, "k_zhenfanguo")
		if re.search(
			rf"(?m)^[ \t]*{re.escape(child)}[ \t]*=[ \t]*\{{",
			target[zhenfan_start:zhenfan_end],
		):
			errors.append(f"obsolete duplicate placeholder remains: {child}")
	if errors:
		raise SystemExit("DESKTOP KINGDOM INTEGRATION AUDIT FAILED:\n" + "\n".join(errors))

	counts = {"k": 0, "d": 0, "c": 0, "b": 0}
	for kingdom in KINGDOMS:
		start, end = find_block(target, kingdom)
		block = target[start:end]
		for tier in counts:
			counts[tier] += len(
				re.findall(
					rf"(?m)^[ \t]*{tier}_[A-Za-z0-9_]+[ \t]*=[ \t]*\{{",
					block,
				)
			)
	print(
		"PASS: integrated 16 Desktop kingdoms "
		f"({counts['k']} kingdoms, {counts['d']} duchies, "
		f"{counts['c']} counties, {counts['b']} baronies)"
	)


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--apply", action="store_true")
	parser.add_argument("--check", action="store_true")
	args = parser.parse_args()
	if not args.apply and not args.check:
		parser.error("specify --apply or --check")
	if not SOURCE_PATH.is_file():
		raise SystemExit(f"missing approved Desktop source: {SOURCE_PATH}")
	if not TARGET_PATH.is_file():
		raise SystemExit(f"missing target title file: {TARGET_PATH}")
	source = SOURCE_PATH.read_text(encoding="utf-8-sig")
	target = TARGET_PATH.read_text(encoding="utf-8-sig")
	if args.apply:
		target = build_integrated_text(source, target)
		TARGET_PATH.write_text(
			target,
			encoding="utf-8-sig",
			newline="\r\n",
		)
	audit(source, target)


if __name__ == "__main__":
	main()
