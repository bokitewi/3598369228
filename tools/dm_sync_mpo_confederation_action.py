#!/usr/bin/env python3
"""Sync the vanilla confederation important action with an unheld-county guard."""

from __future__ import annotations

import argparse
import codecs
import re
from pathlib import Path


KEY = "action_offer_confederation"
OLD_LIMIT = """\
\t\t\t\tlimit = {
\t\t\t\t\tholder = {
\t\t\t\t\t\troot = {"""
SAFE_LIMIT = """\
\t\t\t\tlimit = {
\t\t\t\t\texists = holder
\t\t\t\t\tholder = {
\t\t\t\t\t\troot = {"""


def extract_object(text: str, key: str) -> str:
	match = re.search(rf"(?m)^{re.escape(key)}\s*=\s*\{{", text)
	if not match:
		raise RuntimeError(f"Missing vanilla important action: {key}")
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
	raise RuntimeError(f"Unbalanced vanilla important action: {key}")


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
		/ "important_actions"
		/ "09_mpo_actions.txt"
	)
	target = (
		mod_root
		/ "common"
		/ "important_actions"
		/ "zz_dm_compat_mpo_actions.txt"
	)

	block = extract_object(source.read_text(encoding="utf-8-sig"), KEY)
	if block.count(OLD_LIMIT) != 1:
		raise RuntimeError(f"Vanilla county-holder limit changed in {KEY}")
	block = block.replace(OLD_LIMIT, SAFE_LIMIT, 1)
	header = (
		"# Synced from vanilla 1.19 09_mpo_actions.txt.\n"
		"# Empty total-conversion county shells are skipped before entering holder scope.\n\n"
	)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_bytes(codecs.BOM_UTF8 + (header + block + "\n").encode("utf-8"))
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
