#!/usr/bin/env python3
"""CAD-derived leg clearance of a printed body design.

Sweeps every hip and foot servo through 0..180 degrees against the design's
printed body parts with exact triangle-mesh contact (FCL), and records the
mechanically free range per joint beside the design as `leg-clearance.json`.

    uv run python tools/leg_clearance.py internal-frame-s3            # summary
    uv run python tools/leg_clearance.py internal-frame-s3 --write    # evidence
    uv run python tools/leg_clearance.py internal-frame-s3 --check    # freshness

The summary also compares the free range with manifest/robot.yaml limits and
every motion in manifest/motions.yaml. Exit codes: 0 done or fresh, 1 stale
evidence (--check), 2 design not supported.

Nominal CAD only: no print tolerance, servo or horn play, trim, cables,
servo cases or physical test. Results describe this reference geometry; they
are evidence for designers, not a permission rule for anyone's robot.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PRINTING = 'assets/printing'
LEGS = 'assets/stl/upstream'
EVIDENCE = 'leg-clearance.json'
SCHEMA = 1
BODY_PARTS = ('head-cover', 'head-lid', 'internal-frame', 'bottom-cover')
# Hip print, its foot print. The files are single-corner templates, not an
# assembly: every print is placed by its hip axis (see DATUMS['placement']).
PRINTS = {'L1': 'L3', 'R1': 'R3', 'L2': 'L4', 'R2': 'R4'}
LEG_NAMES = {'L1': 'front_left', 'R1': 'front_right', 'L2': 'back_left', 'R2': 'back_right'}
REST = 90.0
DATUMS = {
    'template_frame': 'upstream v117 leg STL: x fore-aft, y up, z lateral, millimetres',
    'hip_axis_x_mm': 1.5,
    'hip_axis_abs_z_mm': 23.04,
    'foot_axis_y_mm': 15.25,
    'foot_axis_abs_z_mm': 59.9,
    'y_at_servo_flange_seat_mm': 22.184,
    'upstream_assembly_y_at_frame_top_mm': 21.968,
    'placement': 'Template (x, y, z) maps to body (x, -z, y); a print whose file side is not its body side '
                 'is turned 180 degrees about the vertical. The hip axis lands on hip_shaft_xy_mm and template '
                 'y_at_servo_flange_seat_mm on servo_flange_seat_z_mm. The print\'s wide (foot-servo) side then '
                 'faces the middle of the body at every corner, as in the upstream top-down drawing.',
    'servo_convention': 'Hip yaw about +Z, anticlockwise seen from above, is servo_deg - 90. Foot rotation about '
                        'the template +x axis through the foot axis is servo_deg - 90. Rest is 90 on every joint.',
    'source': 'Hip and foot axes: sim/prepare_assets.py (upstream horn circle fits, DECISIONS.md D2). Vertical '
              'seat and print-to-corner assignment: the base design\'s recorded leg samples in '
              'assets/printing/internal-frame-s3/head-cable-clearance.json, which this placement reproduces. '
              'sim/prepare_assets.py assigns the mirrored print to each corner and uses the upstream stack height '
              '(y 21.968 at the frame top, 0.216 mm higher); datum_sensitivity reports the effect of that height.',
}
SETTINGS = {
    'scan_step_deg': 0.5,
    'angle_tolerance_deg': 0.005,
    'profile_step_deg': 1,
    'near_gap_mm': 1.0,
    'overlap_step_deg': 0.5,
    'overlap_limit_mm': 2.0,
    'overlap_tolerance_mm': 0.005,
    'foot_grid_deg': 5,
    'foot_gap_grid_deg': 15,
    'neighbour_foot_grid_deg': 30,
}
SCOPE = ('CAD-derived, not physical. Exact triangle-mesh contact (python-fcl) between the unchanged upstream v117 '
         'leg prints and this design\'s printed body parts, one hip moving at a time with the others at rest; '
         'feet on a grid over each hip\'s contact-free angles. Nominal geometry: no print tolerance, servo or '
         'horn play, trim error, cables, screws, servo cases, ground contact or loaded deflection.')
DEFINITIONS = {
    'toward_middle, toward_end': 'Swing from rest toward the middle of the body (the print\'s wide side) or toward '
                                 'the nearer end (the Standing direction), in degrees from rest.',
    'free_servo_deg': 'Contact-free servo interval that contains rest.',
    'contact_bands': 'Servo intervals in contact with one part. A transient band has free travel on both sides.',
    'max_overlap_mm': 'Transient bands: smallest shift of the print along +-X, +-Y or +-Z that clears the contact, '
                      'at the worst sampled angle. An upper bound of the penetration depth; null if no such shift '
                      'within settings.overlap_limit_mm clears it.',
    'near_bands_servo_deg': 'Servo intervals where the smallest gap is below settings.near_gap_mm, contact included.',
    'gap_profile_mm': 'Smallest distance to each reachable part at whole servo degrees 0..180; 0 is contact.',
    'out_of_reach_vertical_gap_mm': 'Parts wholly above or below the hip print\'s fixed height range.',
}
NOT_MODELLED = [
    'hip and foot servo cases, horns and screws: the design directory has no positioned servo solids',
    'ribbon cables and connectors',
    'two or more joints of different legs moving at once, beyond the neighbour sample',
    'ground contact, loads and dynamics',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def design_dir(name, root=ROOT):
    path = Path(name)
    return path if path.is_dir() else Path(root) / PRINTING / name


def assembly_datums(assembly):
    """The assembly values this check consumes; unrelated receipt edits do not stale the evidence."""
    return {'hip_shaft_xy_mm': assembly['hip_shaft_xy_mm'],
            'servo_flange_seat_z_mm': assembly['servo_flange_seat_z_mm'],
            'coordinates': assembly['coordinates'], 'units': assembly['units']}


def input_hashes(directory, hips, root=ROOT):
    files = {f'{part}.stl': sha(Path(directory) / f'{part}.stl') for part in BODY_PARTS}
    for hip in hips:
        for name in (hip, PRINTS[hip]):
            files[f'{LEGS}/{name}-v117.stl'] = sha(Path(root) / LEGS / f'{name}-v117.stl')
    return files


def supported_hips(assembly):
    hips = sorted(assembly['hip_shaft_xy_mm'], key=lambda n: (n[1], n[0]))
    extra = [h for h in hips if h not in PRINTS]
    if extra:
        raise ValueError(f'Leg stations {extra} are not supported: only the four corner legs '
                         f'{sorted(PRINTS)} are swept. Middle stations also need neighbouring-leg sweeps.')
    return hips


def verify(directory, root=ROOT):
    """Hash-only freshness of committed evidence; no geometry runtime needed."""
    directory = Path(directory)
    path = directory / EVIDENCE
    if not path.exists():
        return {'fresh': False, 'stale': [f'missing {EVIDENCE}; run tools/leg_clearance.py {directory.name} --write']}
    evidence = json.loads(path.read_text())
    stale = []
    if evidence.get('schema') != SCHEMA:
        stale.append('schema')
    if evidence.get('checker_sha256') != sha(Path(__file__)):
        stale.append('tools/leg_clearance.py changed')
    assembly = json.loads((directory / 'assembly.json').read_text())
    if evidence.get('assembly_datums') != assembly_datums(assembly) or \
            evidence.get('assembly_datums_sha256') != canonical_sha(assembly_datums(assembly)):
        stale.append('assembly.json datums changed')
    if evidence.get('datums') != DATUMS or evidence.get('settings') != SETTINGS:
        stale.append('leg datums or settings changed')
    try:
        current = input_hashes(directory, supported_hips(assembly), root)
    except (OSError, ValueError) as error:
        current = {}
        stale.append(str(error))
    recorded = evidence.get('inputs', {})
    stale += [f'{name} changed' for name in sorted(set(current) | set(recorded)) if current.get(name) != recorded.get(name)]
    return {'fresh': not stale, 'stale': stale}


# ---------------------------------------------------------------- geometry

def _rotation(axis, degrees):
    import numpy as np
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    x, y, z = axis
    m = np.eye(4)
    m[:3, :3] = [[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                 [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                 [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]]
    return m


def _translation(vector):
    import numpy as np
    m = np.eye(4)
    m[:3, 3] = vector
    return m


class Leg:
    """One corner leg: template side, placement and joint transforms."""

    def __init__(self, hip, assembly, meshes, seat_y=None):
        import numpy as np
        self.hip, self.foot = hip, PRINTS[hip]
        self.hx, self.hy = assembly['hip_shaft_xy_mm'][hip]
        self.side = 1 if self.hy > 0 else -1                       # body side: +1 left
        self.file_side = 1 if meshes[hip].centroid[2] > 0 else -1   # template z side of the STL
        self.turned = (self.file_side < 0) != (self.side > 0)
        self.wide_x = 1 if self.turned else -1                      # body direction the wide side faces
        self.middle_sign = -self.side * self.wide_x                 # servo direction that swings toward it
        seat_y = DATUMS['y_at_servo_flange_seat_mm'] if seat_y is None else seat_y
        self.hip_centre = np.array([DATUMS['hip_axis_x_mm'], 0, self.file_side * DATUMS['hip_axis_abs_z_mm']])
        self.foot_centre = np.array([0, DATUMS['foot_axis_y_mm'], self.file_side * DATUMS['foot_axis_abs_z_mm']])
        base = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1.0]])
        origin = np.array([self.hip_centre[0], seat_y, self.hip_centre[2]])
        place = base @ _translation(-origin)
        if self.turned:
            place = _rotation((0, 0, 1), 180) @ place
        self.place = _translation([self.hx, self.hy, assembly['servo_flange_seat_z_mm']]) @ place

    def transform(self, hip_deg, foot_deg=None):
        """Template to body for the hip print, or for the foot print when foot_deg is given."""
        joint = _translation(self.hip_centre) @ _rotation((0, 1, 0), hip_deg - REST) @ _translation(-self.hip_centre)
        if foot_deg is not None:
            joint = joint @ _translation(self.foot_centre) @ _rotation((1, 0, 0), foot_deg - REST) @ _translation(-self.foot_centre)
        return self.place @ joint

    def deg(self, servo):
        """Servo degrees to degrees toward the middle (negative: toward the end)."""
        return (servo - REST) * self.middle_sign

    def servo(self, toward_middle_deg):
        return REST + toward_middle_deg * self.middle_sign


class Scene:
    """FCL collision objects for the design's body parts and the leg prints."""

    def __init__(self, directory, assembly, hips, root=ROOT):
        import fcl
        import numpy as np
        import trimesh
        self.fcl = fcl
        self.trimesh = trimesh
        load = lambda path: trimesh.load(path, process=False, force='mesh')
        self.body = {part: load(Path(directory) / f'{part}.stl') for part in BODY_PARTS}
        self.prints = {name: load(Path(root) / LEGS / f'{name}-v117.stl') for hip in hips for name in (hip, PRINTS[hip])}
        self.body_objects = {name: self._object(mesh) for name, mesh in self.body.items()}
        self.print_objects = {name: self._object(mesh) for name, mesh in self.prints.items()}
        self.body_boxes = {name: [list(map(float, corner)) for corner in mesh.bounds] for name, mesh in self.body.items()}
        self.spheres = {}
        for name, mesh in self.prints.items():
            centre = mesh.bounds.mean(axis=0)
            self.spheres[name] = (centre, float(np.linalg.norm(mesh.vertices - centre, axis=1).max()))

    def _object(self, mesh):
        import numpy as np
        model = self.fcl.BVHModel()
        model.beginModel(len(mesh.vertices), len(mesh.faces))
        model.addSubModel(np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int32))
        model.endModel()
        return self.fcl.CollisionObject(model)

    def _pose(self, name, transform):
        obj = self.print_objects[name]
        obj.setTransform(self.fcl.Transform(transform[:3, :3], transform[:3, 3]))
        return obj

    def hit(self, part, name, transform):
        return self.fcl.collide(self.body_objects[part], self._pose(name, transform),
                                self.fcl.CollisionRequest(), self.fcl.CollisionResult()) > 0

    def gap(self, part, name, transform):
        if self.hit(part, name, transform):
            return 0.0
        return max(0.0, self.fcl.distance(self.body_objects[part], self._pose(name, transform),
                                          self.fcl.DistanceRequest(), self.fcl.DistanceResult()))

    def print_hit(self, first, first_transform, second, second_transform):
        return self.fcl.collide(self._pose(first, first_transform), self._pose(second, second_transform),
                                self.fcl.CollisionRequest(), self.fcl.CollisionResult()) > 0

    def print_gap(self, first, first_transform, second, second_transform):
        if self.print_hit(first, first_transform, second, second_transform):
            return 0.0
        return max(0.0, self.fcl.distance(self._pose(first, first_transform), self._pose(second, second_transform),
                                          self.fcl.DistanceRequest(), self.fcl.DistanceResult()))

    def bounds(self, name, transform):
        import numpy as np
        lo, hi = self.prints[name].bounds
        corners = np.array([[x, y, z, 1.0] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        world = corners @ transform.T
        return world[:, :3].min(0), world[:, :3].max(0)

    def far(self, part, name, transform):
        """Lower bound of the gap from the print's bounding sphere and the part's box (conservative, cheap)."""
        centre, radius = self.spheres[name]
        x, y, z = (float(v) for v in transform[:3, :3] @ centre + transform[:3, 3])
        lo, hi = self.body_boxes[part]
        outside = [max(lo[i] - v, 0.0, v - hi[i]) for i, v in enumerate((x, y, z))]
        return max(0.0, math.sqrt(sum(d * d for d in outside)) - radius)

    def clearing_shift(self, part, name, transform):
        """Smallest shift of the print along +-X, +-Y or +-Z that clears a contact (bisection on the boolean test).

        An upper bound of the penetration depth, exact against axis-aligned
        faces. None when no single-axis shift within the limit clears it.
        """
        limit, tolerance = SETTINGS['overlap_limit_mm'], SETTINGS['overlap_tolerance_mm']
        best = None
        for axis in range(3):
            for sign in (1, -1):
                def hit(distance):
                    moved = transform.copy()
                    moved[axis, 3] += sign * distance
                    return self.hit(part, name, moved)
                if hit(limit):
                    continue
                inside, outside = 0.0, limit
                while outside - inside > tolerance:
                    middle = (inside + outside) / 2
                    if hit(middle):
                        inside = middle
                    else:
                        outside = middle
                best = outside if best is None else min(best, outside)
        return best


def _grid(step, lo=0.0, hi=180.0):
    count = int(round((hi - lo) / step))
    return [lo + i * step for i in range(count + 1)]


def bands(predicate, step, tolerance, lo=0.0, hi=180.0, flags=None):
    """Maximal [start, end] intervals where predicate holds, edges refined by bisection.

    Edges are the outermost angles found inside the interval, within `tolerance`
    of the first angle outside it. Intervals narrower than `step` can be missed.
    `flags` supplies already-known predicate values on the grid.
    """
    angles = _grid(step, lo, hi)
    flags = [predicate(a) for a in angles] if flags is None else flags

    def edge(outside, inside):
        while abs(inside - outside) > tolerance:
            middle = (inside + outside) / 2
            if predicate(middle):
                inside = middle
            else:
                outside = middle
        return inside

    found, start = [], None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = angles[index] if index == 0 else edge(angles[index - 1], angles[index])
        if start is not None and (not flag or index == len(flags) - 1):
            end = angles[index] if flag else edge(angles[index], angles[index - 1])
            found.append([round(start, 2), round(end, 2)])
            start = None
    return found


def _inside(angle, intervals):
    return any(a <= angle <= b for a, b in intervals)


def _hip_sweep(scene, leg):
    """Contact bands of one hip print against every body part (boolean scan)."""
    lo, hi = scene.bounds(leg.hip, leg.transform(REST))
    result, unreachable = {}, {}
    for part, mesh in scene.body.items():
        # The print turns about a vertical axis, so its height range is fixed:
        # a part entirely above or below it cannot be touched at any hip angle.
        vertical = max(mesh.bounds[0][2] - hi[2], lo[2] - mesh.bounds[1][2])
        if vertical > 0:
            unreachable[part] = round(float(vertical), 3)
            result[part] = []
            continue
        result[part] = bands(lambda a: scene.hit(part, leg.hip, leg.transform(a)),
                             SETTINGS['scan_step_deg'], SETTINGS['angle_tolerance_deg'])
    return result, unreachable


def _nearest_edge(intervals, servo_sign):
    """Degrees from rest to the nearest interval in one servo direction, with that interval's edge."""
    best = None
    for a, b in intervals:
        if a <= REST <= b:
            continue
        edge = a if servo_sign > 0 else b
        angle = (edge - REST) * servo_sign
        if angle > 0 and (best is None or angle < best[0]):
            best = (angle, edge)
    return best


def _direction(scene, leg, sign, contact, profile, near):
    """Summary of one swing direction from rest. sign: +1 toward the middle, -1 toward the end."""
    step = SETTINGS['profile_step_deg']
    servo_sign = leg.middle_sign * sign
    by_part = {part: _nearest_edge(intervals, servo_sign) for part, intervals in contact.items()}
    first = min(((edge[0], part, edge[1]) for part, edge in by_part.items() if edge), default=None)
    limit = first[0] if first else REST
    samples = [REST + servo_sign * k * step for k in range(int(limit // step) + 1)]
    index = lambda servo: int(round(servo / step))
    ranges = {part: [min(values[index(s)] for s in samples), max(values[index(s)] for s in samples)]
              for part, values in profile.items()}
    if first:
        low = {'min_gap_mm': 0.0, 'min_gap_at_deg': round(first[0], 2),
               'min_gap_at_servo_deg': round(first[2], 2), 'min_gap_partner': first[1]}
    else:
        # No contact over the whole travel: refine the sampled minimum around its angle.
        gap, part, at = min((profile[part][index(s)], part, s) for part in profile for s in samples)
        for k in range(-9, 10):
            servo = at + k * step / 10
            if 0 <= servo <= 180 and (servo - REST) * servo_sign >= 0:
                gap, part, at = min((gap, part, at), min((scene.gap(p, leg.hip, leg.transform(servo)), p, servo) for p in profile))
        low = {'min_gap_mm': round(gap, 3), 'min_gap_at_deg': round((at - REST) * servo_sign, 2),
               'min_gap_at_servo_deg': round(at, 2), 'min_gap_partner': part}
    close = _nearest_edge(near, servo_sign)
    return {
        'body_direction': 'front' if leg.wide_x * sign > 0 else 'rear',
        'servo_direction': 'increasing' if servo_sign > 0 else 'decreasing',
        'travel_deg': REST,
        'first_contact_deg': round(first[0], 2) if first else None,
        'first_contact_servo_deg': round(first[2], 2) if first else None,
        'partner': first[1] if first else None,
        'first_contact_by_part_deg': {part: round(edge[0], 2) if edge else None for part, edge in by_part.items()},
        'free_deg': round(limit, 2),
        'gap_below_near_from_deg': round(close[0], 2) if close and close[0] <= limit else None,
        **low,
        'sampled_gap_range_by_part_mm': ranges,
    }


def _hip(scene, leg):
    step = SETTINGS['profile_step_deg']
    contact, unreachable = _hip_sweep(scene, leg)
    reachable = [part for part in BODY_PARTS if part not in unreachable]
    angles = _grid(step)
    profile = {part: [round(scene.gap(part, leg.hip, leg.transform(a)), 3) for a in angles] for part in reachable}
    rest_index = angles.index(REST)
    rest = {part: profile[part][rest_index] if part in profile
            else round(scene.gap(part, leg.hip, leg.transform(REST)), 3) for part in BODY_PARTS}
    rest_gap, rest_part = min((gap, part) for part, gap in rest.items())
    near_gap = SETTINGS['near_gap_mm']
    near = bands(lambda a: any(scene.gap(part, leg.hip, leg.transform(a)) < near_gap for part in reachable),
                 step, SETTINGS['angle_tolerance_deg'],
                 flags=[any(profile[part][i] < near_gap for part in reachable) for i in range(len(angles))])
    below = max([b for intervals in contact.values() for a, b in intervals if b < REST], default=None)
    above = min([a for intervals in contact.values() for a, b in intervals if a > REST], default=None)
    free = [0.0 if below is None else below, 180.0 if above is None else above]
    listed = []
    for part in BODY_PARTS:
        for a, b in contact[part]:
            band = {'partner': part, 'servo_deg': [a, b],
                    'toward_middle_deg': sorted([round(leg.deg(a), 2), round(leg.deg(b), 2)]),
                    'transient': bool(a > 0 and b < 180)}
            if band['transient']:
                # Free travel on both sides: record how shallow the overlap is.
                count = max(2, int(math.ceil((b - a) / SETTINGS['overlap_step_deg'])) + 1)
                depths = [(scene.clearing_shift(part, leg.hip, leg.transform(s)), s)
                          for s in (a + (b - a) * i / (count - 1) for i in range(count))]
                if all(depth is not None for depth, _ in depths):
                    depth, at = max(depths, key=lambda d: (d[0], -d[1]))
                    band['max_overlap_mm'] = round(depth, 2)
                    band['max_overlap_at_servo_deg'] = round(at, 2)
                else:
                    band['max_overlap_mm'] = None
            listed.append(band)
    listed.sort(key=lambda band: (band['servo_deg'], band['partner']))
    return {
        'leg': LEG_NAMES[leg.hip], 'print': f'{leg.hip}-v117.stl',
        'hip_shaft_xy_mm': [leg.hx, leg.hy],
        'wide_side_faces': 'front' if leg.wide_x > 0 else 'rear',
        'toward_middle_servo_direction': 'increasing' if leg.middle_sign > 0 else 'decreasing',
        'rest': {'servo_deg': REST, 'gap_mm': rest_gap, 'partner': rest_part, 'gaps_mm': rest},
        'toward_middle': _direction(scene, leg, 1, contact, profile, near),
        'toward_end': _direction(scene, leg, -1, contact, profile, near),
        'free_servo_deg': free,
        'contact_bands': listed,
        'near_bands_servo_deg': near,
        'out_of_reach_vertical_gap_mm': unreachable,
        'gap_profile_mm': {'servo_step_deg': step, **profile},
    }


def _free_hip_angles(hip_result, step):
    intervals = [band['servo_deg'] for band in hip_result['contact_bands']]
    return [a for a in _grid(step) if not _inside(a, intervals)]


def _foot(scene, leg, hip_result):
    step, coarse = SETTINGS['foot_grid_deg'], SETTINGS['foot_gap_grid_deg']
    rest = leg.transform(REST)
    own = bands(lambda a: scene.print_hit(leg.hip, rest, leg.foot, leg.transform(REST, a)),
                SETTINGS['scan_step_deg'], SETTINGS['angle_tolerance_deg'])
    own_gap, own_at = min((scene.print_gap(leg.hip, rest, leg.foot, leg.transform(REST, a)), a) for a in _grid(step))
    contacts, best = [], (float('inf'), None, None, None)
    hip_angles = _free_hip_angles(hip_result, step)
    for hip_deg in hip_angles:
        for foot_deg in _grid(step):
            transform = leg.transform(hip_deg, foot_deg)
            measure = hip_deg % coarse == 0 and foot_deg % coarse == 0
            for part in BODY_PARTS:
                bound = scene.far(part, leg.foot, transform)
                if bound == 0.0 and scene.hit(part, leg.foot, transform):
                    contacts.append({'hip_servo_deg': hip_deg, 'foot_servo_deg': foot_deg, 'partner': part})
                    best = min(best, (0.0, hip_deg, foot_deg, part))
                elif measure and bound < best[0]:
                    best = min(best, (scene.gap(part, leg.foot, transform), hip_deg, foot_deg, part))
    free = not own and not contacts
    return {
        'leg': LEG_NAMES[leg.hip], 'print': f'{leg.foot}-v117.stl', 'hip': leg.hip,
        'free_servo_deg': [0.0, 180.0] if free else None,
        'contact_free_on_grid': bool(free),
        'grid': {'hip_servo_deg': [hip_angles[0], hip_angles[-1]], 'hip_angles': len(hip_angles),
                 'step_deg': step, 'poses': len(hip_angles) * len(_grid(step)), 'gap_step_deg': coarse},
        'body_contacts': contacts[:50], 'body_contact_count': len(contacts),
        'min_body_gap_mm': round(best[0], 3), 'min_body_gap_partner': best[3],
        'min_body_gap_at': {'hip_servo_deg': best[1], 'foot_servo_deg': best[2]},
        'own_hip_print_contact_bands_servo_deg': own,
        'own_hip_print_min_gap_mm': round(own_gap, 3), 'own_hip_print_min_gap_at_servo_deg': own_at,
    }


def _neighbours(scene, legs, hips):
    """Same-side legs at their closest hip pose: both swung toward the middle as far as they go."""
    step = SETTINGS['neighbour_foot_grid_deg']
    result = []
    for side in (1, -1):
        pair = sorted([leg for leg in legs.values() if leg.side == side], key=lambda leg: -leg.hx)
        for front, rear in zip(pair, pair[1:]):
            angle = {leg.hip: leg.servo(hips[leg.hip]['toward_middle']['free_deg']) for leg in (front, rear)}
            at = lambda leg, foot=None: leg.transform(angle[leg.hip], foot)
            found = [(scene.print_gap(front.hip, at(front), rear.hip, at(rear)), [front.hip, rear.hip], {})]
            for a in _grid(step):
                found.append((scene.print_gap(front.foot, at(front, a), rear.hip, at(rear)), [front.foot, rear.hip], {front.foot: a}))
                found.append((scene.print_gap(front.hip, at(front), rear.foot, at(rear, a)), [front.hip, rear.foot], {rear.foot: a}))
                for b in _grid(step):
                    found.append((scene.print_gap(front.foot, at(front, a), rear.foot, at(rear, b)),
                                  [front.foot, rear.foot], {front.foot: a, rear.foot: b}))
            gap, prints, feet = min(found, key=lambda item: (item[0], item[1], sorted(item[2].items())))
            result.append({'legs': [front.hip, rear.hip],
                           'hip_servo_deg': {name: round(value, 2) for name, value in angle.items()},
                           'min_gap_mm': round(gap, 3), 'prints': prints, 'foot_servo_deg': feet,
                           'foot_grid_step_deg': step})
    return result


def analyse(directory, root=ROOT):
    """Compute the evidence for one design directory. Deterministic; a few seconds."""
    directory = Path(directory)
    assembly = json.loads((directory / 'assembly.json').read_text())
    hips = supported_hips(assembly)
    scene = Scene(directory, assembly, hips, root)
    legs = {hip: Leg(hip, assembly, scene.prints) for hip in hips}
    middle = sum(leg.hx for leg in legs.values()) / len(legs)
    for leg in legs.values():
        if (middle - leg.hx) * leg.wide_x <= 0:
            raise ValueError(f'{leg.hip}: the print\'s wide side does not face the middle of this body')
    hip_results = {hip: _hip(scene, legs[hip]) for hip in hips}
    foot_results = {legs[hip].foot: _foot(scene, legs[hip], hip_results[hip]) for hip in hips}
    # The same boolean scan with the upstream assembly's stack height.
    alternative = DATUMS['upstream_assembly_y_at_frame_top_mm']
    shift, same = 0.0, True
    for hip in hips:
        other, _ = _hip_sweep(scene, Leg(hip, assembly, scene.prints, seat_y=alternative))
        for part in BODY_PARTS:
            mine = [band['servo_deg'] for band in hip_results[hip]['contact_bands'] if band['partner'] == part]
            if len(mine) != len(other[part]):
                same = False
                continue
            shift = max([shift] + [abs(x - y) for a, b in zip(mine, other[part]) for x, y in zip(a, b)])
    return {
        'schema': SCHEMA,
        'design': directory.name,
        'scope': SCOPE,
        'not_modelled': NOT_MODELLED,
        'definitions': DEFINITIONS,
        'coordinates': assembly['coordinates'],
        'units': 'mm, servo degrees',
        'checker_sha256': sha(Path(__file__)),
        'inputs': input_hashes(directory, hips, root),
        'assembly_datums_sha256': canonical_sha(assembly_datums(assembly)),
        'assembly_datums': assembly_datums(assembly),
        'datums': DATUMS,
        'settings': SETTINGS,
        'datum_sensitivity': {
            'alternative': {'y_at_servo_flange_seat_mm': alternative,
                            'meaning': 'upstream assembly stack height: prints 0.216 mm higher'},
            'same_contact_bands': bool(same),
            'max_contact_edge_shift_deg': round(shift, 2),
        },
        'hips': hip_results,
        'feet': foot_results,
        'neighbours': _neighbours(scene, legs, hip_results),
    }


def dumps(evidence):
    """Stable text: two-space JSON with number lists kept on one line."""
    text = json.dumps(evidence, indent=2)
    number = r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?'
    return re.sub(r'\[\s+((?:%s,\s+)*%s)\s+\]' % (number, number),
                  lambda match: '[' + re.sub(r'\s+', ' ', match[1]) + ']', text) + '\n'


# ------------------------------------------------- manifest and motion compare

def _gap_at(hip, servo):
    """Smallest recorded gap at a servo angle (profile lookup; linear between whole degrees)."""
    step = hip['gap_profile_mm']['servo_step_deg']
    position = min(max(servo, 0.0), 180.0) / step
    low, high = int(math.floor(position)), int(math.ceil(position))
    best = None
    for part, values in hip['gap_profile_mm'].items():
        if part == 'servo_step_deg':
            continue
        value = values[low] + (values[high] - values[low]) * (position - low)
        if best is None or value < best[0]:
            best = (value, part)
    return round(best[0], 3), best[1]


def _classify_point(hip, servo, near_gap):
    for band in hip['contact_bands']:
        if band['servo_deg'][0] <= servo <= band['servo_deg'][1]:
            return {'kind': 'contact', 'partner': band['partner'], 'gap_mm': 0.0, 'band_servo_deg': band['servo_deg'],
                    **({'max_overlap_mm': band['max_overlap_mm']} if 'max_overlap_mm' in band else {})}
    gap, part = _gap_at(hip, servo)
    if gap < near_gap:
        return {'kind': 'near', 'partner': part, 'gap_mm': gap}
    return None


def _classify_path(hip, start, end, near_gap):
    """Worst finding while the servo travels between two targets (ends excluded: they are reported as targets)."""
    lo, hi = sorted((start, end))
    for band in hip['contact_bands']:
        a, b = band['servo_deg']
        if a < hi and b > lo and not (a <= start <= b or a <= end <= b):
            return {'kind': 'crosses-contact', 'partner': band['partner'], 'gap_mm': 0.0, 'band_servo_deg': band['servo_deg'],
                    **({'max_overlap_mm': band['max_overlap_mm']} if 'max_overlap_mm' in band else {})}
    step = hip['gap_profile_mm']['servo_step_deg']
    inner = [k * step for k in range(int(math.floor(lo / step)) + 1, int(math.ceil(hi / step)))]
    if inner:
        (gap, part), at = min((_gap_at(hip, a), a) for a in inner)
        if 0.0 < gap < near_gap:
            return {'kind': 'crosses-near', 'partner': part, 'gap_mm': gap, 'at_servo_deg': at}
    return None


ORDER = {'contact': 0, 'crosses-contact': 1, 'near': 2, 'crosses-near': 3}


def _expand(steps, poses):
    for step in steps:
        if 'repeat' in step:
            for _ in range(step['repeat']['count']):
                yield from _expand(step['repeat']['steps'], poses)
        elif 'pose' in step:
            yield poses[step['pose']]
        elif 'set' in step:
            yield step['set']


def compare(evidence, robot, motions, near_gap=None):
    """Compare the CAD free range with manifest soft limits and every stock motion.

    Pure arithmetic on the evidence: no geometry runtime. Findings are
    observations about this body design, not a gate on anyone's motion code.
    """
    near_gap = SETTINGS['near_gap_mm'] if near_gap is None else near_gap
    hips = evidence['hips']
    limits = []
    for joint in robot['joints']:
        name = joint['name']
        if name not in hips:
            continue
        hip = hips[name]
        lo, hi = joint['limits_deg']
        middle = 1 if hip['toward_middle_servo_direction'] == 'increasing' else -1
        # A stop is a contact band with no free travel beyond it. A transient
        # band has free travel on both sides and is listed, not counted as a stop.
        stops = [band['servo_deg'] for band in hip['contact_bands'] if not band['transient']]
        stop_lo = max([b for a, b in stops if b < REST], default=0.0)
        stop_hi = min([a for a, b in stops if a > REST], default=180.0)
        crossed = [{key: band[key] for key in ('partner', 'servo_deg', 'max_overlap_mm') if key in band}
                   for band in hip['contact_bands'] if band['transient'] and band['servo_deg'][0] < hi and band['servo_deg'][1] > lo]
        row = {'joint': name, 'limits_deg': [lo, hi], 'free_servo_deg': hip['free_servo_deg'],
               'between_stops_servo_deg': [stop_lo, stop_hi],
               'exceeds': bool(lo < stop_lo or hi > stop_hi),
               'transient_bands_within_limits': crossed, 'ends': {}}
        for label, value in (('low', lo), ('high', hi)):
            gap, partner = _gap_at(hip, value)
            found = _classify_point(hip, value, near_gap) or {'kind': 'clear', 'partner': partner, 'gap_mm': gap}
            beyond = max(0.0, stop_lo - value) if label == 'low' else max(0.0, value - stop_hi)
            row['ends'][label] = {'servo_deg': value, 'direction': 'toward_middle' if (value - REST) * middle > 0 else 'toward_end',
                                  'beyond_stop_deg': round(beyond, 2), **found}
        limits.append(row)
    for joint in robot['joints']:
        foot = evidence['feet'].get(joint['name'])
        if foot:
            free = foot['free_servo_deg']
            limits.append({'joint': joint['name'], 'limits_deg': list(joint['limits_deg']), 'free_servo_deg': free,
                           'exceeds': bool(free is None or joint['limits_deg'][0] < free[0] or joint['limits_deg'][1] > free[1])})
    found_motions = []
    for motion, steps in motions['motions'].items():
        state, worst = {}, {}
        for targets in _expand(steps, robot['poses']):
            for name, value in targets.items():
                if name not in hips:
                    continue
                candidates = []
                point = _classify_point(hips[name], value, near_gap)
                if point:
                    candidates.append({**point, 'servo_deg': value})
                if name in state and state[name] != value:
                    path = _classify_path(hips[name], state[name], value, near_gap)
                    if path:
                        candidates.append({**path, 'path_servo_deg': [state[name], value]})
                state[name] = value
                for candidate in candidates:
                    key = (ORDER[candidate['kind']], candidate['gap_mm'])
                    if name not in worst or key < worst[name][0]:
                        worst[name] = (key, candidate)
        for name in [j['name'] for j in robot['joints'] if j['name'] in worst]:
            found_motions.append({'motion': motion, 'joint': name, **worst[name][1]})
    return {
        'near_gap_mm': near_gap,
        'limits': limits,
        'limits_exceed_free_range': [row['joint'] for row in limits if row['exceeds']],
        'limits_cross_transient_bands': [row['joint'] for row in limits if row.get('transient_bands_within_limits')],
        'motions': found_motions,
        'motions_checked': len(motions['motions']),
        'scope': 'Manifest limits against the stops of the single-hip CAD sweep: a limit exceeds the free range '
                 'when it lies past a contact band with no free travel beyond it. A transient band inside the '
                 'limits, with free travel on both sides, is listed separately. Hip targets and the travel '
                 'between consecutive targets of each stock motion are classified against the same sweep. '
                 'Feet are contact-free on the recorded grid. CAD-derived, not physical.',
    }


def summary(evidence):
    """Compact per-joint digest for reports."""
    hips = {}
    for name, hip in evidence['hips'].items():
        hips[name] = {
            'rest_gap_mm': hip['rest']['gap_mm'], 'rest_partner': hip['rest']['partner'],
            'free_servo_deg': hip['free_servo_deg'],
            **{name: {key: hip[name][key] for key in ('first_contact_deg', 'first_contact_servo_deg', 'partner',
                                                     'gap_below_near_from_deg', 'min_gap_mm', 'min_gap_at_servo_deg', 'min_gap_partner')}
               for name in ('toward_middle', 'toward_end')},
            'transient_bands': [{key: band[key] for key in ('partner', 'servo_deg', 'max_overlap_mm') if key in band}
                                for band in hip['contact_bands'] if band['transient']],
        }
    feet = {name: {'free_servo_deg': foot['free_servo_deg'], 'min_body_gap_mm': foot['min_body_gap_mm'],
                   'own_hip_print_min_gap_mm': foot['own_hip_print_min_gap_mm']} for name, foot in evidence['feet'].items()}
    return {'design': evidence['design'], 'hips': hips, 'feet': feet,
            'neighbours_min_gap_mm': min(n['min_gap_mm'] for n in evidence['neighbours']),
            'datum_sensitivity': evidence['datum_sensitivity']}


def load_manifests(root=ROOT):
    import yaml
    return (yaml.safe_load((Path(root) / 'manifest/robot.yaml').read_text()),
            yaml.safe_load((Path(root) / 'manifest/motions.yaml').read_text()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('design', help=f'design directory name under {PRINTING}, or a path')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--write', action='store_true', help=f'compute and write {EVIDENCE} beside the design')
    group.add_argument('--check', action='store_true', help='verify committed evidence against current input hashes')
    args = parser.parse_args(argv)
    directory = design_dir(args.design)
    if args.check:
        status = verify(directory)
        print(json.dumps({'design': directory.name, **status}, indent=2))
        return 0 if status['fresh'] else 1
    try:
        evidence = analyse(directory)
    except (OSError, ValueError) as error:
        print(json.dumps({'design': directory.name, 'not_run': str(error)}, indent=2))
        return 2
    if args.write:
        (directory / EVIDENCE).write_text(dumps(evidence))
    robot, motions = load_manifests()
    print(dumps({'written': str(directory / EVIDENCE) if args.write else None,
                 'scope': SCOPE, **summary(evidence), 'manifest': compare(evidence, robot, motions)}), end='')
    return 0


if __name__ == '__main__':
    sys.exit(main())
