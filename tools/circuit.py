#!/usr/bin/env python3
"""Query current carrier design; export/check a derived aps-circuit/1 artifact.

inspect/query/path always read current design, never the publication artifact.
Native CAD bindings are independently checked; stale geometry suppresses
highlighting and export. Only external conductors are modeled, not internals.
"""
import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = 'assets/cad/instructions/'
ANNOTATIONS = 'manifest/circuit-annotations.json'
OUTPUT = 'reference/circuit/circuit.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def grid(address):
    require(isinstance(address, str) and re.fullmatch(r'[A-X](?:[1-9]|1[0-8])', address),
            f'Invalid carrier address: {address}')
    return ord(address[0]) - ord('A'), int(address[1:])


def routing_graph(routes):
    # All grid holes are candidate junctions, including intermediate contacts.
    # Bare runs are coplanar axis-aligned cylinders. Insulated spans only join
    # endpoints, not holes beneath insulation or crossing bare wires.
    points = {f'{chr(65+x)}{y}': (x, y) for x in range(24) for y in range(1, 19)}
    graph = {}
    for route in routes:
        addresses = route['addresses']
        require(len(addresses) >= 2, f'Incomplete route: {route["id"]}')
        for a, b in zip(addresses, addresses[1:]):
            ax, ay = grid(a)
            bx, by = grid(b)
            dx, dy = bx-ax, by-ay
            require(dx or dy, f'Degenerate route: {route["id"]}')
            if route['kind'] == 'bare':
                require(not dx or not dy, 'Diagonal bare routes need a geometry adapter')
                ordered = sorted(((x-ax)*dx+(y-ay)*dy, p)
                                 for p, (x, y) in points.items()
                                 if (x-ax)*dy == (y-ay)*dx and
                                 0 <= (x-ax)*dx+(y-ay)*dy <= dx*dx+dy*dy)
                segment = [p for _, p in ordered]
            else:
                segment = [a, b]
            for u, v in zip(segment, segment[1:]):
                graph.setdefault(u, {}).setdefault(v, set()).add(route['id'])
                graph.setdefault(v, {}).setdefault(u, set()).add(route['id'])
    components, unseen = [], set(graph)
    while unseen:
        queue = [min(unseen, key=grid)]
        connected = set(queue)
        for address in queue:
            for other in sorted(graph[address], key=grid):
                if other not in connected:
                    connected.add(other)
                    queue.append(other)
        components.append(connected)
        unseen -= connected
    return graph, components


