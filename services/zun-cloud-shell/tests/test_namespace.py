"""Exercise actual namespace policy logic with a synthetic kernel argv boundary."""
import ipaddress
import json
from types import SimpleNamespace
import unittest
from unittest import mock

from afterglow_zun_cloud_shell import config, namespace


class KernelBoundary:
    def __init__(self):
        self.rules = {'-4': [{'priority': 0, 'src': 'all', 'table': 'local'},
                             {'priority': 32766, 'src': 'all', 'table': 'main'}],
                      '-6': [{'priority': 0, 'src': 'all', 'table': 'local'},
                             {'priority': 32766, 'src': 'all', 'table': 'main'}]}
        self.routes = {'-4': [], '-6': []}
        self.local = {'-4': [], '-6': []}
        self.calls = []
        self.discard_rule = False
        self.discard_route = False

    def run(self, netns, family, *args):
        self.calls.append((netns, family, args))
        if args == ('-j', 'rule', 'show'):
            return json.dumps(self.rules[family])
        if args == ('-j', 'route', 'show', 'table', 'local'):
            return json.dumps(self.local[family])
        if args == ('-j', 'route', 'show', 'table', 'main'):
            return json.dumps(self.routes[family])
        if args[:3] == ('route', 'replace', 'blackhole'):
            if not self.discard_route:
                self.routes[family].append({'type': 'blackhole', 'dst': args[3]})
            return ''
        if args[:3] == ('rule', 'add', 'pref') and args[-1] == 'blackhole':
            if not self.discard_rule:
                destination = ipaddress.ip_network(args[5])
                rule = {'priority': int(args[3]), 'src': 'all',
                        'dst': str(destination.network_address), 'action': 'blackhole'}
                if destination.prefixlen != destination.max_prefixlen:
                    rule['dstlen'] = destination.prefixlen
                self.rules[family].append(rule)
            return ''
        raise AssertionError('Unexpected trusted argv: ' + repr(args))


