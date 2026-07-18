"""Generate the minimum legal 3850 history state for the Spring/Autumn map.

The script consumes a fresh CK3 error log, uses the mod's landed-title tree as
the authoritative geography, and:

* fills missing county-capital culture/faith from the nearest de-jure region;
* gives previously landless historical high-title holders a local county first;
* creates stable dm_autoholder_* lowborns for all remaining unheld counties;
* preserves existing holders and every authored character-history file.

Generated character/title files are replaced atomically. Existing province
history files are only changed by inserting absent culture/religion fields into
the already-authored province block.
"""

from __future__ import annotations

import argparse
import codecs
import os
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import TypeAlias


ROOT = Path(__file__).resolve().parents[1]
START_DATE = (3850, 1, 1)
HISTORY_DATE = "3849.12.31"
TITLE_RE = re.compile(r"^[ekdcb]_[A-Za-z0-9_]+$")
DATE_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
ATOM_RE = re.compile(r'"(?:\\.|[^"])*"|[{}=]|[^\s{}=]+')

Value: TypeAlias = str | list[tuple[str | None, "Value"]]
Block: TypeAlias = list[tuple[str | None, Value]]


def strip_comments(text: str) -> str:
	out: list[str] = []
	quoted = False
	escaped = False
	i = 0
	while i < len(text):
		char = text[i]
		if quoted:
			out.append(char)
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
			i += 1
			continue
		if char == '"':
			quoted = True
			out.append(char)
			i += 1
			continue
		if char == "#":
			while i < len(text) and text[i] not in "\r\n":
				i += 1
			continue
		out.append(char)
		i += 1
	return "".join(out)


def atom(value: Value) -> str | None:
	if isinstance(value, list):
		return None
	if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
		return value[1:-1]
	return value


def parse_script(text: str) -> Block:
	tokens = ATOM_RE.findall(strip_comments(text))
	index = 0

	def parse_block(stop_at_close: bool) -> Block:
		nonlocal index
		items: Block = []
		while index < len(tokens):
			if tokens[index] == "}":
				if stop_at_close:
					index += 1
					return items
				index += 1
				continue
			if tokens[index] == "{":
				index += 1
				items.append((None, parse_block(True)))
				continue
			key = tokens[index]
			index += 1
			if index < len(tokens) and tokens[index] == "=":
				index += 1
				if index < len(tokens) and tokens[index] == "{":
					index += 1
					value: Value = parse_block(True)
				elif index < len(tokens):
					value = tokens[index]
					index += 1
				else:
					value = ""
				items.append((key, value))
			else:
				items.append((None, key))
		return items

	return parse_block(False)


def read_script(path: Path) -> Block:
	return parse_script(path.read_text(encoding="utf-8-sig", errors="replace"))


def dated_direct_value(block: Block, field: str) -> str | None:
	events: list[tuple[tuple[int, int, int], int, str]] = []
	order = 0
	for key, value in block:
		if key == field:
			candidate = atom(value)
			if candidate is not None:
				events.append(((0, 0, 0), order, candidate))
				order += 1
			continue
		if key is None or not isinstance(value, list):
			continue
		match = DATE_RE.match(key)
		if not match:
			continue
		date = tuple(map(int, match.groups()))
		if date > START_DATE:
			continue
		for nested_key, nested_value in value:
			if nested_key == field:
				candidate = atom(nested_value)
				if candidate is not None:
					events.append((date, order, candidate))
					order += 1
	if not events:
		return None
	return max(events, key=lambda item: (item[0], item[1]))[2]


def load_title_tree() -> tuple[
	dict[str, str],
	dict[str, list[str]],
	dict[str, str],
	dict[str, int],
	set[str],
]:
	parent: dict[str, str] = {}
	children: dict[str, list[str]] = defaultdict(list)
	capital: dict[str, str] = {}
	province: dict[str, int] = {}
	landless: set[str] = set()

	def walk(title: str, block: Block) -> None:
		for key, value in block:
			if key == "capital":
				candidate = atom(value)
				if candidate and TITLE_RE.match(candidate):
					capital[title] = candidate
			elif key == "landless" and atom(value) == "yes":
				landless.add(title)
			elif key == "province":
				candidate = atom(value)
				if title.startswith("b_") and candidate and candidate.isdigit():
					province[title] = int(candidate)
			elif key and TITLE_RE.match(key) and isinstance(value, list):
				parent[key] = title
				children[title].append(key)
				walk(key, value)

	def walk_container(block: Block) -> None:
		for key, value in block:
			if not isinstance(value, list):
				continue
			if key and TITLE_RE.match(key):
				walk(key, value)
			elif key and key.startswith("h_"):
				# Total-conversion maps commonly wrap their actual empires in
				# a non-title h_* geographical hierarchy container.
				walk_container(value)

	for path in sorted((ROOT / "common" / "landed_titles").glob("*.txt")):
		walk_container(read_script(path))
	return parent, children, capital, province, landless


