#!/usr/bin/env python3
"""Sync the vanilla nomad proselytize decision with an optional-domicile cost guard."""

from __future__ import annotations

import argparse
import codecs
import re
from pathlib import Path


KEY = "proselytize_to_your_people_decision"
OLD_COST_LIMIT = """\
\t\t\t\t\tlimit = {
\t\t\t\t\t\tdomicile.domicile_faith = {
\t\t\t\t\t\t\tNOT = { has_doctrine_parameter = unreformed }
\t\t\t\t\t\t}
\t\t\t\t\t\tfaith = {
\t\t\t\t\t\t\thas_doctrine_parameter = unreformed
\t\t\t\t\t\t}
\t\t\t\t\t}"""
SAFE_COST_LIMIT = """\
\t\t\t\t\tlimit = {
\t\t\t\t\t\texists = domicile.domicile_faith
\t\t\t\t\t\ttrigger_if = {
\t\t\t\t\t\t\tlimit = { exists = domicile.domicile_faith }
\t\t\t\t\t\t\tdomicile.domicile_faith = {
\t\t\t\t\t\t\t\tNOT = { has_doctrine_parameter = unreformed }
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\tfaith = {
\t\t\t\t\t\t\t\thas_doctrine_parameter = unreformed
\t\t\t\t\t\t\t}
\t\t\t\t\t\t}
\t\t\t\t\t}"""


def extract_object(text: str, key: str) -> str:
	match = re.search(rf"(?m)^{re.escape(key)}\s*=\s*\{{", text)
	if not match:
		raise RuntimeError(f"Missing vanilla decision: {key}")
	start = match.start()
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
	raise RuntimeError(f"Unbalanced vanilla decision: {key}")


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
		/ "decisions"
		/ "10_nomad_culture_and_faith_decisions.txt"
	)
	target = (
		mod_root
		/ "common"
		/ "decisions"
		/ "zz_dm_compat_nomad_culture_and_faith_decisions.txt"
	)

	block = extract_object(source.read_text(encoding="utf-8-sig"), KEY)
	if block.count(OLD_COST_LIMIT) != 1:
		raise RuntimeError(f"Vanilla cost block changed in {KEY}")
	block = block.replace(OLD_COST_LIMIT, SAFE_COST_LIMIT, 1)
	header = (
		"# Synced from vanilla 1.19 10_nomad_culture_and_faith_decisions.txt.\n"
		"# Decision cost previews must not enter a missing nomad domicile scope.\n\n"
	)
	target.write_bytes(codecs.BOM_UTF8 + (header + block + "\n").encode("utf-8"))
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
