"""Native Docker boundary, invoked only by the exact-input installer hooks.

Unsigned Zun labels never select scope, grant admission, or prove enforcement.
The configured dedicated project is the scope; its exact service user is the
only creator. Native Docker identity labels are read together with actual limits
and the independently inspected host namespace on EVERY readiness operation.
"""
import copy
import contextvars
import functools
import ipaddress
import json
import math
import os
import re
from types import SimpleNamespace

from oslo_config import cfg
from oslo_concurrency import lockutils

from afterglow_zun_cloud_shell import config
from afterglow_zun_cloud_shell import namespace

REVISION = 'cloud-shell-v1'
PROOF = 'afterglow.runtime_profile'
PREFIX = 'afterglow.native_shell.'
MIB = 1024 * 1024
_creating_holder = contextvars.ContextVar('cloud_shell_creating_holder', default=None)
_creating_network = contextvars.ContextVar('cloud_shell_creating_network', default=None)


class ProfileError(RuntimeError):
    pass


def serialized(function):
    @functools.wraps(function)
    def locked(driver, context, container, *args, **kwargs):
        if not managed(container):
            return function(driver, context, container, *args, **kwargs)
        opts, _ = settings()
        path = opts.lock_path
        if not os.path.isabs(path) or os.path.realpath(path) != path:
            raise ProfileError('Native lock path must be canonical and absolute')
        with lockutils.lock(_holder_name(container), external=True,
                            lock_path=path, lock_file_prefix='afterglow-shell'):
            return function(driver, context, container, *args, **kwargs)
    return locked


def settings():
    opts = cfg.CONF.afterglow_cloud_shell
    if not opts.enabled:
        return None
    if not opts.service_project_id or not opts.service_user_id:
        raise ProfileError('Cloud Shell service identity is required')
    if not re.fullmatch(r'[^\s@]+@sha256:[0-9a-f]{64}', opts.sandbox_image):
        raise ProfileError('Native network holder image must be digest pinned')
    try:
        cidrs = sorted({str(ipaddress.ip_network(value, strict=True))
                        for value in list(opts.blocked_cidrs) + list(config.BASE_CIDRS)})
    except (ValueError, TypeError) as error:
        raise ProfileError('Invalid blocked CIDRs') from error
    if len(cidrs) > 64:
        raise ProfileError('Too many blocked CIDRs')
    return opts, cidrs


def managed(container):
    value = settings()
    return bool(value and container.project_id == value[0].service_project_id)


def admit(context, container):
    if not managed(container):
        return False
    opts, _ = settings()
    if (container.user_id != opts.service_user_id
            or context.project_id != opts.service_project_id
            or context.user_id != opts.service_user_id):
        raise ProfileError('Cloud Shell project admits only its configured service user')
    if getattr(container, 'obj_name', lambda: 'Container')() != 'Container':
        raise ProfileError('Capsules are not admitted in the Cloud Shell project')
    return True


def profile(container):
    opts, cidrs = settings()
    cpu = container.cpu
    memory = container.memory
    if (isinstance(cpu, bool) or not isinstance(cpu, (float, int))
            or not math.isfinite(cpu) or not 0 < cpu <= 1
            or int(cpu * 100000) < 1000):
        raise ProfileError('Cloud Shell CPU must be finite and between 0.01 and one')
    # The pinned real Zun Container.memory is a StringField, not IntegerField.
    if type(memory) is str and re.fullmatch(r'[1-9][0-9]{2,3}', memory):
        memory = int(memory)
    if type(memory) is not int or not 256 <= memory <= 1024:
        raise ProfileError('Cloud Shell memory must be 256..1024 MiB')
    return {'revision': REVISION, 'cpu': cpu, 'memory_mib': memory,
            'pids_limit': 512, 'readonly_rootfs': True, 'tmpfs_mib': 128,
            'shm_mib': 64, 'log_max_size': '8m', 'log_max_files': 3,
            'blocked_cidrs': cidrs, 'network_isolated': True}


def _identity(container):
    return {PREFIX + 'revision': REVISION,
            PREFIX + 'uuid': container.uuid,
            PREFIX + 'project': container.project_id,
            PREFIX + 'user': container.user_id}


def _holder_name(container):
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', container.uuid):
        raise ProfileError('Invalid native container UUID')
    return 'zun-cloud-shell-net-' + container.uuid


