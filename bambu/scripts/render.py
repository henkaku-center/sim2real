"""Tiny MuJoCo-based offscreen renderer for design previews (mm meshes)."""
from __future__ import annotations

import mujoco
import numpy as np
from PIL import Image, ImageDraw

COLORS = {
    "torso": (0.92, 0.88, 0.80, 1), "femur": (0.80, 0.25, 0.15, 1), "foot": (0.85, 0.45, 0.20, 1),
    "servo": (0.25, 0.35, 0.80, 1), "electronics": (0.15, 0.60, 0.30, 1), "battery": (0.9, 0.8, 0.1, 1),
    "shell": (0.30, 0.65, 0.45, 0.55), "mount": (0.55, 0.40, 0.75, 1), "floor": (0.85, 0.85, 0.85, 1),
}


def build(meshes, floor_z=None):
    """meshes: list of (name, trimesh, rgba) in mm."""
    spec = mujoco.MjSpec()
    spec.visual.global_.offwidth = 1600
    spec.visual.global_.offheight = 1200
    spec.visual.headlight.ambient = [0.45, 0.45, 0.45]
    spec.visual.headlight.diffuse = [0.55, 0.55, 0.55]
    spec.add_texture(name="sky", type=mujoco.mjtTexture.mjTEXTURE_SKYBOX, builtin=mujoco.mjtBuiltin.mjBUILTIN_GRADIENT,
                     rgb1=[1, 1, 1], rgb2=[0.92, 0.94, 0.97], width=64, height=64)
    world = spec.worldbody
    if floor_z is not None:
        world.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[0.4, 0.4, 0.01], pos=[0, 0, floor_z / 1000],
                       rgba=COLORS["floor"])
    for i, (name, mesh, rgba) in enumerate(meshes):
        mname = f"m{i}"
        spec.add_mesh(name=mname, uservert=(mesh.vertices / 1000).ravel().tolist(),
                      userface=mesh.faces.ravel().tolist(), inertia=mujoco.mjtMeshInertia.mjMESH_INERTIA_SHELL)
        world.add_geom(type=mujoco.mjtGeom.mjGEOM_MESH, meshname=mname, rgba=rgba, contype=0, conaffinity=0)
    return spec.compile()


def render(meshes, views, size=(640, 480), floor_z=None, label=None):
    model = build(meshes, floor_z)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    out = []
    with mujoco.Renderer(model, size[1], size[0]) as r:
        for v in views:
            cam = mujoco.MjvCamera()
            cam.lookat[:] = np.array(v.get("lookat", (0, 0, 30))) / 1000
            cam.distance = v.get("distance", 420) / 1000
            cam.azimuth, cam.elevation = v["azimuth"], v["elevation"]
            r.update_scene(data, cam)
            img = Image.fromarray(r.render())
            if v.get("title"):
                ImageDraw.Draw(img).text((8, 6), v["title"], fill=(0, 0, 0))
            out.append(img)
    w, h = size
    sheet = Image.new("RGB", (w * len(out), h + (18 if label else 0)), "white")
    for i, img in enumerate(out):
        sheet.paste(img, (i * w, 18 if label else 0))
    if label:
        ImageDraw.Draw(sheet).text((8, 3), label, fill=(0, 0, 0))
    return sheet