def build(root=ROOT):
    """Read current files each call. Return topology even if CAD binding is stale."""
    root = Path(root)
    sources = []

    def read(path, as_json=True):
        raw = (root / path).read_bytes()
        sources.append(dict(path=path, sha256=digest(raw)))
        return json.loads(raw) if as_json else raw

    docs = {name: read(INSTRUCTIONS + name + '.json') for name in (
        'underside-wiring', 'carrier-connections', 's3-installation',
        'servo-hub-installation', 'converter-installation', 'assembly-cad-snapshot')}
    annotations = read(ANNOTATIONS)
    require(annotations['schema'] == 'sim2real-circuit-annotations/1', 'Unknown annotations schema')
    require(not ({'nets', 'routes'} & annotations.keys()), 'Net membership belongs in native routing records')
    interface = read('reference/sesame-s3-interface.json')
    firmware_source = read('firmware/sesame-s3/manifest_generated.h', False).decode()
    read('tools/circuit.py', False)  # Adapter changes invalidate old exports too.
    snapshot = docs['assembly-cad-snapshot']
    issues = []
    for document in snapshot['documents'].values():
        raw = read(document['path'], False)
        if digest(raw) != document['saved_file_sha256']:
            issues.append('Native CAD changed; refresh snapshot: ' + document['path'])
    underside, carrier = docs['underside-wiring'], docs['carrier-connections']
    require(not underside['unresolved'], 'Unresolved routing cannot establish connectivity')
    routes = [dict(id=f'underside.wire.{i}', addresses=a, kind='bare', evidence=['underside-wiring'])
              for i, a in enumerate(underside['traced_routes'], 1)]
    routes += [dict(id=f'jumper.insulation.{j["id"]}', addresses=j['addresses'],
                    kind='insulated', evidence=['carrier-connections']) for j in carrier['jumpers']]
    require(len({r['id'] for r in routes}) == len(routes), 'Duplicate route IDs')
    _, components = routing_graph(routes)

    hardware = {}
    for connection in docs['converter-installation']['connections']:
        a = connection['carrier_address']
        hardware[a] = [f'{prefix}.{a}' for prefix in
                       ('pins', 'top_solder', 'converter_hole_fill', 'carrier_hole_fill', 'bottom_solder')]
    for a in sum(docs['servo-hub-installation']['placement']['confirmed_socket_addresses'], []):
        hardware[a] = [f'hub.socket_contact.{a}', f'hub.socket_tail.{a}', f'SocketBottomSolder_{a}']
    footprint = docs['s3-installation']['footprint']
    for column in footprint['columns']:
        for row in footprint['rows']:
            a = f'{column}{row}'
            hardware[a] = [f's3.{kind}.{a}' for kind in ('socket_contact', 'socket_tail', 'bottom_solder')]
    for strip in carrier['short_tail_headers']:
        for a in strip['addresses']:
            hardware[a] = [f'auxiliary.pin.{a}', f'aux.solder.{a}']

    evidence = dict(annotations['evidence'])
    for name in docs:
        evidence[name] = dict(kind='current-design-record', path=INSTRUCTIONS + name + '.json')
    for item in annotations['evidence']:
        evidence[item]['path'] = ANNOTATIONS
    evidence['firmware'] = dict(kind='software-assignment', path='firmware/sesame-s3/manifest_generated.h',
                                note='An assignment does not establish a physical connection.')
    evidence['interface'] = dict(kind='pin-location-record', path='reference/sesame-s3-interface.json')
    pins = [dict(p) for p in annotations['pins']]
    for connection in docs['converter-installation']['connections']:
        pins.append(dict(id='converter.' + connection['terminal'], component='converter',
                         address=connection['carrier_address'], evidence=['converter-installation']))
    for address, signal in interface['clock_measurement']['pin_binding_provenance']['installed_row_usb_to_far'].items():
        pins.append(dict(id='s3.' + signal, component='s3', address=address, evidence=['interface']))
    for address, terminal in carrier['instructor_confirmed_pinout'].items():
        if terminal['purpose'] == 'OLED':
            pins.append(dict(id='aux.' + terminal['signal'], component='aux', address=address,
                             evidence=['carrier-connections']))
    # Unnamed contacts are queryable without inventing board pin functions.
    named_addresses = {p['address'] for p in pins}
    for address in sorted(set(hardware) - named_addresses, key=grid):
        pins.append(dict(id='carrier.' + address, component='carrier', address=address,
                         evidence=['assembly-cad-snapshot']))
    require(len({p['id'] for p in pins}) == len(pins), 'Duplicate pin IDs')
    pin_ids = {p['id'] for p in pins}
    for unknown in annotations['unknowns']:
        require(set(unknown['pins']) <= pin_ids, 'Unknown pin in uncertainty annotation')
        require(unknown['evidence'] and set(unknown['evidence']) <= evidence.keys(),
                'Unknown uncertainty evidence')
    for label in annotations['netLabels']:
        require(label['anchorPin'] in pin_ids, 'Unknown net-label anchor pin')
        require(set(label) == {'id', 'label', 'colour', 'anchorPin'},
                'Net labels annotate a single anchor, not membership')
    require(len([p['address'] for p in pins if p['address'] is not None]) ==
            len({p['address'] for p in pins if p['address'] is not None}), 'Ambiguous pin address')
    routed = set().union(*components) if components else set()
    for pin in pins:
        address = pin['address']
        if address is not None:
            grid(address)
            require(address in hardware, f'Pin outside documented footprint: {pin["id"]}')
        state = pin.get('state', 'unknown')
        require(state in ('unknown', 'no_connect'), 'Connected state is derived, not annotated')
        require(not (state == 'no_connect' and address in routed),
                f'No-connect annotation conflicts with current routing: {pin["id"]}; update design annotation')
        pin['state'] = 'connected' if address in routed else state
        require(pin['evidence'] and set(pin['evidence']) <= evidence.keys(), 'Unknown pin evidence')

    visible = [o for o in snapshot['objects'] if o['export_visible_geometry']]
    counts = Counter(o['id'] for o in visible)
    native = {o['id']: o for o in visible}
    for pin in pins:
        pin['partIds'] = hardware.get(pin['address'], [])
        for part_id in pin['partIds']:
            if counts[part_id] != 1:
                issues.append('Missing or ambiguous native contact: ' + part_id)
    for route in routes:
        part = native.get(route['id'])
        if not part or part['construction_metadata'].get('Addresses') != route['addresses']:
            issues.append('Native route disagrees with current routing: ' + route['id'])
    saved_routes = {p for p in native if p.startswith(('underside.wire.', 'jumper.insulation.'))}
    if saved_routes != {r['id'] for r in routes}:
        issues.append('Native route inventory differs from current routing')

    nets, claimed = [], set()
    for addresses in components:
        net_routes = [r for r in routes if r['addresses'][0] in addresses]
        members = [p['id'] for p in pins if p['address'] in addresses]
        styles = [s for s in annotations['netLabels'] if s['anchorPin'] in members]
        if len(styles) == 1:
            net_id, label, colour = (styles[0][key] for key in ('id', 'label', 'colour'))
        else:
            # Split/merged/new components are not forced into historical nets.
            net_id = 'route-' + min(addresses, key=grid).lower()
            label = ' / '.join(s['label'] for s in styles) or net_id
            colour = '#888888'
        part_ids, insulation = [], []
        for route in net_routes:
            number = route['id'].split('.')[-1]
            if route['kind'] == 'bare':
                part_ids += [route['id']] + [f'underside.solder.{number}.{a}' for a in route['addresses']]
            else:
                # Keep APS highlight IDs compatible; identify nonconductors too.
                part_ids += [f'jumper.core.{number}', route['id']]
                insulation.append(route['id'])
                part_ids += [f'jumper.solder.{a}' for a in route['addresses']]
        for a in addresses:
            part_ids += hardware.get(a, [])
        part_ids = sorted(set(part_ids))
        for p in part_ids:
            if counts[p] != 1:
                issues.append('Missing or ambiguous native part: ' + p)
            require(p not in claimed, 'Native part claimed by multiple nets: ' + p)
            claimed.add(p)
        nets.append(dict(id=net_id, label=label, colour=colour, layer='external',
                         pins=sorted(members), addresses=sorted(addresses, key=grid),
                         routes=[r['addresses'] for r in net_routes], routeIds=[r['id'] for r in net_routes],
                         partIds=part_ids, conductivePartIds=sorted(set(part_ids)-set(insulation)),
                         insulationPartIds=sorted(insulation),
                         evidence=sorted({e for r in net_routes for e in r['evidence']})))
    require(len({n['id'] for n in nets}) == len(nets), 'Duplicate net labels')
    if issues:
        for pin in pins:
            pin['partIds'] = []
        for net in nets:
            net['partIds'] = net['conductivePartIds'] = net['insulationPartIds'] = []
    firmware = []
    for constant, role in [('SDA', 'SDA'), ('SCL', 'SCL'), ('OE', 'OE'), ('CLOCK_MEASURE_GPIO', 'clock capture')]:
        matches = re.findall(r'constexpr uint32_t ' + constant + r' = (\d+);', firmware_source)
        require(len(matches) == 1, 'Cannot resolve firmware constant: ' + constant)
        pin_id = 's3.GPIO' + matches[0]
        if pin_id not in pin_ids:
            # A software GPIO without a documented carrier location remains
            # unlocated; do not infer a physical footprint from a declaration.
            pins.append(dict(id=pin_id, component='s3', address=None, state='unknown',
                             evidence=['firmware'], partIds=[]))
            pin_ids.add(pin_id)
        firmware.append(dict(id=constant, pin=pin_id, role=role,
                             layer='software', evidence=['firmware']))
    result = dict(schema='aps-circuit/1', id='sesame-course-carrier', generatedBy='tools/circuit.py',
                  scope=annotations['scope'], pins=sorted(pins, key=lambda p: p['id']),
                  nets=sorted(nets, key=lambda n: n['id']), routes=routes, firmware=firmware,
                  unknowns=annotations['unknowns'], evidence=evidence,
                  cadBinding=dict(valid=not issues, issues=sorted(set(issues))),
                  sources=sorted(sources, key=lambda s: s['path']))
    result['fingerprint'] = digest(canonical(result))
    return result


