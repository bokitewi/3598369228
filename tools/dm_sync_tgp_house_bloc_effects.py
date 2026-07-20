#!/usr/bin/env python3
"""Create vanilla house-bloc effects safe around invalidated optional scopes."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


KEY = "tgp_on_member_house_left_shared_effect"
SET_LEADER_KEY = "tgp_set_house_bloc_leading_house_effect"
CREATE_KEY = "tgp_create_house_bloc_effect"
JOIN_KEY = "tgp_join_house_bloc_effect"
JOINED_KEY = "tgp_on_member_house_joined_shared_effect"
OLD_TAIL = """    # Disband if necessary
    if = {
        limit = {
            OR = {
                NOT = { exists = leading_house }
                any_confederation_member_house = { count = 1 }
            }
        }
        hidden_effect = { disband_confederation = yes }
    }
    if = {
        limit = { debug_only = yes }
        debug_log = "house left bloc"
        debug_log_scopes = yes
    }"""
NEW_TAIL = """    if = {
        limit = { debug_only = yes }
        debug_log = "house left bloc"
        debug_log_scopes = yes
    }
    # Disband last: the current confederation scope is invalid afterwards.
    if = {
        limit = {
            OR = {
                NOT = { exists = leading_house }
                any_confederation_member_house = { count = 1 }
            }
        }
        hidden_effect = { disband_confederation = yes }
    }"""


def extract_object(text: str, key: str) -> str:
	match = re.search(rf"(?m)^{re.escape(key)}\s*=\s*\{{", text)
	if not match:
		raise RuntimeError(f"Missing vanilla effect: {key}")
	start = match.start()
	depth = 0
	in_string = False
	in_comment = False
	escaped = False
	for index in range(start, len(text)):
		char = text[index]
		if in_comment:
			if char == "\n":
				in_comment = False
			continue
		if in_string:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				in_string = False
			continue
		if char == "#":
			in_comment = True
		elif char == '"':
			in_string = True
		elif char == "{":
			depth += 1
		elif char == "}":
			depth -= 1
			if depth == 0:
				return text[start : index + 1]
	raise RuntimeError(f"Unbalanced vanilla effect: {key}")


def normalize_indent(block: str) -> str:
	lines: list[str] = []
	for line in block.splitlines():
		leading_spaces = len(line) - len(line.lstrip(" "))
		lines.append("\t" * (leading_spaces // 4) + line[leading_spaces:])
	return "\n".join(lines)


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--vanilla",
		type=Path,
		default=Path(r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"),
	)
	args = parser.parse_args()
	mod_root = Path(__file__).resolve().parents[1]
	source = (
		args.vanilla
		/ "common"
		/ "scripted_effects"
		/ "10_dlc_tgp_house_bloc_scripted_effects.txt"
	)
	target = (
		mod_root
		/ "common"
		/ "scripted_effects"
		/ "zz_dm_compat_tgp_house_bloc_effects.txt"
	)

	text = source.read_text(encoding="utf-8-sig")
	block = extract_object(text, KEY)
	if block.count(OLD_TAIL) != 1:
		raise RuntimeError(f"Vanilla effect tail changed in {KEY}")
	block = block.replace(OLD_TAIL, NEW_TAIL, 1)
	block = normalize_indent(block)

	set_leader_block = extract_object(text, SET_LEADER_KEY)
	old_leader_read = "\tleading_house = { save_scope_as = old_leader }"
	safe_old_leader_read = "\tleading_house ?= { save_scope_as = old_leader }"
	if set_leader_block.count(old_leader_read) != 1:
		raise RuntimeError(f"Vanilla leading-house read changed in {SET_LEADER_KEY}")
	set_leader_block = set_leader_block.replace(
		old_leader_read,
		safe_old_leader_read,
		1,
	)
	set_leader_block = normalize_indent(set_leader_block)

	create_block = extract_object(text, CREATE_KEY)
	indirect_leader = "\t\t\t\t\tleader = house"
	direct_leader = "\t\t\t\t\tleader = scope:bloc_creator"
	leader_count = create_block.count(indirect_leader)
	if leader_count != 6:
		raise RuntimeError(
			f"Expected 6 vanilla house-bloc leader assignments, found {leader_count}"
		)
	create_block = create_block.replace(indirect_leader, direct_leader)
	create_block = normalize_indent(create_block)

	join_block = extract_object(text, JOIN_KEY)
	add_member_marker = "\t\t# ADD MEMBER HOUSE"
	safe_transition = """		# Match the vanilla interaction order for direct event/effect callers:
		# fully finish old-bloc callbacks before adding this house to a new bloc.
		if = {
			limit = {
				exists = scope:old_bloc
				scope:old_bloc != scope:bloc
			}
			scope:joiner = {
				tgp_leave_house_bloc_effect = {
					OPINION = flag:no
					TRUCE = flag:no
				}
			}
		}
