"""Build the finite female Assassin reference basis from accepted legacy poses.

ACT-file x/y are centers. Ragexe's loaded CActLayer x/y subtract ceil(SPR/2).
The reference packet must use those loaded edges and the native +1 endpoint;
canonical actor_target values alone cannot reconstruct the accepted renderer.

The dagger substitution assumes corresponding native solo ACT cells register
their grips to the same hand. It is not a manual per-image hilt measurement.
"""
from __future__ import annotations

import argparse
import configparser
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_formats.grf_reader import GrfFile
from dual_weapon_formats.rig_tables import parse_rig_bytes
from dual_weapon_formats.spr_reader import Spr

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "data/sprite/\uc778\uac04\uc871/\uc5b4\uc138\uc2e0/\uc5b4\uc138\uc2e0_\uc5ec_"
PAIR = "\ub2e8\uac80_\uac80"
TRAIL = PAIR + "_\uac80\uad11"
HEADER = ROOT / "CustomDLL/DualWeapon/native_basis.h"
POSE_SOURCE = ROOT / "Scripts/Patches/AllowDualCustomWeaponSprites.qjs"
GRIP_SOURCE = ROOT / "Inputs/DualWeaponAuthored/grips/female-assassin-views34-45.csv"
ATTACK_CHANNEL = (5, 5, 5, 6, 6, 5, 6, 6)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(client: Path):
    ini = configparser.ConfigParser()
    ini.read(client / "DATA.INI")
    paths = [client / value for _, value in
             sorted(ini["Data"].items(), key=lambda entry: int(entry[0]))]
    opened, resources = {}, {}

    def read(name, extension):
        key = PREFIX + name + extension
        loose = client / key
        data, source = None, loose
        if loose.is_file():
            data = loose.read_bytes()
        else:
            for source in paths:
                if source not in opened:
                    opened[source] = GrfFile(source)
                data = opened[source].read(key.lower())
                if data is not None:
                    break
        if data is None:
            raise FileNotFoundError(key)
        resources[key] = {"source": str(source), "sha256": sha(data)}
        return data

    try:
        acts = {name: parse_act(read(name, ".act"))
                for name in ("13412", "1238", PAIR, TRAIL)}
        sprites = {name: Spr(read(name, ".spr"))
                   for name in ("13412", "1238", PAIR, TRAIL)}
    finally:
        for grf in opened.values():
            grf.close()

    def cell(name, action, frame):
        frames = acts[name]["actions"][action].frames
        if not 0 <= frame < len(frames) or not frames[frame].layers:
            raise ValueError((name, action, frame, "missing exact source cell"))
        layer = frames[frame].layers[0]
        images = [im for im in sprites[name].images
                  if im.is_indexed == (layer.sprite_type == 0)]
        if not 0 <= layer.sprite_index < len(images):
            raise ValueError((name, action, frame, "missing exact source image"))
        image = images[layer.sprite_index]
        if layer.scale_x <= 0 or layer.scale_y <= 0:
            raise ValueError((name, action, frame, "unsupported negative/zero scale"))
        return {
            "x": layer.x - (image.width + 1) // 2,
            "y": layer.y - (image.height + 1) // 2,
            "rawX": layer.x, "rawY": layer.y,
            "width": image.width, "height": image.height,
            "sx": layer.scale_x, "sy": layer.scale_y,
            "angle": layer.rotation, "mirror": layer.mirror,
            "index": layer.sprite_index, "kind": layer.sprite_type,
        }

    source = POSE_SOURCE.read_text(encoding="utf-8")
    from dual_weapon_legacy_assets import payload
    rig_bytes = payload('DualWeaponAuthoredRig')
    rig = parse_rig_bytes(rig_bytes)
    poses = {(r["phase"], r["direction"], r["frame"], r["hand"]): r["transform"]
             for r in rig["records"] if r["family"] == r["gender"] == 0 and r["state"] == 9}
    assert len(poses) == 224
    grips = {}
    with GRIP_SOURCE.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            assert int(row["family"]) == int(row["gender"]) == 0
            assert all(int(row[k]) == 0 for k in ("dx", "dy", "mirror_xor", "rotation_delta"))
            key = tuple(int(row[k]) for k in ("view", "phase", "direction", "source_key"))
            assert key not in grips
            grips[key] = row

    def selected(view, phase, direction, pose):
        key = (pose.flags & 63) | (64 if pose.metadata & 32 else 0)
        row = grips.get((view, phase, direction, key))
        # Hidden sword terminal cells do not require a live grip lookup.
        if row is None and pose.metadata & 8:
            return pose.flags & 31
        if row is None:
            raise ValueError((view, phase, direction, key, "missing accepted grip"))
        assert int(row["preferred_frame"]) == pose.flags & 31
        assert int(row["selected_frame"]) == pose.flags & 31, "legacy ignores selected-frame remapping"
        return int(row["selected_frame"])

    basis = {}
    for phase, target_base, frame_count in ((0, 32, 6), (1, 88, 8)):
        for direction in range(8):
            for frame in range(frame_count):
                channel = ATTACK_CHANNEL[frame] if phase else 5
                guide = cell(TRAIL if channel == 6 else PAIR, target_base + direction, frame)
                guide["channel"] = channel
                hands = []
                for hand, view, name in ((0, 45, "13412"), (1, 34, "1238")):
                    pose = poses[(phase, direction, frame, hand)]
                    assert not pose.metadata & 64, "expect legacy delta encoding"
                    source_attack = int(bool(phase or pose.metadata & 32))
                    source_action = (80 if source_attack else 32) + direction
                    source_frame = selected(view, phase, direction, pose)
                    ref = cell(name, source_action, source_frame)
                    values = {
                        "dx": pose.dx, "dy": pose.dy,
                        "sourceX": ref["x"], "sourceY": ref["y"],
                        "rawX": ref["rawX"], "rawY": ref["rawY"],
                        "width": ref["width"], "height": ref["height"],
                        "sx": ref["sx"], "sy": ref["sy"],
                        "sourceAngle": ref["angle"], "angle": pose.rotation,
                        "sourceMirror": ref["mirror"], "mirrorXor": (pose.flags >> 6) & 1,
                        "sourceFrame": source_frame, "sourceLayer": 0,
                        "order": pose.metadata & 1, "hidden": int(bool(pose.metadata & 8)),
                        "sourceAttack": source_attack,
                        "finalMirror": ref["mirror"] ^ ((pose.flags >> 6) & 1),
                        "packetDelta": int(bool(pose.metadata & 16)),
                        "daggerDx": 0.0, "daggerDy": 0.0,
                        "daggerDxCos": 0.0, "daggerDySin": 0.0,
                        "daggerDxSin": 0.0, "daggerDyCos": 0.0,
                    }
                    if hand == 0 and not values["hidden"]:
                        dagger_frame = selected(34, phase, direction, pose)
                        assert dagger_frame == source_frame
                        dagger = cell("1238", source_action, dagger_frame)
                        assert dagger["sx"] == dagger["sy"] == ref["sx"] == ref["sy"] == 1
                        assert dagger["angle"] == ref["angle"] == 0
                        assert dagger["mirror"] == ref["mirror"]
                        # Loaded center correspondence includes odd-image half-pixel parity.
                        # Raw ACT centers already include source mirroring. Only the extra
                        # legacy mirror correction reflects this vector a second time.
                        dx = (dagger["x"] + dagger["width"] / 2) - (ref["x"] + ref["width"] / 2)
                        dy = (dagger["y"] + dagger["height"] / 2) - (ref["y"] + ref["height"] / 2)
                        if values["mirrorXor"]:
                            dx = -dx
                        angle = math.radians(pose.rotation)
                        values["daggerDxCos"] = dx * math.cos(angle)
                        values["daggerDySin"] = dy * math.sin(angle)
                        values["daggerDxSin"] = dx * math.sin(angle)
                        values["daggerDyCos"] = dy * math.cos(angle)
                        # Keep the unit-scale displacement for readable provenance only.
                        # Runtime must scale X/Y before rotation: its legacy pixel units
                        # differ because the native reference endpoints include +1 pixel.
                        values["daggerDx"] = values["daggerDxCos"] - values["daggerDySin"]
                        values["daggerDy"] = values["daggerDxSin"] + values["daggerDyCos"]
                    hands.append(values)
                basis[(phase, direction, frame)] = {"guide": guide, "hands": hands}

    def number(value):
        text = format(value, ".9g")
        if "." not in text and "e" not in text.lower():
            text += ".0"
        return text + "f"

    def initializer(values, fields, floats):
        return "{" + ", ".join(number(values[k]) if k in floats else str(values[k]) for k in fields) + "}"

    guide_fields = ("x", "y", "width", "height", "sx", "sy", "angle", "mirror", "channel")
    hand_fields = ("dx", "dy", "sourceX", "sourceY", "rawX", "rawY", "width", "height",
                   "sx", "sy", "sourceAngle", "angle", "sourceMirror", "mirrorXor", "sourceFrame",
                   "sourceLayer", "order", "hidden", "sourceAttack", "finalMirror", "packetDelta", "daggerDx", "daggerDy",
                   "daggerDxCos", "daggerDySin", "daggerDxSin", "daggerDyCos")
    floats = {"sx", "sy", "daggerDx", "daggerDy", "daggerDxCos", "daggerDySin", "daggerDxSin", "daggerDyCos"}
    out = [
        "/* Generated by tools/build_dual_weapon_native_basis.py; do not hand-edit.",
        " * Female Assassin reference views 45/34, pair28 held/attack only.",
        " * Legacy rig SHA-256: " + sha(rig_bytes),
        " * Native ACT coordinates are raw ACT coordinates minus ceil(image extent/2).",
        " * Native packet endpoints add one pixel after scaling, including mirrored X.",
        " * daggerDx/Y assume matched native solo ACT grip registration; not authored hilt proof.",
        " * Apply four dagger products as R(diag(unitX,unitY)*delta), not diag*R(delta).",
        " */",
        "#ifndef DUAL_WEAPON_NATIVE_BASIS_H", "#define DUAL_WEAPON_NATIVE_BASIS_H", "",
        "typedef struct {",
        "\tshort x,y; unsigned short width,height; float sx,sy;",
        "\tshort angle; unsigned char mirror,channel;",
        "} DWNativeGuide;",
        "typedef struct {",
        "\tshort dx,dy,sourceX,sourceY,rawX,rawY; unsigned short width,height;",
        "\tfloat sx,sy; short sourceAngle,angle;",
        "\tunsigned char sourceMirror,mirrorXor,sourceFrame,sourceLayer;",
        "\tunsigned char order,hidden,sourceAttack,finalMirror,packetDelta;",
        "\tfloat daggerDx,daggerDy;",
        "\tfloat daggerDxCos,daggerDySin,daggerDxSin,daggerDyCos;",
        "} DWNativeReferenceHand;",
        "typedef struct { DWNativeGuide guide; DWNativeReferenceHand hands[2]; } DWNativeBasis;",
        "", "/* [phase: held=0/attack=1][direction][target frame]; channel=0 means absent. */",
        "static const DWNativeBasis DW_NATIVE_BASIS[2][8][8] = {",
    ]
    for phase in range(2):
        out.append("\t{")
        for direction in range(8):
            out.append(f"\t\t{{ /* phase {phase}, direction {direction} */")
            for frame in range(8):
                record = basis.get((phase, direction, frame))
                if record is None:
                    guide = initializer(dict.fromkeys(guide_fields, 0), guide_fields, floats)
                    hand = initializer(dict.fromkeys(hand_fields, 0), hand_fields, floats)
                    out.append(f"\t\t\t{{{guide}, {{{hand}, {hand}}}}},")
                else:
                    guide = initializer(record["guide"], guide_fields, floats)
                    hands = [initializer(h, hand_fields, floats) for h in record["hands"]]
                    out.append(f"\t\t\t{{{guide}, {{{hands[0]}, {hands[1]}}}}},")
            out.append("\t\t},")
        out.append("\t},")
    out.extend(["};", "", "#endif", ""])
    header = "\n".join(out)
    report = {
        "schema": "dual_weapon_native_basis/v1", "legacy_rig_sha256": sha(rig_bytes),
        "grip_sha256": sha(GRIP_SOURCE.read_bytes()), "header_sha256": sha(header.encode("utf-8")),
        "cells": len(basis), "reference_hands": len(basis) * 2,
        "visible_reference_hands": sum(not h["hidden"] for b in basis.values() for h in b["hands"]),
        "resources": resources, "live_acceptance": False,
        "dagger_substitution_assumption": "matching native solo ACT cells register both original grips to the same hand; no manual hilt landmark acceptance",
        "records": [{"phase": k[0], "direction": k[1], "frame": k[2], **v} for k, v in basis.items()],
    }
    return header, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HEADER)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    header, report = build(args.client)
    if args.check:
        if args.output.read_text(encoding="utf-8") != header:
            raise SystemExit("native basis header is stale")
    else:
        args.output.write_text(header, encoding="utf-8", newline="\n")
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("cells", "reference_hands", "visible_reference_hands", "header_sha256")}))
