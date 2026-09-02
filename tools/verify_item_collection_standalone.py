#!/usr/bin/env python3
"""Verify the standalone Item Collection core and stock-menu launcher in a PE."""

from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path

import pefile


CORE_PATHS = (
    b"item_collection\\chrome\\title_bar_760.bmp\0",
    b"item_collection\\chrome\\bg_collection.bmp\0",
    b"item_collection\\chrome\\loading.bmp\0",
    b"collection\\%s.bmp\0",
    b"item\\%s.bmp\0",
)

STYLE_PATHS = {
    "new": (
        b"bt_itemcollection_normal.bmp\0",
        b"bt_itemcollection_mouseon.bmp\0",
        b"bt_itemcollection_pressed.bmp\0",
    ),
    "classic": (
        b"bt_itemcollection_old_normal.bmp\0",
        b"bt_itemcollection_old_mouseon.bmp\0",
        b"bt_itemcollection_old_pressed.bmp\0",
    ),
}

VTABLES = (
    (0x01028200, 0x00814150, "draw"),
    (0x010281E8, 0x005AAD80, "visibility"),
    (0x010281EC, 0x00812FB0, "create"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("--style", choices=("auto", "new", "classic"), default="auto")
    args = parser.parse_args()

    data = args.exe.read_bytes()
    pe = pefile.PE(data=data, fast_load=False)
    base = pe.OPTIONAL_HEADER.ImageBase
    require(base == 0x00400000, "unexpected image base")

    for path in CORE_PATHS:
        require(path in data, f"missing Item Collection core path: {path[:-1]!r}")
    require(data.count(b"COUI") >= 2, "COUI request/snapshot bridge is absent")
    require(b"Requesting the account collection snapshot...\0" not in data,
            "obsolete loading text remains")
    zero_row_guards = list(re.finditer(
        rb"\x8b\x0d....\x85\xc9\x0f\x84....\x83\xf9\x0f",
        data,
        re.DOTALL,
    ))
    require(len(zero_row_guards) == 1,
            f"expected one zero-row selection guard, found {len(zero_row_guards)}")

    embedded_styles = [
        style for style, paths in STYLE_PATHS.items()
        if all(path in data for path in paths)
    ]
    if args.style == "auto":
        require(len(embedded_styles) == 1,
                f"expected one launcher style, found {embedded_styles}")
        style = embedded_styles[0]
    else:
        style = args.style
        require(style in embedded_styles, f"{style} launcher paths are absent")

    replacements: list[str] = []
    for address, original, label in VTABLES:
        offset = pe.get_offset_from_rva(address - base)
        replacement = struct.unpack_from("<I", data, offset)[0]
        require(replacement != original, f"stock menu {label} vtable was not patched")
        require(replacement >= base, f"stock menu {label} target is not a VA")
        section = pe.get_section_by_rva(replacement - base)
        require(section is not None, f"stock menu {label} target is unmapped")
        require(section.Characteristics & 0x20000000,
                f"stock menu {label} target is not executable")
        replacements.append(f"{label}=0x{replacement:08X}")

    print(
        "ITEM_COLLECTION_STANDALONE_PE_OK "
        f"style={style} {' '.join(replacements)} core=COUI assets=dynamic"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, pefile.PEFormatError, RuntimeError) as exc:
        print(f"ITEM_COLLECTION_STANDALONE_PE_FAIL {exc}")
        raise SystemExit(1)
