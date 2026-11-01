"""Real Git object-tree regressions; no fake Git/status/source implementation."""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shell_installer', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'checkout'
        self.environment = {'PATH': os.defpath, 'HOME': self.temporary.name,
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_TERMINAL_PROMPT': '0', 'LC_ALL': 'C'}

    def git(self, *arguments):
        return subprocess.check_output(['git', '-C', str(self.root),
            '-c', 'user.name=Native installer test', '-c', 'user.email=native@example.invalid',
            *arguments], env=self.environment, text=True).strip()


class ExactInputInstaller(GitFixture):
    def setUp(self):
        super().setUp()
        self.original = Path('/opt/inputs/zun')
        if not self.original.is_dir():
            raise RuntimeError('Canonical offline verification /opt/inputs/zun is required')
        subprocess.run(['git', 'clone', '--local', '--no-hardlinks', str(self.original), str(self.root)],
                       check=True, env=self.environment, capture_output=True)
        self.assertEqual(installer.SOURCE, self.git('rev-parse', 'HEAD'))
        self.inputs = {name: (self.root / name).read_bytes() for name in installer.INPUTS}

    def untouched(self):
        for name, raw in self.inputs.items():
            self.assertEqual(raw, (self.root / name).read_bytes())
        self.assertFalse((self.root / 'zun/afterglow_cloud_shell_build.py').exists())

    def test_hash_mismatch_in_last_input_does_not_patch_first(self):
        name = list(installer.INPUTS)[-1]
        (self.root / name).write_bytes(b'changed input')
        self.inputs[name] = b'changed input'
        with self.assertRaisesRegex(ValueError, 'object mismatch'):
            installer.install(self.root)
        self.untouched()

    def test_all_anchors_checked_before_any_write(self):
        with mock.patch.object(installer, 'method_replace', side_effect=ValueError('late anchor mismatch')):
            with self.assertRaisesRegex(ValueError, 'anchor mismatch'):
                installer.install(self.root)
        self.untouched()

    def test_wrong_actual_commit_does_not_patch(self):
        self.git('commit', '--allow-empty', '-m', 'different actual commit')
        with self.assertRaisesRegex(ValueError, 'commitment mismatch'):
            installer.install(self.root)
        self.untouched()

    def test_manifest_and_package_wheel_hook_inputs(self):
        manifest = installer.install(self.root)
        self.assertEqual(installer.SOURCE, manifest['source_commit'])
        self.assertEqual(64, len(manifest['source_tree_sha256']))
        for path, digest in manifest['files'].items():
            self.assertEqual(digest, hashlib.sha256((self.root / path).read_bytes()).hexdigest())
        receipt = {}
        exec((self.root / 'zun/afterglow_cloud_shell_build.py').read_text(), receipt)
        self.assertEqual(manifest, receipt['BUILD'])
        with self.assertRaisesRegex(ValueError, 'object mismatch'):
            installer.install(self.root)

    def test_duplicate_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError, 'anchor mismatch'):
            installer.replace_once('same same', 'same', 'new')


class WholeSourceTree(GitFixture):
    def setUp(self):
        super().setUp()
        self.root.mkdir()
        self.git('init')
        (self.root / 'unhooked_runtime.py').write_text('VALUE = 1\n')
        (self.root / '.gitignore').write_text('*.pyc\n')
        self.git('add', '.')
        self.git('commit', '-m', 'immutable source fixture')
        self.source = self.git('rev-parse', 'HEAD')

    def test_actual_clean_tree_accepted(self):
        self.assertEqual(64, len(installer.verify_tree(self.root, self.source)))

    def test_assume_unchanged_and_skip_worktree_cannot_hide_unhooked_source_change(self):
        for flag, undo in [('--assume-unchanged', '--no-assume-unchanged'),
                           ('--skip-worktree', '--no-skip-worktree')]:
            with self.subTest(flag=flag):
                path = self.root / 'unhooked_runtime.py'
                path.write_text('VALUE = 1\n')
                self.git('update-index', flag, 'unhooked_runtime.py')
                path.write_text('VALUE = 1\n# harmless comment hidden from git diff\n')
                # Real Git demonstrates why status/diff-based checks are unsafe.
                self.assertEqual('', self.git('diff', 'HEAD', '--', 'unhooked_runtime.py'))
                with self.assertRaisesRegex(ValueError, 'object mismatch'):
                    installer.verify_tree(self.root, self.source)
                path.write_text('VALUE = 1\n')
                self.git('update-index', undo, 'unhooked_runtime.py')

    def test_untracked_and_ignored_runtime_inputs_are_rejected(self):
        for name in ('untracked_runtime.py', 'ignored.pyc'):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(b'untrusted input')
                with self.assertRaisesRegex(ValueError, 'untracked'):
                    installer.verify_tree(self.root, self.source)
                path.unlink()

    def test_executable_mode_change_is_not_hidden_by_core_filemode_false(self):
        self.git('config', 'core.filemode', 'false')
        path = self.root / 'unhooked_runtime.py'
        path.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'mode mismatch'):
            installer.verify_tree(self.root, self.source)

    def test_replacement_ref_cannot_substitute_the_pinned_source_tree(self):
        original_tree = self.git('rev-parse', self.source + '^{tree}')
        path = self.root / 'unhooked_runtime.py'
        path.write_text('VALUE = 1\n# harmless comment in replacement commit\n')
        self.git('add', 'unhooked_runtime.py')
        self.git('commit', '-m', 'replacement source fixture')
        replacement = self.git('rev-parse', 'HEAD')
        self.git('replace', self.source, replacement)
        self.git('update-ref', 'HEAD', self.source)
        self.assertEqual(self.source, self.git('rev-parse', 'HEAD'))
        self.assertNotEqual(original_tree, self.git('rev-parse', self.source + '^{tree}'))
        self.assertEqual('', self.git('diff', 'HEAD'))
        with self.assertRaisesRegex(ValueError, 'object mismatch'):
            installer.verify_tree(self.root, self.source)


if __name__ == '__main__':
    unittest.main()
