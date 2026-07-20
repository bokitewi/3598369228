import struct
import sys
from pathlib import Path

import pefile


EXE = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III\binaries\ck3.exe"
)


def main() -> None:
    target = int(sys.argv[1], 16)
    pe = pefile.PE(str(EXE), fast_load=False)
    found = []
    for section in pe.sections:
        data = section.get_data()
        section_rva = section.VirtualAddress
        for offset in range(0, len(data) - 5):
            if data[offset] != 0xE8:
                continue
            relative = struct.unpack_from("<i", data, offset + 1)[0]
            source = section_rva + offset
            destination = source + 5 + relative
            if destination == target:
                found.append(source)
    print(f"Direct call xrefs to RVA {target:x}: {len(found)}")
    for source in found:
        print(f"{source:x}")


if __name__ == "__main__":
    main()
