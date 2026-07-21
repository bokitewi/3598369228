"""Strict static acceptance checks for the 大梦春秋 reform system."""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import dm_generate_reform_registry as registry


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATHS = [
	ROOT / "common/character_interactions/dm_reform_interactions.txt",
	ROOT / "common/character_interactions/dm_reform_start_interactions_generated.txt",
	ROOT / "common/customizable_localization/dm_reform_actor_office_custom_loc.txt",
	ROOT / "common/decisions/dm_reform_decisions.txt",
	ROOT / "common/on_action/dm_government_reform_on_actions.txt",
	ROOT / "common/script_values/dm_reform_values.txt",
	ROOT / "common/scripted_effects/dm_reform_effects.txt",
	ROOT / "common/scripted_effects/dm_government_reform_effects.txt",
	ROOT / "common/scripted_effects/dm_reform_registry_effects_generated.txt",
	ROOT / "common/scripted_triggers/dm_reform_triggers.txt",
	ROOT / "common/scripted_triggers/dm_government_reform_triggers.txt",
	ROOT / "common/scripted_triggers/dm_reform_registry_triggers_generated.txt",
	ROOT / "common/story_cycles/dm_reform_story_cycle.txt",
	ROOT / "events/dm_reform_events.txt",
	ROOT / "events/dm_reform_events_generated.txt",
]
GUI_PATHS = [
	ROOT / "gui/window_succession_change_law.gui",
	ROOT / "gui/window_treasury_budget_change.gui",
	ROOT / "gui/window_situation_list.gui",
]
LOC_PATHS = [
	ROOT / "localization/simp_chinese/dm_reform_l_simp_chinese.yml",
	ROOT / "localization/simp_chinese/dm_reform_events_generated_l_simp_chinese.yml",
	ROOT / "localization/simp_chinese/dm_government_reform_l_simp_chinese.yml",
]
EVENT_RE = re.compile(r"(?m)^\s*(dm_reform\.(\d+))\s*=\s*\{")
LOC_RE = re.compile(r"(?m)^\s*([A-Za-z0-9_.-]+):\d*\s")


def fail(message: str) -> None:
	raise AssertionError(message)


def stripped(path: Path) -> str:
	return registry.strip_comments(path.read_text(encoding="utf-8-sig"))


def check_balanced(path: Path) -> None:
	text = stripped(path)
	depth = 0
	quoted = False
	escaped = False
	for offset, char in enumerate(text):
		if quoted:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
			continue
		if char == '"':
			quoted = True
		elif char == "{":
			depth += 1
		elif char == "}":
			depth -= 1
			if depth < 0:
				fail(f"{path}: brace underflow at {offset}")
	if quoted or depth:
		fail(f"{path}: unterminated quote or brace depth {depth}")


def block_at(text: str, brace: int) -> str:
	depth = 0
	quoted = False
	escaped = False
	for index in range(brace, len(text)):
		char = text[index]
		if quoted:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
			continue
		if char == '"':
			quoted = True
		elif char == "{":
			depth += 1
		elif char == "}":
			depth -= 1
			if depth == 0:
				return text[brace : index + 1]
	fail("unterminated extracted block")
	return ""


def direct_key_count(block: str, key: str) -> int:
	depth = 1
	quoted = False
	count = 0
	for line in block.splitlines()[1:-1]:
		clean = line.split("#", 1)[0]
		if not quoted and depth == 1 and re.match(rf"\s*{re.escape(key)}\s*=", clean):
			count += 1
		for char in clean:
			if char == '"':
				quoted = not quoted
			elif not quoted and char == "{":
				depth += 1
			elif not quoted and char == "}":
				depth -= 1
	return count


def check_files_and_localization() -> None:
	for path in SCRIPT_PATHS + GUI_PATHS:
		if not path.is_file():
			fail(f"missing required file: {path}")
		check_balanced(path)
		if path.suffix == ".txt":
			registry.read_script(path)
	keys: list[str] = []
	for path in LOC_PATHS:
		if not path.is_file():
			fail(f"missing localization: {path}")
		raw = path.read_bytes()
		if not raw.startswith(b"\xef\xbb\xbf"):
			fail(f"{path}: Simplified Chinese localization must retain UTF-8 BOM")
		text = raw.decode("utf-8-sig")
		if not text.startswith("l_simp_chinese:"):
			fail(f"{path}: wrong localization language header")
		if "\ufffd" in text:
			fail(f"{path}: replacement character found")
		keys.extend(key for key in LOC_RE.findall(text) if key != "l_simp_chinese")
	duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
	if duplicates:
		fail("duplicate reform localization keys: " + ", ".join(duplicates[:20]))
	required = {
		"dm_reform_story_desc",
		"dm_reform_no_reformer",
		"dm_reform_counter_message_title",
		"dm_reform_counter_message_desc",
		"dm_government_reform_law_group",
	}
	missing = sorted(required - set(keys))
	if missing:
		fail("missing reform localization keys: " + ", ".join(missing))


