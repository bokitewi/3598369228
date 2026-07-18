#!/usr/bin/env python3
"""Create narrow vanilla EP3 interaction overlays for the Spring map government."""

from __future__ import annotations

import argparse
from pathlib import Path


KEYS = (
	"start_slander_interaction",
	"start_promote_interaction",
	"start_challenge_status_interaction",
	"start_expand_power_base_interaction",
	"start_depose_interaction",
)
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
		/ "06_ep3_scheme_interactions.txt"
	)
	target = (
		mod_root
		/ "common"
		/ "character_interactions"
		/ "zz_dm_compat_ep3_political_interactions.txt"
	)

	text = source.read_text(encoding="utf-8-sig")
	blocks: list[str] = []
	for key in KEYS:
		block = extract_object(text, key)
		count = block.count(AI_POTENTIAL)
		if count == 1:
			block = block.replace(AI_POTENTIAL, AI_GUARD, 1)
		elif count == 0 and key == "start_expand_power_base_interaction":
			block = (
				block[:-1].rstrip()
				+ "\n\n\tai_potential = {\n"
				+ "\t\tNOT = { has_government = feudal_admin_government }\n"
				+ "\t}\n}"
			)
		else:
			raise RuntimeError(f"Expected exactly one ai_potential block in {key}")
		block = "\n".join(line.lstrip(" ") for line in block.splitlines())
		blocks.append(block)

	header = (
		"# Synced from vanilla 1.19 06_ep3_scheme_interactions.txt.\n"
		"# Players retain every political interaction. Only feudal_admin AI is\n"
		"# excluded because its Spring-map population exceeds the engine's\n"
		"# semiannual political-scheme agent refresh capacity.\n\n"
	)
	target.write_text(header + "\n\n".join(blocks) + "\n", encoding="utf-8-sig")
	print(f"Wrote {target}")
	for key, block in zip(KEYS, blocks, strict=True):
		print(f"{key}: {block.count(chr(10)) + 1} lines")


if __name__ == "__main__":
	main()
