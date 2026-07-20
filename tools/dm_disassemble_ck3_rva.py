import sys
from pathlib import Path

import pefile
from capstone import CS_ARCH_X86, CS_MODE_64, Cs


EXE = Path(
    r"D:\SteamLibrary\steamapps\common\Crusader Kings III\binaries\ck3.exe"
)


def main() -> None:
    target = int(sys.argv[1], 16)
    pe = pefile.PE(str(EXE), fast_load=False)
    begin = max(0, target - 96)
    end = target + 160
    for entry in getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", []):
        if entry.struct.BeginAddress <= target < entry.struct.EndAddress:
            begin = entry.struct.BeginAddress
            end = entry.struct.EndAddress
            print(f"Function RVA {begin:x}-{end:x}")
            break
    offset = pe.get_offset_from_rva(begin)
    data = pe.__data__[offset:offset + (end - begin)]
    disassembler = Cs(CS_ARCH_X86, CS_MODE_64)
    for instruction in disassembler.disasm(data, pe.OPTIONAL_HEADER.ImageBase + begin):
        rva = instruction.address - pe.OPTIONAL_HEADER.ImageBase
        marker = ">>" if rva == target else "  "
        print(
            f"{marker} {rva:08x}: {instruction.mnemonic:8} "
            f"{instruction.op_str}"
        )


if __name__ == "__main__":
    main()
