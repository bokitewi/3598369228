#!/usr/bin/env python3
"""Give compatibility holy-site keys an inert but structurally valid map anchor."""

from __future__ import annotations

import codecs
import re
from pathlib import Path


TOP_LEVEL_EMPTY_OBJECT = re.compile(
	r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{\s*\}\s*(?:#.*)?$"
)


def main() -> None:
	mod_root = Path(__file__).resolve().parents[1]
	path = (
		mod_root
		/ "common"
		/ "religion"
		/ "holy_site_types"
		/ "dm_compat_holy_sites.txt"
	)
	keys: list[str] = []
	for line in path.read_text(encoding="utf-8-sig").splitlines():
		match = TOP_LEVEL_EMPTY_OBJECT.match(line.strip())
		if match and match.group(1) != "key":
			keys.append(match.group(1))

	if not keys:
		raise SystemExit("No empty compatibility holy-site objects were found")

	lines = [
		"# Compatibility-only holy-site database keys.",
		"# Their faith links are deliberately removed; the shared anchor only satisfies",
		"# the 1.19 holy_site_type schema and cannot activate them in gameplay.",
		"",
	]
	for key in sorted(set(keys)):
		lines.extend(
			[
				f"{key} = {{",
				"\tcounty = c_wangcheng",
				"\tbarony = b_793_0",
				"}",
				"",
			]
		)

	payload = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
	path.write_bytes(codecs.BOM_UTF8 + payload)
	print(f"Mapped {len(set(keys))} compatibility holy-site keys to c_wangcheng/b_793_0")


if __name__ == "__main__":
	main()
