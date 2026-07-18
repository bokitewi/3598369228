#!/usr/bin/env python3
"""Sync vanilla accolade effects and guard invalid forced knight assignment."""

from __future__ import annotations

import argparse
from pathlib import Path


def extract_object(text: str, key: str) -> tuple[int, int, str]:
	start = text.index(f"{key} = {{")
	opening = text.index("{", start)
	depth = 0
	in_string = False
	in_comment = False
	escaped = False
	for index in range(opening, len(text)):
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
				return start, index + 1, text[start : index + 1]
	raise RuntimeError(f"Unbalanced object: {key}")


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--vanilla",
		type=Path,
		default=Path(
			r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
		),
	)
	args = parser.parse_args()
	mod_root = Path(__file__).resolve().parents[1]
	relative = Path(
		"common/scripted_effects/00_accolades_scripted_effects.txt"
	)
	source = args.vanilla / relative
	target = mod_root / relative

	text = source.read_text(encoding="utf-8-sig")
	old = """\
\t\tscope:chosen_knight = {
\t\t\tset_knight_status = force
\t\t}
\t\t
\t\tscope:accolade_in_need = {
\t\t\tset_accolade_successor = scope:chosen_knight
\t\t}
"""
	new = """\
\t\t# Total-conversion courts can change while this effect is resolving.
\t\t# Re-check the vanilla knight eligibility trigger before forcing status.
\t\tif = {
\t\t\tlimit = {
\t\t\t\tscope:chosen_knight = {
\t\t\t\t\tcan_be_knight_trigger = { ARMY_OWNER = scope:owner }
\t\t\t\t}
\t\t\t}
\t\t\tscope:chosen_knight = {
\t\t\t\tset_knight_status = force
\t\t\t}
\t\t\tscope:accolade_in_need = {
\t\t\t\tset_accolade_successor = scope:chosen_knight
\t\t\t}
\t\t}
"""
	count = text.count(old)
	if count != 1:
		raise RuntimeError(
			f"Expected one accolade squire assignment block, found {count}"
		)
	text = text.replace(old, new)
	start, end, effect = extract_object(text, "accolade_create_squire_effect")
	lines = effect.splitlines()
	wrapped = (
		lines[0]
		+ "\n"
		+ "\t# Accolade squires require an actual court. Some total-conversion\n"
		+ "\t# government transitions can leave a ruler without one temporarily.\n"
		+ "\tif = {\n"
		+ "\t\tlimit = { court_owner ?= this }\n"
		+ "\n".join("\t" + line for line in lines[1:-1])
		+ "\n\t}\n"
		+ lines[-1]
	)
	text = text[:start] + wrapped + text[end:]

	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text, encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