def query(graph, pin_id):
    pin = next((p for p in graph['pins'] if p['id'] == pin_id), None)
    require(pin is not None, 'Unknown pin ID: ' + pin_id)
    return dict(item=pin, external_nets=[n for n in graph['nets'] if pin_id in n['pins']],
                firmware_assignments=[f for f in graph['firmware'] if f['pin'] == pin_id],
                unknowns=[u for u in graph['unknowns'] if pin_id in u['pins']],
                scope=graph['scope'], cadBinding=graph['cadBinding'], fingerprint=graph['fingerprint'])


def path(graph, first, second):
    a, b = query(graph, first)['item'], query(graph, second)['item']
    topology, _ = routing_graph(graph['routes'])
    start, end = a['address'], b['address']
    previous, queue = {start: None}, deque([start])
    while queue:
        current = queue.popleft()
        if current == end and current is not None:
            addresses = []
            while current is not None:
                addresses.append(current)
                current = previous[current]
            addresses.reverse()
            route_ids = sorted({r for u, v in zip(addresses, addresses[1:]) for r in topology[u][v]})
            return dict(connected=True, layer='external', pins=[first, second],
                        addresses=addresses, routeIds=route_ids, fingerprint=graph['fingerprint'],
                        cadBinding=graph['cadBinding'], scope=graph['scope'])
        for other in sorted(topology.get(current, {}), key=grid):
            if other not in previous:
                previous[other] = current
                queue.append(other)
    return dict(connected=False, layer='external', pins=[first, second],
                note='No recorded external path; module internals and physical continuity are not established.',
                fingerprint=graph['fingerprint'], cadBinding=graph['cadBinding'], scope=graph['scope'])


