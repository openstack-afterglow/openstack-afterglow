#!/usr/bin/env python3
"""Offline, exact-input Zun source integration. Never patch a running service."""
import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
import subprocess

SOURCE = '17a8a03d19ac0a063ff7bb7e54e8503bd60536cd'
INPUTS = {
    'zun/container/docker/driver.py': 'bffc3fddd3cb6a9af6772994d183165e490b8774e214fbd52436fb5ae657f06d',
    'zun/conf/__init__.py': 'ddaf35f9431386a7861eaa72689cf709960e754cc4a27c45f90dd43b0ce4a027',
    'etc/zun/rootwrap.d/zun.filters': '93626d7618ce2c6a6cc56d419a09a08ddac88076c69ed015fb5cfaa0acc94986',
    'setup.cfg': 'e6b2fb20880ab7a4104154a6d6bebac904a50a741adf4ca650ea779fb73e9d3e',
}


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Native source anchor mismatch: ' + repr(old[:80]))
    return text.replace(old, new, 1)


def verify_tree(root, source):
    """Compare actual bytes/modes to Git objects, never the mutable index.

    assume-unchanged, skip-worktree, ignored files and core.filemode cannot
    suppress this check. Git only reads the immutable commit/tree objects.
    """
    root = Path(root)
    tree = subprocess.check_output(['git', '--no-replace-objects', '--no-optional-locks',
        '-c', 'core.fsmonitor=false', 'ls-tree', '-rz', '--full-tree', source], cwd=root)
    tracked = {}
    for record in tree.split(b'\0'):
        if not record:
            continue
        header, raw_name = record.split(b'\t', 1)
        mode, kind, oid = header.split(b' ')
        name = os.fsdecode(raw_name)
        relative = Path(name)
        if (kind != b'blob' or mode not in (b'100644', b'100755', b'120000')
                or relative.is_absolute() or '..' in relative.parts):
            raise ValueError('Unsupported pinned Git object: ' + name)
        path = root / relative
        for parent in relative.parents:
            if parent != Path('.') and (root / parent).is_symlink():
                raise ValueError('Tracked source parent is a symlink: ' + name)
        info = path.lstat()
        if mode == b'120000':
            if not stat.S_ISLNK(info.st_mode):
                raise ValueError('Pinned source mode mismatch: ' + name)
            raw = os.fsencode(os.readlink(path))
        else:
            executable = bool(info.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
            if not stat.S_ISREG(info.st_mode) or executable != (mode == b'100755'):
                raise ValueError('Pinned source mode mismatch: ' + name)
            raw = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest().encode()
        if actual != oid:
            raise ValueError('Pinned source object mismatch: ' + name)
        tracked[name] = True
    actual_files = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if current == root and '.git' in directories:
            directories.remove('.git')
        for name in list(directories):
            path = current / name
            if path.is_symlink():
                actual_files.add(str(path.relative_to(root)))
                directories.remove(name)
        for name in files:
            path = current / name
            if path == root / '.git':
                continue
            actual_files.add(str(path.relative_to(root)))
    if actual_files != set(tracked):
        raise ValueError('Pinned source contains untracked or missing build/runtime inputs')
    return hashlib.sha256(tree).hexdigest()


def method_replace(text, method, old, new):
    opener = '    def ' + method + '('
    start = text.index(opener)
    end = text.find('\n    def ', start + len(opener))
    if end < 0:
        end = len(text)
    before = text[start:end]
    return text[:start] + replace_once(before, old, new) + text[end:]


def prepare(inputs):
    prepared = dict(inputs)
    driver = 'zun/container/docker/driver.py'
    value = prepared[driver]
    value = replace_once(value, 'import datetime\n',
        'from afterglow_zun_cloud_shell import hooks as shell_profile\n\nimport datetime\n')
    value = method_replace(value, '__init__',
        '        super(DockerDriver, self).__init__()\n',
        '        shell_profile.settings()\n'
        '        super(DockerDriver, self).__init__()\n')
    value = method_replace(value, 'create',
        '            binds = self._get_binds(context, volmaps)\n',
        '            binds = self._get_binds(context, volmaps)\n'
        '            shell_profile.prepare(context, container, volmaps, binds, requested_networks)\n')
    value = method_replace(value, 'create',
        '            network_driver.process_networking_config(\n'
        '                container, requested_network, host_config, kwargs, docker,\n'
        '                security_group_ids=security_group_ids)\n',
        '            network_driver.process_networking_config(\n'
        '                container, requested_network, host_config, kwargs, docker,\n'
        '                security_group_ids=security_group_ids)\n'
        '            shell_profile.network_ready(container, network_driver)\n')
    value = method_replace(value, 'create',
        "            kwargs['host_config'] = docker.create_host_config(**host_config)\n",
        '            shell_profile.configure(docker, container, host_config, kwargs)\n'
        "            kwargs['host_config'] = docker.create_host_config(**host_config)\n")
    value = method_replace(value, 'create',
        '            addresses = self._setup_network_for_container(\n'
        '                context, container, requested_networks, network_driver)\n',
        '            if shell_profile.managed(container):\n'
        '                # Exactly one requested network was provisioned on the\n'
        '                # native holder; never attach/query the user namespace.\n'
        '                addresses = container.addresses\n'
        '            else:\n'
        '                addresses = self._setup_network_for_container(\n'
        '                    context, container, requested_networks, network_driver)\n')
    value = method_replace(value, 'create',
        '            response = docker.inspect_container(container.container_id)\n'
        '            self._populate_container(container, response, force=True)\n',
        '            response = docker.inspect_container(container.container_id)\n'
        '            shell_profile.verify(docker, container, response)\n'
        '            self._populate_container(container, response, force=True)\n')
    value = method_replace(value, 'create',
        '        with docker_utils.docker_client() as docker:\n',
        '        shell_profile.admit(context, container)\n'
        '        with docker_utils.docker_client() as docker:\n')
    value = replace_once(value, '    def create(self, context, container, image, requested_networks,\n',
        '    @shell_profile.serialized\n'
        '    @shell_profile.creation\n'
        '    def create(self, context, container, image, requested_networks,\n')
    value = replace_once(value,
        '    def delete(self, context, container, force):\n'
        '        with docker_utils.docker_client() as docker:\n',
        '    @shell_profile.serialized\n'
        '    def delete(self, context, container, force):\n'
        '        with docker_utils.docker_client() as docker:\n'
        '            if shell_profile.delete(self, docker, context, container, force):\n'
        '                return\n')
    value = method_replace(value, 'show',
        '            self._populate_container(container, response)\n'
        '            return container\n',
        '            shell_profile.verify(docker, container, response)\n'
        '            self._populate_container(container, response)\n'
        '            return container\n')
    value = replace_once(value, '    def show(self, context, container):\n',
        '    @shell_profile.serialized\n'
        '    def show(self, context, container):\n')
    value = replace_once(value,
        '            self._populate_container(container, docker_container)\n',
        '            if shell_profile.managed(container):\n'
        '                with docker_utils.docker_client() as native_docker:\n'
        '                    shell_profile.sync_verify(self, context, container, native_docker)\n'
        '                continue\n'
        '            self._populate_container(container, docker_container)\n')
    for method, suffix in [('start', ''), ('unpause', ''), ('execute_create', ', command, interactive=False'), ('get_websocket_url', ''), ('update', ''), ('network_attach', ', requested_network'), ('network_detach', ', network'), ('add_security_group', ', security_group'), ('remove_security_group', ', security_group')]:
        signature = '    def %s(self, context, container%s):\n' % (method, suffix)
        value = replace_once(value, signature,
            '    @shell_profile.serialized\n' + signature + '        with docker_utils.docker_client() as native_docker:\n'
            "            shell_profile.before_action(native_docker, context, container, '%s')\n" % method)
    for method in ('start', 'unpause'):
        old = '            docker.%s(container.container_id)\n' % method
        value = method_replace(value, method, old, old + '            shell_profile.verify(docker, container)\n')
    value = replace_once(value,
        '    def reboot(self, context, container, timeout):\n'
        '        with docker_utils.docker_client() as docker:\n',
        '    @shell_profile.serialized\n'
        '    def reboot(self, context, container, timeout):\n'
        '        with docker_utils.docker_client() as docker:\n'
        '            if shell_profile.reboot(docker, context, container, timeout):\n'
        '                container.status = consts.RUNNING\n'
        '                container.status_reason = None\n'
        '                return container\n')
    prepared[driver] = value
    conf = 'zun/conf/__init__.py'
    prepared[conf] = replace_once(prepared[conf], 'CONF = cfg.CONF\n',
        'CONF = cfg.CONF\n\nfrom afterglow_zun_cloud_shell import config as shell_config\n'
        'shell_config.register_opts(CONF)\n')
    filters = 'etc/zun/rootwrap.d/zun.filters'
    prepared[filters] += (
        '\n# Native Cloud Shell namespace boundary; no arbitrary root shell.\n'
        'afterglow-cloud-shell: RegExpFilter, privsep-helper, root, privsep-helper, '
        '--config-file, /etc/(?!\\.\\.).*, --privsep_context, '
        'afterglow_zun_cloud_shell.namespace.context, --privsep_sock_path, /tmp/.*\n')
    prepared['setup.cfg'] = replace_once(prepared['setup.cfg'],
        'data_files =\n',
        'data_files =\n    etc/zun/rootwrap.d =\n        etc/zun/rootwrap.d/zun.filters\n')
    return prepared


def install(root):
    root = Path(root)
    actual = subprocess.check_output(['git', '--no-replace-objects', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if actual != SOURCE:
        raise ValueError('Zun commitment mismatch: ' + actual)
    tree_digest = verify_tree(root, SOURCE)
    inputs = {}
    for path, digest in INPUTS.items():
        raw = (root / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Pinned native source mismatch: ' + path)
        inputs[path] = raw.decode()
    # Validate ALL anchors and destination collisions before first write.
    prepared = prepare(inputs)
    destination = root / 'zun/afterglow_cloud_shell_build.py'
    if destination.exists():
        raise ValueError('Native build manifest already exists')
    package = Path(__file__).resolve().parent / 'afterglow_zun_cloud_shell'
    manifest = {'schema': 1, 'source_commit': SOURCE, 'hook_revision': 'cloud-shell-v1',
                'input_files': INPUTS,
                'source_tree_sha256': tree_digest,
                'files': {path: hashlib.sha256(text.encode()).hexdigest() for path, text in prepared.items()},
                'extension_files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in sorted(package.glob('*.py'))}}
    for path, text in prepared.items():
        (root / path).write_text(text)
    # Python package data is retained by the normal upstream pbr wheel build.
    destination.write_text('"""Immutable native build receipt (not runtime proof)."""\nBUILD = ' + repr(manifest) + '\n')
    print(json.dumps(manifest, sort_keys=True))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('zun_checkout', type=Path)
    install(parser.parse_args().zun_checkout.resolve())
