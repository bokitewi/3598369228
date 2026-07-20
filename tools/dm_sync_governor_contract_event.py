#!/usr/bin/env python3
"""Sync vanilla governor contracts and guard a transient missing neighbor scope."""

from __future__ import annotations

import argparse
from pathlib import Path


OLD = """		scope:ongoing_contract = { # Save other gov for reward effects
			set_variable = {
				name = other_gov
				value = scope:other_gov
			}
		}
		generate_governance_outcome_effect = { OPTIONS = 5 }"""
NEW = """		# The neighboring governor can disappear between contract acceptance and
		# this event. Keep the vanilla outcomes, but never store an unset scope.
		if = {
			limit = {
				exists = scope:ongoing_contract
				exists = scope:other_gov
			}
			scope:ongoing_contract = { # Save other gov for reward effects
				set_variable = {
					name = other_gov
					value = scope:other_gov
				}
			}
		}
		generate_governance_outcome_effect = { OPTIONS = 5 }"""


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
	relative = Path("events/scheme_events/governor_contract_events.txt")
	source = args.vanilla / relative
	target = mod_root / relative

	text = source.read_text(encoding="utf-8-sig")
	if text.count(OLD) != 1:
		raise RuntimeError("Vanilla governor_contract_event.2000 block changed")
	text = text.replace(OLD, NEW, 1)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(text, encoding="utf-8-sig")
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