def check(root=ROOT, artifact=None):
    """Reject changed sources, tampering, old adapters and stale native geometry."""
    current = build(root)
    require(current['cadBinding']['valid'], 'Stale CAD binding: ' + '; '.join(current['cadBinding']['issues']))
    saved = json.loads(Path(artifact or Path(root) / OUTPUT).read_text())
    require(saved == current, 'Stale or modified circuit export; regenerate from current design')
    return dict(valid=True, fingerprint=current['fingerprint'], nets=len(current['nets']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Design checkout (including tools/circuit.py)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('inspect')
    sub.add_parser('query').add_argument('pin')
    p = sub.add_parser('path')
    p.add_argument('first'); p.add_argument('second')
    for command in ('export', 'check'):
        sub.add_parser(command).add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'check':
            result = check(args.root, args.output)
        else:
            graph = build(args.root)
            if args.command == 'inspect':
                result = graph
            elif args.command == 'query':
                result = query(graph, args.pin)
            elif args.command == 'path':
                result = path(graph, args.first, args.second)
            else:
                require(graph['cadBinding']['valid'], 'Stale CAD binding: ' + '; '.join(graph['cadBinding']['issues']))
                output = args.output or args.root / OUTPUT
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + '\n')
                result = dict(output=str(output), fingerprint=graph['fingerprint'], nets=len(graph['nets']))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps(dict(error=str(error))), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
