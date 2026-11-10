"""Live-design circuit queries and fail-closed publication, no CAD runtime needed."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('circuit', ROOT / 'tools/circuit.py')
circuit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(circuit)


class CircuitTests(unittest.TestCase):
    def test_checked_in_publication_matches_current_design(self):
        self.assertTrue(circuit.check(ROOT)['valid'])

    @classmethod
    def setUpClass(cls):
        cls.baseline = circuit.build(ROOT)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='circuit-test-', dir=ROOT / 'tests')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for source in self.baseline['sources']:
            target = self.root / source['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source['path'], target)
        self.artifact = self.root / circuit.OUTPUT
        self.artifact.parent.mkdir(parents=True)
        self.artifact.write_text(json.dumps(self.baseline))

    def mutate(self, path, callback):
        target = self.root / path
        data = json.loads(target.read_text())
        callback(data)
        target.write_text(json.dumps(data))

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'tools/circuit.py'),
                               '--root', str(self.root), *args], capture_output=True, text=True)

    def test_baseline_and_reproducible_publication(self):
        self.assertEqual(len(self.baseline['nets']), 8)
        self.assertEqual(sum(len(n['partIds']) for n in self.baseline['nets']), 141)
        # Observed APS wiring-checks baseline, without an APS runtime dependency
        # or a copied editable membership fixture. Review when design changes.
        membership = {n['id']: n['partIds'] for n in self.baseline['nets']}
        self.assertEqual(circuit.digest(circuit.canonical(membership)),
                         '2abbbc99661d4fd0a1de220b6854c64866d4c23ad2c78df2f5a5fee1250cca30')
        self.assertEqual(self.baseline['cadBinding'], {'valid': True, 'issues': []})
        self.assertEqual(circuit.build(self.root), self.baseline)
        self.assertTrue(circuit.check(self.root)['valid'])
        self.assertEqual(self.cli('export').returncode, 0)
        self.assertEqual(json.loads(self.artifact.read_text()), self.baseline)
        self.assertEqual(self.cli('check').returncode, 0)

    def test_oe_unknowns_and_software_are_not_wires(self):
        answer = circuit.query(self.baseline, 'hub.OE')
        self.assertEqual(answer['item']['state'], 'no_connect')
        self.assertEqual(answer['external_nets'], [])
        self.assertIn('hub.socket_tail.A7', answer['item']['partIds'])
        self.assertTrue(answer['unknowns'])
        gpio = circuit.query(self.baseline, 's3.GPIO7')
        self.assertEqual(gpio['item']['state'], 'unknown')
        self.assertEqual(gpio['firmware_assignments'][0]['role'], 'OE')
        for first, second in [('hub.OE', 's3.GPIO7'), ('converter.IN-', 'converter.OUT-'),
                              ('switch.IN', 'switch.OUT'), ('hub.CH15.SIGNAL', 's3.GPIO4')]:
            self.assertFalse(circuit.path(self.baseline, first, second)['connected'])

    def test_paths_follow_intermediate_bare_junctions(self):
        for first, second in [('s3.3V3', 'hub.VCC'), ('s3.GPIO2', 'hub.SDA'),
                              ('s3.GPIO3', 'hub.SCL'), ('s3.GND', 'converter.OUT-')]:
            result = circuit.path(self.baseline, first, second)
            self.assertTrue(result['connected'])
            self.assertTrue(result['routeIds'])
        self.assertIn('L13', circuit.path(self.baseline, 's3.3V3', 'hub.VCC')['addresses'])

    def test_route_edit_changes_live_query_and_rejects_stale_export(self):
        # Move X15-X16 to X16-X17: battery+ now joins battery-, not switch.IN.
        self.mutate(circuit.INSTRUCTIONS + 'underside-wiring.json',
                    lambda d: d['traced_routes'].__setitem__(15, ['X16', 'X17']))
        changed = circuit.build(self.root)
        self.assertFalse(circuit.path(changed, 'switch.IN', 'battery.+')['connected'])
        self.assertTrue(circuit.path(changed, 'battery.-', 'battery.+')['connected'])
        self.assertEqual(circuit.query(changed, 'switch.IN')['item']['state'], 'unknown')
        self.assertNotEqual(changed['fingerprint'], self.baseline['fingerprint'])
        self.assertFalse(changed['cadBinding']['valid'])
        self.assertTrue(all(not n['partIds'] for n in changed['nets']))
        result = self.cli('path', 'battery.+', 'battery.-')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['connected'])
        self.assertFalse(json.loads(result.stdout)['cadBinding']['valid'])
        old_bytes = self.artifact.read_bytes()
        self.assertNotEqual(self.cli('export').returncode, 0)
        self.assertEqual(self.artifact.read_bytes(), old_bytes)
        with self.assertRaisesRegex(ValueError, 'Stale CAD binding'):
            circuit.check(self.root)

    def test_removed_route_splits_topology(self):
        self.mutate(circuit.INSTRUCTIONS + 'underside-wiring.json', lambda d: d['traced_routes'].pop())
        changed = circuit.build(self.root)
        self.assertFalse(circuit.path(changed, 'switch.IN', 'battery.+')['connected'])
        self.assertEqual(len(changed['nets']), 7)
        self.assertFalse(changed['cadBinding']['valid'])

    def test_variant_can_wire_oe_after_updating_annotation(self):
        self.mutate(circuit.INSTRUCTIONS + 'carrier-connections.json',
                    lambda d: d['jumpers'].append(dict(id='MyOE', color='yellow', addresses=['A7', 'I17'])))
        with self.assertRaisesRegex(ValueError, 'No-connect annotation conflicts'):
            circuit.build(self.root)
        def change_annotation(data):
            pin = next(p for p in data['pins'] if p['id'] == 'hub.OE')
            pin['state'] = 'unknown'
            pin['evidence'] = ['my-design']
            data['evidence']['my-design'] = dict(kind='design-intent', note='My OE jumper')
        self.mutate(circuit.ANNOTATIONS, change_annotation)
        changed = circuit.build(self.root)
        self.assertTrue(circuit.path(changed, 'hub.OE', 's3.GPIO7')['connected'])
        self.assertEqual(circuit.query(changed, 'hub.OE')['item']['state'], 'connected')
        self.assertEqual(len(changed['nets']), 9)
        self.assertFalse(changed['cadBinding']['valid'])  # new jumper needs native geometry

    def test_insulated_crossings_do_not_create_connections(self):
        routes = [dict(id='bare', kind='bare', addresses=['A5', 'J5']),
                  dict(id='jumper', kind='insulated', addresses=['E3', 'E7'])]
        _, groups = circuit.routing_graph(routes)
        self.assertEqual(len(groups), 2)
        routes[1]['kind'] = 'bare'
        self.assertEqual(len(circuit.routing_graph(routes)[1]), 1)

    def test_firmware_mutation_changes_only_software_assignment(self):
        target = self.root / 'firmware/sesame-s3/manifest_generated.h'
        target.write_text(target.read_text().replace('uint32_t OE = 7;', 'uint32_t OE = 5;'))
        changed = circuit.build(self.root)
        self.assertEqual(changed['nets'], self.baseline['nets'])
        self.assertEqual(circuit.query(changed, 's3.GPIO5')['firmware_assignments'][0]['role'], 'OE')
        self.assertFalse(circuit.path(changed, 'hub.OE', 's3.GPIO5')['connected'])
        with self.assertRaisesRegex(ValueError, 'Stale or modified'):
            circuit.check(self.root)

    def test_native_cad_and_missing_parts_invalidate_highlights(self):
        target = self.root / 'assets/cad/Sesame-S3-Assembly.FCStd'
        with target.open('ab') as stream:
            stream.write(b'changed')
        changed = circuit.build(self.root)
        self.assertFalse(changed['cadBinding']['valid'])
        self.assertTrue(all(not n['partIds'] for n in changed['nets']))
        self.assertNotEqual(self.cli('export').returncode, 0)
        shutil.copyfile(ROOT / 'assets/cad/Sesame-S3-Assembly.FCStd', target)
        def remove_part(data):
            data['objects'] = [o for o in data['objects'] if o['id'] != 'jumper.core.Red_L']
        self.mutate(circuit.INSTRUCTIONS + 'assembly-cad-snapshot.json', remove_part)
        self.assertFalse(circuit.build(self.root)['cadBinding']['valid'])

    def test_tampered_publication_and_changed_evidence_rejected(self):
        self.mutate(circuit.OUTPUT, lambda d: d['nets'][0]['pins'].append('hub.OE'))
        with self.assertRaisesRegex(ValueError, 'Stale or modified'):
            circuit.check(self.root)
        self.artifact.write_text(json.dumps(self.baseline))
        self.mutate(circuit.ANNOTATIONS, lambda d: d.__setitem__('scope', 'Updated scope'))
        with self.assertRaisesRegex(ValueError, 'Stale or modified'):
            circuit.check(self.root)

    def test_unknown_ids_are_errors_in_python_and_cli(self):
        for unknown in ('GND', 'not-a-pin', 'A7'):
            with self.assertRaisesRegex(ValueError, 'Unknown pin ID'):
                circuit.query(self.baseline, unknown)
            with self.assertRaisesRegex(ValueError, 'Unknown pin ID'):
                circuit.path(self.baseline, 'hub.OE', unknown)
            result = self.cli('query', unknown)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('Unknown pin ID', json.loads(result.stderr)['error'])

    def test_digests_cover_every_input_and_adapter(self):
        paths = {s['path'] for s in self.baseline['sources']}
        self.assertIn('tools/circuit.py', paths)
        self.assertIn(circuit.ANNOTATIONS, paths)
        self.assertIn('assets/cad/Sesame-S3-Assembly.FCStd', paths)
        self.assertNotIn('assets/cad/reports/underside-wiring-check.json', paths)
        self.assertNotIn(circuit.OUTPUT, paths)
        for source in self.baseline['sources']:
            self.assertEqual(source['sha256'], circuit.digest((ROOT / source['path']).read_bytes()))

    def test_no_editable_duplicate_nets_or_unresolved_routes(self):
        self.mutate(circuit.ANNOTATIONS, lambda d: d.__setitem__('nets', []))
        with self.assertRaisesRegex(ValueError, 'Net membership belongs'):
            circuit.build(self.root)
        shutil.copyfile(ROOT / circuit.ANNOTATIONS, self.root / circuit.ANNOTATIONS)
        self.mutate(circuit.INSTRUCTIONS + 'underside-wiring.json',
                    lambda d: d['unresolved'].append('Unknown wire'))
        with self.assertRaisesRegex(ValueError, 'Unresolved routing'):
            circuit.build(self.root)


if __name__ == '__main__':
    unittest.main()
