#!/usr/bin/env python3
"""Sync vanilla secret effects and reject secrets assigned after death."""

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
	relative = Path("common/scripted_effects/00_secret_effects.txt")
	text = (args.vanilla / relative).read_text(encoding="utf-8-sig")
	old = """\
\tif = {
\t\tlimit = { #Not already a cannibal
\t\t\tNOR = {
"""
	new = """\
\tif = {
\t\tlimit = { #Not already a cannibal
\t\t\tis_alive = yes
\t\t\tNOR = {
"""
	count = text.count(old)
	if count != 1:
		raise RuntimeError(
			f"Expected one cannibal-secret eligibility block, found {count}"
		)
	target = mod_root / relative
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text.replace(old, new), encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
