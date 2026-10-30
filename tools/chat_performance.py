"""Toggle runtime chat optimizations or summarize their per-process JSONL logs."""

import argparse
import configparser
import json
import os
from pathlib import Path

DEFAULTS = dict(
    stutter_enabled="1",
    cache_enabled="1",
    logging_enabled="1",
    sample_every="64",
    interval_ms="1000",
    reset_sequence="0",
)


def read_config(path):
    p = configparser.ConfigParser()
    p.read(path, encoding="utf-8-sig")
    values = dict(DEFAULTS)
    if p.has_section("ChatPerformance"):
        values.update(p["ChatPerformance"])
    return values


def records(path):
    result = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # A currently written trailing row is incomplete.
    return result


def write_config(root, values):
    assert set(values) == set(DEFAULTS), "Unexpected configuration fields"
    data = (
        "; Runtime controls; no chat text is logged.\r\n[ChatPerformance]\r\n"
        + "".join(k + "=" + str(v) + "\r\n" for k, v in values.items())
    )
    config = root / "ChatPerformance.ini"
    temp = config.with_name(config.name + ".pending." + str(os.getpid()))
    try:
        temp.write_bytes(data.encode("ascii"))
        os.replace(temp, config)
    finally:
        if temp.exists():
            temp.unlink()


def panel(root):
    import tkinter as tk
    from tkinter import ttk

    window = tk.Tk()
    window.title("Chat performance controls")
    window.geometry("580x420")
    window.resizable(False, False)
    box = ttk.Frame(window, padding=18)
    box.pack(fill="both", expand=True)
    ttk.Label(box, text="Chat performance", font=("Segoe UI", 15, "bold")).pack(
        anchor="w"
    )
    ttk.Label(box, text="Changes apply while the client is running.").pack(
        anchor="w", pady=(3, 12)
    )
    settings = read_config(root / "ChatPerformance.ini")
    variables = {}
    status = tk.StringVar(value="Waiting for a running client log.")
    notice = tk.StringVar(value="")

    def apply(reset=False):
        values = read_config(root / "ChatPerformance.ini")
        for name, var in variables.items():
            values[name] = "1" if var.get() else "0"
        if reset:
            values["reset_sequence"] = str(
                (int(values["reset_sequence"]) + 1) & 0xFFFFFFFF
            )
        try:
            write_config(root, values)
            notice.set("Requested settings saved.")
        except OSError as error:
            notice.set(
                "Could not save ChatPerformance.ini: " + str(error.strerror or error)
            )
            saved = read_config(root / "ChatPerformance.ini")
            for name, var in variables.items():
                var.set(saved[name] == "1")

    for name, label in [
        ("stutter_enabled", "Stutter fix"),
        ("cache_enabled", "Measurement cache"),
        ("logging_enabled", "Record runtime logs"),
    ]:
        var = tk.BooleanVar(value=settings[name] == "1")
        variables[name] = var
        ttk.Checkbutton(box, text=label, variable=var, command=apply).pack(
            anchor="w", pady=4
        )
    ttk.Button(
        box,
        text="Reset cache / start a new measurement phase",
        command=lambda: apply(True),
    ).pack(anchor="w", pady=(10, 12))
    ttk.Label(box, textvariable=notice, wraplength=490).pack(anchor="w", pady=(0, 6))
    ttk.Label(box, textvariable=status, wraplength=490).pack(anchor="w")
    detail = tk.StringVar(
        value="Receive a chat message after login to initialize diagnostics."
    )
    ttk.Label(box, textvariable=detail, wraplength=490).pack(anchor="w", pady=(8, 0))

    def refresh():
        paths = list(root.glob("ChatPerformance.*.log"))
        if paths:
            latest = max(paths, key=lambda p: p.stat().st_mtime)
            rows = records(latest)
            if rows:
                r = rows[-1]
                status.set(
                    "Last report from client "
                    + str(r["pid"])
                    + " | Stutter "
                    + ("ON" if r["stutter_enabled"] else "OFF")
                    + " | Cache "
                    + ("ON" if r["cache_enabled"] else "OFF")
                    + " | Logging "
                    + ("ON" if r["logging_enabled"] else "OFF")
                )
                summaries = summarize([latest])
                phase = next(
                    (x for x in reversed(summaries) if x["phase"] == r["phase"]), None
                )
                if phase:
                    hit = (
                        (str(phase["glyph_hit_percent"]) + "% glyph hit rate")
                        if phase["glyph_hit_percent"] is not None
                        else "no glyph requests yet"
                    )
                    timing = (
                        (
                            "Average sampled append: "
                            + str(phase["append_average_us"])
                            + " microseconds."
                        )
                        if phase["append_average_us"] is not None
                        else "Waiting for timing samples."
                    )
                    fragment = (
                        (str(phase["fragment_hit_percent"]) + "% fragment hit rate")
                        if phase["fragment_hit_percent"] is not None
                        else "no fragment requests yet"
                    )
                    native = (
                        phase["glyph_native_dispatches"]
                        + phase["fragment_native_calls"]
                    )
                    detail.set(
                        latest.name
                        + "\nThis phase: "
                        + str(phase["append"])
                        + " pre-wrap calls; "
                        + hit
                        + "; "
                        + fragment
                        + "; "
                        + str(native)
                        + " native width dispatches.\n"
                        + timing
                    )
                else:
                    detail.set(
                        latest.name + "\nWaiting for a completed measurement interval."
                    )
        window.after(1000, refresh)

    window.after(200, refresh)
    window.mainloop()


