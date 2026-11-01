"""Offline manifests reject injected wheels, missing paths, and symlinks."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shell_build_inputs', ROOT / 'prepare_build.py')
preparer = importlib.util.module_from_spec(spec)
# prepare_build imports its sibling install module through the canonical path.
import sys
sys.path.insert(0, str(ROOT))
try:
    spec.loader.exec_module(preparer)
finally:
    sys.path.pop(0)


class BuildInputIntegrity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.wheel = self.root / 'wheels/example-1.0-py3-none-any.whl'
        self.wheel.parent.mkdir()
        self.wheel.write_bytes(b'approved-wheel-fixture')
        self.manifest = {'source_commit': preparer.SOURCE,
            'requirements_commit': preparer.REQUIREMENTS_SOURCE,
            'files': {str(self.wheel.relative_to(self.root)): preparer.sha(self.wheel)}}
        self.save()

    def save(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_extra_wheel_rejected_before_source_or_install_access(self):
        (self.wheel.parent / 'injected-1.0-py3-none-any.whl').write_bytes(b'injected')
        with self.assertRaisesRegex(ValueError, 'unmanifested'):
            preparer.verify(self.root)

    def test_missing_manifested_input_rejected(self):
        self.wheel.unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            preparer.verify(self.root)

    def test_symlink_and_parent_escape_rejected(self):
        self.wheel.unlink()
        self.wheel.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            preparer.verify(self.root)
        self.wheel.unlink()
        self.manifest['files'] = {'../outside.whl': '0' * 64}
        self.save()
        with self.assertRaisesRegex(ValueError, 'unmanifested'):
            preparer.verify(self.root)



if __name__ == '__main__':
    unittest.main()
