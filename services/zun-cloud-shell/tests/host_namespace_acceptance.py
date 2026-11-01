#!/usr/bin/env python3
"""Explicit real-kernel acceptance, separate from synthetic unittest discovery.

Run ONLY inside the parent's disposable verifier with --network=none, no Docker
socket/host mounts/secrets, and SYS_ADMIN/NET_ADMIN/SYS_PTRACE capabilities:
  python /opt/cloud-shell-native/tests/host_namespace_acceptance.py
Missing capabilities/tools are FAILURES, never skips or synthetic substitutes.
This qualifies this verifier's Linux namespace path, not Kuryr or a compute fleet.
"""
from pathlib import Path
import select
import subprocess
import sys
import uuid

from afterglow_zun_cloud_shell import config, namespace


def main():
    environment = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
    # The child only holds a fresh empty network namespace. No daemon/network
    # socket is used, and no workload or route on the verifier's own netns moves.
    child = subprocess.Popen(['/usr/bin/unshare', '--net', sys.executable, '-c',
        'import os,time; print(os.getpid(), flush=True); time.sleep(60)'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=environment, stdin=subprocess.DEVNULL)
    key = Path('/var/run/docker/netns/afterglow-acceptance-' + uuid.uuid4().hex)
    mounted = False
    try:
        ready, _, _ = select.select([child.stdout], [], [], 10)
        if not ready:
            raise RuntimeError('Namespace holder did not become ready')
        value = child.stdout.readline(32).strip()
        if not value.isdecimal():
            raise RuntimeError('unshare failed: ' + child.stderr.read(4096))
        pid = int(value)
        key.parent.mkdir(parents=True, exist_ok=True)
        key.touch(exist_ok=False)
        subprocess.run(['/usr/bin/mount', '--bind', '/proc/%d/ns/net' % pid, str(key)],
                       check=True, timeout=5, env=environment)
        mounted = True
        # A routable synthetic Kuryr-like namespace is essential: an empty
        # namespace would make every route-get fail even without enforcement.
        commands = [
            ('link', 'set', 'lo', 'up'),
            ('link', 'add', 'v0', 'type', 'dummy'),
            ('link', 'set', 'v0', 'up'),
            ('-4', 'addr', 'add', '192.0.2.10/24', 'dev', 'v0'),
            ('-4', 'route', 'add', 'default', 'via', '192.0.2.1'),
            ('-4', 'route', 'add', '10.200.1.0/24', 'via', '192.0.2.1'),
            ('-6', 'addr', 'add', '2001:db8::10/64', 'dev', 'v0', 'nodad'),
            ('-6', 'route', 'add', 'default', 'via', '2001:db8::1'),
        ]
        for command in commands:
            namespace._run(str(key), *command)

        def assert_route(address, expected):
            family = '-6' if ':' in address else '-4'
            arguments = [family, 'route', 'get', address]
            if address.startswith('fe80:'):
                arguments += ['oif', 'v0']
            completed = subprocess.run(['/usr/bin/nsenter', '--net=' + str(key), '--',
                namespace._ip_binary(), *arguments],
                capture_output=True, timeout=5, env=environment)
            if (completed.returncode == 0) != expected:
                raise AssertionError('Route resolution for %s expected %s: %r' %
                                     (address, expected, completed.stderr[:1024]))

        blocked = ('169.254.169.254', '10.200.1.2', 'fd00:ec2::254', 'fe80::a9fe:a9fe')
        controls = ('198.51.100.1', '2001:db8:ffff::1')
        for address in (*blocked, *controls):
            assert_route(address, True)
        cidrs = sorted([*config.BASE_CIDRS, '10.200.0.0/16'])
        assert namespace._isolate(pid, str(key), cidrs, install=True) is True
        assert namespace._isolate(pid, str(key), cidrs, install=False) is True
        for address in blocked:
            assert_route(address, False)
        for address in controls:
            assert_route(address, True)
        print('Actual Linux namespace, IPv4/IPv6 metadata and management-prefix policy readback passed')
    finally:
        child.terminate()
        child.wait(timeout=10)
        if mounted:
            subprocess.run(['/usr/bin/umount', str(key)], check=True, timeout=5, env=environment)
        key.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
