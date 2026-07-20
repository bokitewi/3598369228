"""Isolate vanilla-only historical character links from a total conversion.

This generator reads the current vanilla files and the selected CK3 error log.
It creates same-relative-path overrides which:

* preserve unrelated events and definitions;
* replace events containing missing vanilla character links with disabled stubs;
* preserve affected scripted-effect keys as empty effects;
* preserve affected scripted-trigger keys as always-false triggers;
* suppress the vanilla historical/developer portrait lookup tables.

The generated overrides deliberately never redirect a vanilla historical link
to a Spring-Autumn character.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(
	r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
)
ERROR_LOG = Path(
	r"E:\documents\Paradox Interactive\Crusader Kings III\crashes"
	r"\ck3_20260717_175555\logs\error.log"
)

SCRIPTED_EFFECT_FILES = (
	"common/scripted_effects/00_bookmark_effects.txt",
	"common/scripted_effects/00_ep1_inspiration_effects.txt",
	"common/scripted_effects/00_mongol_invasion_effects.txt",
	"common/scripted_effects/00_pregnancy_effects.txt",
	"common/scripted_effects/00_tributary_setup_effects.txt",
	"common/scripted_effects/01_exp1_historical_artifacts_creation_effect.txt",
	"common/scripted_effects/03_dlc_fp2_scripted_effects.txt",
	"common/scripted_effects/06_dlc_ce1_legend_effects.txt",
	"common/scripted_effects/06_dlc_ce1_legitimacy_effects.txt",
	"common/scripted_effects/07_dlc_ep3_scripted_effects.txt",
	"common/scripted_effects/"
	"07_dlc_ep3_story_cycle_adventurer_ai_scripted_effects.txt",
)

SCRIPTED_TRIGGER_FILES = (
	"common/scripted_triggers/00_game_rule_triggers.txt",
	"common/scripted_triggers/00_laamp_triggers.txt",
	"common/scripted_triggers/07_ep3_triggers.txt",
)

PORTRAIT_LOOKUP_FILES = (
	"gfx/portraits/portrait_modifiers/02_all_developer_characters.txt",
	"gfx/portraits/portrait_modifiers/02_all_historical_characters.txt",
)

CHARACTER_LINK = re.compile(r"\bcharacter:([A-Za-z0-9_]+)")
TOP_LEVEL_BLOCK = re.compile(
	r"(?m)^(?:(scripted_effect|scripted_trigger)[ \t]+)?"
	r"([A-Za-z0-9_.]+)[ \t]*=[ \t]*\{"
)


def missing_character_ids() -> set[str]:
	text = ERROR_LOG.read_text(encoding="utf-8", errors="replace")
	return set(
		re.findall(
			r"Referencing non-existent character in script link "
			r"character:([^\s\r\n]+)",
			text,
		)
	)


def block_end(text: str, opening_brace: int) -> int:
	depth = 0
	in_quote = False
	escaped = False
	index = opening_brace
	while index < len(text):
		character = text[index]
		if in_quote:
			if escaped:
				escaped = False
			elif character == "\\":
				escaped = True
			elif character == '"':
				in_quote = False
		else:
			if character == '"':
				in_quote = True
			elif character == "#":
				newline = text.find("\n", index)
				if newline < 0:
					return len(text)
				index = newline
			elif character == "{":
				depth += 1
			elif character == "}":
				depth -= 1
				if depth == 0:
					return index + 1
		index += 1
	raise RuntimeError(f"Unclosed block beginning at byte {opening_brace}")


def affected_blocks(
	text: str, missing_ids: set[str]
) -> list[tuple[int, int, str | None, str, str]]:
	result: list[tuple[int, int, str | None, str, str]] = []
	for match in TOP_LEVEL_BLOCK.finditer(text):
		start = match.start()
		end = block_end(text, match.end() - 1)
		body = text[match.end() : end - 1]
		links = set(CHARACTER_LINK.findall(body))
		if links & missing_ids:
			result.append(
				(start, end, match.group(1), match.group(2), body)
			)
	return result


def replace_blocks(
	text: str,
	blocks: list[tuple[int, int, str | None, str, str]],
	replacement,
) -> str:
	for start, end, declaration, key, body in reversed(blocks):
		text = (
			text[:start]
			+ replacement(declaration, key, body)
			+ text[end:]
		)
	return text


def event_stub(
	declaration: str | None, key: str, body: str
) -> str:
	if declaration == "scripted_effect":
		return (
			f"scripted_effect {key} = {{\n"
			"\t# Vanilla-world historical setup is intentionally disabled.\n"
			"}"
		)
	if declaration == "scripted_trigger":
		return (
			f"scripted_trigger {key} = {{\n"
			"\talways = no\n"
			"}"
		)
	event_type = re.search(
		r"(?m)^[ \t]*type[ \t]*=[ \t]*([A-Za-z0-9_]+)", body
	)
	type_key = event_type.group(1) if event_type else "character_event"
	return (
		f"{key} = {{\n"
		f"\ttype = {type_key}\n"
		"\thidden = yes\n"
		"\ttrigger = {\n"
		"\t\talways = no\n"
		"\t}\n"
		"}"
	)


def empty_effect(
	declaration: str | None, key: str, _body: str
) -> str:
	prefix = f"{declaration} " if declaration else ""
	return (
		f"{prefix}{key} = {{\n"
		"\t# Vanilla-world historical setup is intentionally disabled.\n"
		"}"
	)


def false_trigger(
	declaration: str | None, key: str, _body: str
) -> str:
	prefix = f"{declaration} " if declaration else ""
	return (
		f"{prefix}{key} = {{\n"
		"\talways = no\n"
		"}"
	)


def write_override(relative_path: str, text: str) -> None:
	destination = ROOT / relative_path
	destination.parent.mkdir(parents=True, exist_ok=True)
	destination.write_text(text, encoding="utf-8-sig", newline="\n")


def generate_event_overrides(missing_ids: set[str]) -> tuple[int, int]:
	file_count = 0
	event_count = 0
	for source in (VANILLA / "events").rglob("*.txt"):
		text = source.read_text(encoding="utf-8-sig", errors="strict")
		blocks = affected_blocks(text, missing_ids)
		if not blocks:
			continue
		relative_path = source.relative_to(VANILLA).as_posix()
		write_override(
			relative_path,
			replace_blocks(text, blocks, event_stub),
		)
		file_count += 1
		event_count += len(blocks)
	return file_count, event_count


def generate_definition_overrides(
	relative_paths: tuple[str, ...],
	missing_ids: set[str],
	replacement,
) -> tuple[int, int]:
	file_count = 0
	definition_count = 0
	for relative_path in relative_paths:
		source = VANILLA / relative_path
		text = source.read_text(encoding="utf-8-sig", errors="strict")
		blocks = affected_blocks(text, missing_ids)
		if not blocks:
			continue
		write_override(
			relative_path,
			replace_blocks(text, blocks, replacement),
		)
		file_count += 1
		definition_count += len(blocks)
	return file_count, definition_count


def generate_portrait_overrides() -> int:
	for relative_path in PORTRAIT_LOOKUP_FILES:
		write_override(
			relative_path,
			"# Vanilla historical character lookup disabled for 大梦春秋 III.\n",
		)
	return len(PORTRAIT_LOOKUP_FILES)


def main() -> None:
	missing_ids = missing_character_ids()
	event_files, events = generate_event_overrides(missing_ids)
	effect_files, effects = generate_definition_overrides(
		SCRIPTED_EFFECT_FILES,
		missing_ids,
		empty_effect,
	)
	trigger_files, triggers = generate_definition_overrides(
		SCRIPTED_TRIGGER_FILES,
		missing_ids,
		false_trigger,
	)
	portrait_files = generate_portrait_overrides()
	print(
		f"Disabled {events} historical events in {event_files} files; "
		f"neutralized {effects} scripted effects in {effect_files} files; "
		f"neutralized {triggers} scripted triggers in {trigger_files} files; "
		f"suppressed {portrait_files} portrait lookup files."
	)


if __name__ == "__main__":
	main()
