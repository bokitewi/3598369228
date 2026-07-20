"""Generate the deterministic registry and script bridge for the reform system.

The effective law database is assembled in CK3 load order: vanilla first, then
this mod. A mod group with the same key replaces the vanilla group. Generated
files are committed and ``--check`` rejects drift after a game/mod update.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


ROOT = Path(__file__).resolve().parents[1]
VANILLA = Path(r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game")
MANIFEST = ROOT / "data" / "dm_reform_registry_overrides.toml"
ATOM_RE = re.compile(
	r'"(?:\\.|[^"])*"|[{}]|(?:\?=|!=|>=|<=|==|=)|[^\s{}=<>!?]+|[<>!?]'
)
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:.@-]*$")

Value: TypeAlias = str | list[tuple[str | None, "Value"]]
Block: TypeAlias = list[tuple[str | None, Value]]


@dataclass(frozen=True)
class Definition:
	key: str
	block: Block
	source: Path
	layer: str


@dataclass(frozen=True)
class Law:
	key: str
	group: str
	block: Block
	source: Path
	theme: str
	axis: str
	level: int
	is_budget: bool
	group_conditions: Block


def strip_comments(text: str) -> str:
	out: list[str] = []
	quoted = False
	escaped = False
	index = 0
	while index < len(text):
		char = text[index]
		if quoted:
			out.append(char)
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
			index += 1
			continue
		if char == '"':
			quoted = True
			out.append(char)
			index += 1
			continue
		if char == "#":
			while index < len(text) and text[index] not in "\r\n":
				index += 1
			continue
		out.append(char)
		index += 1
	return "".join(out)


def parse_script(text: str, source: Path) -> Block:
	tokens = ATOM_RE.findall(strip_comments(text))
	index = 0

	def parse_block(stop_at_close: bool) -> Block:
		nonlocal index
		items: Block = []
		while index < len(tokens):
			token = tokens[index]
			if token == "}":
				if not stop_at_close:
					raise ValueError(f"{source}: unexpected closing brace")
				index += 1
				return items
			if token == "{":
				index += 1
				items.append((None, parse_block(True)))
				continue
			key = token
			index += 1
			if index >= len(tokens) or tokens[index] not in {"=", "?=", "!=", ">=", "<=", "=="}:
				items.append((None, key))
				continue
			operator = tokens[index]
			index += 1
			if index >= len(tokens):
				raise ValueError(f"{source}: missing value after {key!r}")
			if tokens[index] == "{":
				index += 1
				value: Value = parse_block(True)
			else:
				value = tokens[index]
				index += 1
			stored_key = key if operator == "=" else f"{key} {operator}"
			items.append((stored_key, value))
		if stop_at_close:
			raise ValueError(f"{source}: unclosed block")
		return items

	return parse_block(False)


def read_script(path: Path) -> Block:
	return parse_script(path.read_text(encoding="utf-8-sig", errors="strict"), path)


def values(block: Block, key: str) -> list[Value]:
	return [value for item_key, value in block if item_key == key]


def first(block: Block, key: str) -> Value | None:
	found = values(block, key)
	return found[0] if found else None


def atom(value: Value | None) -> str | None:
	return value if isinstance(value, str) else None


def bool_value(block: Block, key: str) -> bool:
	return atom(first(block, key)) == "yes"


def scalar_assignments(path: Path) -> dict[str, str]:
	assignments: dict[str, str] = {}
	for key, value in read_script(path):
		if key and key.startswith("@") and isinstance(value, str):
			assignments[key] = value
	return assignments


def expand_atoms(value: Value, assignments: dict[str, str]) -> Value:
	if isinstance(value, str):
		seen: set[str] = set()
		while value.startswith("@") and value in assignments and value not in seen:
			seen.add(value)
			value = assignments[value]
		return value
	return [(key, expand_atoms(child, assignments)) for key, child in value]


def script_files(root: Path) -> list[Path]:
	return sorted(
		path
		for path in root.glob("*.txt")
		if not path.name.startswith("_")
		and not path.name.endswith((".bak", ".disabled"))
	)


def layer_definitions(root: Path, layer: str) -> dict[str, Definition]:
	definitions: dict[str, Definition] = {}
	for path in script_files(root):
		assignments = scalar_assignments(path)
		for key, value in read_script(path):
			if not key or key.startswith("@") or not isinstance(value, list):
				continue
			if not IDENT_RE.match(key):
				raise ValueError(f"{path}: invalid top-level key {key!r}")
			definitions[key] = Definition(
				key=key,
				block=expand_atoms(value, assignments),
				source=path,
				layer=layer,
			)
	return definitions


def effective_groups() -> dict[str, Definition]:
	vanilla = layer_definitions(VANILLA / "common" / "laws", "vanilla")
	mod = layer_definitions(ROOT / "common" / "laws", "mod")
	return vanilla | mod


def is_law_candidate(key: str, value: Value) -> bool:
	if not isinstance(value, list) or key.startswith("@"):
		return False
	if key in {
		"default",
		"flag",
		"fallback",
		"law_change_cooldown",
		"law_change_opinion",
		"law_change_opinion_reverse",
		"law_change_obedience",
		"law_change_obedience_reverse",
		"law_change_modifier",
		"law_change_modifier_reverse",
		"tier",
		"triggered_desc",
		"sort_order",
	}:
		return False
	law_markers = {
		"can_have",
		"can_pass",
		"potential",
		"modifier",
		"pass_cost",
		"on_pass",
		"ai_will_do",
		"should_start_with",
		"flag",
	}
	return any(child_key in law_markers for child_key, _ in value)


def collect_laws(manifest: dict) -> tuple[list[Law], list[str]]:
	excluded = set(manifest["settings"]["exclude_groups"])
	excluded_laws = set(manifest["settings"].get("exclude_laws", []))
	budgets = set(manifest["settings"]["budget_groups"])
	group_meta = manifest.get("groups", {})
	law_meta = manifest.get("laws", {})
	groups = effective_groups()
	laws: list[Law] = []
	unknown: list[str] = []
	for group_key in sorted(groups):
		definition = groups[group_key]
		if group_key in excluded:
			continue
		is_budget = group_key in budgets or bool_value(definition.block, "is_treasury_budget_group")
		# Treasury budgets use their native direct-enact window and never enter
		# the reform registry or story system.
		if is_budget:
			continue
		flags = {atom(value) for value in values(definition.block, "flag")}
		meta = group_meta.get(group_key)
		is_realm = bool(meta) or bool(
			flags
			& {
				"realm_law",
				"succession_order_laws",
				"succession_gender_laws",
				"admin_law",
				"imperial_policy",
			}
	)
		if not is_realm:
			continue
		if not meta:
			unknown.append(group_key)
			continue
		children = [
			(key, value)
			for key, value in definition.block
			if key and is_law_candidate(key, value)
		]
		if not children:
			raise ValueError(f"{definition.source}: registered group {group_key} has no laws")
		count = len(children)
		for index, (law_key, block) in enumerate(children):
			assert isinstance(block, list)
			if law_key in excluded_laws:
				continue
			if "level" in law_meta.get(law_key, {}):
				level = int(law_meta[law_key]["level"])
			elif count == 1:
				level = 0
			else:
				level = round(-3 + (6 * index / (count - 1)))
			laws.append(
				Law(
					key=law_key,
					group=group_key,
					block=block,
					source=definition.source,
					theme=meta["theme"],
					axis=meta["axis"],
					level=max(-3, min(3, level)),
					is_budget=is_budget,
					group_conditions=(
						first(definition.block, "can_change_law_group")
						if isinstance(first(definition.block, "can_change_law_group"), list)
						else []
					),
				)
			)
	if unknown:
		raise ValueError(
			"realm-law groups need explicit metadata overrides: " + ", ".join(unknown)
		)
	law_keys = [law.key for law in laws]
	if len(law_keys) != len(set(law_keys)):
		duplicates = sorted({key for key in law_keys if law_keys.count(key) > 1})
		raise ValueError("duplicate effective law keys: " + ", ".join(duplicates))
	return laws, sorted(groups)


def indent(text: str, tabs: int) -> str:
	prefix = "\t" * tabs
	return "\n".join(prefix + line if line else "" for line in text.splitlines())


def render_value(value: Value, tabs: int = 0) -> str:
	if isinstance(value, str):
		return value
	lines = ["{"]
	for key, child in value:
		if key is None:
			raise ValueError("anonymous values cannot be rendered")
		child_indent = "\t" * (tabs + 1)
		operator = "="
		rendered_key = key
		for candidate in ("?=", "!=", ">=", "<=", "=="):
			suffix = f" {candidate}"
			if key.endswith(suffix):
				rendered_key = key[: -len(suffix)]
				operator = candidate
				break
		if isinstance(child, list):
			lines.append(
				f"{child_indent}{rendered_key} {operator} {render_value(child, tabs + 1)}"
			)
		else:
			lines.append(f"{child_indent}{rendered_key} {operator} {child}")
	current_indent = "\t" * tabs
	lines.append(f"{current_indent}}}")
	return "\n".join(lines)


def resource_cost(law: Law) -> Block:
	value = first(law.block, "pass_cost")
	return value if isinstance(value, list) else []


def adapt_interaction_scope(value: Value, *, drop_value_descriptions: bool = False) -> Value:
	"""Translate law-context ROOT references to the interaction actor."""
	if isinstance(value, str):
		if value == "root":
			return "scope:actor"
		if value.startswith("root."):
			return "scope:actor." + value[5:]
		return value
	adapted: Block = []
	for key, child in value:
		if drop_value_descriptions and key == "desc":
			continue
		if key == "tgp_japan_defense_mobilization_valid_trigger":
			adapted.append(
				(
					"dm_reform_japan_defense_mobilization_valid_trigger",
					[("CHARACTER", "scope:actor")],
				)
			)
			continue
		adapted_key = "scope:actor" if key == "root" else key
		adapted.append(
			(
				adapted_key,
				adapt_interaction_scope(
					child,
					drop_value_descriptions=drop_value_descriptions,
				),
			)
		)
	return adapted


def interaction_cost(law: Law) -> Block:
	"""Render pass costs in the actor scope expected by character interactions."""
	return [
		(
			resource,
			[
				("value", "0"),
				(
					"scope:actor",
					[
						(
							"add",
							adapt_interaction_scope(
								value,
								drop_value_descriptions=True,
							),
						)
					],
				),
			],
		)
		for resource, value in resource_cost(law)
	]


def block_contains_atom(block: Block, expected: set[str]) -> bool:
	for key, value in block:
		if key in expected:
			return True
		if isinstance(value, str) and value.strip('"') in expected:
			return True
		if isinstance(value, list) and block_contains_atom(value, expected):
			return True
	return False


def strip_powerful_vassal_approval(block: Block) -> Block:
	approval_atoms = {
		"no_powerful_vassal_with_negative_opinion",
		"opposes_succession_law_change_trigger",
	}
	cleaned: Block = []
	for key, value in block:
		if key == "custom_description" and isinstance(value, list):
			if block_contains_atom(value, approval_atoms):
				continue
		if key in approval_atoms:
			continue
		if isinstance(value, list):
			value = strip_powerful_vassal_approval(value)
		cleaned.append((key, value))
	return cleaned


def render_block_entries(block: Block, tabs: int) -> str:
	lines: list[str] = []
	prefix = "\t" * tabs
	for key, value in block:
		if key is None:
			raise ValueError("anonymous values cannot be rendered")
		operator = "="
		rendered_key = key
		for candidate in ("?=", "!=", ">=", "<=", "=="):
			suffix = f" {candidate}"
			if key.endswith(suffix):
				rendered_key = key[: -len(suffix)]
				operator = candidate
				break
		lines.append(f"{prefix}{rendered_key} {operator} {render_value(value, tabs)}")
	return "\n".join(lines)


def law_condition_text(law: Law, keys: tuple[str, ...], tabs: int) -> str:
	blocks: list[Block] = []
	for key in keys:
		value = first(law.block, key)
		if isinstance(value, list):
			blocks.append(
				adapt_interaction_scope(strip_powerful_vassal_approval(value))
			)
	if not blocks:
		return ""
	return "\n".join(render_block_entries(block, tabs) for block in blocks if block)


def refundable_costs(law: Law) -> list[tuple[str, Value]]:
	return [
		(resource, value)
		for resource, value in resource_cost(law)
		if resource in {"gold", "prestige", "piety", "influence", "legitimacy"}
	]


def render_paid_cost_capture(law: Law) -> str:
	lines: list[str] = []
	for resource, value in refundable_costs(law):
		rendered = render_value(
			adapt_interaction_scope(value, drop_value_descriptions=True),
			4,
		)
		lines.append(
			"\t\t\tsave_scope_value_as = {\n"
			f"\t\t\t\tname = dm_reform_paid_{resource}\n"
			f"\t\t\t\tvalue = {rendered}\n"
			"\t\t\t}"
		)
	return "\n".join(lines)


def render_paid_cost_variables(law: Law) -> str:
	lines: list[str] = []
	for resource, _ in refundable_costs(law):
		lines.append(
			f"\t\t\t\tset_variable = {{ name = dm_reform_paid_{resource} "
			f"value = scope:dm_reform_paid_{resource} }}"
		)
	return "\n".join(lines)


GOVERNMENT_REFORM_LEVELS = {
	"feudal_government": -1,
	"republic_government": 0,
	"theocracy_government": 0,
	"clan_government": -1,
	"tribal_government": -2,
	"wanua_government": -2,
	"administrative_government": 3,
	"feudal_admin_government": 2,
	"celestial_government": 3,
	"mandala_government": 0,
	"meritocratic_government": 1,
	"japan_administrative_government": 3,
	"japan_feudal_government": -1,
	"nomad_government": -3,
	"steppe_admin_government": 2,
}


def render_government_reform_ai(law: Law) -> str:
	target_is_risky = law.key in {
		"dm_government_reform_republic_law",
		"dm_government_reform_theocracy_law",
	}
	lines = [
		"\tai_will_do = {",
		f"\t\tbase = {100 + 20 * law.level - (60 if target_is_risky else 0)}",
	]
	families = {
		"dm_government_reform_feudal_law": (
			"feudal_government", "clan_government", "feudal_admin_government",
			"japan_feudal_government",
		),
		"dm_government_reform_clan_law": (
			"feudal_government", "clan_government", "feudal_admin_government",
			"japan_feudal_government",
		),
		"dm_government_reform_feudal_admin_law": (
			"feudal_government", "clan_government", "feudal_admin_government",
			"japan_feudal_government",
		),
		"dm_government_reform_japan_feudal_law": (
			"feudal_government", "clan_government", "feudal_admin_government",
			"japan_feudal_government",
		),
		"dm_government_reform_tribal_law": ("tribal_government", "wanua_government"),
		"dm_government_reform_wanua_law": ("tribal_government", "wanua_government"),
		"dm_government_reform_administrative_law": (
			"administrative_government", "celestial_government",
			"meritocratic_government", "steppe_admin_government",
			"japan_administrative_government",
		),
		"dm_government_reform_celestial_law": (
			"administrative_government", "celestial_government",
			"meritocratic_government", "steppe_admin_government",
			"japan_administrative_government",
		),
		"dm_government_reform_meritocratic_law": (
			"administrative_government", "celestial_government",
			"meritocratic_government", "steppe_admin_government",
			"japan_administrative_government",
		),
		"dm_government_reform_steppe_admin_law": (
			"administrative_government", "celestial_government",
			"meritocratic_government", "steppe_admin_government",
			"japan_administrative_government",
		),
		"dm_government_reform_japan_administrative_law": (
			"administrative_government", "celestial_government",
			"meritocratic_government", "steppe_admin_government",
			"japan_administrative_government",
		),
	}
	for government in families.get(law.key, ()):
		lines.append(
			f"\t\tmodifier = {{ add = 30 scope:actor = {{ has_government = {government} }} }}"
		)
	for government, level in GOVERNMENT_REFORM_LEVELS.items():
		lines.extend(
			[
				"\t\tmodifier = {",
				f"\t\t\tadd = {-20 * level}",
				f"\t\t\tscope:actor = {{ has_government = {government} }}",
				"\t\t}",
			]
		)
		if law.level > level:
			lines.extend(
				[
					"\t\tmodifier = {",
					"\t\t\tadd = 25",
					f"\t\t\tscope:actor = {{ has_government = {government} has_trait = ambitious }}",
					"\t\t}",
					"\t\tmodifier = {",
					"\t\t\tadd = -30",
					f"\t\t\tscope:actor = {{ has_government = {government} has_trait = content }}",
					"\t\t}",
				]
			)
		elif law.level < level:
			lines.extend(
				[
					"\t\tmodifier = {",
					"\t\t\tadd = -20",
					f"\t\t\tscope:actor = {{ has_government = {government} has_trait = ambitious }}",
					"\t\t}",
					"\t\tmodifier = {",
					"\t\t\tadd = 15",
					f"\t\t\tscope:actor = {{ has_government = {government} has_trait = content }}",
					"\t\t}",
				]
			)
	lines.extend(
		[
			"\t\tmodifier = { add = 15 scope:actor = { has_trait = diligent } }",
			"\t\tmodifier = { add = -25 scope:actor = { has_trait = stubborn } }",
			"\t\tmodifier = { add = 10 scope:actor = { has_trait = brave } }",
			"\t\tmodifier = { add = -15 scope:actor = { has_trait = craven } }",
			"\t\tmodifier = { add = -100 scope:actor = { is_in_debt = yes } }",
			"\t\tmodifier = { add = -40 scope:actor = { is_at_war = yes } }",
			"\t\tmodifier = {",
			"\t\t\tadd = -80",
			"\t\t\tscope:actor = {",
			"\t\t\t\tany_character_war = {",
			"\t\t\t\t\tis_war_leader = root",
			"\t\t\t\t\tOR = {",
			"\t\t\t\t\t\tAND = { primary_attacker = root attacker_war_score < -50 }",
			"\t\t\t\t\t\tAND = { primary_defender = root defender_war_score < -50 }",
			"\t\t\t\t\t}",
			"\t\t\t\t}",
			"\t\t\t}",
			"\t\t}",
		]
	)
	if law.key == "dm_government_reform_republic_law":
		lines.extend(
			[
				"\t\tmodifier = { add = 40 scope:actor = { stewardship >= 20 } }",
				"\t\tmodifier = { add = 30 scope:actor = { has_trait = greedy } }",
			]
		)
	elif law.key == "dm_government_reform_theocracy_law":
		lines.extend(
			[
				"\t\tmodifier = { add = 40 scope:actor = { learning >= 20 } }",
				"\t\tmodifier = { add = 30 scope:actor = { has_trait = zealous } }",
				"\t\tmodifier = { add = -30 scope:actor = { has_trait = cynical } }",
			]
		)
	lines.extend(["\t}"])
	return "\n".join(lines)


def render_interaction(law: Law) -> str:
	is_government_reform = law.group == "dm_government_reform_law_group"
	interaction_desc = (
		"dm_government_reform_risk_warning"
		if law.key in {
			"dm_government_reform_republic_law",
			"dm_government_reform_theocracy_law",
		}
		else "dm_reform_start_interaction_desc"
	)
	cost = interaction_cost(law)
	cost_text = ""
	if cost:
		cost_text = "\tcost = " + render_value(cost, 1) + "\n"
	shown_conditions = law_condition_text(law, ("potential",), 3)
	valid_parts = []
	valid_item_count = 0
	if law.group_conditions:
		adapted_group_conditions = adapt_interaction_scope(law.group_conditions)
		assert isinstance(adapted_group_conditions, list)
		valid_parts.append(render_block_entries(adapted_group_conditions, 2))
		valid_item_count += len(adapted_group_conditions)
	law_valid = law_condition_text(law, ("can_have", "can_pass"), 2)
	if law_valid:
		valid_parts.append(law_valid)
	for key in ("can_have", "can_pass"):
		value = first(law.block, key)
		if isinstance(value, list):
			valid_item_count += len(strip_powerful_vassal_approval(value))
	valid_conditions = "\n".join(valid_parts)
	if shown_conditions:
		shown_conditions = "\n" + shown_conditions
	if is_government_reform:
		shown_conditions += """
			trigger_if = {
				limit = { is_ai = yes }
				prestige >= 4000
				is_independent_ruler = yes
				highest_held_title_tier >= tier_kingdom
				NOT = { has_character_flag = dm_government_reform_cooldown }
			}"""
	if valid_conditions:
		if valid_item_count == 1:
			valid_conditions = (
				"\n\t\t\tcustom_description = {\n"
				"\t\t\t\ttext = dm_reform_law_requirements_tt\n"
				+ indent(valid_conditions, 2)
				+ "\n\t\t\t}"
			)
		else:
			valid_conditions = (
				"\n\t\t\tcustom_description = {\n"
				"\t\t\t\ttext = dm_reform_law_requirements_tt\n"
				"\t\t\t\tAND = {\n"
				+ indent(valid_conditions, 3)
				+ "\n\t\t\t\t}\n"
				"\t\t\t}"
			)
	paid_costs = render_paid_cost_variables(law)
	if paid_costs:
		paid_costs = "\n" + paid_costs
	paid_cost_capture = render_paid_cost_capture(law)
	if paid_cost_capture:
		paid_cost_capture += "\n"
	ai_will_do = (
		render_government_reform_ai(law)
		if is_government_reform
		else f"""\tai_will_do = {{
\t\tbase = {max(0, 20 + law.level * 5)}
\t\tmodifier = {{
\t\t\tfactor = 0
\t\t\tscope:actor = {{ is_in_debt = yes }}
\t\t}}
\t\tmodifier = {{
\t\t\tfactor = 1.5
\t\t\tscope:actor = {{ OR = {{ has_trait = ambitious has_trait = diligent }} }}
\t\t}}
\t\tmodifier = {{
\t\t\tfactor = 0.5
\t\t\tscope:actor = {{ OR = {{ has_trait = content has_trait = lazy }} }}
\t\t}}
\t}}"""
	)
	return f"""dm_reform_start_{law.key}_interaction = {{
\tcategory = interaction_category_friendly
\tcommon_interaction = yes
\thidden = yes
\tpopup_on_receive = no
\tai_maybe = yes
\tai_frequency = 36
\tai_accept = {{ base = 100 }}
{ai_will_do}
\tai_targets = {{ ai_recipients = self }}
\tdesc = {interaction_desc}
\ticon = scroll_scales
{cost_text}\tis_shown = {{
\t\tscope:recipient = scope:actor
\t\tscope:actor = {{
\t\t\tis_ruler = yes
\t\t\tNOT = {{ has_realm_law = {law.key} }}
\t\t\tdm_reform_can_start_trigger = yes{shown_conditions}
\t\t}}
\t}}
\tis_valid_showing_failures_only = {{
\t\tscope:actor = {{
\t\t\tdm_reform_can_start_trigger = yes{valid_conditions}
\t\t}}
\t}}
\ton_accept = {{
\t\tscope:actor = {{
{paid_cost_capture}\t\t\tcreate_story = dm_reform_story
\t\t\trandom_owned_story = {{
\t\t\t\tlimit = {{ story_type = dm_reform_story }}
\t\t\t\tset_variable = {{ name = dm_reform_target value = flag:{law.key} }}
\t\t\t\tset_variable = {{ name = dm_reform_theme value = flag:{law.theme} }}
\t\t\t\tset_variable = {{ name = dm_reform_axis value = flag:{law.axis} }}
\t\t\t\tset_variable = {{ name = dm_reform_target_level value = {law.level} }}{paid_costs}
\t\t\t\tdm_reform_capture_current_level_effect = yes
\t\t\t\tif = {{
\t\t\t\t\tlimit = {{ story_owner = {{ has_variable = dm_reform_pending_reformer }} }}
\t\t\t\t\tset_variable = {{
\t\t\t\t\t\tname = dm_reform_pending_reformer
\t\t\t\t\t\tvalue = story_owner.var:dm_reform_pending_reformer
\t\t\t\t\t}}
\t\t\t\t\tsave_scope_as = dm_reform_story
\t\t\t\t\tstory_owner.var:dm_reform_pending_reformer = {{
\t\t\t\t\t\ttrigger_event = {{ id = dm_reform.0210 days = 1 }}
\t\t\t\t\t}}
\t\t\t\t\tstory_owner = {{ remove_variable = dm_reform_pending_reformer }}
\t\t\t\t}}
\t\t\t}}
\t\t\ttrigger_event = {{ id = dm_reform.0001 days = 1 }}
\t\t}}
\t}}
}}"""


def render_success_effect(laws: list[Law]) -> str:
	lines = [
		"dm_reform_apply_target_law_effect = {",
		"\t# ROOT: reform story",
	]
	for index, law in enumerate(laws):
		command = "if" if index == 0 else "else_if"
		lines.extend(
			[
				f"\t{command} = {{",
				f"\t\tlimit = {{ var:dm_reform_target = flag:{law.key} }}",
				"\t\tstory_owner = {",
				"\t\t\tif = {",
				f"\t\t\t\tlimit = {{ NOT = {{ has_realm_law = {law.key} }} }}",
				f"\t\t\t\tadd_realm_law = {law.key}",
				"\t\t\t}",
				"\t\t}",
				"\t}",
			]
		)
	lines.extend(
		[
			"\telse = { debug_log = \"DM_REFORM_ERROR: no registered target law\" }",
			"}",
			"",
		]
	)
	lines.extend(
		[
			"dm_reform_capture_current_level_effect = {",
			"\t# ROOT: reform story",
			"\tset_variable = { name = dm_reform_current_level value = 0 }",
		]
	)
	grouped: dict[str, list[Law]] = {}
	for law in laws:
		grouped.setdefault(law.group, []).append(law)
	for index, law in enumerate(laws):
		command = "if" if index == 0 else "else_if"
		lines.extend(
			[
				f"\t{command} = {{",
				f"\t\tlimit = {{ var:dm_reform_target = flag:{law.key} }}",
			]
		)
		for group_law in grouped[law.group]:
			lines.extend(
				[
					"\t\tif = {",
					f"\t\t\tlimit = {{ story_owner = {{ has_realm_law = {group_law.key} }} }}",
					f"\t\t\tset_variable = {{ name = dm_reform_current_level value = {group_law.level} }}",
					"\t\t}",
				]
			)
		lines.extend(["\t}",])
	lines.extend(
		[
			"\tset_variable = {",
			"\t\tname = dm_reform_interest_delta",
			"\t\tvalue = var:dm_reform_target_level",
			"\t}",
			"\tchange_variable = {",
			"\t\tname = dm_reform_interest_delta",
			"\t\tsubtract = var:dm_reform_current_level",
			"\t}",
			"}",
		]
	)
	return "\n".join(lines)


def render_target_valid_trigger(laws: list[Law]) -> str:
	lines = [
		"dm_reform_target_is_not_current_trigger = {",
		"\t# ROOT: reform story",
		"\tOR = {",
	]
	for law in laws:
		lines.extend(
			[
				"\t\tAND = {",
				f"\t\t\tvar:dm_reform_target = flag:{law.key}",
				f"\t\t\tstory_owner = {{ NOT = {{ has_realm_law = {law.key} }} }}",
				"\t\t}",
			]
		)
	lines.extend(["\t}", "}"])
	lines.extend(["", "dm_reform_target_is_valid_trigger = {", "\t# ROOT: reform story", "\tOR = {"])
	for law in laws:
		conditions = []
		if law.group_conditions:
			conditions.append(
				render_block_entries(
					strip_powerful_vassal_approval(law.group_conditions), 4
				)
			)
		law_conditions = law_condition_text(law, ("potential", "can_have"), 4)
		if law_conditions:
			conditions.append(law_conditions)
		rendered_conditions = "\n".join(conditions)
		if rendered_conditions:
			rendered_conditions = "\n" + rendered_conditions
		lines.extend(
			[
				"\t\tAND = {",
				f"\t\t\tvar:dm_reform_target = flag:{law.key}",
				f"\t\t\tstory_owner = {{{rendered_conditions}",
				"\t\t\t}",
				"\t\t}",
			]
		)
	lines.extend(["\t}", "}"])
	return "\n".join(lines)


def registry_source(path: Path) -> str:
	try:
		return path.relative_to(ROOT).as_posix()
	except ValueError:
		return str(path)


def registry_json(laws: list[Law]) -> str:
	payload = {
		"schema": 1,
		"vanilla_root": str(VANILLA),
		"laws": [
			{
				"key": law.key,
				"group": law.group,
				"source": registry_source(law.source),
				"source_layer": "mod" if ROOT in law.source.parents else "vanilla",
				"theme": law.theme,
				"axis": law.axis,
				"level": law.level,
				"budget": law.is_budget,
				"cost_resources": [key for key, _ in resource_cost(law) if key],
			}
			for law in laws
		],
	}
	return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


EVENT_CATALOG = [
	("crisis", "军令拒行", "martial"),
	("crisis", "伪诏流传", "intrigue"),
	("crisis", "宗嗣拥旗", "diplomacy"),
	("crisis", "郡县抗命", "stewardship"),
	("crisis", "经义成狱", "learning"),
	("crisis", "宫门鼓噪", "prowess"),
	("crisis", "府库封锁", "stewardship"),
	("setback", "郡县观望", "diplomacy"),
	("setback", "文移壅塞", "stewardship"),
	("setback", "军府争章", "martial"),
	("setback", "谣言入市", "intrigue"),
	("setback", "旧典相难", "learning"),
	("setback", "廷臣托病", "diplomacy"),
	("setback", "驿路迟滞", "prowess"),
	("calm", "灯下定稿", "learning"),
	("calm", "案牍核验", "stewardship"),
	("calm", "密议无声", "intrigue"),
	("calm", "校场推演", "martial"),
	("calm", "温言问策", "diplomacy"),
	("calm", "夜巡宫城", "prowess"),
	("calm", "旧案重读", "learning"),
	("encouragement", "群臣联署", "diplomacy"),
	("encouragement", "廷辩转圜", "learning"),
	("encouragement", "仓廪应令", "stewardship"),
	("encouragement", "军府奉诏", "martial"),
	("encouragement", "密探献策", "intrigue"),
	("encouragement", "宿卫效忠", "prowess"),
	("encouragement", "乡议回暖", "diplomacy"),
	("breakthrough", "障壁自裂", "intrigue"),
	("breakthrough", "大廷定论", "diplomacy"),
	("breakthrough", "新制成章", "learning"),
	("breakthrough", "百司齐动", "stewardship"),
	("breakthrough", "诸军奉行", "martial"),
	("breakthrough", "禁中震服", "prowess"),
	("breakthrough", "四方响应", "diplomacy"),
]

# The earlier catalog was damaged by a legacy non-UTF-8 save.  Keep the
# definitive UTF-8 catalog adjacent to the rules so generated localization is
# deterministic and reviewable.
EVENT_CATALOG = [
	("crisis", "军令拒行", "martial"),
	("crisis", "伪诏流传", "intrigue"),
	("crisis", "宗嗣拥旗", "diplomacy"),
	("crisis", "郡县抗命", "stewardship"),
	("crisis", "经义成狱", "learning"),
	("crisis", "宫门鼓噪", "prowess"),
	("crisis", "府库封锁", "stewardship"),
	("setback", "郡县观望", "diplomacy"),
	("setback", "文移壅塞", "stewardship"),
	("setback", "军府争章", "martial"),
	("setback", "谣言入市", "intrigue"),
	("setback", "旧典相难", "learning"),
	("setback", "廷臣托病", "diplomacy"),
	("setback", "驿路迟滞", "prowess"),
	("calm", "灯下定稿", "learning"),
	("calm", "案前核验", "stewardship"),
	("calm", "密议无声", "intrigue"),
	("calm", "校场推演", "martial"),
	("calm", "温言问策", "diplomacy"),
	("calm", "夜巡宫城", "prowess"),
	("calm", "旧案重读", "learning"),
	("encouragement", "群臣联署", "diplomacy"),
	("encouragement", "廷辩转圜", "learning"),
	("encouragement", "仓廪应令", "stewardship"),
	("encouragement", "军府奉诏", "martial"),
	("encouragement", "密探献策", "intrigue"),
	("encouragement", "宿卫效忠", "prowess"),
	("encouragement", "乡议回暖", "diplomacy"),
	("breakthrough", "障壁自裂", "intrigue"),
	("breakthrough", "大廷定论", "diplomacy"),
	("breakthrough", "新制成章", "learning"),
	("breakthrough", "百司齐动", "stewardship"),
	("breakthrough", "诸军奉行", "martial"),
	("breakthrough", "禁中震服", "prowess"),
	("breakthrough", "四方响应", "diplomacy"),
]


CATEGORY_RULES = {
	"crisis": (-4, -2, 3, 1, 22),
	"setback": (-2, -1, 2, 1, 18),
	"calm": (0, 0, 1, 0, 14),
	"encouragement": (-1, 0, 4, 1, 18),
	"breakthrough": (-2, -1, 7, 2, 22),
}

ATTRIBUTE_TRAITS = {
	"diplomacy": ("gregarious", "just"),
	"martial": ("brave", "strategist"),
	"stewardship": ("diligent", "administrator"),
	"intrigue": ("deceitful", "schemer"),
	"learning": ("scholar", "shrewd"),
	"prowess": ("brave", "strong"),
}


def reform_event_id(index: int) -> int:
	return 1101 + index


def reform_actor_list(category: str) -> str:
	if category in {"crisis", "setback"}:
		return "dm_reform_opponents"
	return "dm_reform_supporters"


# Four-option reform event implementation.
CATEGORY_RESULTS = {
	"crisis": ((-12, -6), (-10, -5), (7, 2), (9, 3), 22),
	"setback": ((-7, -3), (-5, -2), (5, 2), (7, 3), 18),
	"calm": ((-2, 0), (0, 0), (2, 0), (4, 0), 14),
	"encouragement": ((-4, -1), (-2, 0), (10, 2), (12, 3), 18),
	"breakthrough": ((-7, -3), (-5, -2), (17, 5), (19, 6), 22),
}

CATEGORY_ACTOR_TRAITS = {
	"crisis": ("wrathful", "vengeful", "arrogant", "ambitious", "stubborn"),
	"setback": ("deceitful", "paranoid", "cynical", "greedy", "lazy", "craven"),
	"encouragement": ("honest", "generous", "gregarious", "compassionate", "patient"),
	"breakthrough": ("diligent", "brave", "ambitious", "stubborn", "just"),
}

ATTRIBUTE_ACTOR_TRAITS = {
	"diplomacy": (
		("gregarious", "compassionate", "forgiving", "honest"),
		("shy", "callous", "vengeful", "deceitful"),
	),
	"martial": (
		("brave", "wrathful", "ambitious", "stubborn"),
		("craven", "calm", "content"),
	),
	"stewardship": (
		("diligent", "temperate", "just", "greedy"),
		("lazy", "arbitrary", "generous"),
	),
	"intrigue": (
		("deceitful", "paranoid", "cynical", "arbitrary"),
		("honest", "trusting", "compassionate"),
	),
	"learning": (
		("patient", "zealous", "cynical", "just"),
		("impatient", "arbitrary", "fickle"),
	),
	"prowess": (
		("brave", "wrathful", "arrogant", "ambitious"),
		("craven", "calm", "humble"),
	),
}

RESOURCE_BY_ATTRIBUTE = {
	"diplomacy": "prestige",
	"martial": "prestige",
	"prowess": "prestige",
	"stewardship": "gold",
	"intrigue": "gold",
	"learning": "piety",
}

RESOURCE_COST_BY_CATEGORY = {
	"calm": 100,
	"setback": 150,
	"encouragement": 150,
	"crisis": 200,
	"breakthrough": 200,
}

PROBABILITY_TIERS = (
	(-10, (35, 45, 19, 1), "disaster"),
	(-5, (25, 40, 30, 5), "very_bad"),
	(0, (15, 35, 40, 10), "uncertain"),
	(5, (10, 25, 45, 20), "favorable"),
	(10, (5, 15, 50, 30), "strong"),
	(None, (1, 9, 50, 40), "overwhelming"),
)


def _trait_or(traits: tuple[str, ...]) -> str:
	return " ".join(f"has_trait = {trait}" for trait in traits)


def _actor_selection(category: str, attribute: str) -> str:
	if category == "calm":
		return """scope:dm_reform_story = {
			story_owner = { save_scope_as = dm_reform_ruler }
			random_list = {
				50 = { scope:dm_reform_ruler = { save_scope_as = dm_reform_actor } }
				50 = {
					trigger = { dm_reform_has_reformer_trigger = yes }
					var:dm_reform_reformer = { save_scope_as = dm_reform_actor }
				}
			}
		}"""
	category_traits = CATEGORY_ACTOR_TRAITS[category]
	positive, opposite = ATTRIBUTE_ACTOR_TRAITS[attribute]
	return f"""scope:dm_reform_story = {{
			random_in_list = {{
				variable = {reform_actor_list(category)}
				weight = {{
					base = 10
					modifier = {{ add = 60 OR = {{ {_trait_or(category_traits)} }} }}
					modifier = {{ add = 25 OR = {{ {_trait_or(positive)} }} }}
					modifier = {{ add = -8 OR = {{ {_trait_or(opposite)} }} }}
				}}
				save_scope_as = dm_reform_actor
			}}
		}}"""


def _result_branch(
	result_name: str,
	progress: int,
	support: int,
	next_event: str,
) -> str:
	return f"""scope:dm_reform_story = {{
						dm_reform_apply_counter_change_effect = {{
							PROGRESS = {progress}
							SUPPORT = {support}
							RESULT = {result_name}
						}}
						dm_reform_check_immediate_outcome_effect = yes
					}}{next_event}"""


def _result_roll(check_value: str, bonus: int, category: str, next_event: str) -> str:
	results = CATEGORY_RESULTS[category][:4]
	result_names = ("disaster", "failure", "success", "great_success")
	parts: list[str] = []
	for index, (boundary, probabilities, tier_name) in enumerate(PROBABILITY_TIERS):
		command = "if" if index == 0 else ("else" if boundary is None else "else_if")
		limit = ""
		if boundary is not None:
			threshold = CATEGORY_RESULTS[category][4] + boundary - bonus
			limit = f"\n\t\t\tlimit = {{ {check_value} <= {threshold} }}"
		branches = []
		for probability, result_name, (progress, support) in zip(
			probabilities, result_names, results
		):
			branches.append(
				f"""\t\t\t\t{probability} = {{
					{_result_branch(result_name, progress, support, next_event)}
				}}"""
			)
		parts.append(
			f"""\t\t{command} = {{{limit}
			scope:dm_reform_story = {{
				set_variable = {{ name = dm_reform_probability_tier value = flag:{tier_name} }}
			}}
			random_list = {{
{chr(10).join(branches)}
			}}
		}}"""
		)
	return "\n".join(parts)


def _option_ai_chance(kind: str, resource: str | None = None) -> str:
	base = {"ruler": 40, "reformer": 30, "trait": 60, "resource": 20}[kind]
	if kind == "ruler":
		modifiers = [
			"modifier = { add = 30 OR = { has_trait = arrogant has_trait = ambitious has_trait = brave has_trait = stubborn } }",
			"modifier = { add = -20 OR = { has_trait = humble has_trait = trusting has_trait = content } }",
		]
	elif kind == "reformer":
		modifiers = [
			"modifier = { add = 30 OR = { has_trait = trusting has_trait = humble has_trait = content } }",
			"modifier = { add = -30 OR = { has_trait = paranoid has_trait = arrogant } }",
			"""modifier = {
				add = 20
				opinion = {
					target = scope:dm_reform_story.var:dm_reform_reformer
					value >= 50
				}
			}""",
			"""modifier = {
				add = 10
				opinion = {
					target = scope:dm_reform_story.var:dm_reform_reformer
					value >= 0
				}
				NOT = {
					opinion = {
						target = scope:dm_reform_story.var:dm_reform_reformer
						value >= 50
					}
				}
			}""",
			"""modifier = {
				add = -20
				opinion = {
					target = scope:dm_reform_story.var:dm_reform_reformer
					value < 0
				}
			}""",
		]
	elif kind == "trait":
		modifiers = [
			"modifier = { add = 40 OR = { has_trait = diligent has_trait = patient } }",
			"modifier = { add = 20 OR = { has_trait = just has_trait = honest } }",
		]
	else:
		modifiers = [
			"modifier = { add = 30 OR = { has_trait = generous has_trait = ambitious has_trait = diligent } }"
		]
		if resource == "prestige":
			modifiers += [
				"modifier = { add = 20 OR = { has_trait = arrogant has_trait = brave } }",
				"modifier = { add = -20 has_trait = humble }",
			]
		elif resource == "gold":
			modifiers.append("modifier = { add = -30 has_trait = greedy }")
		else:
			modifiers += [
				"modifier = { add = 30 has_trait = zealous }",
				"modifier = { add = -30 has_trait = cynical }",
			]
	return f"""\t\tai_chance = {{
			base = {base}
			{chr(10).join(modifiers)}
		}}"""


def render_reform_event_entry(index: int, category: str, attribute: str) -> str:
	eid = reform_event_id(index)
	cooldown_days = 3650 if index < 25 else 1825
	positive_traits, _ = ATTRIBUTE_ACTOR_TRAITS[attribute]
	resource = RESOURCE_BY_ATTRIBUTE[attribute]
	cost = RESOURCE_COST_BY_CATEGORY[category]
	next_event = ""
	if index < 25:
		next_event = f"\n\t\t\t\t\ttrigger_event = {{ id = dm_reform.{2101 + index} days = 1 }}"
	trait_trigger = f"""OR = {{
			scope:dm_reform_story.story_owner = {{ OR = {{ {_trait_or(positive_traits)} }} }}
			scope:dm_reform_story.var:dm_reform_reformer ?= {{ OR = {{ {_trait_or(positive_traits)} }} }}
		}}"""
	return f"""dm_reform.{eid} = {{
	type = character_event
	title = dm_reform.{eid}.t
	desc = dm_reform.{eid}.desc
	theme = court
	left_portrait = scope:dm_reform_actor
	immediate = {{
		scope:dm_reform_story = {{
			set_variable = {{ name = dm_reform_event_{eid}_next_day value = var:dm_reform_elapsed_days }}
			change_variable = {{ name = dm_reform_event_{eid}_next_day add = {cooldown_days} }}
		}}
		{_actor_selection(category, attribute)}
	}}
	option = {{
		name = dm_reform.event.ruler_response
		show_as_unavailable = {{ always = yes }}
		custom_tooltip = dm_reform.{eid}.ruler_tt
{_result_roll(f"dm_reform_ruler_check_{attribute}_value", 0, category, next_event)}
{_option_ai_chance("ruler")}
	}}
	option = {{
		name = dm_reform.event.reformer_response
		trigger = {{ scope:dm_reform_story = {{ dm_reform_has_reformer_trigger = yes }} }}
		show_as_unavailable = {{ always = yes }}
		custom_tooltip = dm_reform.{eid}.reformer_tt
{_result_roll(f"dm_reform_reformer_check_{attribute}_value", 0, category, next_event)}
{_option_ai_chance("reformer")}
	}}
	option = {{
		name = dm_reform.event.trait_response
		trigger = {{ {trait_trigger} }}
		show_as_unavailable = {{ always = yes }}
		custom_tooltip = dm_reform.{eid}.trait_tt
{_result_roll(f"dm_reform_trait_check_{attribute}_value", 5, category, next_event)}
{_option_ai_chance("trait")}
	}}
	option = {{
		name = dm_reform.event.resource_response
		trigger = {{
			{resource} >= {cost}
			trigger_if = {{ limit = {{ is_ai = yes }} {resource} >= {cost * 2} }}
		}}
		show_as_unavailable = {{ always = yes }}
		custom_tooltip = dm_reform.{eid}.resource_tt
		add_{resource} = -{cost}
{_result_roll(f"dm_reform_check_{attribute}_value", 10, category, next_event)}
{_option_ai_chance("resource", resource)}
	}}
}}"""


def render_reform_followup(index: int, final: bool) -> str:
	eid = (3101 if final else 2101) + index
	next_text = ""
	if not final:
		next_text = f"\n\t\ttrigger_event = {{ id = dm_reform.{3101 + index} days = 2 }}"
	return f"""dm_reform.{eid} = {{
\ttype = character_event
\ttitle = dm_reform.chain_followup.t
\tdesc = dm_reform.chain_followup.desc
\ttheme = court
\ttrigger = {{
\t\texists = scope:dm_reform_story
\t\texists = scope:dm_reform_actor
\t\tscope:dm_reform_actor = {{ is_alive = yes }}
\t}}
\ton_trigger_fail = {{ trigger_event = dm_reform.0231 }}
\tleft_portrait = scope:dm_reform_actor
\toption = {{
\t\tname = dm_reform.chain_followup.a{next_text}
\t}}
}}"""


def render_generated_events() -> str:
	parts = ["namespace = dm_reform", ""]
	for index, (category, _, attribute) in enumerate(EVENT_CATALOG):
		parts.append(render_reform_event_entry(index, category, attribute))
		parts.append("")
	for index in range(25):
		parts.append(render_reform_followup(index, False))
		parts.append("")
		parts.append(render_reform_followup(index, True))
		parts.append("")
	return "\n".join(parts)


def render_event_localization() -> str:
	lines = ["l_simp_chinese:"]
	category_desc = {
		"crisis": "反对者借此事发难，局势已逼近失控。你必须依靠自身或改革者的能力化解危机。",
		"setback": "一名反对者使新制的推行受阻。妥善应对仍可能把阻力转化为进展。",
		"calm": "朝堂暂时平静，这段时间适合校订章程并检验变法的薄弱之处。",
		"encouragement": "支持者带来了好消息，也带来了一个扩大成果的机会。",
		"breakthrough": "长期积累终于打开局面；若能抓住这一刻，新制将大步向前。",
	}
	for index, (category, title, _) in enumerate(EVENT_CATALOG):
		eid = reform_event_id(index)
		lines.append(f' dm_reform.{eid}.t:0 "{title}"')
		lines.append(
			f' dm_reform.{eid}.desc:0 '
			f'"[dm_reform_actor.GetShortUIName]（[dm_reform_actor.Custom(\'DMReformActorOffice\')]）'
			f'{category_desc[category]}"'
		)
	return "\ufeff" + "\n".join(lines) + "\n"


def render_event_localization() -> str:
	lines = ["l_simp_chinese:"]
	category_desc = {
		"crisis": "反对者借此事发难，局势已逼近失控。你必须依靠自己或改革者的能力化解危机。",
		"setback": "一名反对者使新制的推行受阻。妥善应对仍可能把阻力转化为进展。",
		"calm": "朝堂暂时平静，这段时间适合校订章程并检验变法的薄弱之处。",
		"encouragement": "支持者带来了好消息，也带来了一个扩大成果的机会。",
		"breakthrough": "长期积累终于打开局面；若能抓住这一刻，新制将大步向前。",
	}
	for index, (category, title, _) in enumerate(EVENT_CATALOG):
		eid = reform_event_id(index)
		lines.append(f' dm_reform.{eid}.t:0 "{title}"')
		lines.append(
			f' dm_reform.{eid}.desc:0 '
			f'"[dm_reform_actor.GetShortUIName]（'
			f'[dm_reform_actor.Custom(\'DMReformActorOffice\')]）：'
			f'{category_desc[category]}"'
		)
	return "\ufeff" + "\n".join(lines) + "\n"


def _signed(value: int) -> str:
	return f"+{value}" if value > 0 else str(value)


def _event_option_tooltip(
	category: str,
	attribute: str,
	check_value: str,
	bonus: int,
	prefix: str,
) -> str:
	difficulty = CATEGORY_RESULTS[category][4]
	thresholds = [difficulty + boundary - bonus for boundary, _, _ in PROBABILITY_TIERS if boundary is not None]
	bands = (
		f"≤{thresholds[0]}：35%/45%/19%/1%；"
		f"{thresholds[0] + 1}—{thresholds[1]}：25%/40%/30%/5%；"
		f"{thresholds[1] + 1}—{thresholds[2]}：15%/35%/40%/10%；"
		f"{thresholds[2] + 1}—{thresholds[3]}：10%/25%/45%/20%；"
		f"{thresholds[3] + 1}—{thresholds[4]}：5%/15%/50%/30%；"
		f"≥{thresholds[4] + 1}：1%/9%/50%/40%"
	)
	result_labels = ("灾难", "失败", "成功", "大成功")
	results = "；".join(
		f"{label}：进度{_signed(progress)}、支持度{_signed(support)}"
		for label, (progress, support) in zip(result_labels, CATEGORY_RESULTS[category][:4])
	)
	return (
		f"{prefix}\\n当前有效属性：[SCOPE.ScriptValue('{check_value}')|0]\\n"
		f"概率顺序均为灾难/失败/成功/大成功：{bands}\\n{results}"
	)


# Final Simplified Chinese event localization, including exact per-option
# probability bands, integer results, payer and resource cost.
def render_event_localization() -> str:
	lines = ["l_simp_chinese:"]
	category_desc = {
		"crisis": "反对者借此事发难，局势已逼近失控。你必须依靠自己或改革者的能力化解危机。",
		"setback": "一名反对者使新制的推行受阻。妥善应对仍可能把阻力转化为进展。",
		"calm": "朝堂暂时平静，这段时间适合校订章程并检验变法的薄弱之处。",
		"encouragement": "支持者带来了好消息，也带来了一个扩大成果的机会。",
		"breakthrough": "长期积累终于打开局面；若能抓住这一刻，新制将大步向前。",
	}
	resource_names = {"prestige": "威望", "gold": "金钱", "piety": "虔诚"}
	for index, (category, title, attribute) in enumerate(EVENT_CATALOG):
		eid = reform_event_id(index)
		lines.append(f' dm_reform.{eid}.t:0 "{title}"')
		lines.append(
			f' dm_reform.{eid}.desc:0 '
			f'"[dm_reform_actor.GetShortUIName]（'
			f'[dm_reform_actor.Custom(\'DMReformActorOffice\')]）：'
			f'{category_desc[category]}"'
		)
		lines.append(
			f' dm_reform.{eid}.ruler_tt:0 "'
			+ _event_option_tooltip(
				category,
				attribute,
				f"dm_reform_ruler_check_{attribute}_value",
				0,
				"由君主亲自主持，只检验君主本人的属性。",
			)
			+ '"'
		)
		lines.append(
			f' dm_reform.{eid}.reformer_tt:0 "'
			+ _event_option_tooltip(
				category,
				attribute,
				f"dm_reform_reformer_check_{attribute}_value",
				0,
				"由改革者主持，只检验改革者本人的属性；没有有效改革者时不可选择。",
			)
			+ '"'
		)
		lines.append(
			f' dm_reform.{eid}.trait_tt:0 "'
			+ _event_option_tooltip(
				category,
				attribute,
				f"dm_reform_trait_check_{attribute}_value",
				5,
				"要求君主或改革者具备本事件匹配特质，使用具备特质者中的较高属性并获得+5检验加值。",
			)
			+ '"'
		)
		resource = RESOURCE_BY_ATTRIBUTE[attribute]
		cost = RESOURCE_COST_BY_CATEGORY[category]
		lines.append(
			f' dm_reform.{eid}.resource_tt:0 "'
			+ _event_option_tooltip(
				category,
				attribute,
				f"dm_reform_check_{attribute}_value",
				10,
				f"由实际接收并决定事件的[ROOT.Char.GetShortUIName]支付{cost}{resource_names[resource]}，"
				"使用君主与改革者中的较高属性并获得+10检验加值；AI支付前必须持有至少双倍资源。",
			)
			+ '"'
		)
	return "\ufeff" + "\n".join(lines) + "\n"


def render_reform_law_buttons(laws: list[Law]) -> str:
	buttons: list[str] = []
	for law in laws:
		if law.is_budget:
			continue
		interaction = f"dm_reform_start_{law.key}_interaction"
		buttons.append(
			f"""button_primary = {{
\t\t\t\t\t\tdatacontext = "[GetPlayer]"
\t\t\t\t\t\tvisible = "[EqualTo_string( SuccessionLawChangeWindow.GetSelectedLaw.GetLaw.GetKey, '{law.key}' )]"
\t\t\t\t\t\tenabled = "[Character.CanSendPlayerInteraction('{interaction}')]"
\t\t\t\t\t\tonclick = "[Character.SendPlayerInteraction('{interaction}')]"
\t\t\t\t\t\ttext = "dm_reform_start_button"
\t\t\t\t\t\tusing = tooltip_above
\t\t\t\t\t\ttooltip = "dm_reform_start_button_tooltip"
\t\t\t\t\t}}"""
		)
	return "\n\n\t\t\t\t\t".join(buttons)


def render_succession_gui(laws: list[Law]) -> str:
	source_path = VANILLA / "gui" / "window_succession_change_law.gui"
	text = source_path.read_text(encoding="utf-8-sig")
	text = text.replace(
		'visible = "[And(SuccessionLawChangeWindow.GetSelectedLaw.ShouldBeApproved, Not( GetPlayer.GetGovernment.HasRule( \'deny_powerful_vassal\' )))]"',
		"visible = no # Powerful-vassal approval is replaced by the reform story.",
		1,
	)
	text = text.replace(
		'visible = "[Not(SuccessionLawChangeWindow.GetSelectedLaw.ShouldBeApproved)]"',
		"visible = yes",
		1,
	)
	text = text.replace(
		'text = "SUCCESSION_LAW_CHANGE_WINDOW_CLAN_TITLE"',
		'text = "dm_reform_law_window_title"',
		1,
	)
	text = text.replace(
		'text = "SUCCESSION_LAW_CHANGE_WINDOW_CLAN_DESC"',
		'text = "dm_reform_law_window_desc"',
		1,
	)
	reformer_desc = """text_multi = {
								text = "dm_reform_law_window_desc"
								default_format = "#weak"
								autoresize = yes
								max_width = 500
							}"""
	reformer_picker = reformer_desc + """

							hbox = {
								layoutpolicy_horizontal = expanding
								spacing = 10

								portrait_head_small = {
									datacontext = "[GetPlayer.MakeScope.Var('dm_reform_pending_reformer').Char]"
									visible = "[Character.IsValid]"
								}

								button_standard = {
									datacontext = "[GetPlayer]"
									onclick = "[OpenCharacterInteraction( 'dm_reform_select_reformer_interaction', Character.Self )]"
									text = "dm_reform_select_reformer_button"
									tooltip = "dm_reform_select_reformer_button_tooltip"
								}

								button_standard = {
									datacontext = "[GetPlayer]"
									visible = "[GetPlayer.MakeScope.Var('dm_reform_pending_reformer').Char.IsValid]"
									enabled = "[Character.CanSendPlayerInteraction('dm_reform_clear_pending_reformer_interaction')]"
									onclick = "[Character.SendPlayerInteraction('dm_reform_clear_pending_reformer_interaction')]"
									text = "dm_reform_self_host_button"
								}
							}"""
	if reformer_desc not in text:
		raise ValueError(f"{source_path}: reformer description insertion point changed")
	text = text.replace(reformer_desc, reformer_picker, 1)
	old_button = """button_primary = {
						enabled = "[SuccessionLawChangeWindow.GetSelectedLaw.CanEnact]"
						onclick = "[SuccessionLawChangeWindow.GetSelectedLaw.Enact]"

						text = "SUCCESSION_LAW_CHANGE_WINDOW_CHANGE"

						using = tooltip_above
						tooltip = "[SuccessionLawChangeWindow.GetSelectedLaw.GetCanEnactDescription]"
					}"""
	new_buttons = render_reform_law_buttons(laws)
	if old_button not in text:
		raise ValueError(f"{source_path}: enact button template changed")
	text = text.replace(old_button, new_buttons, 1)
	return text


def render_treasury_budget_gui() -> str:
	source_path = VANILLA / "gui" / "window_treasury_budget_change.gui"
	text = source_path.read_text(encoding="utf-8-sig")
	# The allocation-law button is the native atomic budget application route.
	# Expose it and remove the separate EnactBudget button so the window performs
	# one direct transaction and never creates a reform story.
	text = text.replace(
		"""button_primary = {
						visible = no
						enabled = "[TreasuryBudgetChangeWindow.CanEnact]"
						onclick = "[TreasuryBudgetChangeWindow.EnactBudgetLaws]""",
		"""button_primary = {
						enabled = "[TreasuryBudgetChangeWindow.CanEnact]"
						onclick = "[TreasuryBudgetChangeWindow.EnactBudgetLaws]""",
		1,
	)
	direct_budget_button = """button_primary = {
						enabled = "[TreasuryBudgetChangeWindow.CanEnact]"
						onclick = "[TreasuryBudgetChangeWindow.EnactBudget]"

						text = "WINDOW_TREASURY_BUDGET_CHANGE_ENACT_BUDGET"

						using = tooltip_above
						tooltip = "[TreasuryBudgetChangeWindow.GetCanEnactBudgetDescription]"
					}"""
	if direct_budget_button not in text:
		raise ValueError(f"{source_path}: native budget button template changed")
	text = text.replace(direct_budget_button, "", 1)
	if "dm_reform_start_budget_interaction" in text:
		raise ValueError("budget GUI unexpectedly retained reform integration")
	return text


