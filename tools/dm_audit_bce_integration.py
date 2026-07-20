#!/usr/bin/env python3
"""Strict, read-only audit for the embedded BCE integration."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import dm_generate_bce_integration as gen


ROOT = gen.ROOT
EXPECTED_REGIONS = 13
EXPECTED_RULES = {
	"bce_noble_family_title": "default_noble_family_title",
	"bce_create_cadet_branch": "default_create_cadet_branch",
}
TRADITIONAL_ONLY = set("國紋貴頭銜預設啟創圖樣與為會將")


def fail(message: str) -> None:
	raise AssertionError(message)


def active_txt(directory: Path) -> list[Path]:
	return list(directory.glob("*.txt"))


def top_key_count(paths: list[Path], key: str) -> int:
	count = 0
	pattern = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=\s*\{{")
	for path in paths:
		count += len(pattern.findall(gen.mask_comments(gen.read(path))))
	return count


def check_source_manifest() -> dict[str, object]:
	data = json.loads(gen.read(gen.MANIFEST))
	if data.get("bce_version") != gen.EXPECTED_BCE_VERSION:
		fail("manifest BCE version mismatch")
	if data.get("asset_count") != 4055:
		fail(f"embedded BCE asset count is {data.get('asset_count')}, expected 4055")
	for item in data["structural_sources"].values():
		path = ROOT / item["path"]
		if not path.exists() or gen.sha256(path) != item["sha256"]:
			fail(f"BCE structural source drift: {item['path']}")
	return data


def check_single_authorities() -> None:
	if top_key_count(active_txt(gen.NAME_DIR), "name_list_han") != 1:
		fail("name_list_han must have exactly one active definition")
	if top_key_count(active_txt(gen.TRIGGER_DIR), "has_recognizable_chinese_seal") != 1:
		fail("has_recognizable_chinese_seal must have exactly one active definition")
	if top_key_count(active_txt(gen.LIST_DIR), "colored_emblem_texture_lists") != 1:
		fail("colored_emblem_texture_lists must have exactly one active definition")
	if top_key_count(active_txt(gen.COA_DIR), "template") != 1:
		fail("random CoA template wrapper must have exactly one active definition")
	for path in gen.SOURCE_RENAMES:
		if path.exists() and path not in (gen.COLORED_LIST, gen.DYNASTY_LOC_ACTIVE):
			fail(f"legacy BCE source still loads: {path.relative_to(ROOT)}")


def check_balanced_files() -> None:
	for path in (
		gen.COA_ACTIVE,
		gen.COLORED_LIST,
		gen.NAME_ACTIVE,
		gen.TRIGGER_ACTIVE,
		ROOT / "common/scripted_effects/00_decisions_effects.txt",
		ROOT / "common/game_rules/bce_game_rules.txt",
	):
		text = gen.mask_comments(gen.read(path))
		depth = 0
		quoted = False
		for index, char in enumerate(text):
			if char == '"':
				quoted = not quoted
			elif not quoted and char == "{":
				depth += 1
			elif not quoted and char == "}":
				depth -= 1
				if depth < 0:
					fail(f"negative brace depth in {path.relative_to(ROOT)} at {index}")
		if quoted or depth:
			fail(f"unbalanced script file {path.relative_to(ROOT)}: depth={depth}, quote={quoted}")


def check_textures() -> int:
	existing = gen.all_texture_names()
	vanilla_gfx = Path(r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game\gfx")
	if vanilla_gfx.exists():
		existing.update(path.name for path in vanilla_gfx.rglob("*.dds"))
	files = [
		gen.COA_ACTIVE,
		gen.COLORED_LIST,
		ROOT / "common/coat_of_arms/coat_of_arms/max_random_templates.txt",
	]
	refs: set[str] = set()
	for path in files:
		refs.update(re.findall(r'"([^"]+\.dds)"', gen.mask_comments(gen.read(path))))
	missing = sorted(ref for ref in refs if Path(ref).name not in existing)
	if missing:
		fail(f"{len(missing)} missing CoA textures, first: {missing[:5]}")
	return len(refs)


def check_titles() -> dict[str, int]:
	titles, order = gen.parse_titles(gen.read(gen.LAND_FILE))
	regions = gen.title_region_map(titles, gen.read(gen.REGION_FILE))
	targets = {key for key in order if key in regions and key[0] in "edkc"}
	if len({regions[key] for key in targets}) != EXPECTED_REGIONS:
		fail("not all thirteen East Asia regions are covered")
	generated = gen.coa_blocks(gen.COA_ACTIVE)
	protected = gen.protected_coas()
	missing = sorted(targets - generated.keys() - protected.keys())
	if missing:
		fail(f"{len(missing)} East Asia county+ titles lack CoAs: {missing[:8]}")
	if any(key.startswith("b_") for key in generated):
		fail("bulk barony CoA generation is forbidden")
	outside = sorted(set(generated) - targets)
	if outside:
		fail(f"generated CoAs escaped world_asia_east: {outside[:8]}")
	return {
		"east_asia_county_plus": len(targets),
		"generated_or_mapped": len(generated),
		"protected": len(targets & protected.keys()),
	}


def check_surnames() -> dict[str, int]:
	loc = gen.load_localization()
	source = gen.read(gen.TRIGGER_BCE_SOURCE)
	recognized = gen.recognizable_names(source)
	_, _, seal_body = gen.nested_named_block(gen.read(gen.COLORED_SOURCE), "chinese_seal_name")
	texture_keys = gen.selection_texture_map(seal_body)
	by_name: dict[str, list[str]] = {}
	for key in recognized:
		if key not in texture_keys:
			continue
		name = gen.chinese_simplified(gen.localized_or_encoded_name(key, loc))
		if name:
			by_name.setdefault(name, []).append(key)
	mapped = 0
	unmatched = 0
	active_trigger = gen.read(gen.TRIGGER_ACTIVE)
	active_lists = gen.read(gen.COLORED_LIST)
	for key in gen.dynasty_names(loc):
		name = gen.chinese_simplified(loc[key])
		if name in by_name:
			mapped += 1
			if not re.search(rf'has_base_name\s*=\s*"{re.escape(key)}"', active_trigger):
				fail(f"mapped surname absent from recognizable trigger: {key}")
			if not re.search(rf'has_base_name\s*=\s*"{re.escape(key)}"', active_lists):
				fail(f"mapped surname absent from BCE texture selection: {key}")
		else:
			unmatched += 1
			if re.search(rf'has_base_name\s*=\s*"{re.escape(key)}"', active_lists):
				fail(f"unsupported surname was assigned a BCE texture: {key}")
	return {"mapped": mapped, "unmatched": unmatched}


def check_rules_and_localization() -> None:
	rules = gen.read(ROOT / "common/game_rules/bce_game_rules.txt")
	for rule, default in EXPECTED_RULES.items():
		m = re.search(
			rf"(?ms)^\s*{re.escape(rule)}\s*=\s*\{{(.*?)^\s*\}}",
			rules,
		)
		if not m or not re.search(rf"\bdefault\s*=\s*{re.escape(default)}\b", m.group(1)):
			fail(f"missing BCE rule/default: {rule} -> {default}")
	effect = gen.read(ROOT / "common/scripted_effects/00_decisions_effects.txt")
	if "DM_BCE_CADET_RULE_BEGIN" not in effect:
		fail("current 1.19 cadet effect is not wired to the BCE branch rule")
	for path in (
		gen.LOC_DIR / "bce_game_rules_l_simp_chinese.yml",
		gen.LOC_DIR / "max_coa_designer_l_simp_chinese.yml",
		gen.DYNASTY_LOC_ACTIVE,
	):
		text = gen.read(path)
		bad = sorted(TRADITIONAL_ONLY & set(text))
		if bad:
			fail(f"Traditional-only BCE localization remains in {path.name}: {bad}")
		for line in text.splitlines():
			match = gen.LOC_RE.match(line)
			if match and gen.chinese_simplified(match.group(2)) != match.group(2):
				fail(f"non-simplified BCE localization remains: {path.name}:{match.group(1)}")
		if "BCE" not in text:
			if path != gen.DYNASTY_LOC_ACTIVE:
				fail(f"BCE branding missing in {path.name}")


def check_duplicate_localization() -> None:
	keys: list[str] = []
	for path in gen.LOC_DIR.rglob("*.yml"):
		for line in gen.read(path).splitlines():
			m = gen.LOC_RE.match(line)
			if m:
				keys.append(m.group(1))
	duplicates = [key for key, count in Counter(keys).items() if count > 1 and key.startswith(("rule_bce_", "setting_", "COA_DESIGNER_CATEGORY_MAX"))]
	if duplicates:
		fail(f"duplicate BCE localization keys: {duplicates[:10]}")


def main() -> int:
	try:
		check_source_manifest()
		check_single_authorities()
		check_balanced_files()
		texture_count = check_textures()
		title_stats = check_titles()
		surname_stats = check_surnames()
		check_rules_and_localization()
		check_duplicate_localization()
		# The generator check is the final drift assertion and is read-only.
		gen.run(check=True)
	except Exception as exc:
		print(f"ERROR: {exc}", file=sys.stderr)
		return 1
	print("BCE integration audit passed")
	print(json.dumps({
		"textures_referenced": texture_count,
		"titles": title_stats,
		"surnames": surname_stats,
	}, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
