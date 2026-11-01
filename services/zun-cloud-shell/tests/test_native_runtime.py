"""Installed pinned Zun + real Docker SDK serialization, synthetic provider only.

No fake Zun modules/sys.modules substitutions. This runner does NOT qualify a
real Docker host, Kuryr, Linux namespace/cgroup enforcement or production fleet.
"""
import contextlib
import copy
import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from docker.errors import NotFound
from docker.types import HostConfig
from oslo_config import cfg
from zun import objects
from zun.common import consts
from zun.container.docker import driver as native
from zun.afterglow_cloud_shell_build import BUILD

from afterglow_zun_cloud_shell import config, hooks, namespace

PROJECT = '11111111111111111111111111111111'
USER = '22222222222222222222222222222222'
UUID = '33333333-3333-4333-8333-333333333333'
IMAGE = 'registry.invalid/holder@sha256:' + 'a' * 64


class DockerBoundary:
    """Synthetic daemon implements Docker inspect shape, not policy decisions."""
    def __init__(self, home):
        self.home = home
        self.containers = {}
        self.names = {}
        self.events = []
        self.next_id = 1
        self.fail_user_create = False

    def create_host_config(self, **kwargs):
        return dict(HostConfig(version='1.41', **kwargs))

    def inspect_image(self, image):
        return {'Id': 'sha256:' + 'b' * 64,
                'Config': {'Entrypoint': ['/bin/sleep'], 'Cmd': ['infinity']}}

    def inspect_network(self, network):
        return {'Driver': 'kuryr', 'Id': network}

    def create_container(self, image, **kwargs):
        role = kwargs.get('labels', {}).get(hooks.PREFIX + 'role')
        if self.fail_user_create and role != 'network':
            raise RuntimeError('synthetic daemon user-create failure')
        if kwargs['name'] in self.names:
            raise RuntimeError('name collision')
        cid = '%064x' % self.next_id
        self.next_id += 1
        self.names[kwargs['name']] = cid
        host = copy.deepcopy(kwargs['host_config'])
        host.setdefault('Privileged', False)
        host.setdefault('AutoRemove', False)
        host.setdefault('RestartPolicy', {'Name': 'no', 'MaximumRetryCount': 0})
        mounts = []
        for bind in host.get('Binds') or []:
            source, destination, mode = bind.split(':')
            mounts.append({'Type': 'bind', 'Source': source, 'Destination': destination, 'RW': mode == 'rw'})
        self.containers[cid] = {'Id': cid, 'Name': '/' + kwargs['name'],
            'Image': self.inspect_image(image)['Id'], 'HostConfig': host,
            'Config': {'Labels': copy.deepcopy(kwargs.get('labels', {})),
                       'Entrypoint': kwargs.get('entrypoint'), 'Cmd': kwargs.get('command'),
                       'User': kwargs.get('user', ''), 'Hostname': ''},
            'State': {'Running': False, 'Paused': False, 'Pid': 0, 'Restarting': False,
                      'StartedAt': '0001-01-01T00:00:00Z', 'FinishedAt': '0001-01-01T00:00:00Z'},
            'NetworkSettings': {'SandboxKey': '/var/run/docker/netns/test',
                'Networks': {host['NetworkMode']: {'NetworkID': host['NetworkMode']}}}, 'Mounts': mounts}
        self.events.append(('create', role or 'user', cid, copy.deepcopy(host)))
        return {'Id': cid}

    def inspect_container(self, cid):
        cid = self.names.get(cid, cid)
        if cid not in self.containers:
            raise NotFound('synthetic missing container')
        return copy.deepcopy(self.containers[cid])

    def list_containers(self):
        return [dict(copy.deepcopy(container), Names=[container['Name']])
                for container in self.containers.values()]

    def start(self, cid):
        self.events.append(('start', cid))
        self.containers[cid]['State'].update(Running=True, Paused=False, Pid=400 + int(cid, 16))

    def stop(self, cid, timeout=None):
        self.events.append(('stop', cid))
        self.containers[cid]['State'].update(Running=False, Pid=0)

    def restart(self, cid, **kwargs):
        self.events.append(('restart', cid))
        raise AssertionError('managed reboot must not call docker.restart')

    def unpause(self, cid):
        self.events.append(('unpause', cid))
        self.containers[cid]['State']['Paused'] = False

    def remove_container(self, cid, force=False):
        self.events.append(('remove', cid))
        del self.containers[cid]
        self.names = {name: value for name, value in self.names.items() if value != cid}

    def exec_create(self, cid, command, **kwargs):
        self.events.append(('exec', cid))
        return {'Id': 'exec-fixture'}

    def update_container(self, cid, **kwargs):
        self.events.append(('update', cid, kwargs))
        return {}


