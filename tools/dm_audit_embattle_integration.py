"""Audit the restored deputy-general mod and player/AI permission boundary."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import dm_generate_reform_registry as registry


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"D:\SteamLibrary\steamapps\workshop\content\1158310\3454148607")
MANIFEST = ROOT / "generated/dm_recovery_manifest.json"
CORE = {
	"events": ROOT / "events/embattle_events.txt",
	"on_action": ROOT / "common/on_action/embattle_on_action.txt",
	"effects": ROOT / "common/scripted_effects/embattle_effects.txt",
	"war_effects": ROOT / "common/scripted_effects/zzz_embattle_00_war_effects.txt",
	"traits": ROOT / "common/traits/embattle_commander_traits.txt",
}


def fail(message: str) -> None:
	raise AssertionError(message)


def source_files() -> list[str]:
	return sorted(
		path.relative_to(SOURCE).as_posix()
		for path in SOURCE.rglob("*")
		if path.is_file() and path.name not in {"descriptor.mod", "thumbnail.png"}
	)


def check_restoration() -> None:
	if not SOURCE.is_dir():
		fail(f"deputy source folder is unavailable: {SOURCE}")
	files = source_files()
	if len(files) != 65:
		fail(f"deputy source now contains {len(files)} approved files, expected 65")
	missing = [relative for relative in files if not (ROOT / relative).is_file()]
	if missing:
		fail("restored deputy files are missing: " + ", ".join(missing[:20]))
	if not MANIFEST.is_file():
		fail("recovery manifest is missing")
	manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
	if manifest.get("embattle_count") != 65:
		fail("recovery manifest no longer records 65 deputy files")
	for excluded in ("descriptor.mod", "thumbnail.png"):
		if excluded not in manifest.get("excluded", []):
			fail(f"recovery manifest no longer excludes source metadata: {excluded}")


def check_syntax() -> dict[str, str]:
	texts: dict[str, str] = {}
	for label, path in CORE.items():
		if not path.is_file():
			fail(f"missing deputy core file: {path}")
		text = path.read_text(encoding="utf-8-sig")
		texts[label] = text
		registry.read_script(path)
		clean = registry.strip_comments(text)
		if clean.count("{") != clean.count("}"):
			fail(f"{path}: unbalanced braces")
		if re.search(r"\bvalue\s*=\s*\{\s*\}", clean):
			fail(f"{path}: empty scripted-value branch remains")
	for path in ROOT.rglob("*"):
		if not path.is_file() or path.suffix.lower() not in {".txt", ".yml", ".gui"}:
			continue
		if "embattle" not in path.name.lower() and "embattle" not in path.as_posix().lower():
			continue
		text = path.read_text(encoding="utf-8-sig", errors="replace")
	return texts


def check_permission_boundary(texts: dict[str, str]) -> None:
	events = texts["events"]
	on_action = texts["on_action"]
	effects = texts["effects"]
	war_effects = texts["war_effects"]
	if "embattle_events.0001 = {" not in events:
		fail("AI-compatible deputy assignment event is missing")
	full_event = events.split("embattle_events.0002 = {", 1)[1]
	if "root = { is_ai = no }" not in full_event:
		fail("full deputy traits/effects event is not restricted by army owner")
	if "embattle_on_army_enter_province" not in on_action or "trigger_event = embattle_events.0001" not in on_action:
		fail("army entry no longer assigns deputies for both player and AI armies")
	for marker in (
		"scope:army.army_owner = { is_ai = no }",
		"combat_attacker.side_commander.commanding_army.army_owner",
		"combat_defender.side_commander.commanding_army.army_owner",
	):
		if marker not in on_action:
			fail(f"player-army battle/experience gate missing: {marker}")
	if "scope:army_owner = { is_ai = no }" not in effects:
		fail("tactic effects are not gated by the actual army owner")
	if "root.side_commander.commanding_army.army_owner" not in war_effects or "is_ai = no" not in war_effects:
		fail("commander trait experience is not gated by the actual army owner")
	if "has_trait = embattle_forder" not in war_effects or "trait = embattle_forder" not in war_effects:
		fail("the deputy-specific forder trait is not used consistently in XP integration")
	trait_text = texts["traits"]
	if re.search(r"(?m)^\s*trait\s*=\s*forder\s*$", trait_text):
		fail("embattle_forder's own level track still references the vanilla forder trait")
	if "exists = embattle_forder" in trait_text:
		fail("embattle_forder's level track still treats a trait key as a scope")


def check_localization_duplicates() -> None:
	keys: list[str] = []
	for path in (ROOT / "localization/simp_chinese").glob("**/*.yml"):
		if "embattle" not in path.name.lower():
			continue
		text = path.read_text(encoding="utf-8-sig")
		keys.extend(
			key
			for key in re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+):\d*\s", text)
			if key != "l_simp_chinese"
		)
	duplicates = sorted({key for key in keys if keys.count(key) > 1})
	if duplicates:
		fail("duplicate deputy localization keys: " + ", ".join(duplicates[:20]))


def main() -> int:
	check_restoration()
	texts = check_syntax()
	check_permission_boundary(texts)
	check_localization_duplicates()
	print(
		"embattle integration audit OK: 65 restored files, AI deputy assignment only, "
		"player-army tactics/events/effects/XP, syntax and localization checks"
	)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except AssertionError as error:
		print(f"EMBATTLE AUDIT FAILED: {error}", file=sys.stderr)
		raise SystemExit(1)
