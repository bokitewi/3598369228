#!/usr/bin/env python3
"""Classify CK3-Tiger reports against a narrow, reviewable false-positive list."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "tools" / "dm_tiger_false_positive_baseline.json"
BLOCKING_SEVERITIES = {"error", "warning"}


def read_text_auto(path: Path) -> str:
	data = path.read_bytes()
	for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
		try:
			return data.decode(encoding)
		except UnicodeDecodeError:
			continue
	raise ValueError(f"cannot decode {path}")


def load_json(path: Path):
	return json.loads(read_text_auto(path))


def report_location(report: dict) -> dict:
	locations = report.get("locations") or []
	return locations[0] if locations else {}


def normalized_path(value: str) -> str:
	return value.replace("/", "\\").lower()


def matches(report: dict, rule: dict) -> bool:
	location = report_location(report)
	if normalized_path(location.get("path", "")) != normalized_path(rule["path"]):
		return False
	for field in ("severity", "confidence", "key", "message"):
		expected = rule.get(field)
		if expected is not None and report.get(field) != expected:
			return False
	expected_line = rule.get("source_line")
	if expected_line is not None and location.get("line", "").strip() != expected_line.strip():
		return False
	return True


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--input", type=Path, required=True, help="CK3-Tiger JSON result")
	parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
	parser.add_argument("--check", action="store_true", help="fail on real errors/warnings or stale rules")
	args = parser.parse_args()

	reports = load_json(args.input)
	rules = load_json(args.baseline).get("rules", [])
	rule_hits = Counter()
	false_positives: list[dict] = []
	actionable: list[dict] = []

	for report in reports:
		if report.get("severity") not in BLOCKING_SEVERITIES:
			continue
		matched_index = next(
			(index for index, rule in enumerate(rules) if matches(report, rule)),
			None,
		)
		if matched_index is None:
			actionable.append(report)
		else:
			rule_hits[matched_index] += 1
			false_positives.append(report)

	stale_rules = [
		(index, rule)
		for index, rule in enumerate(rules)
		if rule_hits[index] != rule.get("expected_count", 1)
	]

	def print_report(report: dict) -> None:
		location = report_location(report)
		print(
			f"{report.get('severity')} {report.get('confidence')} {report.get('key')} "
			f"{location.get('path')}:{location.get('linenr')} {report.get('message')}"
		)

	counts = Counter(report.get("severity") for report in actionable)
	print(
		"tiger triage: "
		f"actionable_errors={counts['error']} "
		f"actionable_warnings={counts['warning']} "
		f"false_positives={len(false_positives)} "
		f"stale_rules={len(stale_rules)}"
	)

	if actionable:
		print("first actionable reports:")
		for report in actionable[:50]:
			print_report(report)
	if stale_rules:
		print("stale or overbroad false-positive rules:")
		for index, rule in stale_rules:
			print(
				f"rule[{index}] expected={rule.get('expected_count', 1)} "
				f"actual={rule_hits[index]} {rule['path']} {rule.get('key')}"
			)

	if args.check and (actionable or stale_rules):
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
