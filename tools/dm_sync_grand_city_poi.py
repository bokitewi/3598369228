#!/usr/bin/env python3
"""Map vanilla grand-city travel points onto Spring-map capitals."""

from __future__ import annotations

import argparse
from pathlib import Path


KEY = "poi_grand_city"
BATTLE_KEY = "poi_battles_historical"
VANILLA_LIST = (
	"\tbuild_province_list = {\n"
	"\t\tprovince:4828 = { add_to_list = provinces } #Baghdad\n"
	"\t\tprovince:2575 = { add_to_list = provinces } #Rome\n"
	"\t\tprovince:496 = { add_to_list = provinces } #Constantinople\n"
	"\t}"
)
SPRING_LIST = (
	"\tbuild_province_list = {\n"
	"\t\tprovince:793 = { add_to_list = provinces } # Wangcheng\n"
	"\t\tprovince:8 = { add_to_list = provinces } # Linzi\n"
	"\t\tprovince:900 = { add_to_list = provinces } # Xianyang\n"
	"\t}"
)


def extract_object(text: str, key: str) -> str:
	start = text.index(f"{key} = {{")
	depth = 0
	in_string = False
	in_comment = False
	escaped = False
	for index in range(start, len(text)):
		char = text[index]
		if in_comment:
			if char == "\n":
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
				return text[start : index + 1]
	raise RuntimeError(f"Unbalanced vanilla object: {key}")


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--vanilla",
		type=Path,
		default=Path(r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"),
	)
	args = parser.parse_args()
	mod_root = Path(__file__).resolve().parents[1]
	source = (
		args.vanilla
		/ "common"
		/ "travel"
		/ "point_of_interest_types"
		/ "travel_point_of_interest_types.txt"
	)
	target = (
		mod_root
		/ "common"
		/ "travel"
		/ "point_of_interest_types"
		/ "zz_dm_compat_travel_point_of_interest_types.txt"
	)

	text = source.read_text(encoding="utf-8-sig")
	block = extract_object(text, KEY)
	if block.count(VANILLA_LIST) != 1:
		raise RuntimeError(f"Vanilla province list changed in {KEY}")
	block = block.replace(VANILLA_LIST, SPRING_LIST, 1)
	block = "\n".join(line.lstrip(" ") for line in block.splitlines())
	battle_block = (
		f"{BATTLE_KEY} = {{\n"
		"\tbuild_province_list = {\n"
		"\t\t# Vanilla historical battle links are outside the Spring map.\n"
		"\t}\n"
		"\ton_visit = {\n"
		"\t}\n"
		"}"
	)

	header = (
		"# Synced from vanilla 1.19 travel_point_of_interest_types.txt.\n"
		"# Baghdad, Rome, and Constantinople map to Wangcheng, Linzi, and Xianyang.\n\n"
	)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(
		header + block + "\n\n" + battle_block + "\n",
		encoding="utf-8-sig",
	)
	print(f"Wrote {target}")
	print(f"{KEY}: {block.count(chr(10)) + 1} lines")
	print(f"{BATTLE_KEY}: {battle_block.count(chr(10)) + 1} lines")


if __name__ == "__main__":
	main()
