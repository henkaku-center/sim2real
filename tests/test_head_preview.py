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
                for a,b in [(actual,expected),(expected,actual)]:
                    delta=a.cut(b)
                    self.assertTrue(delta.isNull() or delta.isValid())
                    self.assertLess(abs(delta.Volume),1e-3)
            changed=copy.deepcopy(params)
            changed['head_cover']['cable_notch_width_mm']=10
            with patch.object(cad,'load_electronics',side_effect=AssertionError('cache miss')):
                wider=cad.preview_head(changed,out)
                self.assertTrue(wider['input_cache_hit'])
                self.assertLess(wider['parts']['head-cover']['volume_mm3'],original['parts']['head-cover']['volume_mm3'])
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
