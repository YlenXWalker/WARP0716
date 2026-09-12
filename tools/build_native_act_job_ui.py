"""Build/check the standalone QJS payload from the maintained x86 source.

Use an x86 MSVC developer prompt or pass --compiler /path/to/x86/cl.exe.
A client EXE is needed only for --profile-client verification, not regeneration.
"""

from pathlib import Path
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import pefile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/native/native_act_job_ui.cpp"
TEMPLATE = ROOT / "tools/native/native_act_job_ui.qjs.in"
PROFILE = ROOT / "tools/native/native_act_job_ui_20250716.json"
TARGET = ROOT / "Scripts/Patches/NativeActJobPreviews.qjs"
OUT = ROOT / "Outputs/native-act-job-ui/native"
BRIDGE_EXPORTS = ("NativeActSkillBridge", "@NativeActEquipmentDraw@52")


def read_profile():
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    if profile["version"] != 1 or profile["buildDate"] != 20250716:
        raise ValueError("Unsupported native profile")
    return profile


def verify_profile_client(path):
    profile = read_profile()
    raw = Path(path).read_bytes()
    pe = pefile.PE(data=raw)
    if (
        pe.FILE_HEADER.Machine != profile["machine"]
        or pe.OPTIONAL_HEADER.ImageBase != profile["imageBase"]
    ):
        raise ValueError("Expected the profiled 32-bit Ragexe image")
    for row in profile["checks"]:
        expected = bytes.fromhex(row["hex"])
        if pe.get_data(row["va"] - profile["imageBase"], len(expected)) != expected:
            raise ValueError(f"{row['label']} differs at {row['va']:#x}")
    return hashlib.sha256(raw).hexdigest()


def build(compiler=None, profile_client=None, check=False):
    profile = read_profile()
    if profile_client:
        print("Verified native client profile: " + verify_profile_client(profile_client))
    compiler = Path(compiler or shutil.which("cl.exe") or shutil.which("cl") or "")
    if not compiler.is_file():
        raise ValueError(
            "Run from an x86 MSVC developer prompt or pass --compiler pointing to x86 cl.exe"
        )
    linker = compiler.with_name("link.exe")
    if not linker.is_file():
        raise ValueError("link.exe must be alongside cl.exe")
    OUT.mkdir(parents=True, exist_ok=True)
    obj, exe = OUT / "native-act.obj", OUT / "native-act.exe"
    commands = [
        [
            str(compiler),
            "/nologo",
            "/c",
            "/O2",
            "/Oi",
            "/GS-",
            "/GR-",
            "/Zl",
            "/W4",
            "/WX",
            "/EHs-c-",
            "/arch:SSE2",
            "/Fo" + str(obj),
            str(SOURCE),
        ],
        [
            str(linker),
            "/nologo",
            "/nodefaultlib",
            "/machine:x86",
            "/safeseh:no",
            "/entry:NativeActSkillBridge",
            "/subsystem:windows",
            "/base:0x10000000",
            "/fixed:no",
            "/dynamicbase",
            "/opt:ref",
            "/incremental:no",
            "/brepro",
            "/out:" + str(exe),
            str(obj),
        ],
    ]
    for command in commands:
        subprocess.run(command, check=True, cwd=OUT)
    pe = pefile.PE(str(exe))
    if pe.FILE_HEADER.Machine != 0x14C or getattr(pe, "DIRECTORY_ENTRY_IMPORT", None):
        raise ValueError("Payload must be x86 and contain no runtime imports")
    sections = [section for section in pe.sections if not section.Name.startswith(b".reloc")]
    start = min(section.VirtualAddress for section in sections)
    end = max(section.VirtualAddress + section.Misc_VirtualSize for section in sections)
    payload = bytearray(end - start)
    for section in sections:
        data = section.get_data()[: section.Misc_VirtualSize]
        offset = section.VirtualAddress - start
        payload[offset : offset + len(data)] = data
    exports = {
        symbol.name.decode(): symbol.address - start for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols
    }
    # Linker export/debug metadata is not needed by the injected code.
    for index in (0, 6):
        directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[index]
        if directory.Size:
            low = directory.VirtualAddress - start
            high = low + directory.Size
            if not 0 <= low <= high <= len(payload):
                raise ValueError("Unexpected linker directory bounds")
            payload[low:high] = bytes(high - low)
    relocations = []
    image_base = pe.OPTIONAL_HEADER.ImageBase + start
    for block in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for relocation in block.entries:
            if not relocation.type:
                continue
            offset = relocation.rva - start
            if relocation.type != 3 or not 0 <= offset <= len(payload) - 4:
                raise ValueError("Unsupported payload relocation")
            target = struct.unpack_from("<I", payload, offset)[0] - image_base
            if not 0 <= target < len(payload):
                raise ValueError("Payload relocation points outside the image")
            relocations.append(offset)
    for name in BRIDGE_EXPORTS:
        if name not in exports or not 0 <= exports[name] < len(payload):
            raise ValueError("Missing bridge entry: " + name)
    metadata = dict(
        imageBase=image_base,
        hex=payload.hex(),
        relocations=relocations,
        exports=exports,
        source_sha256=hashlib.sha256(SOURCE.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
    )
    embedded = dict(metadata, exports={name: exports[name] for name in BRIDGE_EXPORTS})
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in (("blob", embedded), ("checks", profile["checks"])):
        text += (
            "\nNativeActJobPreviews."
            + key
            + " = "
            + json.dumps(value, separators=(",", ":"))
            + ";\n"
        )
    generated = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    if check:
        if TARGET.read_bytes() != generated:
            raise ValueError("Generated QJS is stale; regenerate with this compiler")
    else:
        TARGET.write_bytes(generated)
    (OUT / "blob.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            dict(bytes=len(payload), relocations=len(relocations), exports=exports, check=check)
        )
    )
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    parser.add_argument("--profile-client", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        build(args.compiler, args.profile_client, args.check)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