def check_generator_and_budget_exit() -> None:
	result = subprocess.run(
		[sys.executable, str(ROOT / "tools/dm_generate_reform_registry.py"), "--check"],
		cwd=ROOT,
		text=True,
		capture_output=True,
		check=False,
	)
	if result.returncode:
		fail(result.stdout + result.stderr)
	generated_paths = [
		ROOT / "events/dm_reform_events_generated.txt",
		ROOT / "common/character_interactions/dm_reform_start_interactions_generated.txt",
		ROOT / "common/scripted_effects/dm_reform_registry_effects_generated.txt",
		ROOT / "common/scripted_triggers/dm_reform_registry_triggers_generated.txt",
	]
	for path in generated_paths:
		text = path.read_text(encoding="utf-8-sig")
		if (
			"dm_reform_budget_" in text
			or "dm_reform_start_budget_interaction" in text
			or "dm_reform_target_is_budget" in text
		):
			fail(f"{path}: treasury budget leaked back into reform generation")
	success_dispatch = (
		ROOT / "common/scripted_effects/dm_reform_registry_effects_generated.txt"
	).read_text(encoding="utf-8-sig")
	manifest = registry.tomllib.loads(registry.MANIFEST.read_text(encoding="utf-8"))
	registered_laws, _ = registry.collect_laws(manifest)
	story_target_laws = [
		law for law in registered_laws if registry.is_reform_story_target(law)
	]
	if success_dispatch.count("limit = { NOT = { has_realm_law =") != len(story_target_laws):
		fail("success dispatch does not guard all externally pre-applied target laws")
	for law in registered_laws:
		if (
			law.group == "dm_government_reform_law_group"
			and law.key in registry.GOVERNMENT_REFORM_STATE_ONLY
			and f"var:dm_reform_target = flag:{law.key}" in success_dispatch
		):
			fail(f"{law.key}: internal government-state law leaked into success dispatch")
	treasury = (ROOT / "gui/window_treasury_budget_change.gui").read_text(
		encoding="utf-8-sig"
	)
	if "TreasuryBudgetChangeWindow.EnactBudgetLaws" not in treasury:
		fail("treasury budget window does not call the native direct enact route")
	for forbidden in ("dm_reform_select_reformer", "dm_reform_start_budget"):
		if forbidden in treasury:
			fail(f"treasury budget window retained reform control: {forbidden}")


def check_event_catalog() -> None:
	path = ROOT / "events/dm_reform_events_generated.txt"
	text = path.read_text(encoding="utf-8-sig")
	definitions = EVENT_RE.findall(text)
	if len(definitions) != 85:
		fail(f"generated event catalog has {len(definitions)} nodes, expected 85")
	entry_matches = [match for match in EVENT_RE.finditer(text) if 1101 <= int(match[2]) <= 1135]
	if len(entry_matches) != 35:
		fail("reform event catalog must contain exactly 35 entry decisions")
	for match in entry_matches:
		block = block_at(text, text.index("{", match.start()))
		if direct_key_count(block, "option") != 4:
			fail(f"{match[1]} does not expose exactly four direct options")
		for option_key in (
			"dm_reform.event.ruler_response",
			"dm_reform.event.reformer_response",
			"dm_reform.event.trait_response",
			"dm_reform.event.resource_response",
		):
			if option_key not in block:
				fail(f"{match[1]} missing option {option_key}")
	event_loc = (
		ROOT / "localization/simp_chinese/dm_reform_events_generated_l_simp_chinese.yml"
	).read_text(encoding="utf-8-sig")
	for suffix in ("ruler_tt", "reformer_tt", "trait_tt", "resource_tt"):
		if len(re.findall(rf"(?m)^\s*dm_reform\.11(?:0[1-9]|[12][0-9]|3[0-5])\.{suffix}:0\s", event_loc)) != 35:
			fail(f"generated event localization does not contain 35 exact {suffix} tooltips")
	if text.count("add = 3650") != 25 or text.count("add = 1825") != 10:
		fail("event-chain and independent-event repeat cooldown counts drifted")
	if "dm_reform_event_actor_cooldown" in text:
		fail("removed two-year actor cooldown reappeared")
	if text.count("on_trigger_fail = { trigger_event = dm_reform.0231 }") != 50:
		fail("all 50 follow-up nodes must interrupt when their real actor is invalid")
	for value in (
		"PROGRESS = -12",
		"SUPPORT = -6",
		"PROGRESS = 19",
		"SUPPORT = 6",
	):
		if value not in text:
			fail(f"final integer event result table is incomplete: {value}")
	if text.count("base = 10") < 28 or text.count("add = 60") < 28:
		fail("non-calm event actors are not personality weighted")
	calm_slice = "\n".join(
		block_at(text, text.index("{", match.start()))
		for match in entry_matches
		if 1115 <= int(match[2]) <= 1121
	)
	if "variable = dm_reform_supporters" in calm_slice or "variable = dm_reform_opponents" in calm_slice:
		fail("calm events must not read supporter/opponent lists")
	if calm_slice.count("50 = { scope:dm_reform_ruler") != 7:
		fail("all seven calm entries must give the ruler a 50-weight actor branch")
	if calm_slice.count("50 = {") < 14:
		fail("calm entries must give a valid reformer the other 50-weight actor branch")


