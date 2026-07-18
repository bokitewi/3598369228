#!/usr/bin/env python3
"""Sync vanilla administrative contracts with a valid-neighbor acceptance guard."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


KEY = "discontent_soldiers"
OLD_ACCEPT = """\
\tvalid_to_accept = {
\t\tvalid_governor_contract_trigger = yes
\t\tcustom_tooltip = {"""
SAFE_ACCEPT = """\
\tvalid_to_accept = {
\t\tvalid_governor_contract_trigger = yes
\t\tany_neighboring_and_across_water_realm_same_rank_owner = {
\t\t\tliege = root.liege
\t\t}
\t\tcustom_tooltip = {"""


def extract_object(text: str, key: str) -> str:
	match = re.search(rf"(?m)^{re.escape(key)}\s*=\s*\{{", text)
	if not match:
		raise RuntimeError(f"Missing vanilla task contract: {key}")
	start = match.start()
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
	raise RuntimeError(f"Unbalanced vanilla task contract: {key}")


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
		/ "task_contracts"
		/ "admin_contracts.txt"
	)
	target = mod_root / "common" / "task_contracts" / "admin_contracts.txt"

	text = source.read_text(encoding="utf-8-sig")
	block = extract_object(text, KEY)
	if block.count(OLD_ACCEPT) != 1:
		raise RuntimeError(f"Vanilla acceptance block changed in {KEY}")
	patched_block = block.replace(OLD_ACCEPT, SAFE_ACCEPT, 1)
	if text.count(block) != 1:
		raise RuntimeError(f"Could not uniquely replace vanilla contract {KEY}")
	text = text.replace(block, patched_block, 1)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text, encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