def _get_holder(docker, container):
    holder = docker.inspect_container(_holder_name(container))
    if not isinstance(holder, dict) or not re.fullmatch(r'[0-9a-f]{64}', holder.get('Id', '')):
        raise ProfileError('Native holder identity unavailable')
    labels = holder.get('Config', {}).get('Labels', {})
    expected = dict(_identity(container), **{PREFIX + 'role': 'network'})
    if (any(labels.get(key) != value for key, value in expected.items())
            or set(labels) != set(expected) | {PREFIX + 'addresses'}
            or holder.get('Name') != '/' + _holder_name(container)):
        raise ProfileError('Native holder owner mismatch')
    addresses = json.loads(labels[PREFIX + 'addresses'])
    if not isinstance(addresses, dict) or len(addresses) != 1:
        raise ProfileError('Native holder network ownership missing')
    return holder


def _host_safety(host, holder=False):
    if not isinstance(host, dict):
        raise ProfileError('Docker limits missing')
    if host.get('Privileged') is not False or host.get('ReadonlyRootfs') is not True:
        raise ProfileError('Writable or privileged native container')
    if host.get('CapAdd') or host.get('Devices') or host.get('DeviceRequests'):
        raise ProfileError('Unexpected native capabilities/devices')
    if host.get('PortBindings') or host.get('PublishAllPorts') or host.get('Links'):
        raise ProfileError('Native shell cannot publish/link host ports')
    for key in ('PidMode', 'IpcMode', 'UTSMode', 'UsernsMode', 'CgroupnsMode'):
        if host.get(key) not in (None, '', 'private'):
            raise ProfileError('Foreign host namespace requested')
    if (host.get('Runtime') != 'runc' or host.get('IpcMode') != 'private'
            or host.get('CgroupnsMode') != 'private'):
        raise ProfileError('Native private runtime namespaces unavailable')
    if host.get('RestartPolicy', {}).get('Name') not in ('', 'no'):
        raise ProfileError('Automatic native restart is forbidden')
    if host.get('AutoRemove') is not False:
        raise ProfileError('Automatic native removal is forbidden')
    if holder:
        if (set(host.get('CapDrop') or []) != {'ALL'}
                or not set(host.get('SecurityOpt') or []) >= {'no-new-privileges'}
                or host.get('Binds') or host.get('Mounts') or host.get('Tmpfs')
                or host.get('Memory') != 32 * MIB
                or host.get('MemorySwap') != 32 * MIB
                or host.get('CpuPeriod') != 100000 or host.get('CpuQuota') != 10000
                or host.get('PidsLimit') != 8
                or host.get('LogConfig') != {'Type': 'none', 'Config': {}}):
            raise ProfileError('Native holder controls missing')
    elif (set(host.get('CapDrop') or []) != {'NET_RAW'}
          or host.get('SecurityOpt') not in (None, [])):
        # SETUID/SETGID and ordinary Docker bootstrap capabilities remain usable.
        raise ProfileError('Unexpected shell capability or bootstrap policy')


def _holder_network(docker, container, install=False, user=None):
    holder = _get_holder(docker, container)
    _host_safety(holder.get('HostConfig'), holder=True)
    opts, cidrs = settings()
    image = docker.inspect_image(opts.sandbox_image)
    if holder.get('Image') != image.get('Id'):
        raise ProfileError('Native holder image mismatch')
    conf = holder.get('Config', {})
    if (conf.get('Entrypoint') != ['/pause'] or conf.get('Cmd') not in ([], None)
            or conf.get('User') != '65534:65534' or conf.get('Healthcheck')):
        raise ProfileError('Native holder command mismatch')
    mode = holder['HostConfig'].get('NetworkMode')
    if not isinstance(mode, str) or mode in ('host', 'none', 'bridge', 'default', '') or mode.startswith('container:'):
        raise ProfileError('Unsupported native holder network')
    network = docker.inspect_network(mode)
    if network.get('Driver') != 'kuryr':
        raise ProfileError('Cloud Shell requires a Kuryr network')
    attached = holder.get('NetworkSettings', {}).get('Networks')
    if (not isinstance(attached, dict) or set(attached) != {mode}
            or attached[mode].get('NetworkID') != network.get('Id')
            or set(json.loads(holder['Config']['Labels'][PREFIX + 'addresses'])) != {mode}):
        raise ProfileError('Native holder network attachment changed')
    state = holder.get('State', {})
    if state.get('Running') is not True or state.get('Paused') or state.get('Restarting'):
        raise ProfileError('Native holder is not stably running')
    pid = state.get('Pid')
    key = holder.get('NetworkSettings', {}).get('SandboxKey')
    user_pid = None
    if user is not None:
        if user.get('HostConfig', {}).get('NetworkMode') != 'container:' + holder['Id']:
            raise ProfileError('User container escaped its native network holder')
        if user.get('State', {}).get('Running') is True:
            user_pid = user['State'].get('Pid')
    namespace.isolate(pid, key, cidrs, install=install, user_pid=user_pid)
    again = _get_holder(docker, container)
    if (again.get('State', {}).get('Pid') != pid or again['Id'] != holder['Id']
            or again.get('NetworkSettings', {}).get('SandboxKey') != key):
        raise ProfileError('Native holder changed during verification')
    return holder


