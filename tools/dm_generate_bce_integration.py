#!/usr/bin/env python3
"""Build the embedded BCE 1.8.3 integration for the current East Asia map.

The generator is deliberately self contained.  BCE source files are retained
beside their generated replacements with a ``.bce_source`` suffix, so they are
readable for maintenance but are not loaded by CK3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BCE_WORKSHOP = Path(r"D:\SteamLibrary\steamapps\workshop\content\1158310\3614544116")
COA_DIR = ROOT / "common/coat_of_arms/coat_of_arms"
LIST_DIR = ROOT / "common/coat_of_arms/template_lists"
NAME_DIR = ROOT / "common/culture/name_lists"
TRIGGER_DIR = ROOT / "common/scripted_triggers"
TITLE_SOURCE = COA_DIR / "bce_landed_titles.txt.bce_source"
TITLE_ACTIVE = COA_DIR / "bce_landed_titles.txt"
NAME_DM_SOURCE = NAME_DIR / "01_chinese.txt.bce_source"
NAME_BCE_SOURCE = NAME_DIR / "max_chinese.txt.bce_source"
NAME_ACTIVE = NAME_DIR / "zz_dm_bce_name_list_han.txt"
TRIGGER_BCE_SOURCE = TRIGGER_DIR / "bce_coa_triggers.txt.bce_source"
TRIGGER_ACTIVE = TRIGGER_DIR / "zz_dm_bce_coa_triggers.txt"
COA_ACTIVE = COA_DIR / "zz_dm_bce_integrated_titles.txt"
MANIFEST = ROOT / "tools/dm_bce_source_manifest.json"
ASSET_MANIFEST = ROOT / "tools/dm_bce_asset_manifest.json"
LOC_DIR = ROOT / "localization/simp_chinese"
DYNASTY_LOC_DIR = LOC_DIR / "dynasties"
DYNASTY_LOC_ACTIVE = DYNASTY_LOC_DIR / "max_chinese_dynasty_names_l_simp_chinese.yml"
DYNASTY_LOC_SOURCE = DYNASTY_LOC_DIR / "max_chinese_dynasty_names_l_simp_chinese.yml.bce_source"
REGION_FILE = ROOT / "map_data/geographical_regions/geographical_region.txt"
LAND_FILE = ROOT / "common/landed_titles/00_DM_landed_titles.txt"
COLORED_LIST = LIST_DIR / "max_colored_emblem_lists.txt"
COLORED_SOURCE = LIST_DIR / "max_colored_emblem_lists.txt.bce_source"

SOURCE_RENAMES = {
	TITLE_ACTIVE: TITLE_SOURCE,
	NAME_DIR / "01_chinese.txt": NAME_DM_SOURCE,
	NAME_DIR / "max_chinese.txt": NAME_BCE_SOURCE,
	TRIGGER_DIR / "bce_coa_triggers.txt": TRIGGER_BCE_SOURCE,
	COLORED_LIST: COLORED_SOURCE,
	ROOT / "common/coat_of_arms/coat_of_arms/01_random_templates.txt":
		ROOT / "common/coat_of_arms/coat_of_arms/01_random_templates.txt.bce_source",
	LIST_DIR / "colored_emblem_lists.txt":
		LIST_DIR / "colored_emblem_lists.txt.bce_source",
	DYNASTY_LOC_ACTIVE: DYNASTY_LOC_SOURCE,
}

REGIONS = {
	"world_huaxia_sili": ("yellow", "red", "black"),
	"world_huaxia_yuzhou": ("orange", "black", "white"),
	"world_huaxia_jingzhou": ("red_dark", "black", "yellow"),
	"world_huaxia_yangzhou": ("blue_light", "white", "red"),
	"world_huaxia_qingzhou": ("blue", "white", "yellow"),
	"world_huaxia_jizhou": ("blue", "black", "white"),
	"world_huaxia_youzhou": ("black", "white", "blue_light"),
	"world_huaxia_bingzhou": ("black", "red", "white"),
	"world_huaxia_yongzhou": ("orange", "red_dark", "white"),
	"world_huaxia_yizhou": ("green", "yellow", "black"),
	"world_huaxia_daidi": ("white", "blue", "black"),
	"world_huaxia_chaoxian": ("white", "blue", "red"),
	"world_huaxia_fusang": ("white", "red", "black"),
}

EXPECTED_BCE_VERSION = "1.8.3"
TITLE_KEY_RE = re.compile(r"^[ekdcb]_[A-Za-z0-9_-]+$")
LOC_RE = re.compile(r'^\s*([A-Za-z0-9_.-]+):\d*\s+"(.*)"\s*$')


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8-sig", errors="strict")


def sha256(path: Path) -> str:
	h = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			h.update(chunk)
	return h.hexdigest()


def mask_comments(text: str) -> str:
	out = list(text)
	quoted = False
	escaped = False
	i = 0
	while i < len(out):
		ch = out[i]
		if quoted:
			if escaped:
				escaped = False
			elif ch == "\\":
				escaped = True
			elif ch == '"':
				quoted = False
			i += 1
			continue
		if ch == '"':
			quoted = True
		elif ch == "#":
			while i < len(out) and out[i] not in "\r\n":
				out[i] = " "
				i += 1
			continue
		i += 1
	return "".join(out)


def matching_brace(text: str, opening: int) -> int:
	depth = 0
	quoted = False
	escaped = False
	comment = False
	for i in range(opening, len(text)):
		ch = text[i]
		if comment:
			if ch in "\r\n":
				comment = False
			continue
		if quoted:
			if escaped:
				escaped = False
			elif ch == "\\":
				escaped = True
			elif ch == '"':
				quoted = False
			continue
		if ch == "#":
			comment = True
		elif ch == '"':
			quoted = True
		elif ch == "{":
			depth += 1
		elif ch == "}":
			depth -= 1
			if depth == 0:
				return i
	raise ValueError(f"unclosed block at offset {opening}")


def top_blocks(text: str, key_filter: re.Pattern[str] | None = None) -> list[tuple[str, int, int, str]]:
	masked = mask_comments(text)
	result: list[tuple[str, int, int, str]] = []
	depth = 0
	quoted = False
	i = 0
	while i < len(masked):
		ch = masked[i]
		if ch == '"':
			quoted = not quoted
			i += 1
			continue
		if quoted:
			i += 1
			continue
		if ch == "{":
			depth += 1
		elif ch == "}":
			depth -= 1
		elif depth == 0 and (ch.isalpha() or ch == "_"):
			m = re.match(r"([A-Za-z0-9_.-]+)\s*=\s*\{", masked[i:])
			if m:
				key = m.group(1)
				opening = i + m.group(0).rfind("{")
				end = matching_brace(text, opening)
				if key_filter is None or key_filter.match(key):
					result.append((key, i, end + 1, text[i:end + 1]))
				i = end + 1
				continue
		i += 1
	return result


def direct_assignments(block: str, key: str) -> list[str]:
	masked = mask_comments(block)
	result: list[str] = []
	depth = 0
	quoted = False
	for line in masked.splitlines():
		for ch in line:
			if ch == '"':
				quoted = not quoted
			elif not quoted and ch == "{":
				depth += 1
			elif not quoted and ch == "}":
				depth -= 1
		if depth == 1:
			m = re.match(rf"\s*{re.escape(key)}\s*=\s*\"?([A-Za-z0-9_.-]+)\"?", line)
			if m:
				result.append(m.group(1))
	return result


@dataclass
class Title:
	key: str
	parent: str | None
	order: int
	capital: str | None = None
	children: list[str] = field(default_factory=list)


def parse_titles(text: str) -> tuple[dict[str, Title], list[str]]:
	masked = mask_comments(text)
	titles: dict[str, Title] = {}
	order: list[str] = []
	stack: list[tuple[str, int]] = []
	depth = 0
	quoted = False
	line_start = 0
	for i, ch in enumerate(masked + "\n"):
		if ch == "\n":
			line = masked[line_start:i]
			m = re.match(r"\s*([ekdcb]_[A-Za-z0-9_-]+)\s*=\s*\{", line)
			if m:
				key = m.group(1)
				while stack and stack[-1][1] >= depth + 1:
					stack.pop()
				parent = stack[-1][0] if stack else None
				titles[key] = Title(key=key, parent=parent, order=len(order))
				order.append(key)
				if parent and parent in titles:
					titles[parent].children.append(key)
				stack.append((key, depth + 1))
			if stack:
				m_cap = re.match(r"\s*capital\s*=\s*([cbd]_[A-Za-z0-9_-]+)", line)
				if m_cap and depth == stack[-1][1]:
					titles[stack[-1][0]].capital = m_cap.group(1)
			line_start = i + 1
		if ch == '"':
			quoted = not quoted
		elif not quoted and ch == "{":
			depth += 1
		elif not quoted and ch == "}":
			depth -= 1
	return titles, order


def descendants(titles: dict[str, Title], key: str, prefix: str | None = None) -> list[str]:
	out: list[str] = []
	queue = list(titles.get(key, Title(key, None, 0)).children)
	while queue:
		child = queue.pop(0)
		if prefix is None or child.startswith(prefix):
			out.append(child)
		queue.extend(titles[child].children)
	return out


def parse_region_kingdoms(text: str, region: str) -> list[str]:
	for key, _, _, block in top_blocks(text):
		if key == region:
			return re.findall(r"\bk_[A-Za-z0-9_-]+\b", mask_comments(block))
	raise ValueError(f"missing region {region}")


def load_localization(exclude: set[Path] | None = None) -> dict[str, str]:
	result: dict[str, str] = {}
	exclude = exclude or set()
	vanilla_loc = Path(r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game\localization\simp_chinese")
	for directory in (vanilla_loc, LOC_DIR):
		if not directory.exists():
			continue
		for path in directory.rglob("*.yml"):
			if path in exclude:
				continue
			for line in read(path).splitlines():
				m = LOC_RE.match(line)
				if m:
					result[m.group(1)] = m.group(2).replace('\\"', '"')
	return result


def source_paths() -> dict[str, Path]:
	return {
		"bce_landed_titles": TITLE_SOURCE,
		"dm_name_list_han": NAME_DM_SOURCE,
		"bce_name_list_han": NAME_BCE_SOURCE,
		"bce_coa_trigger": TRIGGER_BCE_SOURCE,
		"bce_colored_emblem_lists": COLORED_SOURCE,
		"bce_random_templates": ROOT / "common/coat_of_arms/coat_of_arms/max_random_templates.txt",
		"bce_template_lists": ROOT / "common/coat_of_arms/template_lists/max_coa_templates.txt",
		"bce_color_lists": ROOT / "common/coat_of_arms/template_lists/max_color_lists.txt",
		"bce_dynasty_localization": DYNASTY_LOC_SOURCE,
	}


def ensure_source_layout(check: bool) -> None:
	for active, source in SOURCE_RENAMES.items():
		if source.exists():
			continue
		if check:
			raise AssertionError(f"missing disabled BCE source: {source.relative_to(ROOT)}")
		if not active.exists():
			raise FileNotFoundError(active)
		active.rename(source)


def descriptor_version() -> str:
	path = BCE_WORKSHOP / "descriptor.mod"
	if not path.exists():
		return EXPECTED_BCE_VERSION
	m = re.search(r'version\s*=\s*"([^"]+)"', read(path))
	return m.group(1) if m else ""


def write_or_check(path: Path, content: str, check: bool) -> None:
	content = content.replace("\r\n", "\n")
	if check:
		if not path.exists() or read(path).replace("\r\n", "\n") != content:
			raise AssertionError(f"generated drift: {path.relative_to(ROOT)}")
		return
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(content, encoding="utf-8-sig", newline="\n")


def build_manifest(check: bool) -> dict[str, object]:
	paths = source_paths()
	for path in paths.values():
		if not path.exists():
			raise FileNotFoundError(path)
	version = descriptor_version()
	if version != EXPECTED_BCE_VERSION:
		raise AssertionError(f"BCE version is {version}, expected {EXPECTED_BCE_VERSION}")
	bce_asset_root = BCE_WORKSHOP / "gfx"
	if bce_asset_root.exists() and not check:
		asset_entries = {
			path.relative_to(BCE_WORKSHOP).as_posix(): sha256(path)
			for path in sorted(bce_asset_root.rglob("*")) if path.is_file()
		}
		write_or_check(
			ASSET_MANIFEST,
			json.dumps(asset_entries, ensure_ascii=False, indent=2) + "\n",
			check=False,
		)
	elif ASSET_MANIFEST.exists():
		asset_entries = json.loads(read(ASSET_MANIFEST))
	else:
		raise FileNotFoundError(
			"BCE workshop assets and embedded asset manifest are both unavailable"
		)
	if check:
		write_or_check(
			ASSET_MANIFEST,
			json.dumps(asset_entries, ensure_ascii=False, indent=2) + "\n",
			check=True,
		)
	aggregate = hashlib.sha256()
	for rel, expected_hash in asset_entries.items():
		path = ROOT / rel
		if not path.exists():
			raise AssertionError(f"embedded BCE asset is missing: {rel}")
		if sha256(path) != expected_hash:
			raise AssertionError(f"embedded BCE asset drift: {rel}")
		aggregate.update(rel.encode("utf-8"))
		aggregate.update(bytes.fromhex(sha256(path)))
	data: dict[str, object] = {
		"bce_version": version,
		"source_workshop_id": "3614544116",
		"asset_count": len(asset_entries),
		"asset_tree_sha256": aggregate.hexdigest(),
		"structural_sources": {
			name: {
				"path": path.relative_to(ROOT).as_posix(),
				"sha256": sha256(path),
			}
			for name, path in paths.items()
		},
	}
	content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
	write_or_check(MANIFEST, content, check)
	return data


def parse_name_section(block: str, section: str) -> list[str]:
	m = re.search(rf"(?m)^\s*{re.escape(section)}\s*=\s*\{{", block)
	if not m:
		return []
	opening = m.end() - 1
	body = block[opening + 1:matching_brace(block, opening)]
	# ##...## is annotation used by the DM source, not part of the name key.
	body = re.sub(r"##.*?##", " ", body)
	body = mask_comments(body)
	return re.findall(r'"([^"]+)"|([A-Za-z0-9_.-]+)', body)


def flat_tokens(pairs: list[tuple[str, str]]) -> list[str]:
	return [a or b for a, b in pairs]


def build_name_list(check: bool) -> dict[str, int]:
	dm = top_blocks(read(NAME_DM_SOURCE))[0][3]
	bce = top_blocks(read(NAME_BCE_SOURCE))[0][3]
	sections = ("cadet_dynasty_names", "dynasty_names", "male_names", "female_names")
	counts: dict[str, int] = {}
	lines = [
		"# Generated by tools/dm_generate_bce_integration.py.",
		"# DM ancient names are authoritative; BCE-only entries follow in source order.",
		"name_list_han = {",
	]
	for section in sections:
		seen: set[str] = set()
		values: list[str] = []
		for source in (dm, bce):
			for value in flat_tokens(parse_name_section(source, section)):
				if value not in seen:
					seen.add(value)
					values.append(value)
		counts[section] = len(values)
		lines.append(f"\t{section} = {{")
		for value in values:
			if section in ("cadet_dynasty_names", "dynasty_names"):
				lines.append(f'\t\t"{value}"')
			else:
				lines.append(f"\t\t{value}")
		lines.append("\t}")
		lines.append("")
	# Keep the current DM behavior for all non-list settings.
	for key in (
		"dynasty_name_first",
		"suggest_family_names",
		"suggest_ancestor_names",
		"pat_grf_name_chance",
		"mat_grf_name_chance",
		"father_name_chance",
		"pat_grm_name_chance",
		"mat_grm_name_chance",
		"mother_name_chance",
	):
		m = re.search(rf"(?m)^\s*{key}\s*=\s*([A-Za-z0-9_.-]+)", dm)
		if not m:
			m = re.search(rf"(?m)^\s*{key}\s*=\s*([A-Za-z0-9_.-]+)", bce)
		if m:
			lines.append(f"\t{key} = {m.group(1)}")
	lines.append("}")
	lines.append("")
	write_or_check(NAME_ACTIVE, "\n".join(lines), check)
	return counts


def chinese_simplified(text: str) -> str:
	if not text:
		return text
	try:
		import ctypes
		from ctypes import wintypes
		LCMAP_SIMPLIFIED_CHINESE = 0x02000000
		kernel32 = ctypes.windll.kernel32
		kernel32.LCMapStringEx.argtypes = (
			wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR, ctypes.c_int,
			wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
			wintypes.LPARAM,
		)
		kernel32.LCMapStringEx.restype = ctypes.c_int
		size = kernel32.LCMapStringEx(
			"zh-CN", LCMAP_SIMPLIFIED_CHINESE, text, len(text),
			None, 0, None, None, 0,
		)
		buffer = ctypes.create_unicode_buffer(size)
		kernel32.LCMapStringEx(
			"zh-CN", LCMAP_SIMPLIFIED_CHINESE, text, len(text),
			buffer, size, None, None, 0,
		)
		return buffer.value
	except Exception:
		return text


def dynasty_names(loc: dict[str, str]) -> list[str]:
	keys: list[str] = []
	for path in (ROOT / "common/dynasties").rglob("*.txt"):
		keys.extend(re.findall(r'\bname\s*=\s*"(dynn_[A-Za-z0-9_.-]+)"', read(path)))
	for path in (ROOT / "common/dynasty_houses").rglob("*.txt"):
		keys.extend(re.findall(r'\bname\s*=\s*"(dynn_[A-Za-z0-9_.-]+)"', read(path)))
	return list(dict.fromkeys(k for k in keys if k in loc))


def localized_or_encoded_name(key: str, loc: dict[str, str]) -> str:
	if key in loc:
		return loc[key]
	chars: list[str] = []
	for token in key.split("_"):
		if re.fullmatch(r"[0-9A-Fa-f]{4,6}", token):
			value = int(token, 16)
			if 0x3400 <= value <= 0x2FA1F:
				chars.append(chr(value))
	return "".join(chars)


def recognizable_names(trigger: str) -> list[str]:
	return list(dict.fromkeys(
		re.findall(r'has_base_name\s*=\s*"?((?:dynn_)[A-Za-z0-9_.-]+)"?', trigger)
	))


def build_trigger(loc: dict[str, str], check: bool) -> tuple[dict[str, str], list[str]]:
	source = read(TRIGGER_BCE_SOURCE)
	recognized = recognizable_names(source)
	_, _, seal_body = nested_named_block(read(COLORED_SOURCE), "chinese_seal_name")
	texture_keys = selection_texture_map(seal_body)
	by_name: dict[str, list[str]] = defaultdict(list)
	for key in recognized:
		if key not in texture_keys:
			continue
		name = localized_or_encoded_name(key, loc)
		if name:
			by_name[chinese_simplified(name)].append(key)
	aliases: dict[str, str] = {}
	unmatched: list[str] = []
	for key in dynasty_names(loc):
		name = chinese_simplified(loc[key])
		if name in by_name:
			aliases[key] = by_name[name][0]
		else:
			unmatched.append(key)
	house_match = re.search(r"house\s*\?=\s*\{", source)
	if not house_match:
		raise AssertionError("BCE recognizable trigger has no house scope")
	house_open = house_match.end() - 1
	or_match = re.search(r"\bOR\s*=\s*\{", source[house_open:])
	if not or_match:
		raise AssertionError("BCE recognizable trigger has no surname OR block")
	or_open = house_open + or_match.end() - 1
	or_close = matching_brace(source, or_open)
	additions = [
		"",
		"\t\t\t# Current-map aliases generated by exact simplified surname.",
	]
	for alias in sorted(aliases):
		additions.append(f'\t\t\thas_base_name = "{alias}"')
	merged = source[:or_close] + "\n".join(additions) + "\n\t\t" + source[or_close:]
	write_or_check(TRIGGER_ACTIVE, merged, check)
	return aliases, unmatched


def nested_named_block(text: str, key: str) -> tuple[int, int, str]:
	m = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\{{", text)
	if not m:
		raise AssertionError(f"missing nested block {key}")
	opening = m.end() - 1
	closing = matching_brace(text, opening)
	return opening, closing, text[opening + 1:closing]


def selection_texture_map(list_body: str) -> dict[str, str]:
	"""Choose one BCE texture for each recognized base name.

	General Hundred-Family patterns win, followed by official patterns and
	period-specific patterns.  Source order breaks equal-priority ties.
	"""
	result: dict[str, tuple[int, int, str]] = {}
	for order, (_, _, _, block) in enumerate(top_blocks("wrapper = {" + list_body + "\n}")):
		# top_blocks sees only wrapper; selections are found below with balanced scanning.
		del order, block
	pos = 0
	order = 0
	while True:
		m = re.search(r"(?m)^\s*special_selection\s*=\s*\{", list_body[pos:])
		if not m:
			break
		opening = pos + m.end() - 1
		closing = matching_brace(list_body, opening)
		block = list_body[opening + 1:closing]
		textures = re.findall(r'=\s*"([^"]+\.dds)"', mask_comments(block))
		if textures:
			texture = textures[-1]
			lower = texture.lower()
			if "max_coa_" in lower or "ce_seal_name_" in lower:
				rank = 0
			elif "official" in lower:
				rank = 1
			elif any(word in lower for word in ("song", "yuan", "ming")):
				rank = 2
			else:
				rank = 3
			for key in re.findall(r'has_base_name\s*=\s*"?([A-Za-z0-9_.-]+)"?', block):
				old = result.get(key)
				candidate = (rank, order, texture)
				if old is None or candidate[:2] < old[:2]:
					result[key] = candidate
		order += 1
		pos = closing + 1
	return {key: value[2] for key, value in result.items()}


def build_colored_lists(aliases: dict[str, str], check: bool) -> None:
	source = read(COLORED_SOURCE)
	opening, closing, body = nested_named_block(source, "chinese_seal_name")
	texture_map = selection_texture_map(body)
	additions = [
		"",
		"\t\t# Exact current-map surname aliases generated by the BCE integration.",
	]
	missing: list[str] = []
	for alias, canonical in sorted(aliases.items()):
		texture = texture_map.get(canonical)
		if not texture:
			missing.append(canonical)
			continue
		additions.extend([
			"\t\tspecial_selection = {",
			"\t\t\ttrigger = {",
			f'\t\t\t\thouse ?= {{ has_base_name = "{alias}" }}',
			"\t\t\t}",
			f'\t\t\t100 = "{texture}"',
			"\t\t}",
		])
	if missing:
		raise AssertionError(
			f"{len(set(missing))} recognized surnames have no BCE texture selection"
		)
	generated = source[:closing] + "\n".join(additions) + "\n\t" + source[closing:]
	generated = "\n".join(line.rstrip() for line in generated.splitlines()) + "\n"
	write_or_check(COLORED_LIST, generated, check)


def coa_blocks(path: Path) -> dict[str, str]:
	return {key: block for key, _, _, block in top_blocks(read(path), TITLE_KEY_RE)}


def all_texture_names() -> set[str]:
	return {path.name for path in (ROOT / "gfx").rglob("*.dds")}


def emblem_textures() -> tuple[list[str], list[str]]:
	text = read(COLORED_LIST)
	background: list[str] = []
	totem: list[str] = []
	for list_name, target in (("bce_coa_background", background), ("bce_coa_totem", totem)):
		m = re.search(rf"(?m)^\s*{list_name}\s*=\s*\{{", text)
		if not m:
			raise AssertionError(f"missing texture list {list_name}")
		opening = m.end() - 1
		body = text[opening + 1:matching_brace(text, opening)]
		target.extend(re.findall(r'=\s*"([^"]+\.dds)"', mask_comments(body)))
	existing = all_texture_names()
	background = list(dict.fromkeys(x for x in background if Path(x).name in existing))
	totem = list(dict.fromkeys(x for x in totem if Path(x).name in existing))
	if not background or not totem:
		raise AssertionError("BCE background/totem texture list resolved empty")
	return background, totem


def protected_coas() -> dict[str, str]:
	result: dict[str, str] = {}
	for path in COA_DIR.glob("*.txt"):
		if path in (COA_ACTIVE, TITLE_ACTIVE):
			continue
		if path.name.startswith("zz_dm_compat_"):
			continue
		result.update(coa_blocks(path))
	return result


def title_region_map(titles: dict[str, Title], region_text: str) -> dict[str, str]:
	result: dict[str, str] = {}
	for region in REGIONS:
		for kingdom in parse_region_kingdoms(region_text, region):
			if kingdom not in titles:
				continue
			result[kingdom] = region
			for key in descendants(titles, kingdom):
				if key[0] in "edkc":
					result[key] = region
	# Empires and duchies can sit above/below region roots: derive from capital,
	# then from their first de-jure county.
	def county_for(key: str) -> str | None:
		title = titles[key]
		if title.capital and title.capital.startswith("c_"):
			return title.capital
		if title.capital and title.capital.startswith("b_") and title.capital in titles:
			parent = titles[title.capital].parent
			if parent and parent.startswith("c_"):
				return parent
		counties = descendants(titles, key, "c_")
		return counties[0] if counties else None
	changed = True
	while changed:
		changed = False
		for key in titles:
			if key in result or key[0] not in "edk":
				continue
			county = county_for(key)
			if county in result:
				result[key] = result[county]
				changed = True
	return result


def localized_bce_map(
	bce: dict[str, str], targets: list[str], loc: dict[str, str], titles: dict[str, Title],
) -> dict[str, str]:
	result: dict[str, str] = {}
	by_name: dict[tuple[str, str], list[str]] = defaultdict(list)
	for key in bce:
		if key in loc:
			by_name[(key[0], chinese_simplified(loc[key]))].append(key)
	vanilla_titles: dict[str, Title] = {}
	vanilla_dir = Path(r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game\common\landed_titles")
	if vanilla_dir.exists():
		for path in sorted(vanilla_dir.glob("*.txt")):
			parsed, _ = parse_titles(read(path))
			for title_key, title in parsed.items():
				vanilla_titles.setdefault(title_key, title)

	def loc_name(title_key: str | None) -> str:
		return chinese_simplified(loc.get(title_key or "", ""))

	def relation_signature(title_map: dict[str, Title], title_key: str) -> tuple[str, str]:
		title = title_map.get(title_key)
		if not title:
			return ("", "")
		parent_name = loc_name(title.parent)
		capital = title.capital
		if capital and capital.startswith("b_") and capital in title_map:
			capital = title_map[capital].parent
		return (parent_name, loc_name(capital))

	for key in targets:
		if key in bce:
			result[key] = key
			continue
		if key not in loc:
			continue
		candidates = by_name[(key[0], chinese_simplified(loc[key]))]
		if len(candidates) == 1:
			result[key] = candidates[0]
		elif candidates:
			target_relation = relation_signature(titles, key)
			proven = [
				candidate for candidate in candidates
				if relation_signature(vanilla_titles, candidate) == target_relation
				and target_relation != ("", "")
			]
			if len(proven) == 1:
				result[key] = proven[0]
	return result


def generated_coa(
	key: str, tier: str, colors: tuple[str, str, str],
	backgrounds: list[str], totems: list[str], salt: int,
) -> tuple[str, tuple[object, ...]]:
	digest = hashlib.sha256(f"{key}:{salt}".encode("ascii")).digest()
	bg = backgrounds[int.from_bytes(digest[:2], "big") % len(backgrounds)]
	bg2 = backgrounds[int.from_bytes(digest[5:7], "big") % len(backgrounds)]
	if bg2 == bg:
		bg2 = backgrounds[(backgrounds.index(bg) + 1) % len(backgrounds)]
	totem = totems[int.from_bytes(digest[2:4], "big") % len(totems)]
	rotation = (digest[4] % 4) * 90
	scale = {"c": 0.72, "d": 0.68, "k": 0.63, "e": 0.58}[tier]
	instances = 1 if tier == "c" else 2 if tier in "dk" else 4
	signature = (colors, bg, bg2 if tier in "ke" else "", totem, rotation, instances)
	lines = [
		f"{key} = {{",
		'\tpattern = "pattern_solid.dds"',
		f'\tcolor1 = "{colors[0]}"',
		f'\tcolor2 = "{colors[1]}"',
		f'\tcolor3 = "{colors[2]}"',
		"\tcolored_emblem = {",
		"\t\tcolor1 = white",
		"\t\tcolor2 = yellow",
		f'\t\ttexture = "{bg}"',
		"\t\tinstance = {",
		"\t\t\tposition = { 0.5 0.5 }",
		"\t\t\tscale = { 1.0 1.0 }",
		"\t\t}",
		"\t}",
	]
	if tier in "ke":
		lines.extend([
			"\tcolored_emblem = {",
			f"\t\tcolor1 = {colors[2]}",
			f"\t\tcolor2 = {colors[0]}",
			f'\t\ttexture = "{bg2}"',
			"\t\tinstance = {",
			"\t\t\tposition = { 0.5 0.5 }",
			"\t\t\tscale = { 0.82 0.82 }",
			"\t\t}",
			"\t}",
		])
	lines.extend([
		"\tcolored_emblem = {",
		f"\t\tcolor1 = {colors[1]}",
		f"\t\tcolor2 = {colors[2]}",
		f'\t\ttexture = "{totem}"',
	])
	positions = {
		1: ((0.5, 0.5),),
		2: ((0.38, 0.5), (0.62, 0.5)),
		4: ((0.36, 0.36), (0.64, 0.36), (0.36, 0.64), (0.64, 0.64)),
	}[instances]
	for x, y in positions:
		lines.extend([
			"\t\tinstance = {",
			f"\t\t\tposition = {{ {x:.2f} {y:.2f} }}",
			f"\t\t\tscale = {{ {scale:.2f} {scale:.2f} }}",
			f"\t\t\trotation = {rotation}",
			"\t\t}",
		])
	lines.extend(["\t}", "}"])
	return "\n".join(lines), signature


def build_title_coas(loc: dict[str, str], check: bool) -> dict[str, object]:
	titles, order = parse_titles(read(LAND_FILE))
	region_map = title_region_map(titles, read(REGION_FILE))
	targets = [key for key in order if key in region_map and key[0] in "edkc"]
	bce = coa_blocks(TITLE_SOURCE)
	protected = protected_coas()
	mapped = localized_bce_map(bce, targets, loc, titles)
	backgrounds, totems = emblem_textures()
	lines = [
		"# Generated by tools/dm_generate_bce_integration.py.",
		"# Priority: existing DM handcrafted > proven BCE source > deterministic BCE style.",
		"",
	]
	stats = defaultdict(int)
	used: dict[tuple[str, str], set[tuple[object, ...]]] = defaultdict(set)
	for key in targets:
		if key in protected:
			stats["handcrafted"] += 1
			continue
		if key in mapped:
			block = bce[mapped[key]]
			if mapped[key] != key:
				block = re.sub(r"^[ekdcb]_[A-Za-z0-9_-]+", key, block, count=1)
			lines.extend([block, ""])
			stats["bce_mapped"] += 1
			continue
		tier = key[0]
		region = region_map[key]
		for salt in range(10000):
			block, signature = generated_coa(
				key, tier, REGIONS[region], backgrounds, totems, salt,
			)
			bucket = used[(region, tier)]
			if signature not in bucket:
				bucket.add(signature)
				break
		else:
			raise AssertionError(f"could not resolve CoA collision for {key}")
		lines.extend([block, ""])
		stats["generated"] += 1
	write_or_check(COA_ACTIVE, "\n".join(lines), check)
	stats["target_count"] = len(targets)
	stats["region_count"] = len(set(region_map[k] for k in targets))
	return dict(stats)


def update_bce_localization(check: bool) -> None:
	path = LOC_DIR / "bce_game_rules_l_simp_chinese.yml"
	content = """l_simp_chinese:
 game_rule_category_bce_mod_series:0 "@bce_icon_rule! Better Chinese Emblems（BCE）"
 rule_bce_noble_family_title:0 "@bce_icon_rule! #Clickable #Bold BCE中式纹章#!#!：贵族头衔"
 setting_default_noble_family_title:0 "启用贵族头衔（默认）"
 setting_default_noble_family_title_desc:0 "非贵族头衔默认不使用姓氏印章。更改此设置后需要重新开局。"
 setting_never_noble_family_title:0 "不限制贵族头衔"
 setting_never_noble_family_title_desc:0 "无论是否拥有贵族头衔，合格家族均可使用BCE姓氏印章。更改此设置后需要重新开局。"
 rule_bce_create_cadet_branch:0 "@bce_icon_rule! #Clickable #Bold BCE中式纹章#!#!：分家支系"
 setting_default_create_cadet_branch:0 "原版分家纹章（默认）"
 setting_default_create_cadet_branch_desc:0 "沿用当前CK3分家逻辑，新支系生成有区别的BCE风格纹章。"
 setting_always_bce_cadet_branch:0 "保留姓氏印章"
 setting_always_bce_cadet_branch_desc:0 "创建分家时保留可识别的BCE姓氏印章，并由当前版本分家效果添加差异。"
