#!/usr/bin/env python3
"""Create the narrow TGP house-bloc compatibility overlay from vanilla 1.19."""

from __future__ import annotations

import argparse
from pathlib import Path


KEY = "house_bloc_desire_to_join_modifiers = {"
NEXT_KEY = "house_bloc_tyranny_war_modifiers = {"
OLD_DISTANCE = """\tmodifier = { # Distance
\t\texists = scope:joiner_temp.domicile
\t\texists = scope:inviter_temp.domicile
\t\tscope:inviter_temp.domicile.domicile_location = {
\t\t\tNOR = {
\t\t\t\tkingdom = scope:joiner_temp.domicile.domicile_location.kingdom
\t\t\t\tcounty = {
\t\t\t\t\tany_neighboring_county = { this = scope:joiner_temp.domicile.domicile_location.county }
\t\t\t\t}
\t\t\t}
\t\t}
\t\tadd = -20
\t\tdesc = AI_DISTANT_DOMICILE_REASON
\t}"""
NEW_DISTANCE = """\tmodifier = { # Distance
\t\texists = scope:joiner_temp.domicile
\t\texists = scope:inviter_temp.domicile
\t\texists = scope:joiner_temp.domicile.domicile_location.kingdom
\t\texists = scope:inviter_temp.domicile.domicile_location.kingdom
\t\texists = scope:joiner_temp.domicile.domicile_location.county
\t\texists = scope:inviter_temp.domicile.domicile_location.county
\t\tscope:inviter_temp.domicile.domicile_location = {
\t\t\tNOR = {
\t\t\t\tkingdom = scope:joiner_temp.domicile.domicile_location.kingdom
\t\t\t\tcounty = {
\t\t\t\t\tany_neighboring_county = { this = scope:joiner_temp.domicile.domicile_location.county }
\t\t\t\t}
\t\t\t}
\t\t}
\t\tadd = -20
\t\tdesc = AI_DISTANT_DOMICILE_REASON
\t}"""


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
		/ "scripted_modifiers"
		/ "10_tgp_japan_modifiers.txt"
	)
	target = (
		mod_root
		/ "common"
		/ "scripted_modifiers"
		/ "zz_dm_compat_tgp_house_bloc_modifiers.txt"
	)

	text = source.read_text(encoding="utf-8-sig")
	start = text.index(KEY)
	end = text.index(NEXT_KEY, start)
	block = text[start:end].rstrip()
	if block.count(OLD_DISTANCE) != 1:
		raise RuntimeError("Vanilla house-bloc distance block no longer matches 1.19 baseline")
	block = block.replace(OLD_DISTANCE, NEW_DISTANCE)

	header = (
		"# Synced from vanilla 1.19 10_tgp_japan_modifiers.txt.\n"
		"# The only change guards domicile title links before measuring distance.\n"
	)
	target.write_text(header + block + "\n", encoding="utf-8-sig", newline="\n")
	print(f"Wrote {target}")
	print(f"Source lines: {block.count(chr(10)) + 1}")
	print("Compatibility changes: 4 domicile title-link guards")


if __name__ == "__main__":
	main()
