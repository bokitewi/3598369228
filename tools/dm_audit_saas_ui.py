"""Audit restored Spring-and-Autumn settlement UI, reformer row, and retainer scopes."""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import dm_generate_reform_registry as registry


ROOT = Path(__file__).resolve().parents[1]
DECISIONS = (
	"declare_new_mandate",
	"zhou_old_state_new_mandate",
	"fate_divergence",
	"new_dynasty_conquest",
)


def fail(message: str) -> None:
	raise AssertionError(message)


def balanced(path: Path) -> None:
	text = registry.strip_comments(path.read_text(encoding="utf-8-sig"))
	if text.count("{") != text.count("}"):
		fail(f"{path}: unbalanced braces")
	registry.read_script(path)


def definition_block(text: str, key: str) -> str:
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


def named_subblock(block: str, key: str) -> str:
	match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\{{", block)
	if not match:
		fail(f"definition is missing {key}")
	brace = block.index("{", match.start())
	depth = 0
	for index in range(brace, len(block)):
		if block[index] == "{":
			depth += 1
		elif block[index] == "}":
			depth -= 1
			if depth == 0:
				return block[brace : index + 1]
	fail(f"unterminated nested block: {key}")
	return ""


def check_settlement_cards() -> None:
	path = ROOT / "common/decisions/spring_and_autumn_final_settlement_decisions.txt"
	gui_path = ROOT / "gui/window_spring_and_autumn_situation.gui"
	story_gui_path = ROOT / "gui/window_situation_list.gui"
	for item in (path, gui_path, story_gui_path):
		if not item.is_file():
			fail(f"missing restored UI file: {item}")
		balanced(item)
	text = path.read_text(encoding="utf-8-sig")
	gui = gui_path.read_text(encoding="utf-8-sig")
	for key in DECISIONS:
		block = definition_block(text, key)
		shown = named_subblock(block, "is_shown")
		valid = named_subblock(block, "is_valid")
		if "situation:spring_and_autumn_situation" not in shown:
			fail(f"{key}: is_shown no longer checks the situation")
		for forbidden in ("current_phase", "has_trait", "primary_title", "highest_held_title_tier"):
			if forbidden in shown:
				fail(f"{key}: eligibility condition leaked back into is_shown: {forbidden}")
		if "custom_description" not in valid:
			fail(f"{key}: is_valid lacks explicit failure descriptions")
		if f"GetDecisionWithKey('{key}')" not in gui:
			fail(f"{key}: GUI decision card binding is missing")
		if "Decision.IsShownForPlayer" not in gui:
			fail("settlement GUI no longer uses Decision.IsShownForPlayer")
	for match in re.finditer(r"create_legend\s*=\s*\{", text):
		block = definition_block(text[match.start() :], "create_legend")
		properties = named_subblock(block, "properties")
		if "ancestor = root" not in properties or "title = title:h_huaxia" not in properties:
			fail("create_legend call has an incomplete properties block")
	story_gui = story_gui_path.read_text(encoding="utf-8-sig")
	if 'name = "dm_reform_missing_reformer"' not in story_gui:
		fail("reform story does not retain its missing-reformer row")
	if 'text = "dm_reform_no_reformer"' not in story_gui:
		fail("missing reformer row does not display 暂无改革者")


def check_situation_localization() -> None:
	path = ROOT / "localization/simp_chinese/situations/situations_l_simp_chinese.yml"
	raw = path.read_bytes()
	if not raw.startswith(b"\xef\xbb\xbf"):
		fail("situation Simplified Chinese localization lost its UTF-8 BOM")
	text = raw.decode("utf-8-sig")
	required = (
		"spring_and_autumn_situation_type_desc",
		"spring_and_autumn_situation_desc",
		"spring_and_autumn_huaxia_sub_region_desc",
		"SAAS_ENDING_DECISION_LOCKED_HINT",
		"saas_requires_warring_states_phase_tt",
		"saas_requires_zhou_reborn_phase_tt",
	)
	for key in required:
		if not re.search(rf"(?m)^\s*{re.escape(key)}:", text):
			fail(f"missing situation localization key: {key}")
	keys = re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+):\d*\s", text)
	duplicates = [key for key, count in Counter(keys).items() if count > 1]
	if duplicates:
		fail("duplicate situation localization keys: " + ", ".join(duplicates[:20]))


def check_retainer_character_scopes() -> None:
	events_path = ROOT / "events/saas_retainer_events.txt"
	loc_path = ROOT / "localization/simp_chinese/saas_retainer_l_simp_chinese.yml"
	for path in (events_path, loc_path):
		if not path.is_file():
			fail(f"missing retainer file: {path}")
	events = events_path.read_text(encoding="utf-8-sig")
	loc = loc_path.read_text(encoding="utf-8-sig")
	# Saved event scopes are character data types in localization and therefore
	# use [retainer.Get...] rather than the invalid [scope:retainer.Get...].
	for invalid in ("[scope:retainer.", "[scope:neighboring_ruler."):
		if invalid in loc:
			fail(f"invalid event-localization data_type invocation remains: {invalid}")
	for valid in ("[retainer.GetShortUIName]", "[neighboring_ruler.GetShortUIName]"):
		if valid not in loc:
			fail(f"retainer localization is missing saved-character scope call: {valid}")
	for saved in ("save_scope_as = retainer", "save_scope_as = neighboring_ruler"):
		if saved not in events:
			fail(f"retainer event chain does not save its localization character scope: {saved}")
	balanced(events_path)


def main() -> int:
	check_settlement_cards()
	check_situation_localization()
	check_retainer_character_scopes()
	print(
		"SAAS UI audit OK: four settlement cards, legend properties, permanent "
		"reformer row, Simplified Chinese keys, retainer character data_type scopes"
	)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except AssertionError as error:
		print(f"SAAS UI AUDIT FAILED: {error}", file=sys.stderr)
		raise SystemExit(1)
