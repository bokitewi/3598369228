#!/usr/bin/env python3
"""Move the approved Korean, Fusang and Rigaojian title subtrees out of e_huaxia.

The current working title file is authoritative for every moved subtree.  The
`main` branch is used only as a registry of which immediate kingdoms belong to
each empire and for each empire's small metadata header.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TITLE_PATH = ROOT / "common/landed_titles/00_DM_landed_titles.txt"
LOC_PATH = ROOT / "localization/simp_chinese/DM_custom_titles_l_simp_chinese.yml"
EMPIRES = ("e_chaoxian", "e_fusang", "e_rigaojian")
KEEP_IN_HUAXIA = {
	"k_daojinguo",
	"k_duomidao",
	"k_zhuziguo",
	"k_zhoufangguo",
	"k_shijianguo",
	"k_aqiguo",
	"k_feituoguo",
}
LANDLESS_IN_HUAXIA = (
	"k_daojinguo",
	"k_duomidao",
	"k_zhuziguo",
	"k_zhoufangguo",
	"k_shijianguo",
	"k_aqiguo",
	"k_feituoguo",
)
CROSS_COUNTY_MOVES = {
	"b_1244_0": "c_yongnu",
	"b_1259_0": "c_tixi",
	"b_1255_0": "c_jucheng",
	"b_1282_0": "c_goumao",
	"b_2631_0": "c_pingquan1",
	"b_2632_0": "c_xifeng2",
}
DISPLAY_NAMES = {
	"e_chaoxian": ("朝鲜", "朝鲜"),
	"e_fusang": ("扶桑", "扶桑"),
	"e_rigaojian": ("日高见", "日高见"),
}


def source_text() -> str:
	data = subprocess.check_output(
		["git", "show", "main:common/landed_titles/00_DM_landed_titles.txt"],
		cwd=ROOT,
	)
	return data.decode("utf-8-sig")


def find_named_block(text: str, key: str, start: int = 0, end: int | None = None) -> tuple[int, int]:
	limit = len(text) if end is None else end
	match = re.search(rf"(?m)^(?P<indent>[ \t]*){re.escape(key)}\s*=\s*\{{", text[start:limit])
	if not match:
		raise ValueError(f"找不到块：{key}")
	block_start = start + match.start()
	open_pos = start + match.end() - 1
	depth = 0
	in_string = False
	escaped = False
	in_comment = False
	for pos in range(open_pos, limit):
		char = text[pos]
		if in_comment:
			if char in "\r\n":
				in_comment = False
			continue
		if in_string:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				in_string = False
			continue
		if char == "#":
			in_comment = True
		elif char == '"':
			in_string = True
		elif char == "{":
			depth += 1
		elif char == "}":
			depth -= 1
			if depth == 0:
				block_end = pos + 1
				while block_end < limit and text[block_end] in "\r\n":
					block_end += 1
				return block_start, block_end
	raise ValueError(f"块未闭合：{key}")


def immediate_kingdoms(block: str) -> list[str]:
	open_pos = block.index("{")
	depth = 0
	in_string = False
	in_comment = False
	result: list[str] = []
	line_start = 0
	for pos, char in enumerate(block):
		if char == "\n":
			line_start = pos + 1
			in_comment = False
			continue
		if in_comment:
			continue
		if char == "#":
			in_comment = True
			continue
		if char == '"':
			in_string = not in_string
			continue
		if in_string:
			continue
		if char == "{":
			if pos != open_pos and depth == 1:
				line = block[line_start:pos]
				match = re.search(r"\b(k_[A-Za-z0-9_]+)\s*=\s*$", line)
				if match:
					result.append(match.group(1))
			depth += 1
		elif char == "}":
			depth -= 1
	return result


def empire_header(block: str) -> str:
	kingdoms = immediate_kingdoms(block)
	if not kingdoms:
		raise ValueError("来源帝国没有直属王国")
	start, _ = find_named_block(block, kingdoms[0])
	return block[:start].rstrip() + "\n"


def move_subtree(text: str, key: str, parent_key: str) -> str:
	parent_start, parent_end = find_named_block(text, parent_key)
	if re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\{{", text[parent_start:parent_end]):
		return text
	start, end = find_named_block(text, key)
	block = text[start:end].strip("\r\n")
	old_indent = re.match(r"[ \t]*", block).group(0)
	text = text[:start] + text[end:]
	parent_start, parent_end = find_named_block(text, parent_key)
	parent_block = text[parent_start:parent_end]
	parent_indent = re.match(r"[ \t]*", parent_block).group(0)
	child_indent = parent_indent + "\t"
	lines = [
		child_indent + (line[len(old_indent):] if line.startswith(old_indent) else line.lstrip())
		for line in block.splitlines()
	]
	close = text.rfind("}", parent_start, parent_end)
	return text[:close] + "\n" + "\n".join(lines) + "\n" + text[close:]


def restore_titles() -> None:
	text = TITLE_PATH.read_text(encoding="utf-8-sig")
	source = source_text()
	# The approved map task is committed on main. Replace only the three named
	# top-level empire subtrees; leave every other dirty-worktree map edit intact.
	if all(re.search(rf"(?m)^{key}\s*=\s*\{{", text) for key in EMPIRES):
		for empire in EMPIRES:
			source_start, source_end = find_named_block(source, empire)
			current_start, current_end = find_named_block(text, empire)
			source_block = source[source_start:source_end].rstrip() + "\n"
			text = text[:current_start] + source_block + text[current_end:]
		# These six historical kings intentionally remain under e_huaxia only as
		# landless titles. Their former landed children now belong exclusively to
		# the restored e_fusang subtree.
		huaxia_start, huaxia_end = find_named_block(text, "e_huaxia")
		replacements: list[tuple[int, int, str]] = []
		for kingdom in LANDLESS_IN_HUAXIA:
			start, end = find_named_block(text, kingdom, huaxia_start, huaxia_end)
			old_block = text[start:end]
			indent = re.match(r"[ \t]*", old_block).group(0)
			color_match = re.search(r"color\s*=\s*\{[^}]+\}", old_block)
			color_line = color_match.group(0) if color_match else "color = { 80 80 80 }"
			replacement = (
				f"{indent}{kingdom} = {{\n"
				f"{indent}\t{color_line}\n"
				f"{indent}\tlandless = yes\n"
				f"{indent}}}\n"
			)
			replacements.append((start, end, replacement))
		# The current Northeast integration had re-used province/title b_3899_0
		# in c_yusinei. The approved Korean subtree owns that unique node.
		if re.search(r"(?m)^\s*c_yusinei\s*=\s*\{", text[huaxia_start:huaxia_end]):
			start, end = find_named_block(text, "c_yusinei", huaxia_start, huaxia_end)
			replacements.append((start, end, ""))
		for start, end, replacement in sorted(replacements, reverse=True):
			text = text[:start] + replacement + text[end:]
		for barony, county in CROSS_COUNTY_MOVES.items():
			text = move_subtree(text, barony, county)
		TITLE_PATH.write_text(text.rstrip() + "\n", encoding="utf-8-sig", newline="\r\n")
		return

	registry: dict[str, list[str]] = {}
	headers: dict[str, str] = {}
	for empire in EMPIRES:
		start, end = find_named_block(source, empire)
		block = source[start:end]
		registry[empire] = [key for key in immediate_kingdoms(block) if key not in KEEP_IN_HUAXIA]
		headers[empire] = empire_header(block)

	huaxia_start, huaxia_end = find_named_block(text, "e_huaxia")
	moved_blocks: dict[str, list[str]] = {empire: [] for empire in EMPIRES}
	removals: list[tuple[int, int]] = []
	for empire, kingdoms in registry.items():
		for kingdom in kingdoms:
			start, end = find_named_block(text, kingdom, huaxia_start, huaxia_end)
			moved_blocks[empire].append(text[start:end].rstrip() + "\n")
			removals.append((start, end))

	for start, end in sorted(removals, reverse=True):
		text = text[:start] + text[end:]

	text = text.rstrip() + "\n\n"
	for empire in EMPIRES:
		text += headers[empire]
		text += "\n".join(block.rstrip() for block in moved_blocks[empire])
		text += "\n}\n\n"
	TITLE_PATH.write_text(text.rstrip() + "\n", encoding="utf-8-sig", newline="\r\n")


def restore_localization() -> None:
	text = LOC_PATH.read_text(encoding="utf-8-sig")
	additions: list[str] = []
	for key, (name, adjective) in DISPLAY_NAMES.items():
		if not re.search(rf"(?m)^\s*{re.escape(key)}:", text):
			additions.append(f' {key}:0 "{name}"')
		if not re.search(rf"(?m)^\s*{re.escape(key)}_adj:", text):
			additions.append(f' {key}_adj:0 "{adjective}"')
	if additions:
		text = text.rstrip() + "\n" + "\n".join(additions) + "\n"
		LOC_PATH.write_text(text, encoding="utf-8-sig", newline="\r\n")


def check() -> None:
	text = TITLE_PATH.read_text(encoding="utf-8-sig")
	errors: list[str] = []
	for empire in EMPIRES:
		if len(re.findall(rf"(?m)^{re.escape(empire)}\s*=\s*\{{", text)) != 1:
			errors.append(f"{empire} 顶层定义不是恰好一次")
	for key in KEEP_IN_HUAXIA:
		if len(re.findall(rf"(?m)^\t{re.escape(key)}\s*=\s*\{{", text)) != 1:
			errors.append(f"{key} 未恰好保留一个 e_huaxia 直属定义")
	for key in ("b_1244_0", "b_1259_0", "b_1255_0", "b_1282_0", "b_2631_0", "b_2632_0", "b_3849_0"):
		if len(re.findall(rf"(?m)^\s*{re.escape(key)}\s*=\s*\{{", text)) != 1:
			errors.append(f"{key} 定义数量不为一")
	loc = LOC_PATH.read_text(encoding="utf-8-sig")
	for key in EMPIRES:
		for loc_key in (key, f"{key}_adj"):
			if len(re.findall(rf"(?m)^\s*{re.escape(loc_key)}:", loc)) != 1:
				errors.append(f"本地化 {loc_key} 数量不为一")
	if errors:
		raise SystemExit("地图法理恢复审计失败：\n" + "\n".join(errors))
	print("PASS: 三帝国法理与本地化恢复基础审计")


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--apply", action="store_true")
	parser.add_argument("--check", action="store_true")
	args = parser.parse_args()
	if args.apply:
		restore_titles()
		restore_localization()
	if args.apply or args.check:
		check()
	else:
		parser.error("指定 --apply 或 --check")


if __name__ == "__main__":
	main()
