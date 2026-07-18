#!/usr/bin/env python3
"""Sync vanilla diarchy events and guarantee the beneficiary county scope."""

from __future__ import annotations

import argparse
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
	relative = Path("events/diarchy_events/diarchy_events.txt")
	text = (args.vanilla / relative).read_text(encoding="utf-8-sig")
	old = """\
\t\tliege = {
\t\t\tany_held_title = {
\t\t\t\tcount >= 2
\t\t\t\ttitle_tier = county
\t\t\t}
\t\t}
"""
	new = """\
\t\tliege = {
\t\t\tsave_temporary_scope_as = liege
\t\t\tany_held_title = {
\t\t\t\tcount >= 2
\t\t\t\ttitle_tier = county
\t\t\t}
\t\t\t# The immediate block requires a non-capital beneficiary county.
\t\t\tany_held_title = {
\t\t\t\tdiarchy_1221_valid_beneficiary_county_basics_trigger = yes
\t\t\t}
\t\t}
"""
	count = text.count(old)
	if count != 1:
		raise RuntimeError(
			f"Expected one diarchy.1221 liege county trigger, found {count}"
		)
	target = mod_root / relative
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text.replace(old, new), encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