"""
	write_or_check(path, content, check)
	designer = LOC_DIR / "max_coa_designer_l_simp_chinese.yml"
	content = """l_simp_chinese:
 COA_DESIGNER_CATEGORY_MAX_COA:0 "BCE中式纹章"
 COA_DESIGNER_CATEGORY_MAX_COA_BG:0 "BCE中式纹章背景"
 COA_DESIGNER_CATEGORY_MAX_COA_HUNDRED:0 "BCE中式纹章—百家姓"
 COA_DESIGNER_CATEGORY_MAX_COA_SONGYUANMING:0 "BCE中式纹章—宋元明常用姓氏"
 COA_DESIGNER_CATEGORY_MAX_COA_RARE:0 "BCE中式纹章—稀有姓氏"
"""
	write_or_check(designer, content, check)


def build_dynasty_localization(check: bool) -> None:
	source = read(DYNASTY_LOC_SOURCE)
	lines: list[str] = []
	source_keys: set[str] = set()
	for line in source.splitlines():
		m = LOC_RE.match(line)
		if not m:
			lines.append(line.rstrip())
			continue
		key, value = m.groups()
		source_keys.add(key)
		value = chinese_simplified(value)
		value = value.replace("\\", "\\\\").replace('"', '\\"')
		lines.append(f' {key}:0 "{value}"')
	loc = load_localization(exclude={DYNASTY_LOC_ACTIVE})
	for line in lines:
		m = LOC_RE.match(line)
		if m:
			loc[m.group(1)] = m.group(2)
	missing_lines: list[str] = []
	for key in recognizable_names(read(TRIGGER_BCE_SOURCE)):
		if key in loc or key in source_keys:
			continue
		value = localized_or_encoded_name(key, loc)
		if value:
			missing_lines.append(f' {key}:0 "{chinese_simplified(value)}"')
	if missing_lines:
		lines.extend([
			"",
			" # Missing BCE surname localizations recovered from encoded Unicode keys.",
			*missing_lines,
		])
	write_or_check(DYNASTY_LOC_ACTIVE, "\n".join(lines) + "\n", check)


def patch_cadet_effect(check: bool) -> None:
	path = ROOT / "common/scripted_effects/00_decisions_effects.txt"
	text = read(path)
	marker = "# DM_BCE_CADET_RULE_BEGIN"
	if marker in text:
		return
	old = """\t\t\t\t\t\t\t# China
