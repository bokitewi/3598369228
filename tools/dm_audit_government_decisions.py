"""Audit government-reform laws and disabled direct conversion decisions."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import dm_generate_reform_registry as registry


ROOT = Path(__file__).resolve().parents[1]
LAW_TO_GOVERNMENT = {
	"dm_government_reform_feudal_law": "feudal_government",
	"dm_government_reform_republic_law": "republic_government",
	"dm_government_reform_theocracy_law": "theocracy_government",
	"dm_government_reform_clan_law": "clan_government",
	"dm_government_reform_tribal_law": "tribal_government",
	"dm_government_reform_wanua_law": "wanua_government",
	"dm_government_reform_administrative_law": "administrative_government",
	"dm_government_reform_feudal_admin_law": "feudal_admin_government",
	"dm_government_reform_celestial_law": "celestial_government",
	"dm_government_reform_mandala_law": "mandala_government",
	"dm_government_reform_meritocratic_law": "meritocratic_government",
	"dm_government_reform_japan_administrative_law": "japan_administrative_government",
	"dm_government_reform_japan_feudal_law": "japan_feudal_government",
	"dm_government_reform_nomad_law": "nomad_government",
	"dm_government_reform_steppe_admin_law": "steppe_admin_government",
}


def fail(message: str) -> None:
	raise AssertionError(message)


def block(text: str, key: str) -> str:
	match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\{{", text)
	if not match:
		fail(f"missing definition: {key}")
	brace = text.index("{", match.start())
	depth = 0
	quoted = False
	for index in range(brace, len(text)):
		char = text[index]
		if char == '"':
			quoted = not quoted
		elif not quoted and char == "{":
			depth += 1
		elif not quoted and char == "}":
			depth -= 1
			if depth == 0:
				return text[brace : index + 1]
	fail(f"unterminated definition: {key}")
	return ""


def check_script(path: Path) -> str:
	if not path.is_file():
		fail(f"missing required file: {path}")
	registry.read_script(path)
	text = path.read_text(encoding="utf-8-sig")
	if registry.strip_comments(text).count("{") != registry.strip_comments(text).count("}"):
		fail(f"{path}: unbalanced braces")
	return text


def check_laws() -> None:
	path = ROOT / "common/laws/dm_government_reform_laws.txt"
	text = check_script(path)
	group = block(text, "dm_government_reform_law_group")
	if "@dm_government_reform_cost = 2000" not in text:
		fail("government reform does not use the fixed 2000 prestige cost")
	for law, government in LAW_TO_GOVERNMENT.items():
		law_block = block(group, law)
		for marker in (
			"flag = dm_government_reform_law",
			f"should_start_with = {{ has_government = {government} }}",
			f"NOT = {{ has_government = {government} }}",
			"pass_cost = { prestige = @dm_government_reform_cost }",
			"dm_government_reform_change_government_effect",
		):
			if marker not in law_block:
				fail(f"{law}: missing government-reform marker {marker}")
	if text.count("custom_description = { text = dm_government_reform_requires_") != 9:
		fail("DLC-dependent targets must remain visible and expose nine gray failure gates")
	for risky in ("republic", "theocracy"):
		interaction = (
			ROOT / "common/character_interactions/dm_reform_start_interactions_generated.txt"
		).read_text(encoding="utf-8-sig")
		iblock = block(interaction, f"dm_reform_start_dm_government_reform_{risky}_law_interaction")
		if "dm_government_reform_risk_warning" not in iblock:
			fail(f"{risky} target lacks its red playability warning")


def check_disabled_decisions() -> None:
	path = ROOT / "common/decisions/zzz_dm_disabled_government_conversion_decisions.txt"
	text = check_script(path)
	keys = re.findall(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{", text)
	if len(keys) != 25 or len(set(keys)) != 25:
		fail(f"disabled direct government decisions: expected 25 unique keys, got {len(keys)}")
	for key in keys:
		decision = block(text, key)
		if "is_shown = { always = no }" not in decision:
			fail(f"{key}: direct government conversion is not hidden")
	if "decision_convert_to_feudal_admin" not in keys:
		fail("the mod's feudal-administrative direct conversion remains enabled")
	if "adopt_nomadic_ways_decision" in keys:
		fail("landless adventure exit was incorrectly disabled")


def check_conversion_and_sync() -> None:
	effects = check_script(ROOT / "common/scripted_effects/dm_government_reform_effects.txt")
	triggers = check_script(ROOT / "common/scripted_triggers/dm_government_reform_triggers.txt")
	on_action = check_script(ROOT / "common/on_action/dm_government_reform_on_actions.txt")
	for marker in (
		"dm_government_reform_change_government_effect = {",
		"dm_government_reform_apply_authority_effect = {",
		"dm_government_reform_sync_law_effect = {",
		"dm_government_reform_on_government_change_effect = {",
		"add_realm_law_skip_effects",
		"dm_government_reform_applying",
	):
		if marker not in effects:
			fail(f"government conversion/sync chain missing {marker}")
	if "on_government_change" not in on_action or "dm_government_reform_on_government_change_effect" not in on_action:
		fail("native on_government_change is not connected to reform synchronization")
	if "dm_government_reform_supported_government_trigger" not in triggers:
		fail("supported landed government whitelist is missing")
	for forbidden in ("every_vassal", "every_direct_vassal", "every_realm_county"):
		if forbidden in effects:
			fail(f"government reform illegally bulk-mutates the realm: {forbidden}")
	for mapping in (
		"has_realm_law = nomadic_authority_1",
		"has_realm_law = nomadic_authority_2",
		"has_realm_law = nomadic_authority_3",
		"has_realm_law = nomadic_authority_4",
		"has_realm_law = nomadic_authority_5",
		"mandala_decree_none",
	):
		if mapping not in effects:
			fail(f"authority-law conversion table is incomplete: {mapping}")
	if effects.count("dm_government_reform_cooldown") != 0:
		fail("20-year outcome cooldown belongs in terminal reform effects, not conversion plumbing")
	terminal = (ROOT / "common/scripted_effects/dm_reform_effects.txt").read_text(
		encoding="utf-8-sig"
	)
	if terminal.count("flag = dm_government_reform_cooldown") != 4:
		fail("government reform cooldown must be applied by exactly four non-neutral outcomes")


def check_localization() -> None:
	path = ROOT / "localization/simp_chinese/dm_government_reform_l_simp_chinese.yml"
	raw = path.read_bytes()
	if not raw.startswith(b"\xef\xbb\xbf"):
		fail("government reform Simplified Chinese localization lost its BOM")
	text = raw.decode("utf-8-sig")
	for law in LAW_TO_GOVERNMENT:
		for key in (law, f"{law}_desc"):
			if not re.search(rf"(?m)^\s*{re.escape(key)}:", text):
				fail(f"government reform localization missing {key}")
	for target in ("republic", "theocracy"):
		key = f"dm_government_reform_{target}_law_desc"
		line = next((line for line in text.splitlines() if key in line), "")
		if "#X" not in line or "失去可玩性" not in line:
			fail(f"{target} localization lacks the red playability warning")


def main() -> int:
	check_laws()
	check_disabled_decisions()
	check_conversion_and_sync()
	check_localization()
	print(
		"government decision audit OK: 15 reform laws, 25 hidden direct conversions, "
		"DLC gates, authority mapping, personal-only adaptation, native sync, cooldowns"
	)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except AssertionError as error:
		print(f"GOVERNMENT DECISION AUDIT FAILED: {error}", file=sys.stderr)
		raise SystemExit(1)
