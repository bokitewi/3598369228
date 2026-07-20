import re
from collections import defaultdict
from pathlib import Path

from dm_generate_history_compat import (
    load_province_history,
    load_title_tree,
)

ROOT = Path(__file__).resolve().parents[1]
PROVINCE_BLOCK = re.compile(r"(?m)^(\d+)\s*=\s*\{")


def strip_comments(text: str) -> str:
    return re.sub(r"#.*", "", text)


def blocks(path: Path):
    text = strip_comments(path.read_text(encoding="utf-8-sig"))
    for match in PROVINCE_BLOCK.finditer(text):
        depth = 0
        end = match.end()
        for index in range(match.end() - 1, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        yield int(match.group(1)), text[match.start():end]


def top_level_keys(directory: Path):
    result = set()
    pattern = re.compile(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{")
    for path in directory.glob("*.txt"):
        text = strip_comments(path.read_text(encoding="utf-8-sig"))
        result.update(pattern.findall(text))
    return result


def main() -> None:
    parent, children, capital, barony_province, landless = load_title_tree()
    metadata, _ = load_province_history()
    county_capital_issues = []
    counties = sorted(
        title for title in parent
        if title.startswith("c_") and title not in landless
    )
    for county in counties:
        barony = capital.get(county)
        if not barony or barony not in barony_province:
            barony = next(
                (
                    child for child in children.get(county, [])
                    if child.startswith("b_") and child in barony_province
                ),
                None,
            )
        if barony is None:
            county_capital_issues.append(
                (county, None, "no capital barony")
            )
            continue
        province = barony_province[barony]
        entry = metadata.get(province, {})
        missing_fields = [
            field for field in ("culture", "religion")
            if field not in entry
        ]
        if missing_fields:
            county_capital_issues.append(
                (county, province, ",".join(missing_fields))
            )

    title_provinces = set()
    for path in (ROOT / "common/landed_titles").glob("*.txt"):
        text = strip_comments(path.read_text(encoding="utf-8-sig"))
        title_provinces.update(
            map(int, re.findall(r"\bprovince\s*=\s*(\d+)", text))
        )

    definitions = defaultdict(list)
    for path in sorted((ROOT / "history/provinces").glob("*.txt")):
        for province, body in blocks(path):
            culture = re.findall(
                r"(?m)^\s*culture\s*=\s*([A-Za-z0-9_]+)",
                body,
            )
            faith = re.findall(
                r"(?m)^\s*(?:religion|faith)\s*=\s*([A-Za-z0-9_]+)",
                body,
            )
            definitions[province].append(
                (path.name, culture[-1] if culture else None,
                 faith[-1] if faith else None)
            )

    cultures = top_level_keys(ROOT / "common/culture/cultures")
    faiths = top_level_keys(ROOT / "common/religion/religion_types")
    missing = sorted(title_provinces - definitions.keys())
    duplicates = {
        key: values for key, values in definitions.items() if len(values) > 1
    }
    incomplete = []
    invalid = []
    for province in sorted(title_provinces & definitions.keys()):
        path, culture, faith = definitions[province][-1]
        if culture is None or faith is None:
            incomplete.append((province, path, culture, faith))
        if (
            (culture is not None and culture not in cultures)
            or (faith is not None and faith not in faiths)
        ):
            invalid.append((province, path, culture, faith))

    print(
        f"title_provinces={len(title_provinces)} "
        f"history_provinces={len(definitions)} missing={len(missing)} "
        f"duplicates={len(duplicates)} incomplete={len(incomplete)} "
        f"invalid={len(invalid)}"
    )
    print(
        f"counties={len(counties)} "
        f"county_capital_issues={len(county_capital_issues)}"
    )
    for county, province, issue in county_capital_issues[:1000]:
        print(
            f"COUNTY_CAPITAL_ISSUE {county} "
            f"province={province} missing={issue}"
        )
    for province in missing[:500]:
        print(f"MISSING {province}")
    for province, values in list(duplicates.items())[:500]:
        print(
            f"DUPLICATE {province} "
            + ", ".join(item[0] for item in values)
        )
    for row in incomplete[:500]:
        print(
            f"INCOMPLETE {row[0]} {row[1]} "
            f"culture={row[2]} faith={row[3]}"
        )
    for row in invalid[:500]:
        print(
            f"INVALID {row[0]} {row[1]} "
            f"culture={row[2]} faith={row[3]}"
        )


if __name__ == "__main__":
    main()
