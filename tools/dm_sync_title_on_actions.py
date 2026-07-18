#!/usr/bin/env python3
"""Sync vanilla title on-actions and isolate character-only confederation logic."""

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
	relative = Path("common/on_action/title_on_actions.txt")
	text = (args.vanilla / relative).read_text(encoding="utf-8-sig")
	old = """\
\t\t\tlimit = {
\t\t\t\tis_confederation_member = yes
\t\t\t\tscope:title.tier >= tier_kingdom
\t\t\t\tgovernment_is_japanese_trigger = no
\t\t\t}
"""
	new = """\
\t\t\tlimit = {
\t\t\t\tis_confederation_member = yes
\t\t\t\t# remove_confederation_member is a character-only effect.
\t\t\t\t# House blocs have their own membership lifecycle.
\t\t\t\tconfederation ?= { is_house_based = no }
\t\t\t\tscope:title.tier >= tier_kingdom
\t\t\t\tgovernment_is_japanese_trigger = no
\t\t\t}
"""
	count = text.count(old)
	if count != 1:
		raise RuntimeError(
			f"Expected one vanilla confederation title-gain block, found {count}"
		)
	text = text.replace(old, new)
	for title in (
		"c_antiocheia",
		"c_jerusalem",
		"c_alexandria",
		"c_roma",
	):
		text = text.replace(
			f"scope:title = title:{title}",
			"always = no",
		)
	target = mod_root / relative
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text, encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