def prepare(context, container, volmaps, binds, requested_networks):
    if not admit(context, container):
        return
    profile(container)
    if any(key == PROOF or key.startswith(PREFIX) for key in (container.labels or {})):
        raise ProfileError('Runtime authority labels are native-only')
    if (container.privileged or container.runtime not in (None, '', 'runc')
            or container.restart_policy and container.restart_policy.get('Name') not in ('', 'no')
            or container.auto_remove or container.cpu_policy == 'dedicated'
            or container.healthcheck or container.exposed_ports):
        raise ProfileError('Unsupported Cloud Shell runtime request')
    if len(requested_networks) != 1:
        raise ProfileError('Cloud Shell requires exactly one Kuryr network')
    if len(volmaps) != 1 or len(binds) != 1:
        raise ProfileError('Cloud Shell requires exactly its Cinder home')
    volume = volmaps[0]
    if (volume.volume_provider != 'cinder' or not volume.cinder_volume_id
            or volume.container_path != '/home/cloudshell'
            or volume.project_id != container.project_id):
        raise ProfileError('Only a service-project Cinder home is permitted')
    for source, value in binds.items():
        if (not os.path.isabs(source) or os.path.realpath(source) != source
                or source == '/' or not os.path.isdir(source)
                or value != {'bind': '/home/cloudshell'}):
            raise ProfileError('Untrusted native home bind')


def configure(docker, container, host, kwargs):
    if not managed(container):
        return None
    requested = profile(container)
    # All limits exist in the original Docker CREATE, never docker.update.
    host.pop('cpu_shares', None)
    host.update(cpu_period=100000, cpu_quota=int(requested['cpu'] * 100000),
                runtime='runc', ipc_mode='private', cgroupns='private',
                mem_limit=requested['memory_mib'] * MIB,
                memswap_limit=requested['memory_mib'] * MIB,
                pids_limit=512, read_only=True,
                tmpfs={'/tmp': 'rw,nosuid,nodev,size=128m,mode=1777'},
                shm_size=64 * MIB,
                log_config={'Type': 'json-file', 'Config': {'max-size': '8m', 'max-file': '3'}},
                restart_policy={'Name': 'no', 'MaximumRetryCount': 0},
                auto_remove=False, cap_drop=['NET_RAW'])
    opts, _ = settings()
    holder_host = dict(network_mode=host['network_mode'], privileged=False,
        runtime='runc', ipc_mode='private', cgroupns='private',
        cap_drop=['ALL'], security_opt=['no-new-privileges'], read_only=True,
        mem_limit=32 * MIB, memswap_limit=32 * MIB,
        cpu_period=100000, cpu_quota=10000, pids_limit=8,
        restart_policy={'Name': 'no', 'MaximumRetryCount': 0}, auto_remove=False,
        log_config={'Type': 'none', 'Config': {}})
    holder_kwargs = {'name': _holder_name(container), 'entrypoint': ['/pause'],
        'command': [], 'user': '65534:65534', 'environment': [],
        'labels': dict(_identity(container), **{PREFIX + 'role': 'network',
            PREFIX + 'addresses': json.dumps(container.addresses, separators=(',', ':'), sort_keys=True)}),
        'host_config': docker.create_host_config(**holder_host)}
    for key in ('networking_config', 'mac_address'):
        if key in kwargs:
            holder_kwargs[key] = kwargs.pop(key)
    created = docker.create_container(opts.sandbox_image, **holder_kwargs)
    holder_id = created['Id']
    _creating_holder.set(holder_id)
    # This is trusted /pause, never a user-provided command or image tag.
    docker.start(holder_id)
    holder = _holder_network(docker, container, install=True)
    host['network_mode'] = 'container:' + holder['Id']
    kwargs['hostname'] = None  # Docker forbids hostname with container mode.
    kwargs['labels'] = dict(kwargs.get('labels') or {}, **_identity(container))
    return holder_id


