"""Native preview equivalence, parameter edits and source-cache invalidation."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import FreeCAD
    import Part
except ImportError:
    raise unittest.SkipTest('Run with FreeCAD Python for native preview checks')

from tools import v3_assembly_cad as cad


class HeadPreviewTest(unittest.TestCase):
    def test_frame_and_spacer_preview_match_full_native_exports(self):
        params=json.loads((cad.REF.parent/'params.json').read_text())
        expected_dir=Path(os.environ.get('INTERNAL_FRAME_OUTPUT',cad.REF.parent))
        with tempfile.TemporaryDirectory() as directory:
            for kind,name in [('frame','internal-frame'),('spacer','pcb-spacer')]:
                out=Path(directory)/kind;cad.preview_part(params,out,kind)
                expected=Part.read(str(expected_dir/(name+'.step')));actual=Part.read(str(out/(name+'.step')))
                self.assertLess(abs(actual.Volume-expected.Volume),1e-3)
                # Identical imported fillets can give a nonempty coincident
                # Boolean difference. Compare the actual delivered STEP bytes.
                self.assertEqual((out/(name+'.step')).read_bytes(),(expected_dir/(name+'.step')).read_bytes())
                self.assertTrue((out/(kind+'-preview.stl')).exists())
                self.assertFalse((out/'assembly.json').exists())

    def test_geometry_change_invalidates_cached_collision_check(self):
        from tools.cad_validation_cache import CheckCache,shape_digest,check_electronics
        body=Part.makeBox(1,1,1);other=Part.makeBox(1,1,1,FreeCAD.Vector(5,0,0))
        with tempfile.TemporaryDirectory() as directory:
            cache=CheckCache(directory,{'checker':cad.sha(cad.ROOT/'tools/cad_validation_cache.py')})
            def check(shape):return cache.run('electronics',{'shape':shape_digest(shape),'other':shape_digest(other)},lambda:check_electronics(shape,{'part':other}))
            self.assertEqual(check(body),[]);self.assertEqual(check(body),[]);self.assertTrue(cache.records[-1]['cache_hit'])
            body.translate(FreeCAD.Vector(5,0,0))
            with self.assertRaises(AssertionError):check(body)

    def test_preview_edits_reuse_inputs_but_not_geometry_or_fit_results(self):
        params=json.loads((cad.REF.parent/'params.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            original=cad.preview_head(params,out)
            self.assertFalse(original['input_cache_hit'])
            self.assertFalse((out/'assembly.json').exists())
            self.assertIn('electronics intersections',original['unchecked'])
            for name in ['head-cover','head-lid']:
                expected_dir=Path(os.environ.get('INTERNAL_FRAME_OUTPUT',cad.REF.parent))
                expected=Part.read(str(expected_dir/(name+'.step')))
                actual=Part.read(str(out/(name+'.step')))
                self.assertLess(abs(actual.Volume-expected.Volume),1e-3)
                self.assertEqual((out/(name+'.step')).read_bytes(),(expected_dir/(name+'.step')).read_bytes())
            changed=copy.deepcopy(params)
            changed['head_cover']['raise_mm']+=2
            with patch.object(cad,'load_electronics',side_effect=AssertionError('cache miss')):
                wider=cad.preview_head(changed,out)
                self.assertTrue(wider['input_cache_hit'])
                self.assertGreater(wider['parts']['head-cover']['volume_mm3'],original['parts']['head-cover']['volume_mm3'])
                restored=cad.preview_head(params,out)
                self.assertEqual(restored['parts'],original['parts'])
                # An electronics-source change must reload measurements.
                original_sha=cad.sha
                def changed_sha(path):
                    return 'changed' if Path(path).name=='Sesame-S3-Assembly.FCStd' else original_sha(path)
                with patch.object(cad,'sha',side_effect=changed_sha):
                    with self.assertRaisesRegex(AssertionError,'cache miss'):cad.preview_datums(out)

    def test_preview_cannot_overwrite_release_directory(self):
        with self.assertRaises(ValueError):cad.preview_head({},cad.REF.parent)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);(out/'assembly.json').write_text('{}')
            with self.assertRaises(ValueError):cad.preview_head({},out)


if __name__=='__main__':unittest.main()
