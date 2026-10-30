"""Execute native 2025-07-16 chat matrices and four runtime switch states.

Requires pefile, capstone and unicorn. Font/CRT/OS boundaries are explicit
in chat_native_test_support; no private UI patch or image pack is required.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import chat_cache_cases
import chat_stutter_cases
from verify_chat_performance import verify

EVENTS = "append_entered copies_avoided stock direct wrap null finished recovered dropped glyph_requests glyph_hits glyph_misses glyph_native glyph_disabled glyph_fallback glyph_busy fragment_requests fragment_hits fragment_misses fragment_native fragment_disabled fragment_fallback fragment_busy invalidations preprocess_samples append_samples config_errors log_errors".split()


def toggles(exe):
    from chat_stutter_cases import StutterMachine

    corpus = [
        b"",
        b"a",
        b"combat event 12345",
        b"W" * 65,
        b"Alice: " + b"wide words " * 30,
        b"<ITEML>one</ITEML> and <ITEML>two</ITEML>",
        b"Alice: ^i[501]Red Potion",
        b"one\r\ntwo",
    ]
    baseline = None
    results = []
    for stutter, cache in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        m = StutterMachine(exe)
        d = m.chat_diagnostics
        m.w(d["link"], 0x10000 | 4 | stutter | (cache << 1))
        m.w(d["link"] + 4, m.r(d["link"] + 4) + 1)
        values = []
        for width in [24, 80, 240]:
            for text in corpus:
                values.append(m.message(text, width))
        if baseline is None:
            baseline = values
        else:
            assert values == baseline, "Runtime controls changed native rows/routes"
        before = m.native_calls
        copies = m.temp_constructs
        for _ in range(100):
            m.message(b"repeat combat message", 240)
        native = m.native_calls - before
        temporary = m.temp_constructs - copies
        assert temporary == (0 if stutter else 100)
        counters = {name: m.r(d["link"] + 12 + 4 * i) for i, name in enumerate(EVENTS)}
        assert (
            counters["copies_avoided"] > 0
            if stutter
            else counters["copies_avoided"] == 0
        )
        assert counters["glyph_hits"] > 0 if cache else counters["glyph_hits"] == 0
        if not cache:
            assert counters["glyph_disabled"] > 0
        # A live flag update must change behavior without modifying a hook.
        hook = bytes(m.u.mem_read(0x83D452, 5))
        m.w(d["link"], 0x20004)
        count = m.temp_constructs
        m.message(b"switch back to native", 80)
        assert (
            m.temp_constructs == count + 1 and bytes(m.u.mem_read(0x83D452, 5)) == hook
        )
        m.w(d["link"], 3)  # Both optimizations enabled, counters disabled.
        before = bytes(m.u.mem_read(d["link"] + 12, len(EVENTS) * 4))
        m.message(b"logging off", 80)
        assert bytes(m.u.mem_read(d["link"] + 12, len(EVENTS) * 4)) == before
        results.append(
            dict(
                stutter=stutter,
                cache=cache,
                wrapping_vectors=len(values),
                native_measurements_for_100_messages=native,
                temporary_strings_for_100_messages=temporary,
                counters=counters,
            )
        )
    assert (
        results[2]["native_measurements_for_100_messages"]
        < results[0]["native_measurements_for_100_messages"]
    )
    assert (
        results[3]["native_measurements_for_100_messages"]
        < results[1]["native_measurements_for_100_messages"]
    )
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("exe", type=Path)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    assert (
        hashlib.sha256(a.source.read_bytes()).hexdigest()
        == "ead7c0a316bc6c27705a5a6876daf5093abec31677f3c1af7525c1709b201bff"
    )
    verify(a.exe, a.source)
    chat_cache_cases.SOURCE = chat_stutter_cases.SOURCE = a.source
    for module, name in [(chat_stutter_cases, "stutter"), (chat_cache_cases, "cache")]:
        sys.argv = [name, str(a.exe), "--report", str(a.output / (name + ".json"))]
        module.main()
    result = dict(
        passed=True,
        states=toggles(a.exe),
        source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),
        exe_sha256=hashlib.sha256(a.exe.read_bytes()).hexdigest(),
    )
    (a.output / "runtime-states.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "PASS all four runtime states, 96 wrapping vectors, logging-off and unchanged native rows"
    )


if __name__ == "__main__":
    main()
