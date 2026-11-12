#!/usr/bin/env python3
"""Ask what a joint does before commanding it; check targets before sending them.

    python3 tools/joints.py query L2            # where it points, how far it travels, what stops it
    python3 tools/joints.py query all
    python3 tools/joints.py check L2 90 180 90  # firmware degrees, legs fitted
    python3 tools/joints.py check L1 45 R2 45   # several joints in one call
    python3 tools/joints.py check pose 135 45 45 135 0 180 0 180   # firmware `pose` order
    python3 tools/joints.py check --bare-horns L2 0 90 180         # legs off

Standard library only. Reads the generated firmware interface and the course
body's leg-clearance evidence, and refuses to answer when either no longer
follows from its sources. It never opens a device and never sends anything.
Exit codes: 0 answered / every target inside the travel, 1 a target outside
it, 2 cannot answer (stale or missing data, unknown joint, bad arguments).
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import leg_clearance

ROOT = Path(__file__).resolve().parents[1]
INTERFACE = 'reference/sesame-s3-interface.json'
COURSE_BODY = 'internal-frame-s3'
REST = 90
PLACE = {'front_left': 'front-left', 'front_right': 'front-right', 'back_left': 'rear-left', 'back_right': 'rear-right'}
WORDS = {'forward': 'forward', 'back': 'backward', 'out_left': 'straight out to the left',
         'out_right': 'straight out to the right', 'down': 'down, toward the ground', 'up': 'up', 'out': 'level, straight out'}


class CannotAnswer(Exception):
    """The committed data is missing, stale or self-contradictory."""


def require(condition, message):
    if not condition:
        raise CannotAnswer(message)


def load(root=ROOT, design=COURSE_BODY):
    """Interface and leg-clearance evidence, only if both still follow from their sources."""
    root = Path(root)
    try:
        interface = json.loads((root / INTERFACE).read_text())
    except (OSError, ValueError) as error:
        raise CannotAnswer(f'Cannot read {INTERFACE}: {error}')
    recorded = interface.get('source_sha256')
    require(isinstance(recorded, dict) and 'manifest/robot.yaml' in recorded,
            f'{INTERFACE} records no manifest hashes; run `uv run python tools/generate_s3_firmware.py`')
    for name, digest in recorded.items():
        path = root / name
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                f'Stale firmware interface: {name} changed since {INTERFACE} was generated; '
                'run `uv run python tools/generate_s3_firmware.py`')
    directory = root / leg_clearance.PRINTING / design
    try:
        status = leg_clearance.verify(directory, root)
        require(status['fresh'], f'Stale leg-clearance evidence for {design}: ' + '; '.join(status['stale'])
                + f'; run `uv run python tools/leg_clearance.py {design} --write`')
        evidence = json.loads((directory / leg_clearance.EVIDENCE).read_text())
    except (OSError, ValueError) as error:
        raise CannotAnswer(f'Cannot read leg-clearance evidence for {design}: {error}')
    joints = {joint['name']: joint for joint in interface['joint_map']}
    require(interface['joint_directions']['rest_firmware_deg'] == REST, 'Rest is not 90 in the interface')
    for name, hip in evidence['hips'].items():
        # The side the CAD sweep finds clear of the head cover is the side a fitted hip turns to.
        side = [0, REST] if hip['toward_end']['servo_direction'] == 'decreasing' else [REST, 180]
        require(name in joints and joints[name]['fitted_travel_firmware_deg'] == side,
                f'{name}: manifest directions and leg-clearance evidence disagree; rely on neither')
    require(set(evidence['feet']) | set(evidence['hips']) == set(joints), 'Interface and evidence list different joints')
    return interface, evidence


def describe(name, interface, evidence):
    joints = {joint['name']: joint for joint in interface['joint_map']}
    require(name in joints, f'Unknown joint: {name}. Joints: ' + ' '.join(joints))
    joint = joints[name]
    hip = joint['role'] == 'hip'
    points, (low, high) = joint['points_at_firmware_deg'], joint['fitted_travel_firmware_deg']
    part = 'leg' if hip else 'foot'
    place = PLACE[joint['leg']]
    where = {'leg': joint['leg'], 'role': joint['role'], 'words': f'{place} {joint["role"]}'}
    in_words = {deg: f'{part} {WORDS[points[deg]]}' for deg in ('0', '90', '180')}
    channel = {'default': joint['default_nvs_channel'], 'status': joint['mapping_status'],
               'hardware_verified': joint['hardware_verified_pca_channel']}
    positive = points['180' if joint['manifest_sign'] > 0 else '0']
    status = f'CAD-derived for {evidence["design"]}; not measured on any robot'
    if hip:
        cad = evidence['hips'][name]
        far, near = (0, 180) if low == 0 else (180, 0)        # far end of the travel, and the other side
        blocked, free = cad['toward_middle'], cad['toward_end']
        neighbour = next(other['name'] for other in interface['joint_map'] if other['role'] == 'hip'
                         and other['name'] != name and other['leg'].split('_')[1] == joint['leg'].split('_')[1])
        travel_words = (f'From Rest at 90° {WORDS[points[str(far)]]} to {far}°, toward the {place.split("-")[0]} '
                        'end of the body. One way only, in the horizontal plane; a hip never swings up or down.')
        limits_words = ('Joint and run modes accept this range. It reaches 10° past Rest on the other side only '
                        'because stock walk and point go there. Bench mode accepts any angle from 0 to 180.')
        internal = f'q = (degrees - 90) x sign. Positive q turns the leg {WORDS[positive]}, toward its own end of the body.'
        beyond = {
            'side': f'{"above" if near == 180 else "below"} 90°',
            'direction': f'{WORDS[points[str(near)]]}, toward the middle of the body',
            'cad_first_contact': {'partner': blocked['partner'], 'servo_deg': blocked['first_contact_servo_deg'],
                                  'degrees_past_rest': blocked['first_contact_deg']},
            'cad_later_contacts': [{'partner': other, 'degrees_past_rest': angle}
                                   for other, angle in blocked['first_contact_by_part_deg'].items()
                                   if angle is not None and other != blocked['partner']],
            'neighbouring_leg': neighbour,
            'leg_to_leg': f'Contact between two legs is not modelled. Turned this way the leg also swings toward the {neighbour} leg on the same side.',
            'status': status,
        }
        bands = [{key: band[key] for key in ('partner', 'servo_deg', 'max_overlap_mm') if key in band}
                 for band in cad['contact_bands'] if band['transient'] and low < band['servo_deg'][1] and band['servo_deg'][0] < high]
        within = {
            'cad_overlap_bands': bands,
            'cad_smallest_gap': None if bands else {'mm': free['min_gap_mm'], 'partner': free['min_gap_partner'],
                                                    'servo_deg': free['min_gap_at_servo_deg']},
            'note': ('Nominal CAD shows a shallow overlap with free travel on both sides; the instructor-confirmed travel passes through it.'
                     if bands else 'No contact in nominal CAD over the whole travel.'),
            'status': status,
        }
    else:
        cad = evidence['feet'][name]
        travel_words = 'The whole 0° to 180°: a foot swings in a vertical plane, down one way from Rest and up the other.'
        limits_words = 'The same 0° to 180° as the servo.'
        internal = f'q = (degrees - 90) x sign. Positive q swings the foot {WORDS[positive]}.'
        beyond = {'servo_range': 'Travel is the servo\'s whole 0° to 180°; nothing lies beyond it.'}
        within = {
            'cad_contact_free': cad['contact_free_on_grid'],
            'cad_smallest_gap': {'mm': cad['min_body_gap_mm'], 'partner': cad['min_body_gap_partner']},
            'note': 'Checked on a grid of hip and foot angles against the printed body; the ground is not modelled.',
            'status': status,
        }
    return {
        'joint': name, 'where': where, 'rest_deg': REST,
        'points_at_deg': points, 'in_words': in_words,
        'fitted_travel_deg': [low, high], 'fitted_travel_words': travel_words,
        'soft_limits_deg': joint['soft_firmware_deg'], 'soft_limits_words': limits_words,
        'sign': joint['manifest_sign'], 'internal_q': internal,
        'hub_channel': channel,
        'beyond_fitted_travel': beyond, 'within_fitted_travel': within,
    }


def provenance(interface, evidence):
    design = evidence['design']
    return {
        'evidence': {
            'directions': {'kind': 'instructor-confirmed on a built robot', 'source': interface['joint_directions']['source'],
                           'path': f'{INTERFACE} joint_map[]'},
            'limits_sign_channel': {'kind': 'reference manifest; channel is a recommended default, not physically verified',
                                    'path': INTERFACE, 'manifest_id': interface['manifest_id']},
            'contact': {'kind': 'CAD-derived, not physical', 'design': design,
                        'path': f'{leg_clearance.PRINTING}/{design}/{leg_clearance.EVIDENCE}',
                        'not_modelled': evidence['not_modelled'] + ['contact between two legs, beyond one sampled pose']},
            'measured_on_your_robot': 'nothing',
        },
        'scope': ('The reference build with its legs fitted. Directions were confirmed by the instructor on a built robot; '
                  'contact figures are nominal CAD for the course body; nothing here was measured on your robot. '
                  'If its wiring, signs or horn positions differ from the reference, this does not describe it: establish '
                  'them from one observed movement first. Bench mode accepts any angle from 0 to 180, so the firmware does '
                  'not stop a target outside the fitted travel. This tool reads committed design data only; it never opens '
                  'a device and never sends a command. Owners may choose other travel on their own robots.'),
    }


def query(name, root=ROOT, design=COURSE_BODY):
    interface, evidence = load(root, design)
    if name == 'all':
        result = {'joints': {joint['name']: describe(joint['name'], interface, evidence) for joint in interface['joint_map']},
                  'pose_order': [joint['name'] for joint in interface['joint_map']]}
    else:
        result = describe(name, interface, evidence)
    return {**result, **provenance(interface, evidence)}


def parse_targets(tokens, order):
    """`NAME DEG...` groups, or `pose` followed by one angle per joint in firmware order."""
    targets, current = [], None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == 'pose':
            values = tokens[index + 1:index + 1 + len(order)]
            require(len(values) == len(order), f'pose needs {len(order)} angles in the order ' + ' '.join(order))
            for name, value in zip(order, values):
                targets.append((name, number(value)))
            index += 1 + len(order)
            current = None
            continue
        if token in order:
            current = token
        else:
            require(current is not None, f'Expected a joint name ({" ".join(order)}) or `pose` before {token}')
            targets.append((current, number(token)))
        index += 1
    require(targets, 'No targets: give a joint name followed by firmware degrees')
    named = {name for name, _ in targets}
    for token in tokens:
        require(token not in order or token in named, f'{token} has no target')
    return targets


def number(text):
    try:
        value = float(text)
    except ValueError:
        raise CannotAnswer(f'Not a joint name or an angle: {text}')
    require(value == value and abs(value) != float('inf'), f'Not a finite angle: {text}')
    return value


def assess(name, degrees, entry, bare_horns):
    """None when the target is acceptable, otherwise one sentence saying why not."""
    shown = f'{degrees:g}'
    if not 0 <= degrees <= 180:
        return f'{name} {shown}° is outside the servo\'s 0–180° range.'
    low, high = entry['fitted_travel_deg']
    if bare_horns or low <= degrees <= high:
        return None
    beyond = entry['beyond_fitted_travel']
    contact = beyond['cad_first_contact']
    past = abs(degrees - REST)
    reach = ('this target is past it' if past >= contact['degrees_past_rest']
             else f'this target stops {contact["degrees_past_rest"] - past:.0f}° short of it')
    soft_low, soft_high = entry['soft_limits_deg']
    soft = (f' It is inside the soft limits {soft_low}–{soft_high}° only because stock walk and point go there.'
            if soft_low <= degrees <= soft_high else '')
    return (f'{name} {shown}° turns the {entry["where"]["words"].rsplit(" ", 1)[0]} leg {beyond["direction"]}; '
            f'fitted travel is {low}–{high}°. In CAD the leg meets the {contact["partner"].replace("-", " ")} '
            f'{contact["degrees_past_rest"]:.0f}° past Rest (at {contact["servo_deg"]:.0f}°); {reach}. '
            f'Contact between two legs is not modelled; turned this way it swings toward the {beyond["neighbouring_leg"]} leg.{soft}')


def check(tokens, bare_horns=False, root=ROOT, design=COURSE_BODY):
    """(exit code, lines). Reads design data only; nothing is sent anywhere."""
    interface, evidence = load(root, design)
    order = [joint['name'] for joint in interface['joint_map']]
    targets = parse_targets(tokens, order)
    entries = {name: describe(name, interface, evidence) for name in {name for name, _ in targets}}
    problems = []
    for name, degrees in targets:
        problem = assess(name, degrees, entries[name], bare_horns)
        if problem and problem not in problems:
            problems.append(problem)
    names = [name for name in order if name in entries]
    travel = ', '.join(f'{name} {entries[name]["fitted_travel_deg"][0]}–{entries[name]["fitted_travel_deg"][1]}°' for name in names)
    mode = ('bare horns, legs off: the full 0–180° is allowed and the fitted travel is not applied'
            if bare_horns else f'legs fitted; fitted travel {travel}')
    if not problems:
        return 0, [f'OK: {len(targets)} target(s) on {" ".join(names)} ({mode}). Reference build; nothing was sent.']
    return 1, [f'NOT OK: {problem}' for problem in problems] + [
        f'{len(problems)} target(s) outside the travel ({mode}). Reference build; nothing was sent. '
        f'`python3 tools/joints.py query {names[0]}` explains the joint.']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=ROOT, help='design checkout (default: this one)')
    parser.add_argument('--design', default=COURSE_BODY, help='printing design whose leg-clearance evidence is used')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('query', help='what one joint does').add_argument('joint', help='joint name, or all')
    checker = sub.add_parser('check', help='are these targets inside the fitted travel?')
    checker.add_argument('--bare-horns', action='store_true', help='legs are off: allow the full 0-180')
    checker.add_argument('targets', nargs='+', help='NAME DEG [DEG ...] [NAME DEG ...] or pose D0 .. D7')
    args = parser.parse_args(argv)
    try:
        if args.command == 'query':
            print(json.dumps(query(args.joint, args.root, args.design), ensure_ascii=False, indent=2))
            return 0
        code, lines = check(args.targets, args.bare_horns, args.root, args.design)
        print('\n'.join(lines))
        return code
    except CannotAnswer as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
