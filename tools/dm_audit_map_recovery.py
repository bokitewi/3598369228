"""Audit the approved three-empire de-jure recovery and Youzhou region."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TITLE_PATH = ROOT / "common/landed_titles/00_DM_landed_titles.txt"
REGION_PATH = ROOT / "map_data/geographical_regions/geographical_region.txt"
DEFINITION_PATH = ROOT / "map_data/definition.csv"
LOC_PATH = ROOT / "localization/simp_chinese/DM_custom_titles_l_simp_chinese.yml"
EXPECTED_COUNTS = {
	"e_chaoxian": {"k": 6, "d": 6, "c": 173, "b": 172},
	"e_fusang": {"k": 35, "d": 71, "c": 436, "b": 647},
	"e_rigaojian": {"k": 1, "d": 14, "c": 80, "b": 167},
}
EXPECTED_YOUZHOU = (
	"k_nifang",
	"k_yanguo1",
	"k_hanguo1",
	"k_jiguo4",
	"k_wuzhongguo",
	"k_lingzhiguo",
	"k_shanrong",
	"k_guzhuguo",
	"k_tuheguo",
	"k_yuren",
	"k_yilv",
	"k_donghu",
	"k_huiren",
	"k_gaoyi",
	"k_moren",
	"k_qingqiu",
	"k_zhoutou",
)
CROSS_COUNTY = {
	"b_1244_0": "c_yongnu",
	"b_1259_0": "c_tixi",
	"b_1255_0": "c_jucheng",
	"b_1282_0": "c_goumao",
	"b_2631_0": "c_pingquan1",
	"b_2632_0": "c_xifeng2",
	"b_3849_0": "c_quechuan",
}
KEEP_HUAXIA = (
	"k_daojinguo",
	"k_duomidao",
	"k_zhuziguo",
	"k_zhoufangguo",
	"k_shijianguo",
	"k_aqiguo",
	"k_feituoguo",
)


def fail(message: str) -> None:
	raise AssertionError(message)


def find_block(text: str, key: str, start: int = 0, end: int | None = None) -> tuple[int, int]:
	limit = len(text) if end is None else end
	match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\{{", text[start:limit])
	if not match:
		fail(f"missing map block: {key}")
	block_start = start + match.start()
	brace = start + match.end() - 1
	depth = 0
	quoted = False
	comment = False
	for index in range(brace, limit):
		char = text[index]
		if comment:
			if char in "\r\n":
				comment = False
			continue
		if char == "#" and not quoted:
			comment = True
		elif char == '"':
			quoted = not quoted
		elif not quoted and char == "{":
			depth += 1
		elif not quoted and char == "}":
			depth -= 1
			if depth == 0:
				return block_start, index + 1
	fail(f"unterminated map block: {key}")
	return 0, 0


def block_text(text: str, key: str) -> str:
	start, end = find_block(text, key)
	return text[start:end]


def immediate_keys(block: str, prefix: str) -> list[str]:
	open_at = block.index("{")
	depth = 0
	quoted = False
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
		if char == "#" and not quoted:
			comment = True
		elif char == '"':
			quoted = not quoted
		elif quoted:
			continue
		elif char == "{":
			if index != open_at and depth == 1:
				line = block[line_start:index]
				match = re.search(rf"\b({prefix}_[A-Za-z0-9_]+)\s*=\s*$", line)
				if match:
					result.append(match.group(1))
			depth += 1
		elif char == "}":
			depth -= 1
	return result


def check_empire_counts_and_uniqueness(text: str) -> None:
	all_definitions = re.findall(r"(?m)^\s*([ekdcb]_[A-Za-z0-9_]+)\s*=\s*\{", text)
	global_counts = Counter(all_definitions)
	for empire, expected in EXPECTED_COUNTS.items():
		if global_counts[empire] != 1:
			fail(f"{empire}: expected one top-level definition, found {global_counts[empire]}")
		block = block_text(text, empire)
		for prefix, count in expected.items():
			keys = re.findall(rf"(?m)^\s*({prefix}_[A-Za-z0-9_]+)\s*=\s*\{{", block)
			if len(keys) != count:
				fail(f"{empire}: {prefix}-tier count {len(keys)}, expected {count}")
			duplicates = [key for key in keys if global_counts[key] != 1]
			if duplicates:
				fail(f"{empire}: titles are not globally unique: {', '.join(duplicates[:20])}")
		if len(immediate_keys(block, "k")) != expected["k"]:
			fail(f"{empire}: immediate kingdom count drifted")


def check_cross_county_moves(text: str) -> None:
	for barony, county in CROSS_COUNTY.items():
		county_block = block_text(text, county)
		if not re.search(rf"(?m)^\s*{re.escape(barony)}\s*=\s*\{{", county_block):
			fail(f"{barony} is not nested under approved parent {county}")
		if len(re.findall(rf"(?m)^\s*{re.escape(barony)}\s*=\s*\{{", text)) != 1:
			fail(f"{barony} is not globally unique")
	huaxia = block_text(text, "e_huaxia")
	immediate = set(immediate_keys(huaxia, "k"))
	for kingdom in KEEP_HUAXIA:
		if kingdom not in immediate:
			fail(f"{kingdom} is no longer an immediate e_huaxia kingdom")


def check_provinces(text: str) -> None:
	with DEFINITION_PATH.open(encoding="utf-8-sig", newline="") as handle:
		provinces = {
			int(row[0])
			for row in csv.reader(handle, delimiter=";")
			if row and row[0].strip().isdigit()
		}
	for empire in EXPECTED_COUNTS:
		block = block_text(text, empire)
		references = {int(value) for value in re.findall(r"\bprovince\s*=\s*(\d+)", block)}
		missing = sorted(references - provinces)
		if missing:
			fail(f"{empire}: referenced provinces absent from definition.csv: {missing[:20]}")


def check_youzhou() -> None:
	text = REGION_PATH.read_text(encoding="utf-8-sig")
	block = block_text(text, "world_huaxia_youzhou")
	match = re.search(r"kingdoms\s*=\s*\{([^}]*)\}", block, re.DOTALL)
	if not match:
		fail("world_huaxia_youzhou has no kingdoms list")
	actual = tuple(re.findall(r"\bk_[A-Za-z0-9_]+\b", match.group(1)))
	if actual != EXPECTED_YOUZHOU:
		fail("Youzhou kingdoms drifted:\nactual=" + " ".join(actual))
	if re.search(r"(?m)^\s*world_region_youzhou\s*=", text):
		fail("nonexistent world_region_youzhou alias was reintroduced")


def check_localization() -> None:
	raw = LOC_PATH.read_bytes()
	if not raw.startswith(b"\xef\xbb\xbf"):
		fail("custom title Simplified Chinese localization lost its UTF-8 BOM")
	text = raw.decode("utf-8-sig")
	for empire in EXPECTED_COUNTS:
		for key in (empire, f"{empire}_adj"):
			if len(re.findall(rf"(?m)^\s*{re.escape(key)}:", text)) != 1:
				fail(f"title localization must contain exactly one {key}")


def main() -> int:
	if not TITLE_PATH.is_file():
		fail(f"missing landed title source: {TITLE_PATH}")
	text = TITLE_PATH.read_text(encoding="utf-8-sig")
	if text.count("{") != text.count("}"):
		fail("landed title file has unbalanced braces")
	check_empire_counts_and_uniqueness(text)
	check_cross_county_moves(text)
	check_provinces(text)
	check_youzhou()
	check_localization()
	print(
		"map recovery audit OK: Chaoxian 6/6/173/172, Fusang 35/71/436/647, "
		"Rigaojian 1/14/80/167, seven county placements, Youzhou 17 kingdoms"
	)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except AssertionError as error:
		print(f"MAP RECOVERY AUDIT FAILED: {error}", file=sys.stderr)
		raise SystemExit(1)
