#!/usr/bin/env python3
"""Create a narrow vanilla fabricate-hook interaction overlay."""

from __future__ import annotations

import argparse
from pathlib import Path


KEY = "fabricate_hook_interaction"
AI_POTENTIAL = "\tai_potential = {\n"
AI_GUARD = (
	"\tai_potential = {\n"
	"\t\tNOT = { has_government = feudal_admin_government }\n"
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
	raise RuntimeError(f"Unbalanced vanilla interaction: {key}")


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
		/ "character_interactions"
		/ "00_perk_interactions.txt"
	)
	target = (
		mod_root
		/ "common"
		/ "character_interactions"
		/ "zz_dm_compat_perk_interactions.txt"
	)

	text = source.read_text(encoding="utf-8-sig")
	block = extract_object(text, KEY)
	if block.count(AI_POTENTIAL) != 1:
		raise RuntimeError(f"Expected exactly one ai_potential block in {KEY}")
	block = block.replace(AI_POTENTIAL, AI_GUARD, 1)
	block = "\n".join(line.lstrip(" ") for line in block.splitlines())

	header = (
		"# Synced from vanilla 1.19 00_perk_interactions.txt.\n"
		"# Players and non-Spring governments retain the interaction. The\n"
		"# populous feudal_admin AI is excluded from automatic scheme creation.\n\n"
	)
	target.write_text(header + block + "\n", encoding="utf-8-sig")
	print(f"Wrote {target}")
	print(f"{KEY}: {block.count(chr(10)) + 1} lines")


if __name__ == "__main__":
	main()