def _verify(docker, container, response=None):
    if not managed(container):
        return
    # Remove stale DB/API proof BEFORE any read; failure never returns authority.
    labels = dict(container.labels or {})
    labels.pop(PROOF, None)
    container.labels = labels
    opts, _ = settings()
    if container.user_id != opts.service_user_id:
        raise ProfileError('Foreign owner inside Cloud Shell project')
    requested = profile(container)
    response = response or docker.inspect_container(container.container_id)
    if response.get('Id') != container.container_id:
        raise ProfileError('Wrong Docker container readback')
    actual_labels = response.get('Config', {}).get('Labels', {})
    if any(actual_labels.get(key) != value for key, value in _identity(container).items()):
        raise ProfileError('Legacy/unproven native container')
    host = response.get('HostConfig')
    _host_safety(host)
    if (host.get('CpuPeriod') != 100000
            or host.get('CpuQuota') != int(requested['cpu'] * 100000)
            or host.get('NanoCpus', 0) != 0
            or host.get('Memory') != requested['memory_mib'] * MIB
            or host.get('MemorySwap') != requested['memory_mib'] * MIB
            or host.get('PidsLimit') != 512 or host.get('ShmSize') != 64 * MIB
            or host.get('Tmpfs') != {'/tmp': 'rw,nosuid,nodev,size=128m,mode=1777'}
            or host.get('LogConfig') != {'Type': 'json-file', 'Config': {'max-size': '8m', 'max-file': '3'}}):
        raise ProfileError('Native Cloud Shell resource controls missing or changed')
    mounts = response.get('Mounts')
    if not isinstance(mounts, list):
        raise ProfileError('Native mount readback unavailable')
    homes = [mount for mount in mounts if mount.get('Destination') == '/home/cloudshell']
    if (len(homes) != 1 or homes[0].get('Type') != 'bind'
            or homes[0].get('RW') is not True
            or any(mount.get('Destination') not in ('/home/cloudshell', '/tmp', '/dev/shm') for mount in mounts)
            or host.get('Mounts')):
        raise ProfileError('Unexpected native mount')
    source = homes[0].get('Source')
    if (not isinstance(source, str) or source == '/' or not os.path.isabs(source)
            or os.path.realpath(source) != source or not os.path.isdir(source)
            or host.get('Binds') != [source + ':/home/cloudshell:rw']):
        raise ProfileError('Native home bind changed')
    _holder_network(docker, container, user=response)
    labels[PROOF] = json.dumps(requested, separators=(',', ':'), sort_keys=True)
    container.labels = labels


def verify(docker, container, response=None):
    try:
        return _verify(docker, container, response)
    except Exception:
        if managed(container) and container.container_id:
            # Never leave a workload running after its native boundary readback
            # fails. This does not remove or alter the persistent home.
            actual = docker.inspect_container(container.container_id)
            labels = actual.get('Config', {}).get('Labels', {})
            if (actual.get('State', {}).get('Running')
                    and all(labels.get(key) == value for key, value in _identity(container).items())):
                docker.stop(container.container_id, timeout=1)
        raise


@serialized
def sync_verify(driver, context, container, docker):
    """One bad shell must not abort host startup or other tenants' state sync."""
    try:
        snapshot = docker.inspect_container(container.container_id)
        verify(docker, container, snapshot)
        driver._populate_container(container, snapshot)
        return True
    except Exception:
        from zun.common import consts
        labels = dict(container.labels or {})
        labels.pop(PROOF, None)
        container.labels = labels
        container.status = consts.ERROR
        container.status_reason = 'Cloud Shell native runtime boundary is unavailable'
        return False


def before_action(docker, context, container, action):
    if not admit(context, container):
        return False
    verify(docker, container)
    if action in ('update', 'network_attach', 'network_detach', 'add_security_group', 'remove_security_group'):
        raise ProfileError('Cloud Shell runtime changes require a fresh container')
    return True


def reboot(docker, context, container, timeout):
    if not before_action(docker, context, container, 'reboot'):
        return False
    # docker.restart can recreate networking without an intervening check.
    docker.stop(container.container_id, timeout=int(timeout) if timeout else 10)
    verify(docker, container)
    docker.start(container.container_id)
    verify(docker, container)
    return True


