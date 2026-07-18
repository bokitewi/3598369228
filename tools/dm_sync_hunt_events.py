#!/usr/bin/env python3
"""Sync vanilla hunt events and guard merchant culture/faith fallbacks."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III"
    r"\game\events\activities\hunt_activity\hunt_events.txt"
)
TARGET = ROOT / "events/activities/hunt_activity/hunt_events.txt"

DOG_OLD = """\
\t\t\trandom_list = {
\t\t\t\t10 = {
\t\t\t\t\tadd_to_list = realm_list
\t\t\t\t\tevery_neighboring_and_across_water_top_liege_realm_owner = { add_to_list = realm_list }
\t\t\t\t\trandom_in_list = {
\t\t\t\t\t\tlist = realm_list
\t\t\t\t\t\trandom_realm_county = {
\t\t\t\t\t\t\tculture = { save_scope_as = merchant_culture }
\t\t\t\t\t\t\tfaith = { save_scope_as = merchant_faith }
\t\t\t\t\t\t}
\t\t\t\t\t}
"""
DOG_NEW = """\
\t\t\troot.culture = { save_scope_as = merchant_culture }
\t\t\troot.faith = { save_scope_as = merchant_faith }
\t\t\trandom_list = {
\t\t\t\t10 = {
\t\t\t\t\tadd_to_list = realm_list
\t\t\t\t\tevery_neighboring_and_across_water_top_liege_realm_owner = { add_to_list = realm_list }
\t\t\t\t\trandom_in_list = {
\t\t\t\t\t\tlist = realm_list
\t\t\t\t\t\trandom_realm_county = {
\t\t\t\t\t\t\tlimit = {
\t\t\t\t\t\t\t\texists = culture
\t\t\t\t\t\t\t\texists = faith
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\tculture = { save_scope_as = merchant_culture }
\t\t\t\t\t\t\tfaith = { save_scope_as = merchant_faith }
\t\t\t\t\t\t}
\t\t\t\t\t}
"""

FALCON_OLD = """\
\t\t\tif = {
\t\t\t\tlimit = {
\t\t\t\t\tNOT = { exists = scope:falcon_salesman }
\t\t\t\t}
\t\t\t\tlocation.empire = {
\t\t\t\t\trandom_in_de_jure_hierarchy = {
\t\t\t\t\t\tlimit = {
\t\t\t\t\t\t\ttier = tier_county
\t\t\t\t\t\t}
\t\t\t\t\t\tculture = { save_scope_as = merchant_culture }
\t\t\t\t\t\tfaith = { save_scope_as = merchant_faith }
\t\t\t\t\t}
\t\t\t\t}
"""
FALCON_NEW = """\
\t\t\tif = {
\t\t\t\tlimit = {
\t\t\t\t\tNOT = { exists = scope:falcon_salesman }
\t\t\t\t}
\t\t\t\troot.culture = { save_scope_as = merchant_culture }
\t\t\t\troot.faith = { save_scope_as = merchant_faith }
\t\t\t\tif = {
\t\t\t\t\tlimit = { exists = location.empire }
\t\t\t\t\tlocation.empire = {
\t\t\t\t\t\trandom_in_de_jure_hierarchy = {
\t\t\t\t\t\t\tlimit = {
\t\t\t\t\t\t\t\ttier = tier_county
\t\t\t\t\t\t\t\texists = culture
\t\t\t\t\t\t\t\texists = faith
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\tculture = { save_scope_as = merchant_culture }
\t\t\t\t\t\t\tfaith = { save_scope_as = merchant_faith }
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t}
"""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8-sig")
    text = replace_once(text, DOG_OLD, DOG_NEW, "dog merchant")
    text = replace_once(text, FALCON_OLD, FALCON_NEW, "falcon merchant")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8-sig", newline="\n")
    print(TARGET)


if __name__ == "__main__":
    main()
