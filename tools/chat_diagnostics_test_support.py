"""Locate the diagnostics ABI and replace only its OS bootstrap in Unicorn tests."""

import struct


def descriptor(pe):
    raw = pe.__data__
    tag = raw.find(b"ChatDiagnostics.v1\0")
    if tag < 0:
        return None
    base = pe.OPTIONAL_HEADER.ImageBase
    va = base + pe.get_rva_from_offset(tag)
    data = pe.get_memory_mapped_image()
    pos = data.find(struct.pack("<I", va))
    assert pos >= 0 and data.find(struct.pack("<I", va), pos + 1) < 0
    names = "version code size link phase config bridge matcher direct wrap finish layout".split()
    result = dict(zip(names, struct.unpack_from("<12I", data, pos + 4)))
    assert result["version"] == 1
    return result


def isolate_os(machine):
    """The Win32 worker runs separately in the real native host integration test."""
    data = descriptor(machine.pe)
    if data:
        machine.u.mem_write(data["phase"], struct.pack("<I", 2))
    return data
