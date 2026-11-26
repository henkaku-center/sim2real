"""Posable, mass-annotated Sesame model built from the upstream STEP leaves.

Robot frame used everywhere in bambu/ (mm):
    X forward (face), Y left, Z up; Z = 0 is the underside of the bottom cover.
    (X, Y, Z) = (26 - ux, uz - 2.38, uy + 1.0) from the upstream STEP frame.

The STEP is posed in the upstream "stand" pose (hip q = +45 deg, knee q = +90
deg in the manifest convention, i.e. lower legs vertical).  Leg poses here use
the same internal convention as manifest/robot.yaml: q = 0 is the 90-degree
firmware rest pose, positive hip q splays the femur towards fore/aft, positive
knee q swings the lower leg down.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

import numpy as np
import trimesh

BAMBU = pathlib.Path(__file__).resolve().parents[1]
ROOT = BAMBU.parent
UPSTREAM = BAMBU / "build" / "upstream"
LEGS = ("front_left", "front_right", "back_left", "back_right")
STEP_POSE = {"hip": 45.0, "knee": 90.0}
PLA_LABELS = ("Internal-Frame", "Bottom-Cover", "COMPOUND001", "femur", "foot-joint")
OLED_KEYS = ("OLED", "Display", "Body -", "COMPOUND")


def to_robot(p):
    p = np.asarray(p, dtype=float)
    return np.stack([26.0 - p[..., 0], p[..., 2] - 2.38, p[..., 1] + 1.0], axis=-1)


def to_robot_dir(v):
    v = np.asarray(v, dtype=float)
    return np.array([-v[0], v[2], v[1]])


def leg_of(xy):
    return ("front" if xy[0] > 0 else "back") + "_" + ("left" if xy[1] > 0 else "right")


def rotation(axis, angle_deg, point):
    return trimesh.transformations.rotation_matrix(np.radians(angle_deg), axis, point)


@dataclass
class Part:
    name: str
    label: str
    group: str  # torso | femur | foot
    leg: str | None
    mass_g: float
    com: np.ndarray  # robot frame, STEP pose
    mesh: trimesh.Trimesh | None
    kind: str  # pla | servo | battery | electronics | lumped


@dataclass
class Leg:
    name: str
    hip_point: np.ndarray
    knee_point: np.ndarray
    knee_axis: np.ndarray
    hip_sign: float
    knee_sign: float = 1.0
    tip: np.ndarray = field(default_factory=lambda: np.zeros(3))


class SesameModel:
    def __init__(self, params: dict):
        self.params = params
        mp = params["mass_model"]
        data = json.loads((UPSTREAM / "parts.json").read_text())["parts"]
        for r in data:
            r["com_r"] = to_robot(r["com"]) if r["com"] else None

        hips = [r for r in data if r["spline_axis"] and abs(r["spline_axis"][1]) > 0.9]
        knees = [r for r in data if r["spline_axis"] and abs(r["spline_axis"][1]) < 0.1]
        assert len(hips) == 4 and len(knees) == 4, (len(hips), len(knees))
        self.legs: dict[str, Leg] = {}
        for h in hips:
            name = leg_of(h["com_r"])
            k = next(k for k in knees if leg_of(k["com_r"]) == name)
            sx, sy = np.sign(h["com_r"][0]), np.sign(h["com_r"][1])
            self.legs[name] = Leg(name, h["com_r"], k["com_r"], to_robot_dir(k["spline_axis"]), -sx * sy)

        servo_rows = [r for r in data if r["label"].startswith("SG90")]
        servo_vol = sum(r["vol"] for r in servo_rows)
        oled_rows = [r for r in data if any(key in r["label"] for key in OLED_KEYS) and r["label"] != "COMPOUND001"]
        elec_rows = [r for r in data if r not in servo_rows and r not in oled_rows
                     and not any(r["label"].startswith(p) for p in PLA_LABELS)
                     and "Batte" not in r["label"] and not r["label"].startswith("KCD1")]
        switch_rows = [r for r in data if r["label"].startswith("KCD1")]
        oled_vol = sum(r["vol"] for r in oled_rows) or 1.0
        elec_vol = sum(r["vol"] for r in elec_rows) or 1.0
        switch_vol = sum(r["vol"] for r in switch_rows) or 1.0

        self.parts: list[Part] = []
        for r in data:
            if r["com_r"] is None or r["vol"] <= 0:
                continue
            label, com = r["label"], r["com_r"]
            if any(label.startswith(p) for p in PLA_LABELS):
                kind, mass = "pla", r["vol"] / 1000 * mp["pla_effective_density_g_cm3"]
            elif r in servo_rows:
                kind, mass = "servo", r["vol"] / servo_vol * 8 * mp["servo_g"]
            elif "Batte" in label:
                kind, mass = "battery", mp["battery_g"]
            elif r in oled_rows:
                kind, mass = "electronics", r["vol"] / oled_vol * mp["oled_g"]
            elif r in switch_rows:
                kind, mass = "electronics", r["vol"] / switch_vol * mp["switch_g"]
            else:
                kind, mass = "electronics", r["vol"] / elec_vol * mp["controller_g"]
            group, leg = self._classify(r, label, com)
            mesh = None
            if r["stl"]:
                mesh = trimesh.load(UPSTREAM / r["stl"], force="mesh")
                mesh.vertices = to_robot(mesh.vertices)
                mesh.fix_normals()
                if np.ptp(mesh.vertices, axis=0).max() > 90:  # malformed switch rocker export
                    mesh = None
            self.parts.append(Part(r["name"], label, group, leg, mass, com, mesh, kind))
        lump = mp["lumped"]
        self.parts.append(Part("lumped", "wiring+screws", "torso", None, lump["mass_g"],
                               np.array(lump["com_mm"], float), None, "lumped"))
        self.s3 = None
        variant = params.get("body", {}).get("variant")
        if variant == "s3-wide":
            self._widen_for_s3(params["body"], mp)
        elif variant == "v3":
            self._rebody_v3(params["body"], mp)

        for leg in self.legs.values():
            foot = [p for p in self.parts if p.group == "foot" and p.leg == leg.name and p.kind == "pla"][0]
            v = foot.mesh.vertices
            leg.tip = v[v[:, 2] < v[:, 2].min() + 0.5].mean(axis=0)  # centre of the sole
            # knee sign: q -> 0 (horizontal) must move the tip away from the body
            t = trimesh.transform_points([leg.tip], rotation(leg.knee_axis, -90.0, leg.knee_point))[0]
            leg.knee_sign = 1.0 if np.linalg.norm(t[:2]) > np.linalg.norm(leg.tip[:2]) else -1.0

    def _widen_for_s3(self, body: dict, mp: dict):
        """APS S3 body: the v122 frame widened through the middle (tools/internal_frame_cad.py).

        Everything beyond the splice moves rigidly by +-widening/2 in Y (legs, servos); the upstream
        frame, bottom cover, top cover and ESP32-S2 electronics are replaced by the widened STLs and
        box proxies of the 70 x 50 mm carrier stack.  The battery stays in the frame cavity.
        """
        src = ROOT / body["frame_dir"]
        asm = json.loads((src / "assembly.json").read_text())
        half, splice = asm["parameters"]["widening_mm"] / 2, asm["parameters"]["splice_y_mm"]
        dz = np.array([0.0, 0.0, body["frame_to_robot_z"]])
        kept = []
        for p in self.parts:
            if p.kind == "electronics" or p.label.startswith(("Internal-Frame", "Bottom-Cover", "COMPOUND001")):
                continue
            if abs(p.com[1]) > splice:
                shift = np.array([0.0, np.sign(p.com[1]) * half, 0.0])
                p.com = p.com + shift
                if p.mesh is not None:
                    p.mesh.apply_translation(shift)
            kept.append(p)
        self.parts = kept
        for leg in self.legs.values():
            shift = np.array([0.0, np.sign(leg.hip_point[1]) * half, 0.0])
            leg.hip_point, leg.knee_point = leg.hip_point + shift, leg.knee_point + shift
        names = {"front_left": "L1", "back_left": "L2", "front_right": "R1", "back_right": "R2"}
        for name, leg in self.legs.items():
            err = np.linalg.norm(leg.hip_point[:2] - asm["hip_shaft_xy_mm"][names[name]])
            assert err < 1.0, (name, leg.hip_point, err)
        for name in ("internal-frame", "bottom-cover"):
            mesh = trimesh.load(src / f"{name}.stl", force="mesh")
            mesh.apply_translation(dz)
            self.parts.append(Part(f"s3-{name}", f"S3-{name}", "torso", None,
                                   mesh.volume / 1000 * mp["pla_effective_density_g_cm3"], mesh.center_mass, mesh, "pla"))
        seat = asm["pcb_seat_z_mm"] + dz[2]
        pcb_size = np.array(asm["pcb_size_mm"], float)
        top = seat + pcb_size[2]
        holes = [[x, y, z + dz[2]] for x, y, z in asm["pcb_mount_holes_mm"]]
        self.s3 = {"pcb_seat_z": seat, "pcb_top_z": top, "pcb_size": pcb_size.tolist(), "pcb_holes": holes,
                   "deck_top_z": asm["servo_flange_seat_z_mm"] + dz[2],
                   "hips": {n: l.hip_point.tolist() for n, l in self.legs.items()}}
        for e in body["electronics"]:
            size = np.array(e["size_mm"], float)
            centre = np.array([e["xy_mm"][0], e["xy_mm"][1], top + e["z_above_pcb_top_mm"] + size[2] / 2])
            if e.get("on_seat"):
                centre[2] = seat + size[2] / 2
            box = trimesh.creation.box(extents=size, transform=trimesh.transformations.translation_matrix(centre))
            self.parts.append(Part(e["name"], e["name"], "torso", None, e["mass_g"], centre, box, "electronics"))

    def _rebody_v3(self, body: dict, mp: dict):
        """Loftwork V3 frame kit (reference/frame-and-cover_261105): each leg assembly (hip servo, femur,
        knee servo, foot) moves rigidly so its hip axis lands on the kit's hip datum; frame, bottom cover,
        head cover and lid are the kit's STLs; the carrier stack is boxed; the battery uses the kit's mount."""
        src = ROOT / body["frame_dir"]
        asm = json.loads((src / "assembly.json").read_text())
        dz = np.array([0.0, 0.0, body["frame_to_robot_z"]])
        names = {"front_left": "L1", "back_left": "L2", "front_right": "R1", "back_right": "R2"}
        shift = {n: np.r_[np.asarray(asm["hip_shaft_xy_mm"][names[n]]) - l.hip_point[:2], 0.0] for n, l in self.legs.items()}
        kept = []
        for p in self.parts:
            if p.kind in ("electronics", "battery") or p.label.startswith(("Internal-Frame", "Bottom-Cover", "COMPOUND001")):
                continue
            leg = p.leg or (leg_of(p.com) if abs(p.com[1]) > 3.5 else None)
            if leg is not None:
                p.com = p.com + shift[leg]
                if p.mesh is not None:
                    p.mesh.apply_translation(shift[leg])
            kept.append(p)
        self.parts = kept
        for n, leg in self.legs.items():
            leg.hip_point, leg.knee_point = leg.hip_point + shift[n], leg.knee_point + shift[n]
        for name in body["pla_parts"]:
            mesh = trimesh.load(src / f"{name}.stl", force="mesh")
            mesh.apply_translation(dz)
            self.parts.append(Part(f"v3-{name}", f"V3-{name}", "torso", None,
                                   mesh.volume / 1000 * mp["pla_effective_density_g_cm3"], mesh.center_mass, mesh, "pla"))
        bm = asm["parameters"]["battery_mount"]
        centre = np.asarray(bm["centre_mm"], float) + dz
        box = trimesh.creation.box(extents=bm["envelope_mm"], transform=trimesh.transformations.translation_matrix(centre))
        self.parts.append(Part("battery", "battery", "torso", None, mp["battery_g"], centre, box, "battery"))
        seat = asm["pcb_seat_z_mm"] + dz[2]
        top = seat + asm["pcb_size_mm"][2]
        self.s3 = {"pcb_seat_z": seat, "pcb_top_z": top, "pcb_size": asm["pcb_size_mm"],
                   "deck_top_z": asm["servo_flange_seat_z_mm"] + dz[2],
                   "servo_mounts": {n: asm["servo_mounts"][names[n]] for n in self.legs},
                   "hips": {n: l.hip_point.tolist() for n, l in self.legs.items()}, "leg_shift": {n: v.tolist() for n, v in shift.items()}}
        for e in body["electronics"]:
            size = np.array(e["size_mm"], float)
            c = np.array([e["xy_mm"][0], e["xy_mm"][1], (seat if e.get("on_seat") else top + e["z_above_pcb_top_mm"]) + size[2] / 2])
            box = trimesh.creation.box(extents=size, transform=trimesh.transformations.translation_matrix(c))
            self.parts.append(Part(e["name"], e["name"], "torso", None, e["mass_g"], c, box, "electronics"))

    def _classify(self, r, label, com):
        if label.startswith("femur"):
            return "femur", leg_of(com)
        if label.startswith("foot-joint"):
            return "foot", leg_of(com)
        if label.startswith("SG90"):
            d_hip = {n: np.linalg.norm(com - l.hip_point) for n, l in self.legs.items()}
            d_knee = {n: np.linalg.norm(com - l.knee_point) for n, l in self.legs.items()}
            nh, nk = min(d_hip, key=d_hip.get), min(d_knee, key=d_knee.get)
            horn = r["vol"] < 200
            if d_hip[nh] < d_knee[nk]:
                return ("femur", nh) if horn else ("torso", None)
            return ("foot", nk) if horn else ("femur", nk)
        return "torso", None

    # ------------------------------------------------------------------ posing
    def transforms(self, pose: dict) -> dict:
        """pose = {"hip": {leg: deg} | deg, "knee": {leg: deg} | deg} -> 4x4 per (group, leg)."""
        out = {}
        for name, leg in self.legs.items():
            hq = pose["hip"][name] if isinstance(pose["hip"], dict) else pose["hip"]
            kq = pose["knee"][name] if isinstance(pose["knee"], dict) else pose["knee"]
            th = rotation([0, 0, 1], leg.hip_sign * (hq - STEP_POSE["hip"]), leg.hip_point)
            knee_pt = trimesh.transform_points([leg.knee_point], th)[0]
            knee_ax = th[:3, :3] @ leg.knee_axis
            tk = rotation(knee_ax, leg.knee_sign * (kq - STEP_POSE["knee"]), knee_pt)
            out[("femur", name)] = th
            out[("foot", name)] = tk @ th
        return out

    def posed(self, pose: dict):
        tf = self.transforms(pose)
        for p in self.parts:
            m = tf.get((p.group, p.leg), np.eye(4))
            mesh = p.mesh.copy().apply_transform(m) if p.mesh is not None else None
            yield p, trimesh.transform_points([p.com], m)[0], mesh

    def mass_properties(self, pose: dict, extra=()):
        """Total mass [g] and CoM [mm]; extra = iterable of (mass_g, com_mm)."""
        ms, cs = [], []
        for p, com, _ in self.posed(pose):
            ms.append(p.mass_g)
            cs.append(com)
        for m, c in extra:
            ms.append(m)
            cs.append(np.asarray(c, float))
        ms, cs = np.array(ms), np.array(cs)
        return ms.sum(), (ms[:, None] * cs).sum(0) / ms.sum()

    def tip(self, pose: dict, leg: str):
        return trimesh.transform_points([self.legs[leg].tip], self.transforms(pose)[("foot", leg)])[0]

    def group_meshes(self, pose: dict) -> dict:
        """Concatenated meshes per (group, leg) for collision checks."""
        acc: dict = {}
        for p, _, mesh in self.posed(pose):
            if mesh is not None:
                acc.setdefault((p.group, p.leg), []).append(mesh)
        return {k: trimesh.util.concatenate(v) for k, v in acc.items()}

    def summary(self, pose: dict):
        rows = {}
        for p, com, _ in self.posed(pose):
            key = p.kind if p.group == "torso" or p.kind != "pla" else p.group
            r = rows.setdefault(key, [0.0, np.zeros(3)])
            r[0] += p.mass_g
            r[1] += p.mass_g * com
        return {k: {"mass_g": round(v[0], 1), "com_mm": (v[1] / v[0]).round(1).tolist()} for k, v in rows.items()}


def load_params(path=None):
    return json.loads(pathlib.Path(path or BAMBU / "params.json").read_text())


if __name__ == "__main__":
    model = SesameModel(load_params())
    for pose_name, pose in model.params["poses"].items():
        mass, com = model.mass_properties(pose)
        print(f"{pose_name:10s} mass={mass:6.1f} g  CoM={com.round(1)}")
    print(json.dumps(model.summary(model.params["poses"]["stand"]), indent=1))
    for name, leg in model.legs.items():
        print(name, "hip", leg.hip_point.round(1), "knee", leg.knee_point.round(1),
              "axis", leg.knee_axis.round(3), "tip", leg.tip.round(1), "ks", leg.knee_sign)
