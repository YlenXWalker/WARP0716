"""Execute ACT UI surface rasterization and compare stock native pixel blending."""

from pathlib import Path
import argparse
import math
import struct
import sys
import unittest
import pefile

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (
    UC_X86_REG_EAX,
    UC_X86_REG_EBP,
    UC_X86_REG_EBX,
    UC_X86_REG_ECX,
    UC_X86_REG_EDI,
    UC_X86_REG_EDX,
    UC_X86_REG_EFLAGS,
    UC_X86_REG_ESI,
    UC_X86_REG_ESP,
)

from build_native_act_job_ui import verify_profile_client

ROOT = Path(__file__).resolve().parents[1]
PROFILE_CLIENT = None


class Fixture:
    images = None

    def __init__(self, fmt=0):
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        if Fixture.images is None:
            Fixture.images = []
            for path in [PROFILE_CLIENT, ROOT / "Outputs/native-act-job-ui/native/native-act.exe"]:
                pe = pefile.PE(str(path))
                base = pe.OPTIONAL_HEADER.ImageBase
                Fixture.images.append(
                    (
                        base,
                        (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095,
                        pe.get_memory_mapped_image(),
                    )
                )
            Fixture.exports = {
                s.name.decode(): base + s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols
            }
        for base, n, data in Fixture.images:
            self.u.mem_map(base, n)
            self.u.mem_write(base, data)
        self.exports = Fixture.exports
        self.u.mem_map(0x30000000, 0x200000)
        self.window = 0x30000000
        self.surface = 0x30001000
        self.layer = 0x30002000
        self.image = 0x30003000
        self.texture = 0x30004000
        self.atlas = 0x30005000
        self.source = 0x30010000
        self.dest = 0x30040000
        self.stack = 0x301E0000
        self.stop = 0x301FF000
        self.lock = 0x301FA000
        self.unlock = 0x301FA100
        self.palette = 0x30006000
        self.video = 0x301F0000
        self.locks = 0
        self.unlocks = 0
        self.lookups = []
        self.fmt = fmt
        self.words(self.window, 0x103223C)
        self.words(self.window + 0x14, 160, 160, 300, 400, self.surface)
        self.words(self.surface, 0xFD5CE4, 160, 160, 0, 0, 0, self.dest, 0)
        self.words(self.texture, 0x30007000, fmt, 0, 256, 256)
        self.words(0x30007000 + 0x10, self.lock, self.unlock)
        self.words(0x12515F8, self.video)
        self.u.mem_write(self.dest, struct.pack("<I", 0xFF404040) * (160 * 160))
        self.u.mem_write(self.lock, b"\xc2\x04\x00")
        self.u.mem_write(self.unlock, b"\xc3")
        for va in [0x566B70, 0x5663D0]:
            self.u.mem_write(va, b"\xc2\x0c\x00")
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def words(self, at, *values):
        self.u.mem_write(
            at, struct.pack("<" + "I" * len(values), *(v & 0xFFFFFFFF for v in values))
        )

    def readwords(self, at, n=1):
        return struct.unpack("<" + "I" * n, self.u.mem_read(at, n * 4))

    def hook(self, u, at, size, _):
        if at == self.lock:
            self.locks += 1
            out = self.readwords(u.reg_read(UC_X86_REG_ESP) + 4)[0]
            self.words(out, 1, self.source, 512)
        elif at == self.unlock:
            self.unlocks += 1
        elif at == 0xA1B7C0:
            self.delegated = (
                u.reg_read(UC_X86_REG_ECX),
                self.readwords(u.reg_read(UC_X86_REG_ESP) + 4, 11),
            )
        elif at in [0x566B70, 0x5663D0]:
            image, palette, out = self.readwords(u.reg_read(UC_X86_REG_ESP) + 4, 3)
            assert (image, palette) == (self.image, self.palette)
            self.lookups.append(at)
            self.u.mem_write(out, bytes(40))
            u.reg_write(UC_X86_REG_EAX, self.texture)

    def setup(self, w=32, h=32, sx=1, sy=1, x=-16, y=-32, mirror=0, angle=0, kind=1):
        self.u.mem_write(
            self.layer, struct.pack("<4iIffii", x, y, 0, mirror, 0xFFFFFFFF, sx, sy, angle, kind)
        )
        self.u.mem_write(self.image, struct.pack("<4hI", w, h, 0, 0, self.texture))
        pixels = bytearray(256 * 256 * 2)
        for yy in range(h):
            for xx in range(w):
                if self.fmt == 0:
                    p = 0x8000 | ((xx % 31) << 10) | ((yy % 31) << 5) | ((xx + yy) % 31)
                else:
                    p = (
                        (((xx + yy) % 15 + 1) << 12)
                        | ((xx % 15) << 8)
                        | ((yy % 15) << 4)
                        | ((xx + yy) % 15)
                    )
                struct.pack_into("<H", pixels, (yy * 256 + xx) * 2, p)
        self.u.mem_write(self.source, bytes(pixels))

    def run(self, name, args, receiver=0, pop=0):
        regs = [UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP]
        values = [0x11110000 + i * 0x100 for i in range(4)]
        for r, v in zip(regs, values):
            self.u.reg_write(r, v)
        self.words(self.stack, self.stop, *args)
        self.u.reg_write(UC_X86_REG_ESP, self.stack)
        self.u.reg_write(UC_X86_REG_ECX, receiver)
        self.u.reg_write(UC_X86_REG_EDX, 0)
        self.u.emu_start(
            self.exports[name] if isinstance(name, str) else name, self.stop, count=3000000
        )
        assert self.u.reg_read(UC_X86_REG_ESP) == self.stack + 4 + pop, "stack imbalance"
        assert [self.u.reg_read(r) for r in regs] == values, "callee-saved register corruption"

    def draw(self):
        layer = bytes(self.u.mem_read(self.layer, 36))
        self.run(
            "NativeActSkillDraw",
            [self.window, self.layer, self.image, self.texture, self.atlas, 0, 0],
        )
        assert bytes(self.u.mem_read(self.layer, 36)) == layer
        return self.pixels()

    def pixels(self):
        return bytes(self.u.mem_read(self.dest, 160 * 160 * 4))

    def occupied(self):
        p = self.pixels()
        return [
            (i % 160, i // 160)
            for i, v in enumerate(struct.unpack("<25600I", p))
            if v != 0xFF404040
        ]


class Checks(unittest.TestCase):
    def test_unit_surface_output_matches_native_blitter(self):
        for fmt in [0, 1]:
            f = Fixture(fmt)
            f.setup(w=16, h=16, x=0, y=-30)
            actual = f.draw()
            f.u.mem_write(f.dest, struct.pack("<I", 0xFF404040) * 25600)
            f.run(0x53CFC0, [48, 105, f.texture, 0, 0, 16, 16, 0, 1, 1, 0], f.surface, 44)
            stock = f.pixels()
            self.assertLessEqual(max(abs(a - b) for a, b in zip(actual, stock)), 1)
            self.assertEqual(f.locks, f.unlocks)

    def test_scale_mirror_rotation_and_clipping(self):
        for sx, sy, angle in [
            (0.25, 0.25, 0),
            (0.5, 0.5, 0),
            (0.37, 0.61, 0),
            (0.5, 0.5, 90),
            (0.5, 0.5, 45),
        ]:
            f = Fixture()
            f.setup(w=64, h=48, sx=sx, sy=sy, x=-32, y=-48, angle=angle)
            f.draw()
            points = f.occupied()
            self.assertTrue(points)
            self.assertTrue(all(0 <= x < 160 and 0 <= y < 160 for x, y in points))
            if not angle:
                self.assertLessEqual(
                    max(x for x, y in points) - min(x for x, y in points) + 1,
                    math.ceil(64 * sx) + 1,
                )
            self.assertEqual((f.locks, f.unlocks), (1, 1))
            self.assertEqual(f.readwords(f.surface + 0x1C)[0], 1)
        a = Fixture()
        a.setup(x=0, y=-40)
        a.draw()
        b = Fixture()
        b.setup(x=0, y=-40, mirror=1)
        b.draw()
        for yy in range(95, 127):
            for xx in range(32):
                self.assertEqual(
                    a.readwords(a.dest + (yy * 160 + 48 + xx) * 4),
                    b.readwords(b.dest + (yy * 160 + 48 + 31 - xx) * 4),
                )

    def test_surface_persists_when_window_moves_without_repaint(self):
        f = Fixture()
        f.setup()
        before = f.draw()
        self.assertTrue(f.occupied())
        f.words(f.window + 0x1C, 800, 900)  # drag updates window placement; no repaint
        self.assertEqual(f.pixels(), before)
        self.assertEqual(
            f.readwords(f.window + 0x5C, 3), (0, 0, 0), "must not depend on an overlay queue"
        )

    def test_atlas_crop_and_invalid_input(self):
        f = Fixture()
        f.setup(kind=0)
        f.u.mem_write(f.atlas, struct.pack("<10f", 0, 0, 0, 0.125, 0.25, 0, 0, 0, 0, 0))
        f.draw()
        self.assertFalse(f.occupied())  # selected atlas rectangle is transparent
        for value in [0, -1, float("nan"), float("inf")]:
            f = Fixture()
            f.setup(sx=value)
            f.draw()
            self.assertEqual(f.locks, 0)

    def test_equipment_thiscall_and_palette_resolution(self):
        for kind in [0, 1]:
            f = Fixture()
            f.setup(kind=kind)
            bits = lambda x: struct.unpack("<I", struct.pack("<f", x))[0]
            f.run(
                "@NativeActEquipmentDraw@52",
                [80, 90, 0, 0, f.image, f.layer, bits(1), bits(0), 0xFFFFFFFF, f.palette, bits(1)],
                f.window,
                44,
            )
            self.assertTrue(f.occupied())
            self.assertEqual(f.locks, f.unlocks)
            self.assertEqual(f.lookups, [0x566B70] if kind == 0 else [])

    def test_other_windows_delegate_with_original_arguments(self):
        f = Fixture()
        f.setup()
        f.words(f.window, 0x103F660)
        f.u.mem_write(0xA1B7C0, b"\xc2\x2c\x00")
        bits = lambda x: struct.unpack("<I", struct.pack("<f", x))[0]
        args = [
            80,
            90,
            0x111,
            0x222,
            f.image,
            f.layer,
            bits(0.8),
            bits(30),
            0xFF123456,
            f.palette,
            bits(1),
        ]
        f.run("@NativeActEquipmentDraw@52", args, f.window, 44)
        self.assertEqual(f.delegated, (f.window, tuple(args)))
        self.assertEqual(f.locks, 0)
        self.assertFalse(f.occupied())

    def test_mid_function_bridge_stack_registers_and_visible_pixels(self):
        f = Fixture()
        f.setup()
        frame = 0x301D0000
        for offset, value in [
            (0xEC, f.window),
            (0xDC, f.layer),
            (0xD4, f.image),
            (0xD8, f.texture),
            (0xE0, 0),
            (0xE8, 0),
        ]:
            f.words(frame - offset, value)
        f.u.mem_write(frame - 0x130, bytes(40))
        regs = [
            UC_X86_REG_EAX,
            UC_X86_REG_EBX,
            UC_X86_REG_ECX,
            UC_X86_REG_EDX,
            UC_X86_REG_ESI,
            UC_X86_REG_EDI,
            UC_X86_REG_EBP,
        ]
        values = [1, 2, 3, 4, 5, 6, frame]
        for r, v in zip(regs, values):
            f.u.reg_write(r, v)
        f.u.reg_write(UC_X86_REG_ESP, f.stack)
        f.u.reg_write(UC_X86_REG_EFLAGS, 0x246)
        f.u.emu_start(f.exports["NativeActSkillBridge"], 0x974F61, count=3000000)
        self.assertEqual([f.u.reg_read(r) for r in regs], values)
        self.assertEqual(f.u.reg_read(UC_X86_REG_ESP), f.stack)
        self.assertEqual(f.u.reg_read(UC_X86_REG_EFLAGS), 0x246)
        self.assertTrue(f.occupied())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-client", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    PROFILE_CLIENT = args.profile_client.resolve()
    verify_profile_client(PROFILE_CLIENT)
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