def load_province_history() -> tuple[
	dict[int, dict[str, str]],
	dict[int, Path],
]:
	metadata: dict[int, dict[str, str]] = {}
	source: dict[int, Path] = {}
	for path in sorted((ROOT / "history" / "provinces").glob("*.txt")):
		if path.name == "dm_autofill_province_history.txt":
			continue
		for key, value in read_script(path):
			if not key or not key.isdigit() or not isinstance(value, list):
				continue
			province_id = int(key)
			entry = metadata.setdefault(province_id, {})
			for field in ("culture", "religion"):
				candidate = dated_direct_value(value, field)
				if candidate:
					entry[field] = candidate
			source[province_id] = path
	return metadata, source


def load_title_holders() -> dict[str, str]:
	holders: dict[str, str] = {}
	for path in sorted((ROOT / "history" / "titles").glob("*.txt")):
		if path.name == "dm_autoholder_titles.txt":
			continue
		for key, value in read_script(path):
			if key and TITLE_RE.match(key) and isinstance(value, list):
				holder = dated_direct_value(value, "holder")
				if holder and holder not in {"0", "none"}:
					holders[key] = holder
	return holders


def load_culture_names() -> dict[str, str]:
	names: dict[str, Counter[str]] = defaultdict(Counter)
	for path in sorted((ROOT / "history" / "characters").glob("*.txt")):
		if path.name == "dm_autoholders.txt":
			continue
		for _, value in read_script(path):
			if not isinstance(value, list):
				continue
			culture = dated_direct_value(value, "culture")
			name = dated_direct_value(value, "name")
			if culture and name:
				names[culture][name] += 1
	result: dict[str, str] = {}
	for culture, counter in names.items():
		best_count = max(counter.values())
		result[culture] = min(
			name for name, count in counter.items() if count == best_count
		)
	return result


def extract_log_sets(error_log: Path) -> tuple[set[str], set[str], set[str]]:
	text = error_log.read_text(encoding="utf-8-sig", errors="replace")
	unheld = set(
		re.findall(
			r"\b(c_[A-Za-z0-9_]+) doesn't have a holder after history",
			text,
		)
	)
	missing_culture = set(
		re.findall(
			r"County (c_[A-Za-z0-9_]+) is missing culture",
			text,
		)
	)
	missing_faith = set(
		re.findall(
			r"County (c_[A-Za-z0-9_]+) is missing faith",
			text,
		)
	)
	return unheld, missing_culture, missing_faith


def extract_landless_historical_holders(path: Path) -> dict[str, str]:
	result: dict[str, str] = {}
	pattern = re.compile(
		r"\bof ([ekd]_[A-Za-z0-9_]+) .*?"
		r"Historical ID ([^)]+)\) should hold at least one landed title"
	)
	for match in pattern.finditer(
		path.read_text(encoding="utf-8-sig", errors="replace")
	):
		result[match.group(1)] = match.group(2).strip()
	return result


def line_brace_delta(line: str) -> int:
	clean = strip_comments(line)
	clean = re.sub(r'"(?:\\.|[^"])*"', '""', clean)
	return clean.count("{") - clean.count("}")


def insert_province_metadata(
	assignments: dict[int, dict[str, str]],
	source: dict[int, Path],
) -> None:
	by_file: dict[Path, dict[int, dict[str, str]]] = defaultdict(dict)
	missing_blocks: dict[int, dict[str, str]] = {}
	for province_id, fields in assignments.items():
		if not fields:
			continue
		if province_id in source:
			by_file[source[province_id]][province_id] = fields
		else:
			missing_blocks[province_id] = fields

	for path, targets in by_file.items():
		raw = path.read_bytes()
		has_bom = raw.startswith(codecs.BOM_UTF8)
		text = raw[len(codecs.BOM_UTF8) :].decode(
			"utf-8", errors="replace"
		) if has_bom else raw.decode("utf-8", errors="replace")
		newline = "\r\n" if "\r\n" in text else "\n"
		lines = text.splitlines()
		depth = 0
		output: list[str] = []
		seen: set[int] = set()
		for line in lines:
			match = (
				re.match(r"^\s*(\d+)\s*=\s*\{", line)
				if depth == 0
				else None
			)
			output.append(line)
			if match:
				province_id = int(match.group(1))
				if province_id in targets:
					for field in ("culture", "religion"):
						if field in targets[province_id]:
							output.append(
								f"\t{field} = {targets[province_id][field]}"
							)
					seen.add(province_id)
			depth += line_brace_delta(line)
		if seen != set(targets):
			raise RuntimeError(
				f"Could not locate province blocks in {path}: "
				f"{sorted(set(targets) - seen)}"
			)
		payload = (newline.join(output) + newline).encode("utf-8")
		temp = path.with_suffix(path.suffix + ".dm_tmp")
		temp.write_bytes(codecs.BOM_UTF8 + payload)
		os.replace(temp, path)

	generated = ROOT / "history" / "provinces" / "dm_autofill_province_history.txt"
	lines = [
		"# Generated compatibility metadata for capital provinces without",
		"# an authored province-history block.",
		"",
	]
	for province_id, fields in sorted(missing_blocks.items()):
		lines.append(f"{province_id} = {{")
		for field in ("culture", "religion"):
			if field in fields:
				lines.append(f"\t{field} = {fields[field]}")
		lines.extend(["}", ""])
	generated.write_bytes(
		codecs.BOM_UTF8 + ("\n".join(lines) + "\n").encode("utf-8")
	)