def court_position_keys() -> list[str]:
	"""Return stable loaded court-position keys for actor office localization."""
	keys: list[str] = []
	seen: set[str] = set()
	for base in (VANILLA, ROOT):
		directory = base / "common" / "court_positions" / "types"
		if not directory.is_dir():
			continue
		for path in sorted(directory.glob("*.txt")):
			text = strip_comments(path.read_text(encoding="utf-8-sig"))
			for key in re.findall(
				r"(?m)^([A-Za-z0-9_]+_court_position)\s*=\s*\{",
				text,
			):
				if key not in seen:
					seen.add(key)
					keys.append(key)
	return keys


def render_actor_office_custom_loc() -> str:
	lines = [
		"DMReformActorOffice = {",
		"\ttype = character",
		"\tlog_loc_errors = no",
		"",
		"\ttext = {",
		"\t\ttrigger = { this = scope:dm_reform_story.story_owner }",
		"\t\tlocalization_key = dm_reform_actor_office_ruler",
		"\t}",
		"\ttext = {",
		"\t\ttrigger = { scope:dm_reform_story.var:dm_reform_reformer ?= this }",
		"\t\tlocalization_key = dm_reform_actor_office_reformer",
		"\t}",
		"\ttext = {",
		"\t\ttrigger = { is_councillor_of = scope:dm_reform_story.story_owner }",
		"\t\tlocalization_key = dm_reform_actor_office_councillor",
		"\t}",
	]
	for key in court_position_keys():
		lines.extend(
			[
				"\ttext = {",
				"\t\ttrigger = {",
				f"\t\t\thas_court_position = {key}",
				"\t\t}",
				f"\t\tlocalization_key = {key}",
				"\t}",
			]
		)
	lines.extend(
		[
			"\ttext = {",
			"\t\ttrigger = { is_powerful_vassal_of = scope:dm_reform_story.story_owner }",
			"\t\tlocalization_key = dm_reform_actor_office_powerful_vassal",
			"\t}",
			"\ttext = {",
			"\t\ttrigger = { exists = var:movement_member }",
			"\t\tlocalization_key = dm_reform_actor_office_movement_leader",
			"\t}",
			"\ttext = {",
			"\t\ttrigger = { is_vassal_of = scope:dm_reform_story.story_owner }",
			"\t\tlocalization_key = dm_reform_actor_office_vassal",
			"\t}",
			"\ttext = {",
			"\t\tlocalization_key = dm_reform_actor_office_courtier",
			"\t\tfallback = yes",
			"\t}",
			"}",
			"",
		]
	)
	return "\n".join(lines)


