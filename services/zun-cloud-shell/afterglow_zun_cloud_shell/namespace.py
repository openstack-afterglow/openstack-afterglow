"""Host-only network isolation; never execute a command in a user container.

The existing Zun privsep helper starts this context. The compute must see the
Docker host's /proc and sandbox mount namespace. A remote Docker daemon, Docker
Desktop guest invisible to compute, or missing capabilities fails closed.
"""
import ipaddress
import json
import os
import re
import subprocess

from oslo_privsep import capabilities
from oslo_privsep import priv_context

context = priv_context.PrivContext(
    'afterglow_zun_cloud_shell', cfg_section='afterglow_cloud_shell_privsep',
    pypath=__name__ + '.context', capabilities=[capabilities.CAP_SYS_ADMIN,
        capabilities.CAP_NET_ADMIN, capabilities.CAP_SYS_PTRACE])


class IsolationError(RuntimeError):
    pass


def _ip_binary():
    # Fixed root-controlled distribution paths only; never user PATH/config.
    for path in ('/usr/sbin/ip', '/usr/bin/ip', '/sbin/ip', '/bin/ip'):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise IsolationError('Trusted host iproute2 binary unavailable')


def _run(netns, *args):
    completed = subprocess.run(
        ['/usr/bin/nsenter', '--net=' + netns, '--', _ip_binary(), *args],
        check=True, capture_output=True, text=True, timeout=5,
        env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'},
        stdin=subprocess.DEVNULL)
    if len(completed.stdout) > 65536:
        raise IsolationError('Network readback exceeds bound')
    return completed.stdout


def _namespace(pid, sandbox_key):
    if type(pid) is not int or pid <= 1:
        raise IsolationError('Sandbox PID missing')
    if not isinstance(sandbox_key, str) or not re.fullmatch(
            r'/(?:var/)?run/docker/netns/[A-Za-z0-9_-]{1,128}', sandbox_key):
        raise IsolationError('Unsupported Docker sandbox path')
    netns = '/proc/%d/ns/net' % pid
    before = os.stat(netns)
    sandbox = os.stat(sandbox_key)
    own = os.stat('/proc/self/ns/net')
    if ((before.st_dev, before.st_ino) != (sandbox.st_dev, sandbox.st_ino)
            or (before.st_dev, before.st_ino) == (own.st_dev, own.st_ino)):
        raise IsolationError('Sandbox is not a distinct host-visible namespace')
    return netns, (before.st_dev, before.st_ino)


def _read_rules(netns, family, cidrs):
    rules = json.loads(_run(netns, family, '-j', 'rule', 'show'))
    if not isinstance(rules, list):
        raise IsolationError('Unknown policy rule response')
    expected = {index: cidr for index, cidr in enumerate(cidrs, 1)}
    found = {}
    for rule in rules:
        priority = rule.get('priority')
        if type(priority) is not int or priority < 0:
            raise IsolationError('Unknown policy rule priority')
        if priority == 0:
            if (rule.get('table') != 'local' or rule.get('src') != 'all'
                    or rule.get('dst', 'all') != 'all'
                    or set(rule) - {'priority', 'src', 'dst', 'table', 'protocol', 'flags'}
                    or rule.get('flags')):
                raise IsolationError('Unknown local policy routing rule')
        elif priority <= len(cidrs):
            destination = rule.get('dst')
            if destination:
                if 'dstlen' in rule:
                    address = ipaddress.ip_address(destination)
                    prefix = rule['dstlen']
                    if type(prefix) is not int or not 0 <= prefix <= address.max_prefixlen:
                        raise IsolationError('Unknown policy destination prefix')
                    destination = str(ipaddress.ip_network('%s/%d' % (address, prefix), strict=True))
                else:
                    destination = str(ipaddress.ip_network(destination, strict=True))
            if (priority in found or expected.get(priority) != destination
                    or rule.get('action') != 'blackhole'
                    or rule.get('src') != 'all'
                    or set(rule) - {'priority', 'src', 'dst', 'dstlen', 'action', 'protocol', 'flags'}
                    or rule.get('flags')):
                raise IsolationError('Conflicting metadata policy rule')
            found[priority] = destination
    if found != expected:
        raise IsolationError('Metadata policy rules absent')


def _check_local(netns, family, cidrs):
    denied = [ipaddress.ip_network(value) for value in cidrs]
    routes = json.loads(_run(netns, family, '-j', 'route', 'show', 'table', 'local'))
    if not isinstance(routes, list):
        raise IsolationError('Unknown local routes')
    for route in routes:
        destination = route.get('dst')
        if destination and destination != 'default':
            network = ipaddress.ip_network(destination, strict=False)
            if any(network.overlaps(item) for item in denied):
                raise IsolationError('Blocked destination assigned inside sandbox')


def _isolate(pid, sandbox_key, cidrs, install=False, user_pid=None):
    """Install/read back policy denial and main-table blackholes atomically
    with respect to the still-unstarted user workload. Kernel namespace handles
    are pinned by an open fd across each nsenter invocation, preventing PID reuse.
    """
    if not isinstance(cidrs, list) or not 2 <= len(cidrs) <= 64:
        raise IsolationError('Invalid blocked destination set')
    canonical = sorted({str(ipaddress.ip_network(item, strict=True)) for item in cidrs})
    if canonical != cidrs:
        raise IsolationError('Noncanonical blocked destination set')
    netns, identity = _namespace(pid, sandbox_key)
    descriptor = os.open(netns, os.O_RDONLY | os.O_CLOEXEC)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != identity:
            raise IsolationError('Namespace changed before isolation')
        # nsenter opens this path while the privileged helper retains the fd.
        pinned = '/proc/%d/fd/%d' % (os.getpid(), descriptor)
        for version in (4, 6):
            family = '-%d' % version
            destinations = [item for item in cidrs if ipaddress.ip_network(item).version == version]
            _check_local(pinned, family, destinations)
            if install:
                # No arbitrary shell, user arguments, or command retry/replay.
                # A fresh native holder must have no nondefault early rules.
                rules = json.loads(_run(pinned, family, '-j', 'rule', 'show'))
                if any(0 < rule.get('priority', -1) <= len(destinations) for rule in rules):
                    raise IsolationError('Sandbox has conflicting early rules')
                for priority, cidr in enumerate(destinations, 1):
                    _run(pinned, family, 'route', 'replace', 'blackhole', cidr)
                    _run(pinned, family, 'rule', 'add', 'pref', str(priority), 'to', cidr, 'blackhole')
            _read_rules(pinned, family, destinations)
            routes = json.loads(_run(pinned, family, '-j', 'route', 'show', 'table', 'main'))
            for cidr in destinations:
                if not any(route.get('type') == 'blackhole' and
                           str(ipaddress.ip_network(route.get('dst'), strict=False)) == cidr
                           for route in routes if route.get('dst') not in (None, 'default')):
                    raise IsolationError('Metadata blackhole route absent')
        if user_pid is not None:
            if type(user_pid) is not int or user_pid <= 1:
                raise IsolationError('User namespace PID missing')
            joined = os.stat('/proc/%d/ns/net' % user_pid)
            if (joined.st_dev, joined.st_ino) != identity:
                raise IsolationError('User did not join its native sandbox')
        if _namespace(pid, sandbox_key)[1] != identity:
            raise IsolationError('Sandbox changed during isolation')
        return True
    finally:
        os.close(descriptor)


@context.entrypoint
def isolate(pid, sandbox_key, cidrs, install=False, user_pid=None):
    return _isolate(pid, sandbox_key, cidrs, install, user_pid)
