#!/usr/bin/env python3
"""Sync vanilla nomad flavour events and require a real domicile for herd logic."""

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
	relative = Path("events/dlc/mpo/mpo_nomads_flavour_events.txt")
	text = (args.vanilla / relative).read_text(encoding="utf-8-sig")
	old = """\
\t\tgovernment_has_flag = government_is_nomadic
\t\tis_available_adult = yes
\t\tdomicile = { herd < max_herd } # You are not at your Herd limit
"""
	new = """\
\t\tgovernment_has_flag = government_is_nomadic
\t\tis_available_adult = yes
\t\texists = domicile
\t\tdomicile = { herd < max_herd } # You are not at your Herd limit
"""
	count = text.count(old)
	if count != 1:
		raise RuntimeError(
			f"Expected one nomad_events.0130 domicile trigger, found {count}"
		)
	target = mod_root / relative
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text.replace(old, new), encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
