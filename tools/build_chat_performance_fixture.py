"""Build six isolated WARP cases without deploying a client or changing profiles."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml
from verify_chat_performance import ROOT, SOURCE_SHA256, verify


def build(source, output):
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
    table = ROOT / "Tables/Patch.yml"
    settings = ROOT / "Settings.yml"
    skipped = ROOT / "SkippedPatches.log"
    saved = {
        p: p.read_bytes() if p.exists() else None for p in [table, settings, skipped]
    }
    cases = {
        "baseline": [],
        "stutter": ["ChatStutterFix"],
        "cache": ["ChatMeasurementCache"],
        "both": ["ChatMeasurementCache", "ChatStutterFix"],
        "reverse-invocation": ["ChatStutterFix", "ChatMeasurementCache"],
    }
    recommended = yaml.safe_load(
        (ROOT / "profiles/community_recommended.yml").read_text(encoding="utf-8-sig")
    )
    cases["recommended"] = recommended["patches"] + cases["both"]
    results = {}
    try:
        for name, patches in cases.items():
            arm = output / name
            arm.mkdir(parents=True, exist_ok=False)
            target = arm / "Ragnarok.exe"
            recipe = dict(recommended) if name == "recommended" else {"inputs": {}}
            recipe.update(
                {"from": source.as_posix(), "to": target.as_posix(), "patches": patches}
            )
            profile = arm / "profile.yml"
            profile.write_text(yaml.safe_dump(recipe, sort_keys=False))
            if name == "reverse-invocation":
                table.write_bytes(
                    saved[table]
                    .replace(
                        b"365 : ChatMeasurementCache", b"366 : ChatMeasurementCache"
                    )
                    .replace(b"366 : ChatStutterFix", b"365 : ChatStutterFix")
                )
            else:
                table.write_bytes(saved[table])
            if skipped.exists():
                skipped.unlink()
            r = subprocess.run(
                [str(ROOT / "win32/WARP_console.exe"), "-using", str(profile)],
                cwd=ROOT,
                capture_output=True,
                timeout=180,
            )
            log = r.stdout + r.stderr
            (arm / "build.log").write_bytes(log)
            assert (
                r.returncode == 0 and b"-E-" not in log and b"Patch Error" not in log
            ), name
            assert (
                not skipped.exists()
                or not skipped.read_text(encoding="utf-8-sig").strip()
            ), name
            assert not (arm / "ChatPerformance.ini").exists(), (
                "Unexpected runtime configuration"
            )
            stutter, cache = (
                "ChatStutterFix" in patches,
                "ChatMeasurementCache" in patches,
            )
            verify(target, source, stutter=stutter, cache=cache)
            results[name] = dict(
                exe=target.relative_to(output).as_posix(),
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                patches=patches,
            )
            print("PASS WARP", name, flush=True)
    finally:
        for p, contents in saved.items():
            if contents is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_bytes(contents)
    (output / "builds.json").write_text(json.dumps(results, indent=2) + "\n")
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    build(a.source.resolve(), a.output.resolve())


if __name__ == "__main__":
    main()
