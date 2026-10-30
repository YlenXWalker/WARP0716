"""Independently verify the embedded chat runtime, native hooks and tag helpers."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

import pefile
from chat_diagnostics_test_support import descriptor

ROOT = Path(__file__).resolve().parents[1]


def verify(exe, source_path):
    pe = pefile.PE(str(exe))
    d = descriptor(pe)
    assert d
    assert (
        pe.FILE_HEADER.Machine == 0x14C
        and pe.OPTIONAL_HEADER.ImageBase == 0x400000
        and not pe.OPTIONAL_HEADER.DllCharacteristics & 0x40
    )
    raw = (ROOT / "Inputs/ChatDiagnostics/runtime.bin").read_bytes()
    meta = json.loads((ROOT / "Inputs/ChatDiagnostics/runtime.json").read_text())
    magic, version, size, count, config, link, client, crc = struct.unpack_from(
        "<8I", raw
    )
    assert (magic, version, size, client) == (0x44474843, 1, d["size"], 20250716)
    payload = bytearray(raw[32 + count * 4 :])
    for off in struct.unpack_from("<" + "I" * count, raw, 32):
        struct.pack_into(
            "<I", payload, off, struct.unpack_from("<I", payload, off)[0] + d["code"]
        )
    values = struct.unpack("<4I", pe.get_data(d["config"] - 0x400000, 16))
    imports = {
        i.name.decode(): i.address
        for dll in pe.DIRECTORY_ENTRY_IMPORT
        for i in dll.imports
        if i.name
    }

    def binding(slot, name):
        if slot == imports[name]:
            return
        # CustomDLL may publish a shared lazy slot instead of the original IAT.
        resolver = struct.unpack("<I", pe.get_data(slot - 0x400000, 4))[0]
        assert resolver == slot + 16
        b = pe.get_data(resolver - 0x400000, 38)
        assert (
            b[:3] == b"\x9c\x60\x68"
            and b[7:9] == b"\xff\x15"
            and b[13] == 0x68
            and b[18:21] == b"\x50\xff\x15"
        )
        assert b[25] == 0xA3 and b[30:34] == b"\x61\x9d\xff\x25"
        dll, mod, export, proc, store, jump = [
            struct.unpack_from("<I", b, o)[0] for o in [3, 9, 14, 21, 26, 34]
        ]
        assert (
            mod == imports["GetModuleHandleA"]
            and proc == imports["GetProcAddress"]
            and store == jump == slot
        )
        assert (
            pe.get_data(dll - 0x400000, 64).split(b"\0")[0].lower() == b"kernel32.dll"
        )
        assert pe.get_data(export - 0x400000, 64).split(b"\0")[0].decode() == name

    binding(values[0], "GetModuleHandleA")
    binding(values[1], "GetProcAddress")
    assert values[2] == d["matcher"]
    struct.pack_into("<4I", payload, config, *values)
    struct.pack_into("<I", payload, link, 0x10000 | values[3] | 4)
    assert pe.get_data(d["code"] - 0x400000, size) == payload, (
        "Only declared configuration words may differ from compiled telemetry"
    )
    for site, target, size in [
        (0x83D452, d["bridge"], 5),
        (0x83D49B, d["direct"], 5),
        (0x83D4AF, d["wrap"], 5),
        (0x83D606, d["finish"], 6),
    ]:
        data = pe.get_data(site - 0x400000, size)
        assert (
            data[0] == 0xE9
            and site + 5 + struct.unpack_from("<i", data, 1)[0] == target
        )
        if size == 6:
            assert data[5] == 0x90
    source = pefile.PE(str(source_path))
    for va, size in [(0x575780, 0xE1), (0x7FAF70, 0x132)]:
        assert pe.get_data(va - 0x400000, size) == source.get_data(va - 0x400000, size)
    assert (
        hashlib.sha256(
            (ROOT / "Scripts/Runtime/ChatDiagnostics/runtime.cpp")
            .read_bytes()
            .replace(b"\r\n", b"\n")
        ).hexdigest()
        == meta["source_sha256"]
    )
    assert (
        hashlib.sha256(
            (ROOT / "Scripts/Runtime/ChatDiagnostics/api.h")
            .read_bytes()
            .replace(b"\r\n", b"\n")
        ).hexdigest()
        == meta["shared_api_sha256"]
    )
    return d


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    assert (
        hashlib.sha256(args.source.read_bytes()).hexdigest()
        == "ead7c0a316bc6c27705a5a6876daf5093abec31677f3c1af7525c1709b201bff"
    )
    result = verify(args.exe, args.source)
    print(json.dumps(dict(passed=True, descriptor=result), indent=2))


if __name__ == "__main__":
    main()
