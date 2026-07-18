#!/usr/bin/env python3
"""Sync vanilla travel events and avoid effects on an already dead sacrifice."""

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
	relative = Path("events/travel_events/travel_events_james.txt")
	text = (args.vanilla / relative).read_text(encoding="utf-8-sig")
	old = """\
\t\tscope:sacrificed_person_scope ?= {
\t\t\tremove_character_flag = is_naked
\t\t\tsilent_disappearance_ai_if_created_effect = yes
\t\t}
"""
	new = """\
\t\tscope:sacrificed_person_scope ?= {
\t\t\tif = {
\t\t\t\tlimit = { is_alive = yes }
\t\t\t\tremove_character_flag = is_naked
\t\t\t}
\t\t\tsilent_disappearance_ai_if_created_effect = yes
\t\t}
"""
	count = text.count(old)
	if count != 1:
		raise RuntimeError(
			f"Expected one travel_events.4021 cleanup block, found {count}"
		)
	target = mod_root / relative
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text.replace(old, new), encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
