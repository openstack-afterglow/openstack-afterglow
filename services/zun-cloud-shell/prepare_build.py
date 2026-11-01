#!/usr/bin/env python3
"""Explicit networked dependency-builder step, NEVER run on a compute service.

For each target architecture run this on a matching Python 3.12 builder:
  python prepare_build.py --prepare /empty/output/build-inputs/arm64
Use amd64 for the other builder. Copy build-inputs/<arch> into this service's
build context; Dockerfile selects the matching wheelhouse through TARGETARCH.
--verify is network-free and used by the canonical Dockerfile.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import os
import shutil
import tempfile
import sys
import urllib.request

from install import INPUTS, SOURCE, verify_tree

REQUIREMENTS_SOURCE = '32c73b362852b9d1dc5774db1380b2b130c28cde'
CONSTRAINTS_SHA256 = '20c96ad3b45ba26ea17465deeb2f44f093eb5305f570ab37d7609cf9b5546417'
REQUIREMENTS_SHA256 = '8f2b8db5496ac1c2b256238748a1c08fcda54fb2e463fd6d03b293a539477e0b'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root):
    if (root / 'manifest.json').is_symlink():
        raise ValueError('Build receipt cannot be a symlink')
    receipt = json.loads((root / 'manifest.json').read_text())
    actual_files = set()
    for path in root.rglob('*'):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError('Build inputs contain a symlink/special file: ' + str(path))
        if path.is_file() and path != root / 'manifest.json':
            actual_files.add(str(path.relative_to(root)))
    if actual_files != set(receipt['files']):
        raise ValueError('Build inputs contain unmanifested or missing files')
    if (receipt['source_commit'] != SOURCE
            or receipt['requirements_commit'] != REQUIREMENTS_SOURCE):
        raise ValueError('Wrong native dependency source')
    verify_tree(root / 'zun', SOURCE)
    if sha(root / 'upper-constraints.txt') != CONSTRAINTS_SHA256:
        raise ValueError('Wrong pinned dependency constraints')
    if sha(root / 'zun/requirements.txt') != REQUIREMENTS_SHA256:
        raise ValueError('Wrong pinned Zun requirements')
    for name, digest in INPUTS.items():
        if sha(root / 'zun' / name) != digest:
            raise ValueError('Wrong pinned native source: ' + name)
    for name, digest in receipt['files'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or sha(root / path) != digest:
            raise ValueError('Build input digest mismatch: ' + name)
    return receipt


def prepare(root, wheelhouse=None):
    if root.exists():
        raise ValueError('Destination must be absent (never overwrite build inputs)')
    root.mkdir(parents=True)
    scratch = tempfile.TemporaryDirectory(prefix='afterglow-shell-inputs-')
    home = Path(scratch.name)
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(home),
        'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_TERMINAL_PROMPT': '0', 'PIP_CONFIG_FILE': os.devnull,
        'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PIP_NO_CACHE_DIR': '1',
        'TMPDIR': str(home)}
    subprocess.run(['git', 'init', str(root / 'zun')], check=True, env=environment)
    for args in (['remote', 'add', 'origin', 'https://opendev.org/openstack/zun.git'],
                 ['fetch', '--depth', '1', 'origin', SOURCE],
                 ['checkout', '--detach', 'FETCH_HEAD']):
        subprocess.run(['git', '-C', str(root / 'zun'), *args], check=True, env=environment)
    url = ('https://raw.githubusercontent.com/openstack/requirements/'
           + REQUIREMENTS_SOURCE + '/upper-constraints.txt')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=30) as response:
        (root / 'upper-constraints.txt').write_bytes(response.read(1024 * 1024))
    if (sha(root / 'upper-constraints.txt') != CONSTRAINTS_SHA256
            or sha(root / 'zun/requirements.txt') != REQUIREMENTS_SHA256):
        raise ValueError('Upstream pinned input digest mismatch')
    for name, digest in INPUTS.items():
        if sha(root / 'zun' / name) != digest:
            raise ValueError('Upstream source mismatch: ' + name)
    if wheelhouse is not None:
        (root / 'wheels').mkdir()
        for wheel in sorted(wheelhouse.iterdir()):
            if wheel.is_symlink() or not wheel.is_file() or wheel.suffix != '.whl':
                raise ValueError('Prebuilt wheelhouse accepts regular wheels only: ' + str(wheel))
            shutil.copyfile(wheel, root / 'wheels' / wheel.name)
    else:
        # DOWNLOAD ONLY: never execute third-party sdist setup/build hooks while
        # networked. If a platform has no wheel, fail with pip's exact package
        # error; provide an approved prebuilt wheelhouse instead.
        subprocess.run([sys.executable, '-m', 'pip', '--isolated', 'download',
                        '--only-binary=:all:', '--dest', str(root / 'wheels'),
                        '--constraint', str(root / 'upper-constraints.txt'),
                        '--requirement', str(root / 'zun/requirements.txt'),
                        'setuptools==80.9.0', 'wheel==0.45.1', 'pbr==7.0.1'], check=True, env=environment)
    scratch.cleanup()
    files = {str(path.relative_to(root)): sha(path)
             for path in sorted(root.rglob('*')) if path.is_file()}
    receipt = {'schema': 1, 'source_commit': SOURCE,
               'requirements_commit': REQUIREMENTS_SOURCE,
               'python': sys.version, 'files': files}
    (root / 'manifest.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
    verify(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--prepare', type=Path)
    selection.add_argument('--verify', type=Path)
    parser.add_argument('--wheelhouse', type=Path,
                        help='Approved architecture-matching prebuilt wheels (no sdists)')
    arguments = parser.parse_args()
    if arguments.prepare:
        prepare(arguments.prepare.resolve(), arguments.wheelhouse.resolve() if arguments.wheelhouse else None)
    else:
        verify(arguments.verify.resolve())
