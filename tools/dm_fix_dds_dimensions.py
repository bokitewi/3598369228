"""Losslessly expose the existing block padding of compressed DDS textures.

DXT/BC textures are stored in 4x4 blocks.  The imported CoA files include the
padding blocks already, but many headers advertise dimensions such as 250x250.
CK3 1.19 requires both advertised dimensions to be divisible by four.  Rounding
the header up to the block boundary changes no compressed image data and keeps
every mip level at the same byte offset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXTURE_ROOT = ROOT / "gfx"
MANIFEST = ROOT / "tools" / "dm_dds_dimension_fixes.json"
COA_RELATIVE_ROOT = Path("gfx/coat_of_arms/colored_emblems")
SUPPORTED_FOURCC = {
	b"DXT1": 8,
	b"DXT3": 16,
	b"DXT5": 16,
	b"ATI1": 8,
	b"BC4U": 8,
	b"ATI2": 16,
	b"BC5U": 16,
}


def sha256_bytes(data: bytes) -> str:
	return hashlib.sha256(data).hexdigest()


def mip_storage(width: int, height: int, levels: int, block_size: int) -> int:
	total = 0
	for _ in range(max(1, levels)):
		total += max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block_size
		width = max(1, width // 2)
		height = max(1, height // 2)
	return total


def inspect(data: bytes) -> tuple[int, int, int, bytes, int]:
	if len(data) < 128 or data[:4] != b"DDS ":
		raise ValueError("not a legacy DDS file")
	height, width = struct.unpack_from("<II", data, 12)
	mip_levels = struct.unpack_from("<I", data, 28)[0]
	fourcc = data[84:88]
	if fourcc not in SUPPORTED_FOURCC:
		raise ValueError(f"unsupported compressed DDS FourCC {fourcc!r}")
	return width, height, mip_levels, fourcc, SUPPORTED_FOURCC[fourcc]


def rounded(value: int) -> int:
	return (value + 3) & ~3


def tracked_paths() -> set[str]:
	result = subprocess.check_output(
		["git", "ls-files", "-z", "--", "gfx"],
		cwd=ROOT,
	)
	return {
		path.decode("utf-8").replace("\\", "/")
		for path in result.split(b"\0")
		if path
	}


def fix() -> dict[str, object]:
	files: list[dict[str, object]] = []
	if MANIFEST.is_file():
		files.extend(
			json.loads(MANIFEST.read_text(encoding="utf-8")).get("files", [])
		)
	known_paths = {item["path"] for item in files}
	tracked = tracked_paths()
	for path in sorted(TEXTURE_ROOT.rglob("*.dds")):
		relative_path = path.relative_to(ROOT).as_posix()
		if (
			Path(relative_path).is_relative_to(COA_RELATIVE_ROOT)
			and relative_path not in tracked
		):
			continue
		if relative_path in known_paths:
			continue
		data = path.read_bytes()
		try:
			width, height, levels, fourcc, block_size = inspect(data)
		except ValueError:
			continue
		new_width, new_height = rounded(width), rounded(height)
		if (new_width, new_height) == (width, height):
			continue
		old_storage = mip_storage(width, height, levels, block_size)
		new_storage = mip_storage(new_width, new_height, levels, block_size)
		if old_storage != new_storage:
			raise RuntimeError(
				f"header-only correction would move mip offsets: {path}"
			)
		updated = bytearray(data)
		struct.pack_into("<II", updated, 12, new_height, new_width)
		updated_bytes = bytes(updated)
		path.write_bytes(updated_bytes)
		files.append(
			{
				"path": relative_path,
				"fourcc": fourcc.decode("ascii"),
				"old_width": width,
				"old_height": height,
				"new_width": new_width,
				"new_height": new_height,
				"original_sha256": sha256_bytes(data),
				"installed_sha256": sha256_bytes(updated_bytes),
			}
		)
	return {"method": "DDS header block-boundary correction", "files": files}


def check() -> None:
	data = json.loads(MANIFEST.read_text(encoding="utf-8"))
	for item in data["files"]:
		path = ROOT / item["path"]
		current = path.read_bytes()
		if sha256_bytes(current) != item["installed_sha256"]:
			raise SystemExit(f"DDS dimension correction drifted: {item['path']}")
		width, height, *_ = inspect(current)
		if width % 4 or height % 4:
			raise SystemExit(f"DDS dimensions are still invalid: {item['path']}")
	print(f"DDS dimension manifest OK: {len(data['files'])} files")


def revert_coat_of_arms(tiger_baseline: Path) -> None:
	data = json.loads(MANIFEST.read_text(encoding="utf-8"))
	kept: list[dict[str, object]] = []
	reverted = 0
	for item in data["files"]:
		relative = Path(item["path"])
		if not relative.is_relative_to(COA_RELATIVE_ROOT):
			kept.append(item)
			continue
		path = (ROOT / relative).resolve()
		coa_root = (ROOT / COA_RELATIVE_ROOT).resolve()
		if not path.is_relative_to(coa_root):
			raise SystemExit(f"unsafe CoA rollback path: {path}")
		current = path.read_bytes()
		current_hash = sha256_bytes(current)
		if current_hash == item["original_sha256"]:
			reverted += 1
			continue
		if current_hash != item["installed_sha256"]:
			raise SystemExit(f"CoA file changed after correction: {relative}")
		updated = bytearray(current)
		struct.pack_into(
			"<II",
			updated,
			12,
			int(item["old_height"]),
			int(item["old_width"]),
		)
		original = bytes(updated)
		if sha256_bytes(original) != item["original_sha256"]:
			raise SystemExit(f"CoA rollback hash mismatch: {relative}")
		path.write_bytes(original)
		reverted += 1

	baseline_bytes = tiger_baseline.read_bytes()
	if baseline_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
		baseline_text = baseline_bytes.decode("utf-16")
	else:
		baseline_text = baseline_bytes.decode("utf-8-sig")
	reports = json.loads(baseline_text)
	missing: set[Path] = set()
	registry_path = (
		"gfx\\coat_of_arms\\colored_emblems\\dm_coa_designer_emblems.txt"
	)
	prefix, suffix = "file ", " does not exist"
	for report in reports:
		locations = report.get("locations") or [{}]
		message = report.get("message", "")
		if (
			report.get("key") == "missing-file"
			and locations[0].get("path") == registry_path
			and message.startswith(prefix)
			and message.endswith(suffix)
		):
			missing.add(Path(message[len(prefix) : -len(suffix)]))

	removed = 0
	coa_root = (ROOT / COA_RELATIVE_ROOT).resolve()
	for relative in sorted(missing):
		path = (ROOT / relative).resolve()
		if not path.is_relative_to(coa_root):
			raise SystemExit(f"unsafe restored CoA removal path: {path}")
		if path.is_file():
			path.unlink()
			removed += 1

	data["files"] = kept
	MANIFEST.write_text(
		json.dumps(data, ensure_ascii=False, indent=2) + "\n",
		encoding="utf-8",
	)
	print(
		f"reverted {reverted} CoA headers and removed "
		f"{removed} baseline-missing CoA files"
	)


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--check", action="store_true")
	parser.add_argument("--revert-coa", type=Path)
	args = parser.parse_args()
	if args.check:
		check()
		return
	if args.revert_coa:
		revert_coat_of_arms(args.revert_coa)
		return
	data = fix()
	MANIFEST.write_text(
		json.dumps(data, ensure_ascii=False, indent=2) + "\n",
		encoding="utf-8",
	)
	print(f"corrected {len(data['files'])} compressed DDS headers")


if __name__ == "__main__":
	main()
