import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CULTURE_DIR = ROOT / "common" / "culture" / "cultures"
TEST_FILE = CULTURE_DIR / "zz_dm_diagnostic_minimal_cultures.txt"
VANILLA_TEST_FILE = CULTURE_DIR / "zz_dm_diagnostic_minimal_vanilla_cultures.txt"
CUSTOM_FILES = (
    "ba_cultures.txt",
    "baipu_cultures.txt",
    "beidi_cultures.txt",
    "dongyi_cultures.txt",
    "jingchu_cultures.txt",
    "shangren_cultures.txt",
    "shu_cultures.txt",
    "xianmin_cultures.txt",
    "xiaren_cultures.txt",
    "xirong_cultures.txt",
    "zhouren_cultures.txt",
)


def top_level_keys(path: Path):
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line and not line[0].isspace() and "= {" in line:
            key = line.split("=", 1)[0].strip()
            if key.replace("_", "").isalnum():
                yield key


def enable() -> None:
    cultures = []
    for name in CUSTOM_FILES:
        source = CULTURE_DIR / name
        backup = source.with_suffix(source.suffix + ".diagnostic_disabled")
        if source.exists():
            cultures.extend(top_level_keys(source))
            source.replace(backup)
        elif backup.exists():
            cultures.extend(top_level_keys(backup))
        else:
            raise FileNotFoundError(source)
    entries = []
    for index, culture in enumerate(dict.fromkeys(cultures)):
        entries.append(
            f"{culture} = {{\n"
            f"\tcolor = {{ {(index * 37) % 255} "
            f"{(index * 67) % 255} {(index * 97) % 255} }}\n"
            "\tname_order_convention = dynasty_always_first\n"
            "\tethos = ethos_communal\n"
            "\theritage = heritage_zhouren\n"
            "\tlanguage = language_chinese\n"
            "\tmartial_custom = martial_custom_male_only\n"
            "\thead_determination = head_determination_domain\n"
            "\ttraditions = { tradition_agrarian }\n"
            "\tname_list = name_list_han\n"
            "\tcoa_gfx = { chinese_group_coa_gfx }\n"
            "\tbuilding_gfx = { chinese_building_gfx }\n"
            "\tclothing_gfx = { chinese_clothing_gfx }\n"
            "\tunit_gfx = { chinese_unit_gfx }\n"
            "\tethnicities = { 10 = asian_han_chinese }\n"
            "}\n"
        )
    TEST_FILE.write_text("\n".join(entries), encoding="utf-8-sig")
    print(f"Enabled diagnostic templates for {len(entries)} cultures.")


def disable() -> None:
    if TEST_FILE.exists():
        TEST_FILE.unlink()
    restored = 0
    for name in CUSTOM_FILES:
        source = CULTURE_DIR / name
        backup = source.with_suffix(source.suffix + ".diagnostic_disabled")
        if backup.exists():
            if source.exists():
                raise RuntimeError(f"Refusing to overwrite {source}")
            backup.replace(source)
            restored += 1
    print(f"Restored {restored} custom culture files.")


def enable_vanilla() -> None:
    cultures = []
    sources = sorted(CULTURE_DIR.glob("00_*.txt"))
    for source in sources:
        backup = source.with_suffix(source.suffix + ".all_diagnostic_disabled")
        cultures.extend(top_level_keys(source))
        source.replace(backup)
    entries = []
    for index, culture in enumerate(dict.fromkeys(cultures)):
        entries.append(
            f"{culture} = {{\n"
            f"\tcolor = {{ {(index * 31) % 255} "
            f"{(index * 61) % 255} {(index * 91) % 255} }}\n"
            "\tname_order_convention = suffix\n"
            "\tethos = ethos_communal\n"
            "\theritage = heritage_zhouren\n"
            "\tlanguage = language_chinese\n"
            "\tmartial_custom = martial_custom_male_only\n"
            "\thead_determination = head_determination_domain\n"
            "\ttraditions = { tradition_agrarian }\n"
            "\tname_list = name_list_han\n"
            "\tcoa_gfx = { chinese_group_coa_gfx }\n"
            "\tbuilding_gfx = { chinese_building_gfx }\n"
            "\tclothing_gfx = { chinese_clothing_gfx }\n"
            "\tunit_gfx = { chinese_unit_gfx }\n"
            "\tethnicities = { 10 = asian_han_chinese }\n"
            "}\n"
        )
    VANILLA_TEST_FILE.write_text(
        "\n".join(entries),
        encoding="utf-8-sig",
    )
    print(
        f"Enabled diagnostic templates for "
        f"{len(entries)} vanilla cultures."
    )


def disable_vanilla() -> None:
    if VANILLA_TEST_FILE.exists():
        VANILLA_TEST_FILE.unlink()
    restored = 0
    for backup in sorted(
        CULTURE_DIR.glob("00_*.txt.all_diagnostic_disabled")
    ):
        source = Path(
            str(backup).removesuffix(".all_diagnostic_disabled")
        )
        if source.exists():
            raise RuntimeError(f"Refusing to overwrite {source}")
        backup.replace(source)
        restored += 1
    print(f"Restored {restored} vanilla culture files.")


def main() -> None:
    modes = {"enable", "disable", "enable_vanilla", "disable_vanilla"}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        raise SystemExit(
            "Usage: dm_diagnostic_minimal_cultures.py "
            "enable|disable|enable_vanilla|disable_vanilla"
        )
    if sys.argv[1] == "enable":
        enable()
    elif sys.argv[1] == "disable":
        disable()
    elif sys.argv[1] == "enable_vanilla":
        enable_vanilla()
    else:
        disable_vanilla()


if __name__ == "__main__":
    main()
