"""Render design previews into bambu/preview/ (MuJoCo offscreen, deterministic)."""
import json
import pathlib
import sys

import mujoco
import numpy as np
import trimesh
from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sim_check  # noqa: E402
from analyze import load_shell  # noqa: E402
from render import COLORS, render  # noqa: E402
from sesame_model import BAMBU, SesameModel, load_params  # noqa: E402

OUT = BAMBU / "preview"


def robot_meshes(model, pose):
    out = []
    for p, _, mesh in model.posed(pose):
        if mesh is None:
            continue
        key = p.kind if p.kind in ("servo", "electronics", "battery") else p.group
        out.append((p.name, mesh, COLORS[key]))
    return out


def variant_previews(model, params, shell, out):
    """Variants s3-cover / v3-brackets: assembly, the mount parts on the body, print parts."""
    stl = BAMBU / params["paths"]["stl_dir"]
    green = (0.30, 0.65, 0.45, 1)
    color = {k: (green if k == "shell-dome" else COLORS["mount"]) for k in shell}
    title = {"s3-cover": "S3 wide body", "v3-brackets": "V3 body", "v3-crown": "V3 body, screw-free crown", "v3-mushroom": "V3 body, mushroom stem-lid", "v3-headarms": "V3 body, head arms + twist lock"}[params["shell"]["variant"]]
    views = [{"azimuth": 135, "elevation": -20, "title": "isometric", "distance": 560, "lookat": (0, 0, 45)},
             {"azimuth": 180, "elevation": -5, "title": "front (face)", "distance": 560, "lookat": (0, 0, 45)},
             {"azimuth": 90, "elevation": -5, "title": "left side", "distance": 560, "lookat": (0, 0, 45)},
             {"azimuth": 90, "elevation": -89, "title": "top", "distance": 560, "lookat": (0, 0, 45)}]
    for pose_name, floor in (("stand", -30.6), ("tuck", -5.0)):
        meshes = robot_meshes(model, params["poses"][pose_name]) + [(k, m, color[k]) for k, m in shell.items()]
        render(meshes, views, size=(480, 400), floor_z=floor,
               label=f"{title} + self-righting shell, pose '{pose_name}'").save(out / f"assembly-{pose_name}.png")
    mounts = [(k, m, color[k]) for k, m in shell.items() if k != "shell-dome"]
    close = [{"azimuth": 135, "elevation": -30, "title": "mount parts on the body", "distance": 300, "lookat": (0, 0, 35)},
             {"azimuth": 90, "elevation": -5, "title": "left side", "distance": 300, "lookat": (0, 0, 35)},
             {"azimuth": 180, "elevation": -5, "title": "front", "distance": 300, "lookat": (0, 0, 35)}]
    for pose_name, pose, floor in (("stand", params["poses"]["stand"], -30.6), ("hip90", {"hip": 90.0, "knee": 0.0}, -5.0),
                                   ("hip-10", {"hip": -10.0, "knee": 45.0}, -30.6)):
        render(robot_meshes(model, pose) + mounts, close, size=(480, 400), floor_z=floor,
               label=f"mount parts, legs '{pose_name}'").save(out / f"mount-{pose_name}.png")
    imgs = []
    for k in shell:
        m = trimesh.load(stl / f"{'head-mount' if k == 'head-arms' else k}.stl")  # head-arms prints as part of head-mount
        big = k == "shell-dome"
        for elev in ((-35, 40) if big else (-35,)):
            if k in ("lid-key",):
                continue
            imgs.append(render([(k, m, color[k])],
                               [{"azimuth": 135, "elevation": elev, "title": f"{k}.stl" + (" from below" if elev > 0 else " (as printed)"),
                                 "distance": 460 if big else 160, "lookat": (0, 0, 45 if big else 4)}],
                               size=(480, 400), floor_z=None if elev > 0 else 0.0))
    sheet = Image.new("RGB", (480 * len(imgs), 400), "white")
    for i, im in enumerate(imgs):
        sheet.paste(im, (480 * i, 0))
    sheet.save(out / "print-parts.png")


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--params", help="params JSON (default bambu/params.json)")
    params = load_params(ap.parse_args().params)
    out = BAMBU / params.get("paths", {}).get("preview_dir", "preview")
    out.mkdir(parents=True, exist_ok=True)
    model = SesameModel(params)
    shell, extra, _ = load_shell(params=params)
    if params["shell"]["variant"] in ("s3-cover", "v3-brackets", "v3-crown", "v3-mushroom", "v3-headarms"):
        variant_previews(model, params, shell, out)
        recovery_sheet(model, params, shell, extra, out)
        print("previews:", sorted(p.name for p in out.iterdir()))
        return
    OUT.mkdir(exist_ok=True)
    two = load_shell(variant="two-piece")[0]
    green = (0.30, 0.65, 0.45, 1)
    dome = (two["shell-dome"], green)
    mount = (two["shell-mount"], COLORS["mount"])
    views = [{"azimuth": 135, "elevation": -20, "title": "isometric", "distance": 520, "lookat": (0, 0, 45)},
             {"azimuth": 180, "elevation": -5, "title": "front (face)", "distance": 520, "lookat": (0, 0, 45)},
             {"azimuth": 90, "elevation": -5, "title": "left side", "distance": 520, "lookat": (0, 0, 45)},
             {"azimuth": 90, "elevation": -89, "title": "top", "distance": 520, "lookat": (0, 0, 45)}]
    for pose_name, floor in (("stand", -30.6), ("tuck", -5.0)):
        meshes = robot_meshes(model, params["poses"][pose_name]) + [("dome", *dome), ("mount", *mount)]
        render(meshes, views, size=(480, 400), floor_z=floor,
               label=f"Sesame + self-righting shell, pose '{pose_name}'").save(OUT / f"assembly-{pose_name}.png")
    meshes = robot_meshes(model, params["poses"]["stand"]) + [("mount", *mount)]
    render(meshes, views[:2], size=(480, 400), floor_z=-30.6, label="mount (saddle + mast) on the top cover").save(OUT / "mount.png")
    pv = [("shell-onepiece", "shell-onepiece.stl (rim on bed)", 420, (0, 0, 45), -35),
          ("shell-onepiece", "shell-onepiece.stl seen from below (saddle, mast)", 420, (0, 0, 45), 40),
          ("drill-guide", "drill-guide.stl (skirts on bed)", 160, (0, 0, 8), -35),
          ("shell-dome", "two-piece: shell-dome.stl", 420, (0, 0, 45), -35),
          ("shell-mount", "two-piece: shell-mount.stl", 220, (0, 0, 40), -35)]
    imgs = []
    for name, title, dist, look, elev in pv:
        m = trimesh.load(BAMBU / "stl" / f"{name}.stl")
        imgs.append(render([(name, m, COLORS["mount"] if name in ("shell-mount", "drill-guide") else green)],
                           [{"azimuth": 135, "elevation": elev, "title": title, "distance": dist, "lookat": look}],
                           size=(480, 400), floor_z=None if elev > 0 else 0.0))
    sheet = Image.new("RGB", (480 * 3, 400 * 2), "white")
    for i, im in enumerate(imgs):
        sheet.paste(im, (480 * (i % 3), 400 * (i // 3)))
    sheet.save(OUT / "print-parts.png")
    one = shell["shell-onepiece"] if "shell-onepiece" in shell else None
    if one is not None:
        meshes = robot_meshes(model, params["poses"]["stand"]) + [("one", one, (0.30, 0.65, 0.45, 0.45))]
        render(meshes, views[:3], size=(480, 400), floor_z=-30.6,
               label="one-piece shell on the robot (translucent)").save(OUT / "assembly-onepiece.png")

    recovery_sheet(model, params, shell, extra, OUT)
    print("previews:", sorted(p.name for p in OUT.iterdir()))


def recovery_sheet(model, params, shell, extra, out):
    """Recovery sequence from supine (articulated MuJoCo model)."""
    _, (m, frames) = sim_check.recovery_tests(model, params, shell, extra, frames_for="supine")
    d = mujoco.MjData(m)
    tiles = []
    with mujoco.Renderer(m, 300, 360) as r:
        for label, qpos in frames:
            d.qpos[:] = qpos
            mujoco.mj_forward(m, d)
            cam = mujoco.MjvCamera()
            cam.lookat[:] = [d.qpos[0], d.qpos[1], 0.05]
            cam.distance, cam.azimuth, cam.elevation = 0.55, 150, -20
            r.update_scene(d, cam)
            im = Image.fromarray(r.render())
            ImageDraw.Draw(im).text((6, 6), label, fill=(0, 0, 0))
            tiles.append(im)
    cols = 5
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (360 * cols, 300 * rows), "white")
    for i, im in enumerate(tiles):
        sheet.paste(im, (360 * (i % cols), 300 * (i // cols)))
    sheet.save(out / "recovery-supine.png")


if __name__ == "__main__":
    main()
