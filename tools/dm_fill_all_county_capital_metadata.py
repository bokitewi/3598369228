from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from dm_generate_history_compat import (
    ROOT,
    atom,
    dated_direct_value,
    insert_province_metadata,
    load_title_tree,
    read_script,
)


GENERATED_NAME = "dm_autofill_province_history.txt"


def load_all_province_history():
    metadata = {}
    authored_source = {}
    generated_entries = {}
    directory = ROOT / "history" / "provinces"
    for path in sorted(directory.glob("*.txt")):
        for key, value in read_script(path):
            if not key or not key.isdigit() or not isinstance(value, list):
                continue
            province = int(key)
            entry = metadata.setdefault(province, {})
            fields = {}
            for field in ("culture", "religion"):
                candidate = dated_direct_value(value, field)
                if candidate:
                    entry[field] = candidate
                    fields[field] = candidate
            if path.name == GENERATED_NAME:
                generated_entries[province] = fields
            else:
                authored_source[province] = path
    return metadata, authored_source, generated_entries


def main() -> None:
    parent, children, capital, barony_province, landless = load_title_tree()
    metadata, authored_source, generated_entries = (
        load_all_province_history()
    )

    @lru_cache(maxsize=None)
    def descendant_provinces(title):
        if title.startswith("b_"):
            province = barony_province.get(title)
            return (province,) if province is not None else ()
        values = []
        for child in children.get(title, []):
            values.extend(descendant_provinces(child))
        return tuple(dict.fromkeys(values))

    def county_capital_province(county):
        explicit = capital.get(county)
        if explicit and explicit in barony_province:
            return barony_province[explicit]
        for child in children.get(county, []):
            if child.startswith("b_") and child in barony_province:
                return barony_province[child]
        raise RuntimeError(f"County {county} has no capital barony province")

    def ancestor_chain(title):
        result = []
        while title in parent:
            title = parent[title]
            result.append(title)
        return result

    global_modes = {}
    for field in ("culture", "religion"):
        counter = Counter(
            entry[field] for entry in metadata.values() if field in entry
        )
        if not counter:
            raise RuntimeError(f"No province history contains {field}")
        global_modes[field] = counter.most_common(1)[0][0]

    @lru_cache(maxsize=None)
    def regional_mode(title, field):
        counter = Counter(
            metadata[province][field]
            for province in descendant_provinces(title)
            if field in metadata.get(province, {})
        )
        if not counter:
            return None
        best = max(counter.values())
        return min(key for key, count in counter.items() if count == best)

    def infer(county, field):
        capital_province = county_capital_province(county)
        if field in metadata.get(capital_province, {}):
            return metadata[capital_province][field]
        for province in descendant_provinces(county):
            if field in metadata.get(province, {}):
                return metadata[province][field]
        for ancestor in ancestor_chain(county):
            candidate = regional_mode(ancestor, field)
            if candidate:
                return candidate
        return global_modes[field]

    assignments = defaultdict(dict)
    for province, fields in generated_entries.items():
        assignments[province].update(fields)

    repaired_counties = 0
    inserted_fields = 0
    counties = sorted(
        title for title in parent
        if title.startswith("c_") and title not in landless
    )
    for county in counties:
        province = county_capital_province(county)
        missing = [
            field for field in ("culture", "religion")
            if field not in metadata.get(province, {})
        ]
        if not missing:
            continue
        repaired_counties += 1
        for field in missing:
            value = infer(county, field)
            assignments[province][field] = value
            metadata.setdefault(province, {})[field] = value
            inserted_fields += 1
            print(
                f"{county}: province {province}: "
                f"{field} = {value}"
            )

    insert_province_metadata(assignments, authored_source)
    print(
        f"Repaired {repaired_counties} county capitals "
        f"with {inserted_fields} metadata fields."
    )


if __name__ == "__main__":
    main()