def output_files(laws: list[Law]) -> dict[Path, str]:
	header = "# GENERATED by tools/dm_generate_reform_registry.py. DO NOT EDIT.\n\n"
	interactions = (
		header
		+ "\n\n".join(render_interaction(law) for law in laws)
		+ "\n"
	)
	effects = header + render_success_effect(laws) + "\n"
	triggers = header + render_target_valid_trigger(laws) + "\n"
	return {
		ROOT / "generated" / "dm_reform_registry.json": registry_json(laws),
		ROOT / "common" / "character_interactions" / "dm_reform_start_interactions_generated.txt": interactions,
		ROOT / "common" / "scripted_effects" / "dm_reform_registry_effects_generated.txt": effects,
		ROOT / "common" / "scripted_triggers" / "dm_reform_registry_triggers_generated.txt": triggers,
		ROOT / "events" / "dm_reform_events_generated.txt": render_generated_events(),
		ROOT
		/ "localization"
		/ "simp_chinese"
		/ "dm_reform_events_generated_l_simp_chinese.yml": render_event_localization(),
		ROOT / "gui" / "window_succession_change_law.gui": render_succession_gui(laws),
		ROOT / "gui" / "window_treasury_budget_change.gui": render_treasury_budget_gui(),
		ROOT
		/ "common"
		/ "customizable_localization"
		/ "dm_reform_actor_office_custom_loc.txt": render_actor_office_custom_loc(),
	}


