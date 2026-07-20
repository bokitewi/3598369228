#!/usr/bin/env python3
"""Sync vanilla tournament effects and guard missing prior-round match variables."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


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
		"common/scripted_effects/04_dlc_ep2_tournament_effects.txt"
	)
	source = args.vanilla / relative
	target = mod_root / relative

	text = source.read_text(encoding="utf-8-sig")
	patterns = (
		(
			r"(?m)^(\s*)limit = \{ "
			r"scope:activity\.var:contest_versus_progress = 2 \}"
			r"(?=\n\1set_variable = \{\n\1\tname = last_versus_match"
			r"\n\1\tvalue = var:contest_semi_finalist_match_\$CONTEST\$)",
			"contest_semi_finalist_match_$CONTEST$",
		),
		(
			r"(?m)^(\s*)limit = \{ "
			r"scope:activity\.var:contest_versus_progress = 1 \}"
			r"(?=\n\1set_variable = \{\n\1\tname = last_versus_match"
			r"\n\1\tvalue = var:contest_qualified_match_\$CONTEST\$)",
			"contest_qualified_match_$CONTEST$",
		),
	)
	for pattern, variable in patterns:
		def replacement(match: re.Match[str]) -> str:
			indent = match.group(1)
			progress = "2" if "semi_finalist" in variable else "1"
			return (
				f"{indent}limit = {{\n"
				f"{indent}\tscope:activity.var:contest_versus_progress = {progress}\n"
				f"{indent}\texists = var:{variable}\n"
				f"{indent}}}"
			)

		text, count = re.subn(pattern, replacement, text)
		if count != 2:
			raise RuntimeError(
				f"Expected 2 guarded reads of {variable}, found {count}"
			)

	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text, encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
