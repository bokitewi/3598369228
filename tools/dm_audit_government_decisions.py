"""Audit government-reform targets, paths, UI and disabled conversion decisions."""

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
TARGET_LAWS = {
	"primitive": {
		"dm_government_reform_nomad_law",
		"dm_government_reform_tribal_law",
		"dm_government_reform_wanua_law",
	},
	"feudal": {
		"dm_government_reform_clan_law",
		"dm_government_reform_feudal_law",
	},
	"administrative": {
		"dm_government_reform_feudal_admin_law",
		"dm_government_reform_celestial_law",
		"dm_government_reform_meritocratic_law",
	},
	"special": {
		"dm_government_reform_mandala_law",
		"dm_government_reform_republic_law",
	},
}
SELECTABLE_LAWS = set().union(*TARGET_LAWS.values())
STATE_ONLY_LAWS = set(LAW_TO_GOVERNMENT) - SELECTABLE_LAWS
PATH_TRIGGER = {
	"primitive": "dm_government_reform_can_target_primitive_trigger = yes",
	"feudal": "dm_government_reform_can_target_feudal_trigger = yes",
	"administrative": "dm_government_reform_can_target_administrative_trigger = yes",
	"special": "dm_government_reform_can_target_special_trigger = yes",
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


def compact(text: str) -> str:
	return " ".join(text.split())


def government_set(script_block: str) -> set[str]:
	return set(re.findall(r"has_government\s*=\s*([A-Za-z0-9_]+)", script_block))


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
	if re.search(r"(?m)^\s*flag\s*=\s*realm_law\s*$", group):
		fail("government reform is incorrectly routed to the Crown Authority icon row")
	if "flag = dm_government_reform_law_group" not in group:
		fail("government reform law group lacks its dedicated routing flag")
	for law, government in LAW_TO_GOVERNMENT.items():
		law_block = block(group, law)
		for marker in (
			"flag = dm_government_reform_law",
			f"should_start_with = {{ has_government = {government} }}",
			"pass_cost = { prestige = @dm_government_reform_cost }",
			"dm_government_reform_change_government_effect",
		):
			if marker not in law_block:
				fail(f"{law}: missing government-reform marker {marker}")
	for category, laws in TARGET_LAWS.items():
		for law in laws:
			expected = (
				"dm_government_reform_can_target_feudal_admin_trigger = yes"
				if law == "dm_government_reform_feudal_admin_law"
				else PATH_TRIGGER[category]
			)
			if expected not in block(group, law):
				fail(f"{law}: missing transition path {expected}")
	for law in STATE_ONLY_LAWS:
		if "can_pass = { always = no }" not in compact(block(group, law)):
			fail(f"{law}: excluded government law is not state-only")
	if text.count("custom_description = { text = dm_government_reform_requires_") != 5:
		fail("the ten selectable targets must expose exactly five DLC failure gates")
	interactions = check_script(
		ROOT / "common/character_interactions/dm_reform_start_interactions_generated.txt"
	)
	for law in SELECTABLE_LAWS:
		interaction = block(interactions, f"dm_reform_start_{law}_interaction")
		if law == "dm_government_reform_republic_law" and "dm_government_reform_risk_warning" not in interaction:
			fail("republic target lacks its red playability warning")
	for law in STATE_ONLY_LAWS:
		if f"dm_reform_start_{law}_interaction" in interactions:
			fail(f"{law}: excluded government was generated as a target")


def check_realm_law_gui() -> None:
	path = ROOT / "gui/00_window_my_realm_M_COPF.gui"
	text = check_script(path)
	route = "GuiLawGroup.GetLawGroup.HasFlag( 'dm_government_reform_law_group' )"
	if text.count(route) != 1:
		fail("government reform must be routed exactly once into the lower law list")
	vanilla_realm_gui = check_script(registry.VANILLA / "gui/window_my_realm.gui")
	if "OpenSuccessionLawChangeWindow( GuiLawGroup.Self )" not in vanilla_realm_gui:
		fail("lower law rows no longer open the existing law-selection window")
	change_window = check_script(ROOT / "gui/window_succession_change_law.gui")
	for law in SELECTABLE_LAWS:
		interaction = f"dm_reform_start_{law}_interaction"
		if change_window.count(interaction) != 2:
			fail(f"{law}: selection window lacks its custom interaction binding")
	for law in STATE_ONLY_LAWS:
		if f"dm_reform_start_{law}_interaction" in change_window:
			fail(f"{law}: excluded target leaked into selection actions")
	if "GuiLaw.Enact" in change_window:
		fail("government reform selection can still enact a law directly")
	for category in TARGET_LAWS:
		if change_window.count(f'dm_government_reform_category_{category}') != 1:
			fail(f"{category}: category heading is missing or duplicated")
		category_pattern = re.compile(
			r"vbox\s*=\s*\{(?:(?!\n\s*vbox\s*=\s*\{).)*"
			rf'text\s*=\s*"dm_government_reform_category_{category}".*?'
			r'hbox\s*=\s*\{\s*datamodel\s*=\s*"\[SuccessionLawChangeWindow.GetOtherLaws\]"',
			re.DOTALL,
		)
		if not category_pattern.search(change_window):
			fail(f"{category}: category title is not placed above its government row")
	if change_window.count("dm_government_reform_category_locked") != 4:
		fail("all four categories must retain a locked-row explanation")
	if change_window.count("maximumsize = { -1 110 }") != 4:
		fail("government categories lack the four compact vertical bounds")
	if change_window.count('visible = "[And( And(') != 4:
		fail("category target rows do not combine category and transition visibility")
	category_tail = change_window.find("dm_government_reform_category_special")
	if category_tail < 0 or "expand = {}" not in change_window[category_tail:]:
		fail("government category list lacks its trailing expansion spacer")
	if change_window.count("SuccessionLawChangeWindow.GetOtherLaws") < 6:
		fail("four category rows are not bound to the native law data model")
	if "Not( EqualTo_string( GuiLaw.GetLaw.GetKey" not in change_window:
		fail("current government is not filtered out of the target rows")


def check_disabled_decisions() -> None:
	path = ROOT / "common/decisions/zzz_dm_disabled_government_conversion_decisions.txt"
	text = check_script(path)
	keys = re.findall(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{", text)
	if len(keys) != 25 or len(set(keys)) != 25:
		fail(f"disabled direct government decisions: expected 25 unique keys, got {len(keys)}")
	for key in keys:
		if "is_shown = { always = no }" not in block(text, key):
			fail(f"{key}: direct government conversion is not hidden")
	if "decision_convert_to_feudal_admin" not in keys:
		fail("the mod's direct feudal-administrative conversion remains enabled")
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
	for marker in (
		"dm_government_reform_supported_government_trigger",
		"dm_government_reform_selectable_government_trigger",
		"dm_government_reform_excluded_source_trigger",
		"dm_government_reform_can_target_primitive_trigger",
		"dm_government_reform_can_target_feudal_trigger",
		"dm_government_reform_can_target_administrative_trigger",
		"dm_government_reform_can_target_special_trigger",
		"dm_government_reform_can_target_feudal_admin_trigger",
	):
		if marker not in triggers:
			fail(f"government transition matrix missing {marker}")
	expected_selectable = {LAW_TO_GOVERNMENT[law] for law in SELECTABLE_LAWS}
	expected_excluded = {LAW_TO_GOVERNMENT[law] for law in STATE_ONLY_LAWS}
	if government_set(block(triggers, "dm_government_reform_selectable_government_trigger")) != expected_selectable:
		fail("selectable-government whitelist differs from the ten approved targets")
	if government_set(block(triggers, "dm_government_reform_excluded_source_trigger")) != expected_excluded:
		fail("excluded-source whitelist differs from the five approved governments")
	if government_set(block(triggers, "dm_government_reform_can_target_primitive_trigger")) != {
		"nomad_government", "tribal_government", "wanua_government"
	}:
		fail("primitive transition row does not enforce same-class origins")
	if government_set(block(triggers, "dm_government_reform_can_target_administrative_trigger")) != {
		"clan_government", "feudal_government", "feudal_admin_government",
		"celestial_government", "meritocratic_government", "mandala_government",
		"republic_government",
	}:
		fail("administrative/special transition origins differ from the approved matrix")
	fallback = block(triggers, "dm_government_reform_can_target_feudal_admin_trigger")
	for marker in ("is_ai = no", "dm_government_reform_excluded_source_trigger = yes"):
		if marker not in fallback:
			fail(f"excluded-government player fallback missing {marker}")
	story_targets = block(triggers, "dm_reform_is_government_reform_trigger")
	for law in STATE_ONLY_LAWS:
		if f"var:dm_reform_target = flag:{law}" in story_targets:
			fail(f"{law}: excluded government remains a story target")
	on_change = compact(block(effects, "dm_government_reform_on_government_change_effect"))
	if "NOT = { dm_government_reform_selectable_government_trigger = yes }" not in on_change:
		fail("external switch to a non-selectable government does not neutral-end reform")
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
		fail("outcome cooldown belongs in terminal effects, not conversion plumbing")
	terminal = (ROOT / "common/scripted_effects/dm_reform_effects.txt").read_text(encoding="utf-8-sig")
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
	for key in (
		"dm_government_reform_category_help",
		"dm_government_reform_category_primitive",
		"dm_government_reform_category_feudal",
		"dm_government_reform_category_administrative",
		"dm_government_reform_category_special",
		"dm_government_reform_category_locked",
		"dm_government_reform_exception_help",
	):
		if not re.search(rf"(?m)^\s*{re.escape(key)}:", text):
			fail(f"government reform localization missing {key}")
	republic = next(
		(line for line in text.splitlines() if "dm_government_reform_republic_law_desc" in line),
		"",
	)
	if "#X" not in republic or "失去可玩性" not in republic:
		fail("republic localization lacks the red playability warning")


def main() -> int:
	check_laws()
	check_realm_law_gui()
	check_disabled_decisions()
	check_conversion_and_sync()
	check_localization()
	print(
		"government decision audit OK: 15 synchronized government states, 10 selectable "
		"targets in four categories, transition matrix and player-only fallback, 25 hidden "
		"direct conversions, authority mapping, native sync and cooldowns"
	)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except AssertionError as error:
		print(f"GOVERNMENT DECISION AUDIT FAILED: {error}", file=sys.stderr)
		raise SystemExit(1)