def check_roster_pulse_notifications() -> None:
	effects = (ROOT / "common/scripted_effects/dm_reform_effects.txt").read_text(
		encoding="utf-8-sig"
	)
	values = (ROOT / "common/script_values/dm_reform_values.txt").read_text(
		encoding="utf-8-sig"
	)
	story = (ROOT / "common/story_cycles/dm_reform_story_cycle.txt").read_text(
		encoding="utf-8-sig"
	)
	for iterator in ("every_powerful_vassal", "every_councillor", "every_court_position_holder"):
		if iterator not in effects:
			fail(f"participant union is missing {iterator}")
	actor_office = (
		ROOT / "common/customizable_localization/dm_reform_actor_office_custom_loc.txt"
	).read_text(encoding="utf-8-sig")
	if "any_court_position_employer" in actor_office:
		fail("actor-office localization uses an unsupported court-position employer iterator")
	if "has_court_position =" not in actor_office:
		fail("actor-office localization does not dispatch real court-position keys")
	if "dm_reform_eligible_participants" not in effects:
		fail("participant union is not deduplicated through its temporary roster")
	if "days = { 1 7 }" not in effects:
		fail("new participants are not queued to answer in 1-7 days")
	if "is_powerful_vassal_of = scope:dm_reform_ruler" not in values or "multiply = 0.5" not in values:
		fail("pure councillor/court-position legal interest is not halved")
	for attribute in ("diplomacy", "martial", "stewardship", "intrigue", "learning", "prowess"):
		if f"dm_reform_trait_check_{attribute}_value = {{" not in values:
			fail(f"matching-trait check does not isolate qualified {attribute} hosts")
	if "days = { 70 90 }" not in story:
		fail("formal reform pulse is not 70-90 days")
	if "dm_reform_ai_quick_pulse_effect = yes" not in story:
		fail("pure-AI shortcut is not connected to the story pulse")
	for marker in (
		"dm_reform_ai_quick_choose_option_effect = {",
		"RULER_VALUE = dm_reform_ruler_check_",
		"REFORMER_VALUE = dm_reform_reformer_check_",
		"COMBINED_VALUE = dm_reform_check_",
		"story_owner = { add_$RESOURCE$ = -$COST$ }",
		"var:dm_reform_ai_check_value <= $TIER_1$",
	):
		if marker not in effects:
			fail(f"pure-AI four-option probability path is missing {marker}")
	if "dm_reform_capacity_value <= $TIER_" in effects:
		fail("pure-AI shortcut bypassed the selected ruler/reformer/trait/resource check")
	if "story_owner = { is_ai = no }" not in story or "var:dm_reform_reformer = { is_ai = no }" not in story:
		fail("visible event priority for player ruler/reformer is incomplete")
	for marker in (
		"dm_reform_apply_counter_change_effect = {",
		"dm_reform_old_progress_display",
		"floor = yes",
		"send_interface_message",
		"dm_reform_notification_score",
		"dm_reform_pending_participants",
	):
		if marker not in effects:
			fail(f"counter notification transaction is missing {marker}")


def check_reformer_data_chain() -> None:
	trigger = (ROOT / "common/scripted_triggers/dm_reform_triggers.txt").read_text(
		encoding="utf-8-sig"
	)
	effects = (ROOT / "common/scripted_effects/dm_reform_effects.txt").read_text(
		encoding="utf-8-sig"
	)
	events = (ROOT / "events/dm_reform_events.txt").read_text(encoding="utf-8-sig")
	gui = (ROOT / "gui/window_situation_list.gui").read_text(encoding="utf-8-sig")
	for stable_rule in ("is_alive = yes", "is_adult = yes", "is_imprisoned = no", "has_trait = incapable"):
		if stable_rule not in trigger:
			fail(f"stable reformer qualification missing {stable_rule}")
	if "is_available_adult" in trigger:
		fail("temporary availability leaked back into reformer validity")
	if "dm_reform_install_reformer_effect = {" not in effects:
		fail("canonical reformer installation effect is missing")
	if events.count("dm_reform_install_reformer_effect = {") < 1:
		fail("delayed invitation acceptance does not use the canonical installer")
	if "remove_list_variable" not in effects or "name = dm_reform_reformer" not in effects:
		fail("canonical reformer installer does not clean participant lists")
	for marker in (
		'name = "dm_reform_missing_reformer"',
		'text = "dm_reform_reformer_label"',
		'text = "dm_reform_no_reformer"',
	):
		if marker not in gui:
			fail(f"story card missing permanent reformer-row marker: {marker}")


def main() -> int:
	check_files_and_localization()
	check_generator_and_budget_exit()
	check_event_catalog()
	check_roster_pulse_notifications()
	check_reformer_data_chain()
	print(
		"reform audit OK: 70-90 day pulse, participant union, 35 four-option "
		"entries/85 nodes, notifications, pure-AI shortcut, budget exit, reformer UI"
	)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except AssertionError as error:
		print(f"REFORM AUDIT FAILED: {error}", file=sys.stderr)
		raise SystemExit(1)
