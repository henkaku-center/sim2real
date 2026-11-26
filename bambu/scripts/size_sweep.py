"""Size sweep: smallest sphere radius that still passes the static and MuJoCo checks.

    uv run python -I bambu/scripts/size_sweep.py     -> bambu/build/size_sweep.json
    uv run python -I bambu/scripts/size_sweep.py --params bambu/params-s3wide.json --R 90 94 98 --e 16
    uv run python -I bambu/scripts/size_sweep.py --params bambu/params-v3.json --R 96 100 --static-only
"""
import copy
import itertools
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import design  # noqa: E402
import sim_check  # noqa: E402
from analyze import BELLY_TILT_DEG, load_shell  # noqa: E402
from sesame_model import BAMBU, SesameModel, load_params  # noqa: E402
from stability import equilibria  # noqa: E402

import numpy as np  # noqa: E402

GRID = {"sphere_radius": [74, 78, 82, 86, 90], "center_above_com": [12, 16, 20], "rim_z": [33]}


def evaluate(params, static_only=False):
    with tempfile.TemporaryDirectory() as tmp:
        summary = design.main(params, out_dir=f"{tmp}/stl", build_dir=f"{tmp}/build", quiet=True)
        model = SesameModel(params)
        shell, extra, cad = load_shell(f"{tmp}/stl", params=params)
        pose = params["poses"]["tuck"]
        _, com = model.mass_properties(pose, extra)
        pts = np.vstack([m.vertices for _, _, m in model.posed(pose) if m is not None] + [v.vertices for v in shell.values()])
        worst = 0
        for d in [np.zeros(3)] + [np.array(v, float) for v in itertools.product((-1, 0, 1), repeat=3) if any(v)]:
            g = com + (params["acceptance"]["com_perturbation_mm"] * d / np.linalg.norm(d) if d.any() else 0)
            _, eq = equilibria(pts, g, min_report_margin=-5)
            worst = max([worst] + [e["margin_mm"] for e in eq if e["stable"] and not e["micro"] and e["tilt_deg"] >= BELLY_TILT_DEG])
        bb = cad["shell-dome"]["bbox_mm"]
        row = {"shell_g": [round(m, 1) for m, _ in extra],
               "dome_size_mm": [round(bb[1][i] - bb[0][i], 1) for i in range(3)], "apex_z_mm": round(bb[1][2], 1),
               "worst_other_margin_mm": round(worst, 2)}
        if static_only:
            return row
        drop = sim_check.drop_tests(model, params, shell, extra)
        rec, _ = sim_check.recovery_tests(model, params, shell, extra)
        return {**row, "drop_success": drop["success_rate"],
                "recovered": sum(r["recovered"] for r in rec), "recovery_cases": len(rec)}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--params", help="params JSON (default bambu/params.json)")
    ap.add_argument("--R", type=float, nargs="+", default=GRID["sphere_radius"])
    ap.add_argument("--e", type=float, nargs="+", default=GRID["center_above_com"])
    ap.add_argument("--rim", type=float, nargs="+", default=GRID["rim_z"])
    ap.add_argument("--static-only", action="store_true", help="skip MuJoCo (about 40 s per point)")
    args = ap.parse_args()
    base = load_params(args.params)
    rows = []
    for R, e, rim in itertools.product(args.R, args.e, args.rim):
        p = copy.deepcopy(base)
        p["shell"].update({"sphere_radius": R, "center_above_com": e, "rim_z": rim})
        try:
            r = evaluate(p, args.static_only)
        except SystemExit as exc:
            r = {"error": str(exc)[-300:]}
        r.update({"R": R, "e": e, "rim_z": rim})
        rows.append(r)
        print(json.dumps(r), flush=True)
    (BAMBU / base.get("paths", {}).get("build_dir", "build") / "size_sweep.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
