#!/usr/bin/env python3
"""Sync vanilla sway events and reject delayed outcomes with no scheme owner."""

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
	relative = Path(
		"events/scheme_events/sway_scheme/sway_ongoing_events.txt"
	)
	text = (args.vanilla / relative).read_text(encoding="utf-8-sig")
	old = """\
\ttrigger = {
\t\texists = scope:scheme
\t\tscope:scheme = { scheme_progress < scope:scheme.scheme_phase_duration }
\t\tscope:target = {
\t\t\tis_alive = yes
\t\t}
\t}
"""
	new = """\
\ttrigger = {
\t\texists = scope:scheme
\t\t# A delayed compliment outcome can survive cancellation or owner death.
\t\texists = scope:scheme.scheme_owner
\t\tscope:scheme = { scheme_progress < scope:scheme.scheme_phase_duration }
\t\tscope:target = {
\t\t\tis_alive = yes
\t\t}
\t}
"""
	count = text.count(old)
	if count != 1:
		raise RuntimeError(
			f"Expected one sway_ongoing.1003 trigger block, found {count}"
		)
	text = text.replace(old, new)
	target = mod_root / relative
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text, encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