class NamespacePolicy(unittest.TestCase):
    def setUp(self):
        self.kernel = KernelBoundary()
        self.cidrs = sorted(config.BASE_CIDRS)
        self.stack = mock.patch.multiple(namespace.os,
            open=mock.Mock(return_value=42), close=mock.Mock(),
            fstat=mock.Mock(return_value=SimpleNamespace(st_dev=1, st_ino=2)),
            stat=mock.Mock(return_value=SimpleNamespace(st_dev=1, st_ino=2)))
        self.stack.start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(namespace, '_namespace', return_value=('/proc/400/ns/net', (1, 2))).start()
        mock.patch.object(namespace, '_run', side_effect=self.kernel.run).start()

    def isolate(self, install=True, **kwargs):
        return namespace._isolate(400, '/var/run/docker/netns/test', self.cidrs,
                                  install=install, **kwargs)

    def test_each_ipv4_ipv6_cidr_installed_and_read_back_before_success(self):
        self.assertTrue(self.isolate())
        for cidr in self.cidrs:
            family = '-%d' % ipaddress.ip_network(cidr).version
            self.assertIn({'type': 'blackhole', 'dst': cidr}, self.kernel.routes[family])
            self.assertTrue(any(rule.get('dst') == str(ipaddress.ip_network(cidr).network_address) and rule.get('action') == 'blackhole'
                                for rule in self.kernel.rules[family]))
        self.assertTrue(self.isolate(install=False, user_pid=500))
        namespace.os.close.assert_called_with(42)

    def test_successful_command_without_rule_or_route_readback_is_not_proof(self):
        self.kernel.discard_rule = True
        with self.assertRaises(namespace.IsolationError):
            self.isolate()
        self.kernel = KernelBoundary()
        # Mock side_effect was bound to the first object; replace it explicitly.
        namespace._run.side_effect = self.kernel.run
        self.kernel.discard_route = True
        with self.assertRaises(namespace.IsolationError):
            self.isolate()

    def test_existing_rule_with_equal_priority_cannot_mask_denial(self):
        self.kernel.rules['-4'].append({'priority': 1, 'src': 'all', 'table': 'main'})
        with self.assertRaises(namespace.IsolationError):
            self.isolate()
        self.assertFalse(self.kernel.routes['-4'])

    def test_metadata_local_address_cannot_bypass_priority_one(self):
        self.kernel.local['-4'] = [{'type': 'local', 'dst': '169.254.169.254'}]
        with self.assertRaises(namespace.IsolationError):
            self.isolate()

    def test_missing_or_changed_rule_on_restart_is_rejected_not_repaired(self):
        self.isolate()
        self.kernel.rules['-6'] = [rule for rule in self.kernel.rules['-6'] if rule.get('priority') != 1]
        calls = len(self.kernel.calls)
        with self.assertRaises(namespace.IsolationError):
            self.isolate(install=False)
        self.assertFalse(any(args[:2] == ('rule', 'add')
                             for _, _, args in self.kernel.calls[calls:]))

    def test_user_namespace_mismatch_fails(self):
        self.isolate()
        namespace.os.stat.return_value = SimpleNamespace(st_dev=1, st_ino=999)
        with self.assertRaises(namespace.IsolationError):
            self.isolate(install=False, user_pid=500)

    def test_pid_reuse_before_namespace_fd_open_fails(self):
        namespace.os.fstat.return_value = SimpleNamespace(st_dev=1, st_ino=999)
        with self.assertRaises(namespace.IsolationError):
            self.isolate()
        self.assertFalse(self.kernel.calls)

    def test_invalid_cidr_and_pid_do_not_reach_commands(self):
        for values in ([], ['169.254.1.1/16', 'fd00::/8'], ['::/0', '::/0']):
            with self.subTest(values=values), self.assertRaises((ValueError, namespace.IsolationError)):
                namespace._isolate(400, '/var/run/docker/netns/test', values, True)
        self.assertFalse(self.kernel.calls)

    def test_conditional_policy_rule_never_proves_global_denial(self):
        self.isolate()
        for key, value in [('fwmark', '0x1'), ('iif', 'eth0'), ('not', True),
                           ('uidrange', '1000-1000'), ('flags', ['not'])]:
            with self.subTest(key=key):
                rule = next(rule for rule in self.kernel.rules['-4'] if rule.get('priority') == 1)
                rule[key] = value
                with self.assertRaises(namespace.IsolationError):
                    self.isolate(install=False)
                del rule[key]

    def test_management_cidr_subroute_cannot_override_earlier_policy_denial(self):
        self.cidrs = sorted([*config.BASE_CIDRS, '10.200.0.0/16'])
        self.isolate()
        # More-specific main route is irrelevant to the preceding RPDB blackhole.
        self.kernel.routes['-4'].append({'dst': '10.200.1.2/32', 'gateway': '192.0.2.1'})
        self.assertTrue(self.isolate(install=False))
        rule = next(rule for rule in self.kernel.rules['-4'] if rule.get('dst') == '10.200.0.0' and rule.get('dstlen') == 16)
        self.assertLess(rule['priority'], 32766)


class HostNamespaceIdentity(unittest.TestCase):
    def test_remote_or_unknown_docker_namespace_is_rejected(self):
        for pid, path in [(0, '/var/run/docker/netns/test'), (True, '/var/run/docker/netns/test'),
                          (400, '/proc/1/ns/net'), (400, '/var/run/docker/netns/../../host')]:
            with self.subTest(pid=pid, path=path), self.assertRaises(namespace.IsolationError):
                namespace._namespace(pid, path)

    def test_host_network_and_mismatched_sandbox_inode_are_rejected(self):
        host = SimpleNamespace(st_dev=1, st_ino=1)
        other = SimpleNamespace(st_dev=1, st_ino=2)
        for values in ([host, host, host], [other, host, host]):
            with mock.patch.object(namespace.os, 'stat', side_effect=values):
                with self.assertRaises(namespace.IsolationError):
                    namespace._namespace(400, '/var/run/docker/netns/test')

    def test_argv_is_bounded_host_command_not_container_shell(self):
        with mock.patch.object(namespace, '_ip_binary', return_value='/usr/bin/ip'), mock.patch.object(namespace.subprocess, 'run', return_value=SimpleNamespace(stdout='[]')) as call:
            self.assertEqual('[]', namespace._run('/proc/400/fd/42', '-4', '-j', 'rule', 'show'))
        args, kwargs = call.call_args
        self.assertEqual(['/usr/bin/nsenter', '--net=/proc/400/fd/42', '--',
                          '/usr/bin/ip', '-4', '-j', 'rule', 'show'], args[0])
        self.assertEqual(5, kwargs['timeout'])
        self.assertNotIn('shell', kwargs)
        self.assertEqual('C', kwargs['env']['LC_ALL'])


if __name__ == '__main__':
    unittest.main()