"""
	if join_block.count(add_member_marker) != 1:
		raise RuntimeError(f"Vanilla member insertion changed in {JOIN_KEY}")
	join_block = join_block.replace(
		add_member_marker,
		safe_transition + add_member_marker,
		1,
	)
	for old, new, expected in (
		(
			"\tsave_scope_as = joiner",
			"\tsave_temporary_scope_as = joiner",
			1,
		),
		(
			"\thouse_confederation ?= { save_scope_as = old_bloc }",
			"\thouse_confederation ?= { save_temporary_scope_as = old_bloc }",
			1,
		),
		(
			"\t\tsave_scope_as = inviter",
			"\t\tsave_temporary_scope_as = inviter",
			1,
		),
		(
			"\t\thouse_confederation ?= { save_scope_as = bloc }",
			"\t\thouse_confederation ?= { save_temporary_scope_as = bloc }",
			1,
		),
	):
		if join_block.count(old) != expected:
			raise RuntimeError(f"Vanilla temporary-scope anchor changed: {old}")
		join_block = join_block.replace(old, new, expected)
	join_block = normalize_indent(join_block)

	joined_block = extract_object(text, JOINED_KEY)
	for old, new in (
		("\tsave_scope_as = bloc", "\tsave_temporary_scope_as = bloc"),
		("\t\tsave_scope_as = joiner", "\t\tsave_temporary_scope_as = joiner"),
	):
		if joined_block.count(old) != 1:
			raise RuntimeError(f"Vanilla joined-callback scope changed: {old}")
		joined_block = joined_block.replace(old, new, 1)
	vassal_transition = """\
\t\tif = {
\t\t\tlimit = { exists = house_confederation }
\t\t\tset_variable = {
\t\t\t\tname = bloc_leaving_reason
\t\t\t\tvalue = flag:reason_followed_liege
\t\t\t\tdays = 4
\t\t\t}
\t\t\ttgp_leave_house_bloc_effect = {
\t\t\t\tOPINION = flag:no
\t\t\t\tTRUCE = flag:yes
\t\t\t}
\t\t}
\t\ttgp_join_house_bloc_effect = {
\t\t\tINVITER = scope:joiner
\t\t\tOPINION = flag:no
\t\t}
"""
	safe_vassal_transition = """\
\t\t# The list can outlive a title/government change. Re-evaluate the exact
\t\t# vanilla member-house conditions without replacing the permanent
\t\t# callback scope:house reserved by the engine.
\t\tif = {
\t\t\tlimit = {
\t\t\t\texists = scope:bloc
\t\t\t\thouse_head ?= {
\t\t\t\t\ttrigger_if = {
\t\t\t\t\t\tlimit = {
\t\t\t\t\t\t\texists = scope:bloc.leading_house.house_head.top_liege
\t\t\t\t\t\t}
\t\t\t\t\t\ttop_liege ?= scope:bloc.leading_house.house_head.top_liege
\t\t\t\t\t}
\t\t\t\t\tis_alive = yes
\t\t\t\t\tany_held_title = { is_noble_family_title = yes }
\t\t\t\t\ttgp_uses_house_blocs_trigger = yes
\t\t\t\t}
\t\t\t}
\t\t\tif = {
\t\t\t\tlimit = { exists = house_confederation }
\t\t\t\tset_variable = {
\t\t\t\t\tname = bloc_leaving_reason
\t\t\t\t\tvalue = flag:reason_followed_liege
\t\t\t\t\tdays = 4
\t\t\t\t}
\t\t\t\ttgp_leave_house_bloc_effect = {
\t\t\t\t\tOPINION = flag:no
\t\t\t\t\tTRUCE = flag:yes
\t\t\t\t}
\t\t\t}
\t\t\ttgp_join_house_bloc_effect = {
\t\t\t\tINVITER = scope:joiner
\t\t\t\tOPINION = flag:no
\t\t\t}
\t\t}
"""
	if joined_block.count(vassal_transition) != 1:
		raise RuntimeError("Vanilla recursive vassal-house transition changed")
	joined_block = joined_block.replace(
		vassal_transition,
		safe_vassal_transition,
		1,
	)
	joined_block = normalize_indent(joined_block)

	for old, new in (
		("\tsave_scope_as = bloc", "\tsave_temporary_scope_as = bloc"),
		("\t\tsave_scope_as = leaver", "\t\tsave_temporary_scope_as = leaver"),
		(
			"\t\thouse_head ?= { save_scope_as = house_head }",
			"\t\thouse_head ?= { save_temporary_scope_as = house_head }",
		),
	):
		if block.count(old) != 1:
			raise RuntimeError(f"Vanilla left-callback scope changed: {old}")
		block = block.replace(old, new, 1)

	header = (
		"# Synced from vanilla 1.19 10_dlc_tgp_house_bloc_scripted_effects.txt.\n"
		"# Logging occurs before a one-house bloc is disbanded and invalidates its scope.\n"
		"# Re-entrant join/leave callbacks use temporary scopes to prevent nested\n"
		"# vassal-house processing from overwriting the parent bloc and house.\n\n"
	)
	target.write_text(
		header
		+ create_block
		+ "\n\n"
		+ set_leader_block
		+ "\n\n"
		+ join_block
		+ "\n\n"
		+ joined_block
		+ "\n\n"
		+ block
		+ "\n",
		encoding="utf-8-sig",
	)
	print(f"Wrote {target}")
	print(f"{CREATE_KEY}: {create_block.count(chr(10)) + 1} lines")
	print(f"{SET_LEADER_KEY}: {set_leader_block.count(chr(10)) + 1} lines")
	print(f"{JOIN_KEY}: {join_block.count(chr(10)) + 1} lines")
	print(f"{JOINED_KEY}: {joined_block.count(chr(10)) + 1} lines")
	print(f"{KEY}: {block.count(chr(10)) + 1} lines")


if __name__ == "__main__":
	main()
