#!/usr/bin/env python3
"""Sync the vanilla EP3 event file with an appointment-law guard."""

from __future__ import annotations

import argparse
from pathlib import Path


KEY = "ep3_landless_admin.1040"
TRIGGER = "\ttrigger = {\n\t\tis_governor = yes\n"
GUARD = (
	"\ttrigger = {\n"
	"\t\tis_governor = yes\n"
	"\t\tprimary_title = {\n"
	"\t\t\tOR = {\n"
	"\t\t\t\thas_title_law_flag = appointment_type_succession\n"
	"\t\t\t\tholder = { has_realm_law_flag = appointment_type_succession }\n"
	"\t\t\t}\n"
	"\t\t}\n"
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
	raise RuntimeError(f"Unbalanced vanilla event: {key}")


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
		/ "events"
		/ "dlc"
		/ "ep3"
		/ "ep3_landless_admin_events.txt"
	)
	target = (
		mod_root
		/ "events"
		/ "dlc"
		/ "ep3"
		/ "ep3_landless_admin_events.txt"
	)

	text = source.read_text(encoding="utf-8-sig")
	block = extract_object(text, KEY)
	if block.count(TRIGGER) != 1:
		raise RuntimeError(f"Expected exactly one trigger block in {KEY}")
	patched_block = block.replace(TRIGGER, GUARD, 1)
	if text.count(block) != 1:
		raise RuntimeError(f"Could not uniquely replace vanilla event {KEY}")
	text = text.replace(block, patched_block, 1)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text, encoding="utf-8-sig")
	print(f"Wrote {target}")
	print(f"{KEY}: {patched_block.count(chr(10)) + 1} lines")


if __name__ == "__main__":
	main()
