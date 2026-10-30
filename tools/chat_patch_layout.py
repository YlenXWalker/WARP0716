"""Locate installed chat code through its actual native call/jump sites."""

import json
import struct
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_32, Cs

ROOT = Path(__file__).resolve().parents[1]


def target(pe, address, opcode):
    data = pe.get_data(address - pe.OPTIONAL_HEADER.ImageBase, 5)
    if data[0] != opcode:
        return None
    return address + 5 + struct.unpack_from("<i", data, 1)[0]


def installed_stutter(pe):
    bridge = target(pe, 0x83D452, 0xE9)
    if bridge is None:
        return None
    code = pe.get_data(bridge - pe.OPTIONAL_HEADER.ImageBase, 96)
    decoder = Cs(CS_ARCH_X86, CS_MODE_32)
    decoder.detail = True
    matcher = next(
        i.operands[0].imm for i in decoder.disasm(code, bridge) if i.mnemonic == "call"
    )
    return dict(bridge=bridge, matcher=matcher)


def installed_cache(pe):
    fragment = target(pe, 0x83DEB7, 0xE8)
    if fragment == 0xA21C90:
        return None
    assert fragment is not None
    meta = json.loads((ROOT / "Inputs/ChatMeasurementCache/runtime.json").read_text())
    code = fragment - meta["exports"]["@ChatFragmentWidth@32"]
    state = struct.unpack(
        "<I",
        pe.get_data(
            code + meta["exports"]["ChatCacheApi"] - pe.OPTIONAL_HEADER.ImageBase, 4
        ),
    )[0]
    return dict(
        code=code,
        code_size=meta["size"],
        state=state,
        state_size=meta["layout"][0],
        bridge=target(pe, 0xA23BA9, 0xE9),
        glyph=code + meta["exports"]["_ChatGlyphWidth@16"],
        fragment=fragment,
        layout=code + meta["exports"]["ChatCacheLayout"],
    )
