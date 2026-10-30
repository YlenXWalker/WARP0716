"""Run the production x86 telemetry/cache runtimes using real Windows APIs."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "Outputs/chat-performance/native-host"
    out.mkdir(parents=True, exist_ok=True)
    vswhere = (
        Path(os.environ["ProgramFiles(x86)"])
        / "Microsoft Visual Studio/Installer/vswhere.exe"
    )
    vs = Path(
        subprocess.check_output(
            [
                str(vswhere),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            text=True,
        ).strip()
    )
    command = out / "build.cmd"
    command.write_text(
        f'@echo off\ncall "{vs / "Common7/Tools/VsDevCmd.bat"}" -arch=x86 -host_arch=x64 >nul\nif errorlevel 1 exit /b 1\ncd /d "{out}"\ncl /nologo /EHsc /O2 /MT /std:c++17 "{ROOT / "tools/native/chat_diagnostics_host.cpp"}" /Fe:test.exe /link /DYNAMICBASE /FIXED:NO /IMPLIB:test-{os.getpid()}.lib\nexit /b %errorlevel%\n'
    )
    r = subprocess.run(
        ["cmd.exe", "/d", "/c", str(command)], capture_output=True, timeout=180
    )
    (out / "build.log").write_bytes(r.stdout + r.stderr)
    assert not r.returncode, "See " + str(out / "build.log")
    r = subprocess.run(
        [str(out / "test.exe")], cwd=out, capture_output=True, timeout=40
    )
    (out / "run.log").write_bytes(r.stdout + r.stderr)
    assert not r.returncode, "See " + str(out / "run.log")
    lines = r.stdout.decode().splitlines()
    name = next(s[4:] for s in lines if s.startswith("LOG "))
    records = [json.loads(x) for x in (out / name).read_text().splitlines()]
    steady = [x for x in records if x["event"] == "interval"]
    assert {(x["stutter_enabled"], x["cache_enabled"]) for x in steady} == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    }
    assert any(x["glyph_hits"] > 0 and x["cache_enabled"] for x in steady)
    assert all(not x["glyph_hits"] for x in steady if not x["cache_enabled"])
    assert any(
        x["append_samples"] > 0 and int(x["append_ticks_hex"], 16) > 0 for x in steady
    )
    assert all(x["log_errors"] == 0 for x in records)
    report = dict(
        passed=True,
        real_win32_worker_and_file_io=True,
        four_runtime_states_verified=True,
        counter_free_logging_off=True,
        log=str(out / name),
        rows=len(records),
        binary_sha256=hashlib.sha256((out / "test.exe").read_bytes()).hexdigest(),
        live_gameplay_accepted=False,
    )
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(r.stdout.decode())


if __name__ == "__main__":
    main()
