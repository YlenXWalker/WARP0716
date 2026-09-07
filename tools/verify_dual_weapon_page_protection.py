"""Reproduce the reported NX crash and test the replacement in mapped PE images.

Runs the installed equipment entry, its owner and actual prologue trampolines.
Native equipment/resource bodies are ABI stubs, not a game/GPU simulation.
VirtualProtect follows Windows page rounding and removes EXECUTE for PAGE_RW.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from capstone.x86_const import X86_OP_IMM
from unicorn import (Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE,
                     UC_PROT_READ, UC_PROT_WRITE, UC_PROT_EXEC, UC_ERR_FETCH_PROT)
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
                              UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI,
                              UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP)

ROOT = Path(__file__).resolve().parents[1]
EQUIP = 0xD403A0
CONTINUE = EQUIP + 5
DRAW = 0xC4A0D0
ACTOR = 0x6BD279D0  # Receiver from the user's crash report.
STACK = 0x70010000
VP, STOP = 0x70020000, 0x70020100
VIEW, PAIR, ADD, RELEASE = 0xD8A1D0, 0xD39130, 0xA8E800, 0xA8F910
CLASS, SUFFIX = 0xD5DDB0, 0xD60DE0


def run(path: Path, expect_crash: bool) -> dict:
    blob = path.read_bytes()
    pe = pefile.PE(data=blob, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase

    def read(va, size):
        off = pe.get_offset_from_rva(va - base)
        return blob[off:off + size]

    def branch(va):
        data = read(va, 5)
        assert data[0] in (0xE8, 0xE9)
        return va + 5 + struct.unpack_from('<i', data, 1)[0]

    owner = branch(branch(EQUIP))
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    cs.detail = True
    # Only the stable owner prologue is needed to recover the first stock call
    # and VirtualProtect import. The generalized owner has appended helpers;
    # never treat an older owner's total byte count as its current boundary.
    owner_ins = list(cs.disasm(read(owner, 0x200), owner))
    assert read(owner, 3) == bytes.fromhex('55 8B EC')
    first_call = next(i for i in owner_ins if i.mnemonic == 'call')
    assert first_call.operands[0].type == X86_OP_IMM
    trampoline = first_call.operands[0].imm
    first_return = first_call.address + first_call.size
    iat = next(i.operands[0].mem.disp for i in owner_ins
               if i.mnemonic == 'call' and i.operands[0].type != X86_OP_IMM)
    assert first_call.address < next(i.address for i in owner_ins
                                    if i.mnemonic == 'call' and i.operands[0].type != X86_OP_IMM)
    draw_wrapper = branch(DRAW)
    pushes = [i.operands[0].imm for i in cs.disasm(read(draw_wrapper, 100), draw_wrapper)
              if i.mnemonic == 'push' and i.operands[0].type == X86_OP_IMM]
    ctx = struct.unpack('<21I', read(pushes[1], 84))
    state = ctx[0] - 0x1000
    assert read(trampoline, 5) == bytes.fromhex('55 8B EC 6A FF')
    assert branch(trampoline + 5) == CONTINUE

    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    uc.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage + 0xFFF) & ~0xFFF, UC_PROT_READ)
    uc.mem_write(base, blob[:pe.OPTIONAL_HEADER.SizeOfHeaders])
    for sec in pe.sections:
        address = base + sec.VirtualAddress
        uc.mem_write(address, sec.get_data())
        flags = sec.Characteristics
        perm = ((UC_PROT_READ if flags & 0x40000000 else 0) |
                (UC_PROT_WRITE if flags & 0x80000000 else 0) |
                (UC_PROT_EXEC if flags & 0x20000000 else 0))
        end = (address + max(sec.Misc_VirtualSize, sec.SizeOfRawData) + 0xFFF) & ~0xFFF
        uc.mem_protect(address & ~0xFFF, end - (address & ~0xFFF), perm)
    uc.mem_map(ACTOR & ~0xFFF, 0x2000, UC_PROT_READ | UC_PROT_WRITE)
    uc.mem_map(STACK - 0x10000, 0x10000, UC_PROT_READ | UC_PROT_WRITE)
    uc.mem_map(VP, 0x1000, UC_PROT_READ | UC_PROT_EXEC)
    uc.mem_map(0x71000000, 0x10000, UC_PROT_READ | UC_PROT_WRITE)
    uc.mem_write(VP, b'\xC2\x10\x00')
    uc.mem_write(STOP, b'\xCC')

    def w(p, *values):
        uc.mem_write(p, struct.pack('<' + 'I' * len(values), *values))

    def r(p):
        return struct.unpack('<I', uc.mem_read(p, 4))[0]

    def returned(value, argc):
        esp = uc.reg_read(UC_X86_REG_ESP)
        uc.reg_write(UC_X86_REG_EIP, r(esp))
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + argc * 4)
        uc.reg_write(UC_X86_REG_EAX, value)
        uc.reg_write(UC_X86_REG_ECX, 0xDEAD0001)
        uc.reg_write(UC_X86_REG_EDX, 0xDEAD0002)

    w(iat, VP)
    assert r(state) == 0, 'test must exercise cold initialization'
    protections, native_calls, scenarios = [], [], []
    stock_events = []
    class_calls, suffix_calls = [], []
    valid_resources = set()
    suffixes = {1238: '_제니나이프'.encode('cp949'),
                13412: '_트윈엣지_B'.encode('cp949')}
    suffix_addresses = {1238: 0x71008000, 13412: 0x71008200}
    for item, pointer in suffix_addresses.items():
        uc.mem_write(pointer, suffixes[item] + b'\0')
    resource_prefix = 'sprite\\인간족\\어세신\\어세신_여'.encode('cp949')

    def hook(_, address, size, data):
        esp = uc.reg_read(UC_X86_REG_ESP)
        if address == VP:
            ptr, length, mode, scratch = (r(esp + x) for x in (4, 8, 12, 16))
            assert mode == 0x04 and length == 0x5000 and ptr == state
            begin, end = ptr & ~0xFFF, (ptr + length + 0xFFF) & ~0xFFF
            protections.append({'address': hex(ptr), 'length': hex(length), 'mode': hex(mode),
                                'rounded_begin': hex(begin), 'rounded_end_exclusive': hex(end)})
            w(scratch, 0x40)
            uc.mem_protect(begin, end - begin, UC_PROT_READ | UC_PROT_WRITE)
            returned(1, 4)
        elif address == CONTINUE:
            # The real trampoline has executed PUSH EBP / MOV EBP,ESP / PUSH -1.
            frame = uc.reg_read(UC_X86_REG_EBP)
            assert esp == frame - 4 and r(esp) == 0xFFFFFFFF
            assert uc.reg_read(UC_X86_REG_ECX) == ACTOR
            main, off = r(frame + 8), r(frame + 12)
            native_calls.append([main, off])
            stock_events.append([main, off])
            w(ACTOR + 0x440, main, off)
            spr, act = 0x71000000, 0x71000040
            w(ACTOR + 0x4AC, spr, spr + 28)
            w(ACTOR + 0x4B8, act, act + 28)
            # Distinct, sufficiently sized CResource fixtures. Names start at
            # decimal 20 (0x14), as in live captures; the real emitted suffix
            # guard must execute against these bytes before publishing a row.
            # Full ACT/SPR content is exercised by the compositor verifier.
            kind = 0 if main and off else 1 if main == 1238 else 2 if main == 13412 else 3
            resource = 0x71001000 + kind * 0x1000
            pointers = [resource + i * 0x200 for i in range(4)]
            name_suffix = suffixes[main] if main and not off else b'_native_stock'
            for pointer, extension in zip(pointers, [b'.spr', b'.act', b'.spr', b'.act']):
                filename = resource_prefix + name_suffix + extension + b'\0'
                assert len(filename) < 240
                uc.mem_write(pointer + 20, filename)
                valid_resources.add(pointer)
            w(spr + 20, pointers[0], pointers[2])
            w(act + 20, pointers[1], pointers[3])
            uc.reg_write(UC_X86_REG_EBP, r(frame))
            uc.reg_write(UC_X86_REG_ESP, frame + 4)
            returned(0, 2)
        elif address == VIEW:
            returned({1238: 34, 13412: 45}.get(r(esp + 4), 0), 1)
        elif address == PAIR:
            a, b = r(esp + 4), r(esp + 8)
            returned((25 if a == b else 28) if a and b else (1 if a == 1238 else 2), 2)
        elif address == CLASS:
            view = r(esp + 4)
            class_calls.append(view)
            returned({34: 1, 45: 2}.get(view, view), 1)
        elif address == SUFFIX:
            # Native D60DE0 ignores incoming ECX; its item ID is the stack argument.
            item = r(esp + 4)
            suffix_calls.append(item)
            returned(suffix_addresses.get(item, 0), 1)
        elif address in (ADD, RELEASE):
            assert uc.reg_read(UC_X86_REG_ECX) in valid_resources
            returned(0, 0)

    uc.hook_add(UC_HOOK_CODE, hook)
    failure = None
    vectors = [(0, 0), (0, 0), (1238, 0), (0, 1238), (1238, 1238),
               (13412, 1238), (1238, 13412), (0, 0)]
    for main, off in vectors:
        esp = STACK - 0x100
        w(esp, STOP, main, off)
        saved = [UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP]
        for n, reg in enumerate(saved):
            uc.reg_write(reg, 0x99000000 + n * 16)
        uc.reg_write(UC_X86_REG_ECX, ACTOR)
        uc.reg_write(UC_X86_REG_ESP, esp)
        stock_events.clear()
        class_calls.clear()
        suffix_calls.clear()
        try:
            uc.emu_start(EQUIP, STOP, count=100000)
        except UcError as error:
            failure = {'errno': error.errno, 'reason': str(error),
                       'eip': hex(uc.reg_read(UC_X86_REG_EIP)),
                       'return_address': hex(r(uc.reg_read(UC_X86_REG_ESP))),
                       'invocation': len(scenarios) + 1}
            assert expect_crash and error.errno == UC_ERR_FETCH_PROT, failure
            assert uc.reg_read(UC_X86_REG_EIP) == trampoline == 0x1E5F000, failure
            assert r(uc.reg_read(UC_X86_REG_ESP)) == first_return == 0x1E664A1, failure
            assert len(scenarios) == 1 and stock_events == [], failure
            break
        assert uc.reg_read(UC_X86_REG_EIP) == STOP
        assert uc.reg_read(UC_X86_REG_ESP) == esp + 12
        for n, reg in enumerate(saved):
            assert uc.reg_read(reg) == 0x99000000 + n * 16
        assert (r(ACTOR + 0x440), r(ACTOR + 0x444)) == (main, off)
        expected = [[main, off]]
        if off:
            expected += [[off, 0]]
            if main:
                expected += [[main, 0]]
            expected += [[main, off]]
        assert stock_events == expected, (stock_events, expected)
        registry_row = ctx[0] + ((ACTOR >> 4) & 255) * 60
        if not expect_crash:
            if off:
                assert r(registry_row) == ACTOR, 'resource guard or registry publication was bypassed/failed'
                assert (r(registry_row + 48), r(registry_row + 52)) == (
                    0 if not main else 1 if main == 1238 else 2, 1 if off == 1238 else 2)
                assert class_calls == [34 if off == 1238 else 45] + ([34 if main == 1238 else 45] if main else [])
                assert suffix_calls == [off] + ([main] if main else [])
            else:
                assert r(registry_row) == 0
                assert not class_calls and not suffix_calls
        scenarios.append({'main': main, 'off': off, 'stock_calls': list(stock_events),
                          'view_class_calls': list(class_calls), 'item_suffix_calls': list(suffix_calls),
                          'registry_owner': hex(r(registry_row))})
    assert bool(failure) == expect_crash
    assert len(protections) == 1 and r(state) == 1
    if not expect_crash:
        assert state % 0x1000 == 0
        begin, end = state, state + 0x5000
        # Actual pages retain EXECUTE for both prologue trampolines and owners.
        compositor_entry = next(i.operands[0].imm for i in cs.disasm(read(draw_wrapper, 160), draw_wrapper)
                                if i.mnemonic == 'call' and i.operands[0].type == X86_OP_IMM)
        for va in [trampoline, trampoline + 16, owner, draw_wrapper, compositor_entry]:
            region = next((a, b, p) for a, b, p in uc.mem_regions() if a <= va <= b)
            assert region[2] & UC_PROT_EXEC and not begin <= va < end
        assert all(not p & UC_PROT_EXEC for a, b, p in uc.mem_regions()
                   if a < end and b >= begin)
    return {'path': str(path), 'sha256': hashlib.sha256(blob).hexdigest(),
            'equipment_owner': hex(owner), 'trampoline': hex(trampoline),
            'first_native_return': hex(first_return), 'state': hex(state),
            'virtual_protect': protections, 'completed_scenarios': scenarios,
            'native_calls': len(native_calls), 'expected_crash': expect_crash,
            'failure': failure, 'passed': True,
            'scope': 'Real PE hook/owner/trampoline and resource-name guard; Windows protection model; native equipment/view/class/suffix/resource ABI stubs; no live GPU acceptance'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crashed', type=Path, help='Optional historical NX-crash fixture')
    parser.add_argument('--fixed', type=Path)
    parser.add_argument('--report', type=Path, default=ROOT / 'docs/evidence/dual-weapon-cleanup-protection-20260907.json')
    args = parser.parse_args()
    if not args.crashed and not args.fixed:
        parser.error('provide --fixed and/or --crashed')
    report = {'crashed': run(args.crashed, True)} if args.crashed else {}
    if args.fixed:
        report['fixed'] = run(args.fixed, False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