class NetworkBoundary:
    def __init__(self):
        self.neutron_api = SimpleNamespace()
        self.disconnected = []
        self.ports = {}
        self.disconnected_addresses = []

    def get_or_create_network(self, context, network):
        pass

    def process_networking_config(self, container, requested, host, kwargs, docker, **extra):
        host['network_mode'] = requested['network']
        kwargs['networking_config'] = {'EndpointsConfig': {requested['network']: {}}}
        self.ports['synthetic-port'] = 'allocated'
        container.addresses = {requested['network']: [
            {'port': 'synthetic-port', 'preserve_on_delete': False}]}

    def on_container_started(self, container):
        pass

    def disconnect_container_from_network(self, container, network):
        self.disconnected.append((container.container_id, network))
        self.disconnected_addresses.append(copy.deepcopy(container.addresses))
        for entry in container.addresses[network]:
            if entry['preserve_on_delete']:
                self.ports[entry['port']] = 'unbound'
            else:
                self.ports.pop(entry['port'], None)


class InstalledNativeRuntime(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = self.temporary.name
        for name, value in {'enabled': True, 'service_project_id': PROJECT,
                'service_user_id': USER, 'sandbox_image': IMAGE,
                'blocked_cidrs': ['10.200.0.0/16'], 'lock_path': self.home}.items():
            cfg.CONF.set_override(name, value, group=config.GROUP)
            self.addCleanup(cfg.CONF.clear_override, name, group=config.GROUP)
        cfg.CONF.set_override('docker_remote_api_version', '1.41', group='docker')
        self.addCleanup(cfg.CONF.clear_override, 'docker_remote_api_version', group='docker')
        self.context = SimpleNamespace(project_id=PROJECT, user_id=USER)
        self.container = objects.Container(
            uuid=UUID, name='test-shell', project_id=PROJECT, user_id=USER,
            cpu=.5, memory='1024', privileged=False, runtime='runc',
            restart_policy=None, auto_remove=False, cpu_policy='shared',
            healthcheck=None, labels={'client': 'unsigned'}, container_id=None,
            command=['/bin/sleep', 'infinity'], entrypoint=['/bin/sleep'],
            environment={}, workdir='/home/cloudshell', tty=True,
            interactive=True, hostname=None, disk=0, exposed_ports={},
            security_groups=['synthetic-egress-only'], addresses={},
            status=consts.CREATING, task_state=None)
        self.volume = SimpleNamespace(volume_provider='cinder', cinder_volume_id=UUID,
                                      container_path='/home/cloudshell', project_id=PROJECT)
        self.docker = DockerBoundary(self.home)
        self.network = NetworkBoundary()
        self.driver = native.DockerDriver.__new__(native.DockerDriver)
        self.driver._get_volume_driver = lambda volume: SimpleNamespace(
            bind_mount=lambda context, volume: (self.home, '/home/cloudshell'))
        self.driver._cleanup_exposed_ports = lambda *args: None
        self.saved = mock.patch.object(objects.Container, 'save', autospec=True).start()
        self.addCleanup(mock.patch.stopall)
        @contextlib.contextmanager
        def client():
            yield self.docker
        mock.patch.object(native.docker_utils, 'docker_client', client).start()
        mock.patch.object(native.zun_network, 'driver', return_value=self.network).start()
        mock.patch.object(native.utils, 'get_security_group_ids', return_value=['synthetic-egress-only']).start()
        self.route_failure = False
        def boundary(pid, key, cidrs, install=False, user_pid=None):
            self.docker.events.append(('isolate', install, tuple(cidrs), user_pid))
            if self.route_failure:
                raise namespace.IsolationError('synthetic kernel readback failure')
            return True
        mock.patch.object(namespace, 'isolate', side_effect=boundary).start()

    def create(self):
        return self.driver.create(self.context, self.container,
            {'repo': 'registry.invalid/cloudshell', 'tag': 'immutable'},
            [{'network': '44444444-4444-4444-8444-444444444444'}],
            {UUID: [self.volume]})

    def test_loaded_pinned_real_driver_and_build_receipt(self):
        self.assertEqual('17a8a03d19ac0a063ff7bb7e54e8503bd60536cd', BUILD['source_commit'])
        self.assertEqual(hooks.REVISION, BUILD['hook_revision'])
        path = Path(inspect.getfile(native))
        self.assertEqual(BUILD['files']['zun/container/docker/driver.py'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIs(native.DockerDriver, __import__('zun.container.docker.driver', fromlist=['DockerDriver']).DockerDriver)

    def test_quota_pid_rootfs_tmpfs_logs_before_user_create_and_native_proof(self):
        self.create()
        user = self.docker.inspect_container(self.container.container_id)
        host = user['HostConfig']
        self.assertEqual(100000, host['CpuPeriod'])
        self.assertEqual(50000, host['CpuQuota'])
        self.assertNotIn('CpuShares', host)
        self.assertEqual(512, host['PidsLimit'])
        self.assertTrue(host['ReadonlyRootfs'])
        self.assertEqual({'/tmp': 'rw,nosuid,nodev,size=128m,mode=1777'}, host['Tmpfs'])
        self.assertEqual(64 * hooks.MIB, host['ShmSize'])
        self.assertEqual({'Type': 'json-file', 'Config': {'max-size': '8m', 'max-file': '3'}}, host['LogConfig'])
        self.assertEqual(['NET_RAW'], host['CapDrop'])  # setuid bootstrap remains permitted
        self.assertNotIn('SecurityOpt', host)
        events = self.docker.events
        installed = next(index for index, event in enumerate(events) if event[:2] == ('isolate', True))
        user_create = next(index for index, event in enumerate(events) if event[:2] == ('create', 'user'))
        self.assertLess(installed, user_create)
        self.assertFalse(user['State']['Running'])
        proof = json.loads(self.container.labels[hooks.PROOF])
        self.assertEqual(1024, proof['memory_mib'])
        self.assertEqual(sorted(set(config.BASE_CIDRS) | {'10.200.0.0/16'}), proof['blocked_cidrs'])
        self.assertNotIn(hooks.PROOF, user['Config']['Labels'])

    def test_unsigned_no_label_service_project_is_still_enforced(self):
        self.container.labels = {}
        self.create()
        self.assertIn(hooks.PROOF, self.container.labels)
        self.assertEqual(512, self.docker.inspect_container(self.container.container_id)['HostConfig']['PidsLimit'])

    def test_user_cannot_supply_native_or_proof_labels(self):
        for label in (hooks.PROOF, hooks.PREFIX + 'revision'):
            with self.subTest(label=label):
                self.container.labels = {label: hooks.REVISION}
                with self.assertRaises(hooks.ProfileError):
                    self.create()
        self.assertFalse(self.docker.events)

    def test_wrong_service_user_even_with_labels_is_denied(self):
        self.container.user_id = 'foreign-user'
        with self.assertRaises(hooks.ProfileError):
            self.create()
        self.assertFalse(self.docker.events)

    def test_foreign_caller_cannot_admit_service_owned_object(self):
        self.context.user_id = 'foreign-caller'
        with self.assertRaises(hooks.ProfileError):
            self.create()
        self.assertFalse(self.docker.events)

    def test_invalid_cpu_and_memory_fail_without_workload(self):
        for cpu in (0, -1, .00001, .00999, 1.01, float('inf'), float('nan')):
            self.container.cpu = cpu
            with self.subTest(cpu=cpu), self.assertRaises(hooks.ProfileError):
                self.create()
        self.container.cpu = .5
        for memory in ('0', '255', '1025', '1024M', 'NaN'):
            self.container.memory = memory
            with self.subTest(memory=memory), self.assertRaises(hooks.ProfileError):
                self.create()
        self.assertFalse(self.docker.events)

    def test_lower_requested_limits_are_preserved(self):
        self.container.cpu = .25
        self.container.memory = '256'
        self.create()
        host = self.docker.inspect_container(self.container.container_id)['HostConfig']
        self.assertEqual(25000, host['CpuQuota'])
        self.assertEqual(256 * hooks.MIB, host['Memory'])
        self.assertEqual(256, json.loads(self.container.labels[hooks.PROOF])['memory_mib'])

    def test_metadata_failure_never_creates_or_starts_user_and_reaps_holder(self):
        self.route_failure = True
        with self.assertRaises(namespace.IsolationError):
            self.create()
        self.assertFalse(any(event[:2] == ('create', 'user') for event in self.docker.events))
        self.assertEqual({}, self.docker.containers)
        self.assertNotIn(hooks.PROOF, self.container.labels)

    def test_user_create_failure_reaps_exact_holder_not_other_resources(self):
        self.docker.fail_user_create = True
        with self.assertRaises(RuntimeError):
            self.create()
        self.assertEqual({}, self.docker.containers)
        self.assertEqual(1, len(self.network.disconnected))

    def test_holder_create_failure_cleans_only_successful_invocation_port_snapshot(self):
        self.network.ports['unrelated-port'] = 'allocated'
        original_create = self.docker.create_container

        def fail_holder(image, **kwargs):
            if kwargs.get('labels', {}).get(hooks.PREFIX + 'role') == 'network':
                # Mutating the DB object's addresses must not widen cleanup:
                # only the successful process_networking_config snapshot counts.
                self.container.addresses = {'other-network': [
                    {'port': 'unrelated-port', 'preserve_on_delete': False}]}
                raise RuntimeError('synthetic holder image is not preseeded')
            return original_create(image, **kwargs)

        with mock.patch.object(self.docker, 'create_container', side_effect=fail_holder):
            with self.assertRaisesRegex(RuntimeError, 'not preseeded'):
                self.create()
        self.assertEqual({'unrelated-port': 'allocated'}, self.network.ports)
        self.assertEqual({}, self.docker.containers)
        self.assertEqual([(None, '44444444-4444-4444-8444-444444444444')], self.network.disconnected)
        self.assertEqual({'port': 'synthetic-port', 'preserve_on_delete': False},
                         next(iter(self.network.disconnected_addresses[0].values()))[0])

    def test_holder_create_failure_preserves_requested_existing_port(self):
        original_network = self.network.process_networking_config

        def existing_port(*args, **kwargs):
            original_network(*args, **kwargs)
            for entries in self.container.addresses.values():
                entries[0]['preserve_on_delete'] = True

        with mock.patch.object(self.network, 'process_networking_config', side_effect=existing_port), mock.patch.object(self.docker, 'create_container', side_effect=RuntimeError('holder create failed')):
            with self.assertRaisesRegex(RuntimeError, 'holder create failed'):
                self.create()
        self.assertEqual({'synthetic-port': 'unbound'}, self.network.ports)
        self.assertTrue(next(iter(self.network.disconnected_addresses[0].values()))[0]['preserve_on_delete'])

    def test_pre_holder_native_cleanup_failure_is_reported_as_uncertain(self):
        with mock.patch.object(self.docker, 'create_container', side_effect=RuntimeError('holder create failed')), mock.patch.object(self.network, 'disconnect_container_from_network', side_effect=RuntimeError('native Neutron cleanup failed')):
            with self.assertRaisesRegex(hooks.ProfileError, 'uncertain for ports: synthetic-port'):
                self.create()
        self.assertEqual({'synthetic-port': 'allocated'}, self.network.ports)

    def test_failed_process_config_response_is_not_claimed_as_owned_cleanup(self):
        original_network = self.network.process_networking_config

        def unknown_result(*args, **kwargs):
            original_network(*args, **kwargs)
            raise RuntimeError('native process_networking_config result is unknown')

        with mock.patch.object(self.network, 'process_networking_config', side_effect=unknown_result):
            with self.assertRaisesRegex(RuntimeError, 'result is unknown'):
                self.create()
        self.assertEqual({'synthetic-port': 'allocated'}, self.network.ports)
        self.assertEqual([], self.network.disconnected)

    def test_lifecycle_rechecks_and_update_cannot_weaken_controls(self):
        self.create()
        self.driver.start(self.context, self.container)
        self.driver.execute_create(self.context, self.container, ['/bin/bash'], True)
        self.driver.reboot(self.context, self.container, 5)
        self.container.memory = '256'
        with self.assertRaises(hooks.ProfileError):
            self.driver.update(self.context, self.container)
        self.assertFalse(any(event[0] == 'update' for event in self.docker.events))
        self.assertFalse(any(event[0] == 'restart' for event in self.docker.events))
        self.assertTrue(any(event[0] == 'exec' for event in self.docker.events))

    def test_all_security_relevant_inspect_tampering_and_unknown_fail_closed(self):
        self.create()
        cid = self.container.container_id
        original = copy.deepcopy(self.docker.containers[cid])
        for key, value in [('CpuQuota', 0), ('CpuPeriod', 0), ('PidsLimit', -1),
                ('ReadonlyRootfs', False), ('Memory', 0), ('MemorySwap', -1),
                ('ShmSize', 0), ('Tmpfs', {}), ('LogConfig', {}),
                ('Privileged', True), ('CapAdd', ['NET_ADMIN']),
                ('NetworkMode', 'host'), ('PidMode', 'host')]:
            with self.subTest(key=key):
                self.docker.containers[cid] = copy.deepcopy(original)
                self.docker.containers[cid]['HostConfig'][key] = value
                with self.assertRaises(hooks.ProfileError):
                    self.driver.start(self.context, self.container)
                self.assertNotIn(hooks.PROOF, self.container.labels)
        self.docker.containers[cid] = copy.deepcopy(original)
        self.docker.containers[cid].pop('HostConfig')
        with self.assertRaises(hooks.ProfileError):
            self.driver.show(self.context, self.container)

    def test_revoked_metadata_routes_block_restart_unpause_exec(self):
        self.create()
        self.route_failure = True
        for method, args in [(self.driver.start, ()), (self.driver.reboot, (1,)),
                             (self.driver.unpause, ()), (self.driver.execute_create, (['id'],))]:
            with self.subTest(method=method.__name__), self.assertRaises(namespace.IsolationError):
                method(self.context, self.container, *args)
        self.assertFalse(any(event[0] == 'exec' for event in self.docker.events))
        self.assertNotIn(hooks.PROOF, self.container.labels)

    def test_delete_user_before_holder_preserves_home_and_no_global_scan(self):
        self.create()
        user = self.container.container_id
        holder = self.docker.names[hooks._holder_name(self.container)]
        marker = Path(self.home, 'user-data')
        marker.write_text('preserve this Cinder home')
        self.driver.delete(self.context, self.container, False)
        removed = [event[1] for event in self.docker.events if event[0] == 'remove']
        self.assertEqual([user, holder], removed)
        self.assertEqual('preserve this Cinder home', marker.read_text())
        self.assertEqual([(holder, '44444444-4444-4444-8444-444444444444')], self.network.disconnected)

    def test_missing_holder_or_foreign_holder_never_gets_adopted(self):
        self.create()
        holder = self.docker.names[hooks._holder_name(self.container)]
        self.docker.containers[holder]['Config']['Labels'][hooks.PREFIX + 'user'] = 'other'
        with self.assertRaises(hooks.ProfileError):
            self.driver.start(self.context, self.container)
        with self.assertRaises(hooks.ProfileError):
            self.driver.delete(self.context, self.container, False)
        self.assertIn(holder, self.docker.containers)

    def test_foreign_project_retains_stock_driver_behavior(self):
        self.container.project_id = 'other-project'
        self.context.project_id = 'other-project'
        self.create()
        host = self.docker.inspect_container(self.container.container_id)['HostConfig']
        self.assertEqual(512, host['CpuShares'])
        self.assertNotIn('CpuQuota', host)
        self.assertNotIn(hooks.PROOF, self.container.labels)
        self.assertEqual(1, len(self.docker.containers))

    def test_exact_orphan_holder_recovery_before_fresh_create(self):
        self.create()
        first_holder = self.docker.names[hooks._holder_name(self.container)]
        self.docker.remove_container(self.container.container_id, force=True)
        self.container.container_id = None
        self.container.labels = {'client': 'unsigned'}
        self.container.addresses = {}  # crash before DB addresses were saved
        self.create()
        self.assertNotIn(first_holder, self.docker.containers)
        self.assertEqual(2, len(self.docker.containers))
        self.assertEqual(first_holder, self.network.disconnected[0][0])

    def test_crash_before_user_id_saved_still_deletes_exact_native_user_and_holder(self):
        self.create()
        self.container.container_id = None
        self.container.addresses = {}
        self.driver.delete(self.context, self.container, True)
        self.assertEqual({}, self.docker.containers)
        self.assertEqual(1, len(self.network.disconnected))

    def test_existing_native_user_is_never_adopted_by_create(self):
        self.create()
        previous = set(self.docker.containers)
        self.container.container_id = None
        with self.assertRaisesRegex(hooks.ProfileError, 'silently adopted'):
            self.create()
        self.assertEqual(previous, set(self.docker.containers))

    def test_foreign_or_host_holder_network_never_runs_user(self):
        self.create()
        holder = self.docker.names[hooks._holder_name(self.container)]
        self.docker.containers[holder]['HostConfig']['NetworkMode'] = 'host'
        with self.assertRaises(hooks.ProfileError):
            self.driver.start(self.context, self.container)

    def test_running_user_stops_when_namespace_readback_fails(self):
        self.create()
        self.driver.start(self.context, self.container)
        self.route_failure = True
        with self.assertRaises(namespace.IsolationError):
            self.driver.show(self.context, self.container)
        self.assertFalse(self.docker.inspect_container(self.container.container_id)['State']['Running'])

    def test_namespace_and_security_group_mutations_are_refused(self):
        self.create()
        for method, value in [(self.driver.network_attach, {'network': 'other'}),
                              (self.driver.network_detach, 'existing'),
                              (self.driver.add_security_group, 'other'),
                              (self.driver.remove_security_group, 'existing')]:
            with self.subTest(method=method.__name__), self.assertRaises(hooks.ProfileError):
                method(self.context, self.container, value)

    def test_managed_creation_never_runs_kuryr_setup_for_user(self):
        with mock.patch.object(self.driver, '_setup_network_for_container',
                side_effect=AssertionError('user must not enter Kuryr network setup')) as setup:
            self.create()
        setup.assert_not_called()

    def test_exposed_ports_are_denied_before_native_workload(self):
        self.container.exposed_ports = {'80/tcp': {}}
        with self.assertRaises(hooks.ProfileError):
            self.create()
        self.assertFalse(self.docker.events)

    def test_failed_shell_boundary_does_not_abort_other_project_list_or_host_sync(self):
        self.create()
        self.driver.start(self.context, self.container)
        managed = self.container
        managed_id = managed.container_id
        foreign_id = 'f' * 64
        foreign = objects.Container(uuid='55555555-5555-4555-8555-555555555555',
            project_id='foreign-project', user_id='foreign-user',
            container_id=foreign_id, status=consts.STOPPED, task_state=None,
            labels={}, hostname=None)
        foreign_docker = copy.deepcopy(self.docker.containers[managed_id])
        foreign_docker.update(Id=foreign_id, Name='/zun-' + foreign.uuid)
        self.docker.containers[foreign_id] = foreign_docker
        self.route_failure = True
        with mock.patch.object(self.driver, '_get_local_containers', return_value=[managed, foreign]):
            containers, absent = self.driver.list(self.context)
        self.assertEqual([managed, foreign], containers)
        self.assertEqual([], absent)
        self.assertEqual(consts.ERROR, managed.status)
        self.assertNotIn(hooks.PROOF, managed.labels)
        self.assertFalse(self.docker.inspect_container(managed_id)['State']['Running'])
        self.assertTrue(self.docker.inspect_container(foreign_id)['State']['Running'])

    def test_minimum_cpu_is_kernel_valid_quota_and_keeps_requested_proof(self):
        self.container.cpu = .01
        self.create()
        host = self.docker.inspect_container(self.container.container_id)['HostConfig']
        self.assertEqual(1000, host['CpuQuota'])
        self.assertEqual(.01, json.loads(self.container.labels[hooks.PROOF])['cpu'])

    def test_show_and_sync_snapshot_and_failure_stop_are_inside_lifecycle_lock(self):
        self.create()
        self.driver.start(self.context, self.container)
        original_inspect = self.docker.inspect_container
        for operation in ('show', 'sync'):
            with self.subTest(operation=operation):
                entered = threading.Event()
                release = threading.Event()
                reboot_attempted = threading.Event()
                reboot_stopped = threading.Event()
                failures = []

                def gated_inspect(cid):
                    if (threading.current_thread().name == 'native-observation'
                            and cid == self.container.container_id and not entered.is_set()):
                        entered.set()
                        if not release.wait(5):
                            raise AssertionError('Observation release timed out')
                    return original_inspect(cid)

                original_stop = self.docker.stop

                def observed_stop(cid, timeout=None):
                    if threading.current_thread().name == 'native-reboot':
                        reboot_stopped.set()
                    return original_stop(cid, timeout)

                def observe():
                    try:
                        if operation == 'show':
                            self.driver.show(self.context, self.container)
                        else:
                            hooks.sync_verify(self.driver, self.context, self.container, self.docker)
                    except Exception as error:
                        failures.append(error)

                def restart():
                    reboot_attempted.set()
                    try:
                        self.driver.reboot(self.context, self.container, 1)
                    except Exception as error:
                        failures.append(error)

                with mock.patch.object(self.docker, 'inspect_container', side_effect=gated_inspect), mock.patch.object(self.docker, 'stop', side_effect=observed_stop):
                    observer = threading.Thread(target=observe, name='native-observation')
                    rebooter = threading.Thread(target=restart, name='native-reboot')
                    observer.start()
                    try:
                        self.assertTrue(entered.wait(5))
                        rebooter.start()
                        self.assertTrue(reboot_attempted.wait(5))
                        self.assertFalse(reboot_stopped.wait(.2))
                    finally:
                        release.set()
                        observer.join(5)
                        if rebooter.ident is not None:
                            rebooter.join(5)
                    self.assertFalse(observer.is_alive())
                    self.assertFalse(rebooter.is_alive())
                    self.assertTrue(reboot_stopped.is_set())
                    self.assertEqual([], failures)


if __name__ == '__main__':
    unittest.main()
