"""Verify standalone exports using upstream WARP, without any game assets."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
import pefile
from build_native_act_job_ui import ROOT, read_profile, verify_profile_client

PATCH = ROOT / "Scripts/Patches/NativeActJobPreviews.qjs"
SITES = ((0x8B3557, 2), (0x974E9E, 6), (0x7ACEF9, 5))


def embedded_payload():
    text = PATCH.read_text(encoding="utf-8")
    return json.loads(re.search(r"NativeActJobPreviews.blob = (\{.*?\});", text).group(1))


def make_fixture(output):
    fixture = output / "fixture"
    fixture.mkdir()
    # Intentionally omit tools/native and all generated developer outputs.
    for name in (
        "win32",
        "Scripts",
        "Tables",
        "Patches",
        "Inputs",
        "Languages",
        "Styles",
        "Images",
    ):
        shutil.copytree(ROOT / name, fixture / name)
    shutil.copy2(ROOT / "Patches.yml", fixture / "Patches.yml")
    return fixture


def export(fixture, folder, source, patches, expected_error=None):
    folder.mkdir()
    target, profile = folder / "client.exe", folder / "profile.yml"
    inputs = {"$skillTreeRepaintFloor": {"data": "363030206d7300", "display": "600 ms", "type": 10}}
    profile.write_text(
        "from: "
        + json.dumps(str(source.resolve()))
        + "\nto: "
        + json.dumps(str(target))
        + "\ninputs: "
        + json.dumps(inputs)
        + "\npatches:\n"
        + "".join("    - " + patch + "\n" for patch in patches),
        encoding="utf-8",
    )
    run = subprocess.run(
        [str(fixture / "win32/WARP_console.exe"), "-using", str(profile)],
        cwd=fixture,
        capture_output=True,
        timeout=180,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log = run.stdout + run.stderr
    (folder / "warp.log").write_bytes(log)
    if expected_error:
        if expected_error.encode() not in log:
            raise AssertionError(log.decode(errors="replace")[-5000:])
        if target.exists():
            before, after = pefile.PE(str(source)), pefile.PE(str(target))
            for address, size in SITES:
                assert before.get_data(address - 0x400000, size) == after.get_data(
                    address - 0x400000, size
                )
    elif run.returncode or b"-E-" in log or not target.exists():
        raise AssertionError(log.decode(errors="replace")[-5000:])
    return target


def verify_target(source, target, check_all_code=True):
    before, after = pefile.PE(str(source)), pefile.PE(str(target))
    blob = embedded_payload()
    assert after.get_data(0x8B3557 - 0x400000, 7).hex() == "6a01e8c292efff"
    jump = after.get_data(0x974E9E - 0x400000, 6)
    assert jump[0] == 0xE9 and jump[5] == 0x90
    entry = 0x974EA3 + struct.unpack_from("<i", jump, 1)[0]
    payload = entry - blob["exports"]["NativeActSkillBridge"]
    expected = bytearray.fromhex(blob["hex"])
    for offset in blob["relocations"]:
        value = (
            struct.unpack_from("<I", expected, offset)[0] + payload - blob["imageBase"]
        ) & 0xFFFFFFFF
        struct.pack_into("<I", expected, offset, value)
    assert bytes(expected) == after.get_data(payload - 0x400000, len(expected))
    call = after.get_data(0x7ACEF9 - 0x400000, 5)
    assert call[0] == 0xE8
    assert (
        0x7ACEFE + struct.unpack_from("<i", call, 1)[0]
        == payload + blob["exports"]["@NativeActEquipmentDraw@52"]
    )
    # Resource selection remains completely native, including SPR/ACT names.
    for row in read_profile()["checks"]:
        if row["label"] == "Native resource loader":
            assert after.get_data(row["va"] - 0x400000, 5).hex() == row["hex"]
    changed = []
    if check_all_code:
        allowed = {address + i for address, size in SITES for i in range(size)}
        for section in before.sections:
            if not section.Characteristics & 0x20000000:
                continue
            original = section.get_data()
            patched = after.get_data(section.VirtualAddress, len(original))
            for offset, (old, new) in enumerate(zip(original, patched)):
                if old != new:
                    address = 0x400000 + section.VirtualAddress + offset
                    assert address in allowed or payload <= address < payload + len(expected), hex(
                        address
                    )
                    changed.append(address)
        old = (
            before.get_data(payload - 0x400000, len(expected))
            if before.get_section_by_rva(payload - 0x400000)
            else b""
        )
        assert not any(old), "Allocation overlaps original bytes"
    return dict(
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        payload=hex(payload),
        original_code_changes=[hex(address) for address in changed],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-client", type=Path, required=True)
    args = parser.parse_args()
    client = args.profile_client.resolve()
    original_hash = verify_profile_client(client)
    output = Path(tempfile.mkdtemp(prefix="native-act-check-", dir=ROOT / "Outputs"))
    fixture = make_fixture(output)
    results = []
    for name, patches in [
        ("standalone", ["NativeActJobPreviews"]),
        ("repaint-first", ["ReduceExpensiveUIRender", "NativeActJobPreviews"]),
        ("preview-first", ["NativeActJobPreviews", "ReduceExpensiveUIRender"]),
    ]:
        target = export(fixture, output / name, client, patches)
        result = verify_target(client, target, name == "standalone")
        if name != "standalone":
            pe = pefile.PE(str(target))
            assert (
                pe.get_dword_at_rva(0x103F6B0 - 0x400000) != 0x977E80
            ), "Repaint gate was not installed"
        results.append(dict(case=name, **result))
        print("PASS " + name, flush=True)
    target = export(
        fixture, output / "reapply", output / "standalone/client.exe", ["NativeActJobPreviews"]
    )
    results.append(dict(case="safe-reapply", **verify_target(client, target)))
    print("PASS safe-reapply", flush=True)
    for name, address in [("changed-renderer", 0xA1B851), ("changed-resource-loader", 0x974B56)]:
        raw = bytearray(client.read_bytes())
        pe = pefile.PE(data=bytes(raw))
        raw[pe.get_offset_from_rva(address - 0x400000)] ^= 1
        bad = output / (name + ".exe")
        bad.write_bytes(raw)
        export(fixture, output / name, bad, ["NativeActJobPreviews"], "differs at")
        results.append(dict(case=name, rejected_before_hook_writes=True))
        print("PASS " + name, flush=True)
    patch_file = fixture / "Scripts/Patches/NativeActJobPreviews.qjs"
    saved = patch_file.read_bytes()
    try:
        patch_file.write_bytes(
            saved + b"\r\nNativeActJobPreviews.blob.relocations = [0x7fffffff];\r\n"
        )
        export(
            fixture,
            output / "bad-relocation",
            client,
            ["NativeActJobPreviews"],
            "invalid payload relocation",
        )
    finally:
        patch_file.write_bytes(saved)
    results.append(dict(case="bad-relocation", rejected_before_hook_writes=True))
    print("PASS bad-relocation", flush=True)
    assert hashlib.sha256(client.read_bytes()).hexdigest() == original_hash
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("PASS " + str(output), flush=True)


if __name__ == "__main__":
    main()
