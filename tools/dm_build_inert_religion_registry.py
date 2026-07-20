"""Build the inert external-religion key registry for the 3850 conversion.

The total conversion replaces ``common/religion/religion_types``.  Vanilla
scripts still resolve their built-in religion and faith keys at load time, even
though those religions have no characters, counties, holy sites, or gameplay
entry points on the 3850 map.  The old solution used 49 ``dm_compat_*`` files.
This generator consolidates those exact registered keys into one auditable
file and assigns one technical holy site because CK3 1.19 requires every faith
to declare at least one.

The registry is inert by construction: no history or map file may use one of
its faiths.  Its sole purpose is static key resolution for unreachable vanilla
branches.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
	ROOT
	/ "common"
	/ "religion"
	/ "religion_types"
	/ "zz_dm_inert_external_religion_registry.txt"
)
SOURCE_GLOB = "common/religion/religion_types/dm_compat_"
VANILLA_RELIGION_ROOT = Path(
	r"D:\SteamLibrary\steamapps\common\Crusader Kings III\game"
) / "common" / "religion" / "religion_types"
BLOCK_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)\s*=\s*\{")
FAITHS_RE = re.compile(r"^\s*faiths\s*=\s*\{")
HOLY_SITE_RE = re.compile(r"(?m)^\s*holy_site\s*=")


def strip_comment(line: str) -> str:
	quoted = False
	escaped = False
	for index, char in enumerate(line):
		if quoted:
			if escaped:
				escaped = False
			elif char == "\\":
				escaped = True
			elif char == '"':
				quoted = False
		elif char == '"':
			quoted = True
		elif char == "#":
			return line[:index]
	return line


def brace_delta(line: str) -> int:
	clean = strip_comment(line)
	clean = re.sub(r'"(?:\\.|[^"])*"', '""', clean)
	return clean.count("{") - clean.count("}")


def source_paths() -> list[str]:
	result = subprocess.check_output(
		["git", "ls-tree", "-r", "--name-only", "HEAD"],
		cwd=ROOT,
		text=True,
		encoding="utf-8",
	).splitlines()
	paths = sorted(
		path
		for path in result
		if path.startswith(SOURCE_GLOB) and path.endswith(".txt")
	)
	if len(paths) != 49:
		raise RuntimeError(f"Expected 49 legacy registry sources, found {len(paths)}")
	return paths


def vanilla_source(path: str) -> Path:
	filename = Path(path).name.removeprefix("dm_compat_")
	result = VANILLA_RELIGION_ROOT / filename
	if not result.is_file():
		raise RuntimeError(f"Missing CK3 1.19 religion source: {result}")
	return result


def inject_required_holy_sites(text: str, source: str) -> tuple[str, int]:
	lines = text.splitlines()
	depth = 0
	faiths_depth: int | None = None
	inserts: dict[int, str] = {}
	removals: set[int] = set()
	faith_count = 0
	index = 0
	while index < len(lines):
		clean = strip_comment(lines[index])
		before = depth
		delta = brace_delta(lines[index])
		if FAITHS_RE.match(clean):
			faiths_depth = before + delta
		elif faiths_depth is not None and before == faiths_depth:
			match = BLOCK_RE.match(clean)
			if match:
				block_depth = delta
				end = index
				while block_depth > 0:
					end += 1
					if end >= len(lines):
						raise RuntimeError(
							f"Unclosed faith {match.group(2)} in {source}"
						)
					block_depth += brace_delta(lines[end])
				for block_line in range(index + 1, end):
					if HOLY_SITE_RE.match(strip_comment(lines[block_line])):
						removals.add(block_line)
				inserts[index] = (
					f"{match.group(1)}\tholy_site = dm_compat_registry"
				)
				faith_count += 1
			elif clean.strip().startswith("}"):
				faiths_depth = None
		depth += delta
		index += 1

	output: list[str] = []
	for line_index, line in enumerate(lines):
		if line_index in removals:
			continue
		output.append(line)
		if line_index in inserts:
			output.append(inserts[line_index])
	return "\n".join(output) + "\n", faith_count


def remove_known_vanilla_doctrine_conflict(
	text: str, source: str
) -> tuple[str, int]:
	if Path(source).name != "00_buddhism.txt":
		return text, 0

	lines = text.splitlines()
	start = next(
		(
			index
			for index, line in enumerate(lines)
			if re.match(r"^\s*avatamsaka\s*=\s*\{", strip_comment(line))
		),
		None,
	)
	if start is None:
		raise RuntimeError(f"Missing avatamsaka faith in {source}")

	depth = brace_delta(lines[start])
	end = start
	while depth > 0:
		end += 1
		if end >= len(lines):
			raise RuntimeError(f"Unclosed avatamsaka faith in {source}")
		depth += brace_delta(lines[end])

	block = lines[start : end + 1]
	all_doctrine = [
		index
		for index, line in enumerate(block)
		if strip_comment(line).strip()
		== "doctrine = doctrine_bastardry_all"
	]
	legitimization = [
		index
		for index, line in enumerate(block)
		if strip_comment(line).strip()
		== "doctrine = doctrine_bastardry_legitimization"
	]
	if len(all_doctrine) != 1 or len(legitimization) != 1:
		raise RuntimeError(
			"Expected exactly one avatamsaka bastardry conflict in "
			f"{source}; found all={len(all_doctrine)} "
			f"legitimization={len(legitimization)}"
		)

	del lines[start + legitimization[0]]
	return "\n".join(lines) + "\n", 1


def render() -> bytes:
	parts = [
		"# Generated inert key registry for vanilla religions outside the",
		"# 3850 total-conversion map. Do not add these faiths to history.",
		"",
	]
	total_faiths = 0
	total_doctrine_conflicts = 0
	for path in source_paths():
		source_path = vanilla_source(path)
		source_bytes = source_path.read_bytes()
		source_text = source_bytes.decode("utf-8-sig")
		injected, faith_count = inject_required_holy_sites(
			source_text, str(source_path)
		)
		injected, conflict_count = remove_known_vanilla_doctrine_conflict(
			injected, str(source_path)
		)
		total_faiths += faith_count
		total_doctrine_conflicts += conflict_count
		parts.extend(
			[
				f"# CK3 1.19 source: {source_path.name}",
				f"# SHA-256: {hashlib.sha256(source_bytes).hexdigest()}",
				injected.rstrip(),
				"",
			]
		)
	if total_faiths != 140:
		raise RuntimeError(f"Expected 140 registered faiths, found {total_faiths}")
	if total_doctrine_conflicts != 1:
		raise RuntimeError(
			"Expected exactly one known vanilla doctrine conflict, found "
			f"{total_doctrine_conflicts}"
		)
	return codecs.BOM_UTF8 + ("\n".join(parts) + "\n").encode("utf-8")


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--check", action="store_true")
	args = parser.parse_args()
	expected = render()
	if args.check:
		if not OUTPUT.is_file() or OUTPUT.read_bytes() != expected:
			raise SystemExit("inert religion registry drifted; regenerate it")
		print("inert religion registry check OK: 49 sources, 140 faiths")
		return
	OUTPUT.write_bytes(expected)
	print("generated inert religion registry: 49 sources, 140 faiths")


if __name__ == "__main__":
	main()
