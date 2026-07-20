"""Generate missing Simplified Chinese adjective keys for landed titles."""

from __future__ import annotations

import argparse
import codecs
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TITLE_ROOT = ROOT / "common" / "landed_titles"
LOC_ROOT = ROOT / "localization" / "simp_chinese"
VANILLA_LOC_ROOT = Path(
	r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
) / "localization" / "simp_chinese"
OUTPUT = LOC_ROOT / "dm_generated_title_adj_l_simp_chinese.yml"
TITLE_RE = re.compile(r"^\s*([ekdcbh]_[A-Za-z0-9_]+)\s*=\s*\{")
LOC_RE = re.compile(r'^\s*([A-Za-z0-9_.-]+):\d*\s+"(.*)"\s*(?:#.*)?$')
HASH_COLLISION_KEYS = {
	# These three keys collide with existing CK3 localization hashes. Defining
	# them would overwrite unrelated text at runtime, so the title-name fallback
	# is safer than emitting an adjective entry.
	"b_1560_0_adj",
	"b_2676_0_adj",
	"c_tengshushi_adj",
	"c_yangjiao_adj",
}


def title_keys() -> set[str]:
	result: set[str] = set()
	for path in sorted(TITLE_ROOT.glob("*.txt")):
		for line in path.read_text(encoding="utf-8-sig").splitlines():
			match = TITLE_RE.match(line)
			if match:
				result.add(match.group(1))
	return result


def localization() -> dict[str, str]:
	result: dict[str, str] = {}
	for root in (VANILLA_LOC_ROOT, LOC_ROOT):
		for path in sorted(root.rglob("*.yml")):
			if path == OUTPUT:
				continue
			for line in path.read_text(encoding="utf-8-sig").splitlines():
				match = LOC_RE.match(line)
				if match:
					result[match.group(1)] = match.group(2)
	return result


def render() -> bytes:
	keys = title_keys()
	loc = localization()
	missing_names = sorted(key for key in keys if key not in loc)
	if missing_names:
		raise RuntimeError(
			"landed titles still lack base Simplified Chinese names: "
			+ ", ".join(missing_names)
		)
	rows = [
		(key + "_adj", loc[key])
		for key in sorted(keys)
		if key + "_adj" not in loc and key + "_adj" not in HASH_COLLISION_KEYS
	]
	lines = [
		"l_simp_chinese:",
		"# Generated: CK3 title adjectives reuse the corresponding Chinese name.",
	]
	lines.extend(f' {key}:0 "{value}"' for key, value in rows)
	return codecs.BOM_UTF8 + ("\n".join(lines) + "\n").encode("utf-8")


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--check", action="store_true")
	args = parser.parse_args()
	expected = render()
	if args.check:
		if not OUTPUT.is_file() or OUTPUT.read_bytes() != expected:
			raise SystemExit("generated title adjective localization drifted")
		print("generated title adjective localization check OK")
		return
	OUTPUT.write_bytes(expected)
	print(f"generated {expected.count(b':0 ')} title adjective keys")


if __name__ == "__main__":
	main()