def cleanup_network(docker, context, container, network_driver):
    if not managed(container):
        return False
    # Deletion may use the native reconciler's elevated context, but identity
    # comes only from exact DB object + independently read native holder labels.
    from docker.errors import NotFound
    try:
        holder = _get_holder(docker, container)
    except NotFound:
        holder = None
    addresses = (json.loads(holder['Config']['Labels'][PREFIX + 'addresses'])
                 if holder else container.addresses)
    proxy = SimpleNamespace(container_id=holder['Id'] if holder else None,
                            addresses=addresses)
    for network in addresses or {}:
        network_driver.disconnect_container_from_network(proxy, network)
    if holder:
        docker.remove_container(holder['Id'], force=True)
    return True


def delete(driver, docker, context, container, force):
    if not managed(container):
        return False
    from docker.errors import NotFound
    from zun.network import network as zun_network
    target = container.container_id or driver.get_container_name(container)
    try:
        actual = docker.inspect_container(target)
    except NotFound:
        actual = None
    if actual is not None:
        labels = actual.get('Config', {}).get('Labels', {})
        if any(labels.get(key) != value for key, value in _identity(container).items()):
            raise ProfileError('Refusing to delete an unproven native container')
        docker.remove_container(actual['Id'], force=force)
    network_driver = zun_network.driver(context=context, docker_api=docker)
    cleanup_network(docker, context, container, network_driver)
    driver._cleanup_exposed_ports(network_driver.neutron_api, container)
    return True


def network_ready(container, network_driver):
    """Record only a successful native port result owned by this invocation."""
    if not managed(container):
        return
    addresses = copy.deepcopy(container.addresses)
    if (not isinstance(addresses, dict) or len(addresses) != 1
            or any(not isinstance(entries, list) or not entries
                   or any(not isinstance(entry, dict)
                          or not isinstance(entry.get('port'), str) or not entry['port']
                          or type(entry.get('preserve_on_delete')) is not bool
                          for entry in entries)
                   for entries in addresses.values())):
        raise ProfileError('Native network allocation ownership is uncertain; automatic cleanup unavailable')
    _creating_network.set((network_driver, addresses))


def cleanup_pre_holder(docker, container, allocation):
    network_driver, addresses = allocation
    from docker.errors import NotFound
    try:
        holder = _get_holder(docker, container)
    except NotFound:
        holder = None
    if holder and json.loads(holder['Config']['Labels'][PREFIX + 'addresses']) != addresses:
        raise ProfileError('Refusing cleanup of a replaced native network allocation')
    proxy = SimpleNamespace(container_id=holder['Id'] if holder else None,
                            addresses=addresses)
    for network in addresses:
        network_driver.disconnect_container_from_network(proxy, network)
    if holder:
        docker.remove_container(holder['Id'], force=True)


def creation(function):
    @functools.wraps(function)
    def guarded(driver, context, container, *args, **kwargs):
        token = _creating_holder.set(None)
        network_token = _creating_network.set(None)
        try:
            if admit(context, container):
                recover_orphan(driver, context, container)
            return function(driver, context, container, *args, **kwargs)
        except Exception:
            holder_id = _creating_holder.get()
            if holder_id:
                from zun.container.docker import utils as docker_utils
                from docker.errors import NotFound
                with docker_utils.docker_client() as docker:
                    try:
                        holder = _get_holder(docker, container)
                    except NotFound:
                        holder = None
                    if holder is not None and holder['Id'] == holder_id:
                        delete(driver, docker, context, container, True)
            elif _creating_network.get() is not None:
                from zun.container.docker import utils as docker_utils
                allocation = _creating_network.get()
                try:
                    with docker_utils.docker_client() as docker:
                        cleanup_pre_holder(docker, container, allocation)
                except Exception as error:
                    ports = sorted(entry['port'] for entries in allocation[1].values() for entry in entries)
                    raise ProfileError('Native pre-holder network cleanup is uncertain for ports: '
                                       + ','.join(ports)) from error
            raise
        finally:
            _creating_holder.reset(token)
            _creating_network.reset(network_token)
    return guarded


def recover_orphan(driver, context, container):
    # Recovery is by one exact UUID-derived native holder name, never a global
    # Docker scan. A still-present user container blocks recovery/adoption.
    from docker.errors import NotFound
    from zun.container.docker import utils as docker_utils
    from zun.network import network as zun_network
    with docker_utils.docker_client() as docker:
        try:
            holder = _get_holder(docker, container)
        except NotFound:
            return
        try:
            docker.inspect_container(driver.get_container_name(container))
        except NotFound:
            network_driver = zun_network.driver(context=context, docker_api=docker)
            cleanup_network(docker, context, container, network_driver)
            return
        raise ProfileError('Existing native user container cannot be silently adopted')
