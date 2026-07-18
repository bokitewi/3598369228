#!/usr/bin/env python3
"""Write safe title localization for nomad titles during holder assignment."""

from pathlib import Path


def main() -> None:
	root = Path(__file__).resolve().parents[1]
	target = (
		root
		/ "localization"
		/ "simp_chinese"
		/ "dm_compat_nomad_l_simp_chinese.yml"
	)
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_text(
		'l_simp_chinese:\n nomad_title_name: "游牧营地"\n',
		encoding="utf-8-sig",
	)
	print(f"Wrote {target}")


if __name__ == "__main__":
	main()