def write_generated(
	path: Path,
	lines: list[str],
) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	temp = path.with_suffix(path.suffix + ".dm_tmp")
	temp.write_bytes(codecs.BOM_UTF8 + ("\n".join(lines) + "\n").encode("utf-8"))
	os.replace(temp, path)


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--error-log", required=True, type=Path)
	parser.add_argument("--landless-log", required=True, type=Path)
	args = parser.parse_args()

	parent, children, capital, barony_province, landless_titles = load_title_tree()
	province_metadata, province_source = load_province_history()
	current_holders = load_title_holders()
	culture_names = load_culture_names()
	unheld, missing_culture, missing_faith = extract_log_sets(args.error_log)
	landless_holders = extract_landless_historical_holders(args.landless_log)

	# County shells retained for stable script/localization keys are explicitly
	# landless and must not receive map history or generated landed holders.
	ignored_landless = (
		(unheld | missing_culture | missing_faith) & landless_titles
	)
	unheld -= landless_titles
	missing_culture -= landless_titles
	missing_faith -= landless_titles

	@lru_cache(maxsize=None)
	def descendant_provinces(title: str) -> tuple[int, ...]:
		if title.startswith("b_"):
			value = barony_province.get(title)
			return (value,) if value is not None else ()
		values: list[int] = []
		for child in children.get(title, []):
			values.extend(descendant_provinces(child))
		return tuple(dict.fromkeys(values))

	@lru_cache(maxsize=None)
	def descendant_counties(title: str) -> tuple[str, ...]:
		values: list[str] = []
		for child in children.get(title, []):
			if child.startswith("c_"):
				values.append(child)
			else:
				values.extend(descendant_counties(child))
		return tuple(dict.fromkeys(values))

	def county_capital_province(county: str) -> int:
		explicit = capital.get(county)
		if explicit and explicit in barony_province:
			return barony_province[explicit]
		for child in children.get(county, []):
			if child.startswith("b_") and child in barony_province:
				return barony_province[child]
		raise RuntimeError(f"County {county} has no defined capital barony province")

	def ancestor_chain(title: str) -> list[str]:
		result: list[str] = []
		while title in parent:
			title = parent[title]
			result.append(title)
		return result

	global_culture = Counter(
		entry["culture"]
		for entry in province_metadata.values()
		if "culture" in entry
	).most_common(1)[0][0]
	global_religion = Counter(
		entry["religion"]
		for entry in province_metadata.values()
		if "religion" in entry
	).most_common(1)[0][0]

	@lru_cache(maxsize=None)
	def regional_mode(title: str, field: str) -> str | None:
		counter = Counter(
			province_metadata[province_id][field]
			for province_id in descendant_provinces(title)
			if field in province_metadata.get(province_id, {})
		)
		if not counter:
			return None
		best_count = max(counter.values())
		return min(
			value for value, count in counter.items() if count == best_count
		)

	def infer(county: str, field: str) -> str:
		capital_id = county_capital_province(county)
		if field in province_metadata.get(capital_id, {}):
			return province_metadata[capital_id][field]
		for province_id in descendant_provinces(county):
			if field in province_metadata.get(province_id, {}):
				return province_metadata[province_id][field]
		for ancestor in ancestor_chain(county):
			candidate = regional_mode(ancestor, field)
			if candidate:
				return candidate
		return global_culture if field == "culture" else global_religion

	all_referenced_counties = unheld | missing_culture | missing_faith
	unknown_counties = sorted(
		county for county in all_referenced_counties if county not in parent
	)
	if unknown_counties:
		raise RuntimeError(
			f"Log references {len(unknown_counties)} counties outside the title "
			f"tree: {unknown_counties[:20]}"
		)

	province_insertions: dict[int, dict[str, str]] = defaultdict(dict)
	for county in sorted(missing_culture | missing_faith):
		province_id = county_capital_province(county)
		if county in missing_culture and "culture" not in province_metadata.get(
			province_id, {}
		):
			province_insertions[province_id]["culture"] = infer(
				county, "culture"
			)
		if county in missing_faith and "religion" not in province_metadata.get(
			province_id, {}
		):
			province_insertions[province_id]["religion"] = infer(
				county, "religion"
			)

	# Make inferred metadata visible to autoholder generation before writing.
	for province_id, fields in province_insertions.items():
		province_metadata.setdefault(province_id, {}).update(fields)

	assignments: dict[str, tuple[str, str | None]] = {}
	available = set(unheld)
	rank_order = {"e": 0, "k": 1, "d": 2}
	for high_title, holder in sorted(
		landless_holders.items(),
		key=lambda item: (
			rank_order.get(item[0][0], 9),
			item[0],
		),
	):
		candidates = [
			county
			for county in descendant_counties(high_title)
			if county in available
		]
		if not candidates:
			continue
		preferred = capital.get(high_title)
		county = (
			preferred
			if preferred in candidates
			else sorted(candidates)[0]
		)
		assignments[county] = (holder, high_title)
		available.remove(county)

	new_characters: dict[str, tuple[str, str, str]] = {}
	for index, county in enumerate(sorted(available), start=1):
		character = f"dm_autoholder_{index:04d}"
		province_id = county_capital_province(county)
		culture = province_metadata.get(province_id, {}).get(
			"culture", infer(county, "culture")
		)
		religion = province_metadata.get(province_id, {}).get(
			"religion", infer(county, "religion")
		)
		name = culture_names.get(culture, "nanming1")
		new_characters[character] = (name, culture, religion)

		liege = next(
			(
				ancestor
				for ancestor in ancestor_chain(county)
				if ancestor.startswith(("d_", "k_", "e_"))
				and (
					ancestor in current_holders
					or ancestor in landless_holders
				)
			),
			None,
		)
		assignments[county] = (character, liege)

	insert_province_metadata(province_insertions, province_source)

	character_lines = [
		"# Generated non-historical county holders for the 3850 start.",
		"# They are intentionally lowborn and absent from bookmarks/events.",
		"",
	]
	for character, (name, culture, religion) in sorted(new_characters.items()):
		character_lines.extend(
			[
				f"{character} = {{",
				f'\tname = "{name}"',
				f"\tculture = {culture}",
				f"\treligion = {religion}",
				"\t3810.1.1 = {",
				"\t\tbirth = yes",
				"\t}",
				"}",
				"",
			]
		)
	generated_character_path = (
		ROOT / "history" / "characters" / "dm_autoholders.txt"
	)
	generated_title_path = (
		ROOT / "history" / "titles" / "dm_autoholder_titles.txt"
	)
	preserve_existing_holders = (
		not unheld
		and generated_character_path.exists()
		and generated_title_path.exists()
	)
	if not preserve_existing_holders:
		write_generated(generated_character_path, character_lines)

	title_lines = [
		"# Generated minimum legal holders for counties unowned at 3850.1.1.",
		"",
	]
	for county, (holder, liege) in sorted(assignments.items()):
		title_lines.extend(
			[
				f"{county} = {{",
				f"\t{HISTORY_DATE} = {{",
				f"\t\tholder = {holder}",
			]
		)
		if liege:
			title_lines.append(f"\t\tliege = {liege}")
		title_lines.extend(["\t}", "}", ""])
	if not preserve_existing_holders:
		write_generated(generated_title_path, title_lines)

	reused = len(assignments) - len(new_characters)
	print(f"Unheld counties assigned: {len(assignments)}")
	print(f"Landless county shells ignored: {len(ignored_landless)}")
	print(f"Existing historical high-title holders reused: {reused}")
	print(f"Generated dm_autoholder characters: {len(new_characters)}")
	if preserve_existing_holders:
		print("Existing generated holder files preserved (log has no unheld counties)")
	print(f"Capital province blocks updated: {len(province_insertions)}")
	print(
		"Inserted culture fields: "
		f"{sum('culture' in fields for fields in province_insertions.values())}"
	)
	print(
		"Inserted religion fields: "
		f"{sum('religion' in fields for fields in province_insertions.values())}"
	)


if __name__ == "__main__":
	main()