\t\t\t\t\t\t\thas_cultural_pillar = heritage_chinese
\t\t\t\t\t\t\thas_name_list = name_list_han"""
	new = """\t\t\t\t\t\t\t# DM_BCE_CADET_RULE_BEGIN
\t\t\t\t\t\t\t# The BCE alternative preserves a recognizable surname seal;
\t\t\t\t\t\t\t# all other branches keep the current 1.19 cadet effect.
\t\t\t\t\t\t\ttrigger_if = {
\t\t\t\t\t\t\t\tlimit = {
\t\t\t\t\t\t\t\t\tNOT = { has_game_rule = always_bce_cadet_branch }
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t\tOR = {
\t\t\t\t\t\t\t\t\thas_cultural_pillar = heritage_chinese
\t\t\t\t\t\t\t\t\thas_name_list = name_list_han
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t# DM_BCE_CADET_RULE_END"""
	if old not in text:
		raise AssertionError("current cadet-house Chinese branch no longer matches expected 1.19 layout")
	if check:
		raise AssertionError("cadet effect is not wired to always_bce_cadet_branch")
	path.write_text(text.replace(old, new, 1), encoding="utf-8-sig", newline="\n")


def remove_legacy_trigger(check: bool) -> None:
	path = TRIGGER_DIR / "00_coa_triggers.txt"
	text = read(path)
	blocks = [b for b in top_blocks(text) if b[0] == "has_recognizable_chinese_seal"]
	if not blocks:
		return
	if check:
		raise AssertionError("legacy has_recognizable_chinese_seal remains in 00_coa_triggers.txt")
	_, start, end, _ = blocks[0]
	trimmed = text[:start].rstrip() + "\n"
	if text[end:].strip():
		trimmed += text[end:].lstrip()
	path.write_text(trimmed, encoding="utf-8-sig", newline="\n")


def run(check: bool) -> dict[str, object]:
	ensure_source_layout(check)
	remove_legacy_trigger(check)
	patch_cadet_effect(check)
	build_dynasty_localization(check)
	loc = load_localization()
	manifest = build_manifest(check)
	name_counts = build_name_list(check)
	aliases, unmatched = build_trigger(loc, check)
	build_colored_lists(aliases, check)
	title_stats = build_title_coas(loc, check)
	update_bce_localization(check)
	result = {
		"manifest": manifest,
		"name_counts": name_counts,
		"mapped_dynasty_names": len(aliases),
		"unmatched_dynasty_names": len(unmatched),
		"title_stats": title_stats,
	}
	return result


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--check", action="store_true")
	args = parser.parse_args()
	try:
		result = run(args.check)
	except Exception as exc:
		print(f"ERROR: {exc}", file=sys.stderr)
		return 1
	print(json.dumps(result, ensure_ascii=False, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