def summarize(paths):
    rows = []
    for path in paths:
        for r in records(path):
            if r.get("event") == "interval" and r.get("logging_enabled"):
                rows.append(r)
    groups = {}
    for r in rows:
        key = (
            r["pid"],
            r["session_filetime_hex"],
            r["phase"],
            r["stutter_enabled"],
            r["cache_enabled"],
        )
        g = groups.setdefault(
            key,
            dict(
                intervals=0,
                append=0,
                optimized=0,
                stock=0,
                glyph_requests=0,
                glyph_hits=0,
                glyph_misses=0,
                glyph_native_dispatches=0,
                fragment_requests=0,
                fragment_hits=0,
                fragment_native_calls=0,
                preprocess_samples=0,
                append_samples=0,
                preprocess_ticks=0,
                append_ticks=0,
                frequency=int(r["qpc_frequency_hex"], 16),
                errors=0,
            ),
        )
        g["intervals"] += 1
        for target, source in [
            ("append", "append_entered"),
            ("optimized", "temporary_copies_avoided"),
            ("stock", "stock_preprocess_entered"),
            ("glyph_requests", "glyph_requests"),
            ("glyph_hits", "glyph_hits"),
            ("glyph_misses", "glyph_misses"),
            ("glyph_native_dispatches", "glyph_native_dispatches"),
            ("fragment_requests", "fragment_requests"),
            ("fragment_hits", "fragment_hits"),
            ("fragment_native_calls", "fragment_native_calls"),
            ("preprocess_samples", "preprocess_samples"),
            ("append_samples", "append_samples"),
        ]:
            g[target] += r[source]
        g["preprocess_ticks"] += int(r["preprocess_ticks_hex"], 16)
        g["append_ticks"] += int(r["append_ticks_hex"], 16)
        g["errors"] += r["config_errors"] + r["log_errors"]
    output = []
    for (pid, session, phase, stutter, cache), g in groups.items():
        result = dict(
            pid=pid,
            session=session,
            phase=phase,
            stutter_enabled=stutter,
            cache_enabled=cache,
            **g,
        )
        result["fragment_hit_percent"] = (
            round(100 * g["fragment_hits"] / g["fragment_requests"], 2)
            if g["fragment_requests"]
            else None
        )
        result["glyph_hit_percent"] = (
            round(100 * g["glyph_hits"] / g["glyph_requests"], 2)
            if g["glyph_requests"]
            else None
        )
        for name in ["preprocess", "append"]:
            samples = g[name + "_samples"]
            result[name + "_average_us"] = (
                round(g[name + "_ticks"] * 1000000 / g["frequency"] / samples, 3)
                if samples and g["frequency"]
                else None
            )
        output.append(result)
    return output


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-root", type=Path, required=True)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("set")
    for name in ["stutter", "cache", "logging"]:
        p.add_argument("--" + name, choices=["on", "off"])
    p.add_argument(
        "--reset",
        action="store_true",
        help="Start a new phase and invalidate cached measurements",
    )
    p.add_argument("--sample-every", type=int)
    p.add_argument("--interval-ms", type=int)
    sub.add_parser("status")
    sub.add_parser("panel")
    p = sub.add_parser("summary")
    p.add_argument("logs", nargs="*", type=Path)
    a = ap.parse_args()
    root = a.game_root.resolve()
    config = root / "ChatPerformance.ini"
    if a.command == "panel":
        panel(root)
        return
    if a.command == "summary":
        paths = a.logs or sorted(root.glob("ChatPerformance.*.log"))
        print(json.dumps(summarize(paths), indent=2))
        return
    values = read_config(config)
    if a.command == "set":
        for name in ["stutter", "cache", "logging"]:
            if getattr(a, name) is not None:
                values[name + "_enabled"] = "1" if getattr(a, name) == "on" else "0"
        if a.reset:
            values["reset_sequence"] = str(
                (int(values["reset_sequence"]) + 1) & 0xFFFFFFFF
            )
        if a.sample_every is not None:
            assert 0 < a.sample_every <= 4096 and not a.sample_every & (
                a.sample_every - 1
            ), "Sampling must be a power of two in 1..4096"
            values["sample_every"] = str(a.sample_every)
        if a.interval_ms is not None:
            assert 250 <= a.interval_ms <= 5000
            values["interval_ms"] = str(a.interval_ms)
        write_config(root, values)
        print("Updated runtime controls; the client reads them within 250 ms.")
    paths = sorted(root.glob("ChatPerformance.*.log"), key=lambda p: p.stat().st_mtime)
    last = records(paths[-1])[-1:] if paths else []
    print(
        json.dumps(
            dict(
                config=str(config),
                requested=values,
                latest_log=str(paths[-1]) if paths else None,
                last_logged_state=last,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
