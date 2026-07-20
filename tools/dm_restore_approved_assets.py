#!/usr/bin/env python3
"""Restore only the approved cross-task assets.

This intentionally does not inspect or restore the rest of the dirty worktree.
Git files are read one blob at a time; the deputy-general integration is copied
from its workshop source without descriptor/thumbnail metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EMBATTLE_SOURCE = Path(
	r"D:\SteamLibrary\steamapps\workshop\content\1158310\3454148607"
)

OBEDIENCE_FILES = (
	"common/casus_belli_types/zz_dm_obedience_mpo_wars.txt",
	"common/character_interactions/09_mpo_interactions.txt",
	"common/character_interactions/zz_dm_obedience_tributary_interactions.txt",
	"common/governments/00_government_types.txt",
	"common/governments/01_japan_government_types.txt",
	"common/governments/02_government_types_COPF.txt",
	"common/script_values/dm_obedience_values.txt",
	"common/scripted_triggers/zz_dm_obedience_semantic_triggers.txt",
	"localization/simp_chinese/replace/dm_obedience_l_simp_chinese.yml",
	"tools/dm_audit_obedience.py",
)

EMBATTLE_EXCLUDED = {"descriptor.mod", "thumbnail.png"}
MANIFEST_PATH = ROOT / "generated/dm_recovery_manifest.json"


def sha256(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


def git_blob(ref: str, relative: str) -> bytes:
	return subprocess.check_output(
		["git", "show", f"{ref}:{relative}"],
		cwd=ROOT,
	)


def embattle_files() -> list[str]:
	if not EMBATTLE_SOURCE.is_dir():
		raise SystemExit(f"副将模组来源不存在：{EMBATTLE_SOURCE}")
	return sorted(
		path.relative_to(EMBATTLE_SOURCE).as_posix()
		for path in EMBATTLE_SOURCE.rglob("*")
		if path.is_file() and path.name not in EMBATTLE_EXCLUDED
	)


def write_exact(relative: str, data: bytes) -> None:
	target = ROOT / relative
	target.parent.mkdir(parents=True, exist_ok=True)
	target.write_bytes(data)


def build_manifest(restored: bool) -> dict:
	entries: list[dict[str, str]] = []
	for relative in OBEDIENCE_FILES:
		source = git_blob("bokitewi", relative)
		target = ROOT / relative
		entries.append(
			{
				"path": relative,
				"source": f"git:bokitewi:{relative}",
				"source_sha256": sha256(source),
				"target_sha256": sha256(target.read_bytes()) if target.is_file() else "MISSING",
				"state": "restore_then_maintain",
			}
		)
	for relative in embattle_files():
		source_path = EMBATTLE_SOURCE / relative
		target = ROOT / relative
		entries.append(
			{
				"path": relative,
				"source": str(source_path),
				"source_sha256": sha256(source_path.read_bytes()),
				"target_sha256": sha256(target.read_bytes()) if target.is_file() else "MISSING",
				"state": "restore_then_integrate",
			}
		)
	return {
		"schema": 1,
		"restored": restored,
		"obedience_count": len(OBEDIENCE_FILES),
		"embattle_count": len(embattle_files()),
		"excluded": [
			"descriptor.mod",
			"thumbnail.png",
			"all unrelated dirty-worktree deletions",
		],
		"entries": entries,
	}


def restore() -> None:
	for relative in OBEDIENCE_FILES:
		write_exact(relative, git_blob("bokitewi", relative))
	for relative in embattle_files():
		write_exact(relative, (EMBATTLE_SOURCE / relative).read_bytes())
	MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
	MANIFEST_PATH.write_text(
		json.dumps(build_manifest(True), ensure_ascii=False, indent=2) + "\n",
		encoding="utf-8",
	)


def check() -> None:
	missing: list[str] = []
	for relative in (*OBEDIENCE_FILES, *embattle_files()):
		if not (ROOT / relative).is_file():
			missing.append(relative)
	if missing:
		raise SystemExit("恢复清单仍有缺失：\n" + "\n".join(missing))
	if not MANIFEST_PATH.is_file():
		raise SystemExit(f"恢复清单不存在：{MANIFEST_PATH}")
	print(
		f"恢复清单通过：忠顺 {len(OBEDIENCE_FILES)} 项，"
		f"副将 {len(embattle_files())} 项。"
	)


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--restore", action="store_true")
	parser.add_argument("--check", action="store_true")
	args = parser.parse_args()
	if args.restore == args.check:
		parser.error("必须且只能指定 --restore 或 --check")
	if args.restore:
		restore()
		check()
	else:
		check()


if __name__ == "__main__":
	main()