def write_or_check(outputs: dict[Path, str], check: bool) -> bool:
	ok = True
	for path, expected in outputs.items():
		if check:
			encoding = "utf-8" if expected.startswith("\ufeff") else "utf-8-sig"
			actual = path.read_text(encoding=encoding) if path.exists() else None
			if actual != expected:
				print(f"DRIFT: {path.relative_to(ROOT)}", file=sys.stderr)
				ok = False
			continue
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(expected, encoding="utf-8", newline="\n")
		print(f"WROTE: {path.relative_to(ROOT)}")
	return ok


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--check", action="store_true")
	parser.add_argument("--list", action="store_true")
	args = parser.parse_args()
	if not VANILLA.is_dir():
		raise SystemExit(f"vanilla game root not found: {VANILLA}")
	manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
	laws, _ = collect_laws(manifest)
	if args.list:
		for law in laws:
			print(f"{law.group}\t{law.key}\t{law.theme}\t{law.axis}\t{law.level}")
		print(f"registered laws: {len(laws)}", file=sys.stderr)
		return 0
	outputs = output_files(laws)
	for path, text in list(outputs.items()):
		text = "\n".join(line.rstrip() for line in text.split("\n"))
		if (
			(
				path.suffix == ".txt"
				or (
					path.suffix in {".gui", ".yml"}
					and any(ord(character) > 127 for character in text)
				)
			)
			and not text.startswith("\ufeff")
		):
			text = "\ufeff" + text
		outputs[path] = text
	if not write_or_check(outputs, args.check):
		return 1
	print(f"reform registry OK: {len(laws)} laws, {len(outputs)} generated files")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
