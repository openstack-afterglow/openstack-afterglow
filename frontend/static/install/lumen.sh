#!/bin/sh
# Public contract: sh -s -- [CODEX_BASE_URL ANTHROPIC_BASE_URL]
# Requires macOS/Linux, Python 3.11+, and a controlling terminal.
# LUMEN_CA_BUNDLE optionally selects an operator-trusted PEM bundle.
# Codex terminal defaults live in $CODEX_HOME/lumen-cli.config.toml, selected by
# --profile lumen-cli. Root desktop defaults stay untouched unless model opt-in
# is requested; both configs share path validation, private backups and updates.
set +x
set +v
exec python3 - "$@" <<'LUMEN_PY'
import copy
import ipaddress
import json
import math
import os
import re
import secrets
import shlex
import signal
import ssl
import stat
import sys
import termios
from pathlib import Path
from urllib.parse import urlsplit

try:
    import tomllib
except ImportError:
    sys.exit('Lumen installer requires Python 3.11 or newer.')


class Rejected(Exception):
    def __init__(self, label='Invalid inputs or unsafe writable paths.'):
        super().__init__(label)


def require(condition, label='Invalid inputs or unsafe writable paths.'):
    if not condition:
        raise Rejected(label)


def interrupted(signum, frame):
    raise Rejected('Installation interrupted.')


for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGTSTP):
    signal.signal(sig, interrupted)


class Terminal:
    def __init__(self):
        self.fd = None
        try:
            self.fd = os.open('/dev/tty', os.O_RDWR | os.O_NOCTTY)
            require(os.isatty(self.fd))
            self.settings = termios.tcgetattr(self.fd)
        except (OSError, termios.error, Rejected):
            if self.fd is not None:
                os.close(self.fd)
            raise Rejected('A controlling terminal is required.') from None

    def prompt(self, label, secret=False):
        complete = False
        try:
            if secret:
                hidden = copy.deepcopy(self.settings)
                hidden[3] &= ~(termios.ECHO | termios.ECHONL)
                termios.tcsetattr(self.fd, termios.TCSANOW, hidden)
            os.write(self.fd, label.encode())
            data = bytearray()
            while True:
                char = os.read(self.fd, 1)
                require(char)
                if char in (b'\n', b'\r'):
                    break
                data.extend(char)
                require(len(data) <= 4096)
            decoded = data.decode('utf-8')
            complete = True
            return decoded
        finally:
            if not complete:
                termios.tcflush(self.fd, termios.TCIFLUSH)
            termios.tcsetattr(self.fd, termios.TCSANOW, self.settings)
            if secret:
                os.write(self.fd, b'\n')

    def close(self):
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.settings)
        finally:
            os.close(self.fd)


def public_url(value):
    try:
        require(isinstance(value, str) and len(value) <= 2048)
        require(re.fullmatch(r'https://[A-Za-z0-9.\[\]:/-]+(?:[A-Za-z0-9._~/-]*)', value))
        require('?' not in value and '#' not in value and '@' not in value)
        parsed = urlsplit(value)
        require(parsed.scheme == 'https' and parsed.hostname and not parsed.username)
        require(parsed.port is None or 1 <= parsed.port <= 65535)
        require(not parsed.netloc.endswith(':'))
        host = parsed.hostname
        try:
            ipaddress.ip_address(host)
        except ValueError:
            labels = host.rstrip('.').split('.')
            require(len(host) <= 253)
            require(all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in labels))
        require(re.fullmatch(r'/[A-Za-z0-9._~/-]*', parsed.path) or not parsed.path)
        return value.rstrip('/')
    except (Rejected, ValueError):
        raise Rejected('Invalid HTTPS endpoint.') from None


def model_id(value):
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', value), 'Invalid model ID.')
    return value


def absolute(value):
    require(value and os.path.isabs(value) and '\x00' not in value)
    require(not any(ord(char) < 32 or ord(char) == 127 for char in value))
    require('..' not in Path(value).parts)
    return Path(os.path.normpath(value))


class Files:
    """Anchor operations to no-follow directory descriptors, including ancestors."""
    def __init__(self):
        self.dirs = {Path('/'): os.open('/', os.O_RDONLY | os.O_DIRECTORY)}
        self.snapshots = {}
        self.temps = []

    def directory(self, path, create=False):
        if path in self.dirs:
            return self.dirs[path]
        parent = self.directory(path.parent, create)
        if parent is None:
            return None
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        except FileNotFoundError:
            if not create:
                return None
            os.mkdir(path.name, 0o700, dir_fd=parent)
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        info = os.fstat(fd)
        try:
            require(info.st_uid in (0, os.getuid()))
            require(not info.st_mode & 0o022 or (info.st_uid == 0 and info.st_mode & stat.S_ISVTX))
        except BaseException:
            os.close(fd)
            raise
        self.dirs[path] = fd
        return fd

    def read(self, path):
        parent = self.directory(path.parent)
        if parent is None:
            self.snapshots[path] = None
            return None
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            self.snapshots[path] = None
            return None
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid())
            require(not info.st_mode & 0o022 and info.st_size <= 4 * 1024 * 1024)
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                content = stream.read()
            self.snapshots[path] = (info.st_ino, info.st_dev, info.st_mtime_ns, info.st_size, info.st_mode, content)
            return content
        finally:
            os.close(fd)

    def unchanged(self, path):
        previous = self.snapshots[path]
        self.read(path)
        require(self.snapshots[path] == previous)

    def temporary(self, path, content, kind, mode=0o600):
        parent = self.directory(path.parent, True)
        name = '.' + path.name + '.lumen-' + kind + '-' + secrets.token_hex(12)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        self.temps.append((parent, name))
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        return parent, name

    def install(self, changes, private_dirs, key_path, profiles):
        # All content and paths have been validated before the first mutation.
        staged = []
        committed = []
        backups = []
        modes = {path: (stat.S_IMODE(self.snapshots[path][-2])
                        if path in profiles and self.snapshots[path] is not None else 0o600)
                 for path in changes}
        try:
            for path, content in changes.items():
                self.unchanged(path)
                old = self.snapshots[path]
                if old is not None and old[-1] == content:
                    continue
                staged.append((path, self.temporary(path, content, 'pending', modes[path])))
                if old is not None and path != key_path:
                    backups.append(self.temporary(path, old[-1], 'backup'))
            for path in private_dirs:
                fd = self.directory(path, True)
                require(os.fstat(fd).st_uid == os.getuid())
                os.fchmod(fd, 0o700)
            for path, (parent, name) in staged:
                self.unchanged(path)
                os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                committed.append(path)
                os.fsync(parent)
            # Tighten permissions even on an otherwise identical rerun.
            for path in changes:
                parent = self.directory(path.parent)
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    os.fchmod(fd, modes[path])
                finally:
                    os.close(fd)
            for backup in backups:
                self.temps.remove(backup)
        except BaseException:
            for path in reversed(committed):
                parent = self.directory(path.parent)
                old = self.snapshots[path]
                if old is None:
                    os.unlink(path.name, dir_fd=parent)
                else:
                    _, name = self.temporary(path, old[-1], 'rollback', stat.S_IMODE(old[-2]))
                    os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            raise

    def close(self):
        for parent, name in self.temps:
            try:
                os.unlink(name, dir_fd=parent)
            except FileNotFoundError:
                pass
        for fd in self.dirs.values():
            os.close(fd)


def toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return '[' + ', '.join(toml_value(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(json.dumps(key) + ' = ' + toml_value(item) for key, item in value.items()) + ' }'
    return value.isoformat()


def key_path(tree):
    path = []
    while isinstance(tree, dict) and len(tree) == 1:
        key, tree = next(iter(tree.items()))
        path.append(key)
    return tuple(path)


def get(tree, path):
    for key in path:
        tree = tree[key]
    return tree


def put(tree, path, value):
    for key in path[:-1]:
        tree = tree.setdefault(key, {})
        require(isinstance(tree, dict))
    tree[path[-1]] = value


def same(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(same(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and isinstance(right, float) and math.isnan(left) and math.isnan(right):
        return True
    return left == right


def codex_config(text, base, root_settings):
    if text and not text.endswith('\n'):
        text += '\n'
    original = tomllib.loads(text)
    desired = {('model_providers', 'lumen', key): value for key, value in {
        'name': 'Lumen Responses', 'base_url': base, 'env_key': 'LUMEN_API_KEY',
        'wire_api': 'responses', 'requires_openai_auth': False, 'supports_websockets': False,
    }.items()}
    desired.update({(key,): value for key, value in root_settings.items()})
    expected = copy.deepcopy(original)
    for path, value in desired.items():
        put(expected, path, value)

    # Parse complete TOML statements rather than matching lines inside strings,
    # arrays, comments, or nested tables. Preserve untouched statements verbatim.
    statements = []
    pending = ''
    for line in text.splitlines(keepends=True):
        pending += line
        try:
            parsed = tomllib.loads(pending)
        except tomllib.TOMLDecodeError:
            continue
        statements.append((pending, parsed))
        pending = ''
    require(not pending)
    remaining = dict(desired)
    context = ()
    output = []
    provider_insert = None
    dotted_insert = None
    first_table = None
    for statement, parsed in statements:
        stripped = statement.lstrip()
        if stripped.startswith('['):
            if first_table is None:
                first_table = len(output)
            # An array-of-tables cannot be the provider being installed.
            context = key_path(parsed)
            if context == ('model_providers', 'lumen') and not stripped.startswith('[['):
                provider_insert = len(output) + 1
            output.append(statement)
            continue
        if not parsed:
            output.append(statement)
            continue
        # Find the assignment's key independently of its possibly inline value.
        # Quoted keys can contain '='; choose the first parseable key prefix.
        assignment = None
        for index, char in enumerate(statement):
            if char != '=':
                continue
            try:
                assignment = key_path(tomllib.loads(statement[:index] + '= 0'))
                lhs = statement[:index].strip()
                break
            except tomllib.TOMLDecodeError:
                pass
        require(assignment is not None)
        path = context + assignment
        affected = [target for target in desired if target[:len(path)] == path]
        if affected:
            value = copy.deepcopy(get(parsed, assignment))
            for target in affected:
                if target == path:
                    value = desired[target]
                else:
                    require(isinstance(value, dict))
                    put(value, target[len(path):], desired[target])
                remaining.pop(target, None)
            output.append(lhs + ' = ' + toml_value(value) + '\n')
            if path[:2] == ('model_providers', 'lumen') and len(context) < 2:
                dotted_insert = (len(output), context)
        else:
            output.append(statement)
    roots = {path: value for path, value in remaining.items() if len(path) == 1}
    if roots:
        position = first_table if first_table is not None else len(output)
        fields = ''.join(path[0] + ' = ' + toml_value(value) + '\n' for path, value in roots.items())
        output.insert(position, fields)
        if dotted_insert is not None and position <= dotted_insert[0]:
            dotted_insert = (dotted_insert[0] + 1, dotted_insert[1])
        if provider_insert is not None and (first_table is None or first_table < provider_insert):
            provider_insert += 1
        for path in roots:
            remaining.pop(path)
    fields = ''.join(path[-1] + ' = ' + toml_value(value) + '\n' for path, value in remaining.items())
    if fields:
        if provider_insert is not None:
            output.insert(provider_insert, fields)
        elif dotted_insert is not None:
            position, prefix = dotted_insert
            fields = ''.join('.'.join(path[len(prefix):]) + ' = ' + toml_value(value) + '\n'
                             for path, value in remaining.items())
            output.insert(position, fields)
        else:
            output.append('\n[model_providers.lumen]\n' + fields)
    result = ''.join(output)
    require(same(tomllib.loads(result), expected))
    return result


START = '# >>> Lumen CLI >>>'
END = '# <<< Lumen CLI <<<'


def profile(text, block):
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip('\r\n') == START]
    ends = [index for index, line in enumerate(lines) if line.rstrip('\r\n') == END]
    require(len(starts) == len(ends) and len(starts) <= 1)
    if starts:
        require(starts[0] < ends[0])
        return ''.join(lines[:starts[0]]) + block + ''.join(lines[ends[0] + 1:])
    return text + ('' if not text or text.endswith('\n') else '\n') + block


def run():
    require(sys.platform in ('darwin', 'linux'))
    require(len(sys.argv) in (1, 3))
    tty = None
    files = Files()
    try:
        if len(sys.argv) == 3:
            codex, anthropic = map(public_url, sys.argv[1:])
        else:
            tty = Terminal()
            codex = public_url(tty.prompt('Codex HTTPS base URL: '))
            anthropic = public_url(tty.prompt('Anthropic HTTPS base URL: '))
        home = absolute(os.environ.get('HOME', ''))
        codex_home = absolute(os.environ.get('CODEX_HOME', str(home / '.codex')))
        zdotdir = absolute(os.environ.get('ZDOTDIR', str(home)))
        config_home = absolute(os.environ.get('XDG_CONFIG_HOME', str(home / '.config')))
        private = config_home / 'lumen'
        key = private / 'key.sh'
        config = codex_home / 'config.toml'
        cli_config = codex_home / 'lumen-cli.config.toml'
        candidates = [home / name for name in ('.bash_profile', '.bash_login', '.profile')]
        # Inspect every login candidate, including symlinks, before selecting one.
        login_contents = {path: files.read(path) for path in candidates}
        login = next((path for path in candidates if login_contents[path] is not None), home / '.profile')
        profiles = list(dict.fromkeys([home / '.bashrc', login, zdotdir / '.zshrc']))
        old = {path: files.read(path) for path in [key, config, cli_config, *profiles]}
        for directory in (home, codex_home, zdotdir, private):
            fd = files.directory(directory)
            if fd is not None:
                require(os.fstat(fd).st_uid == os.getuid())
        config_text = (old[config] or b'').decode('utf-8')
        tomllib.loads(config_text)
        cli_config_text = (old[cli_config] or b'').decode('utf-8')
        tomllib.loads(cli_config_text)
        # Check profile markers before asking for a credential.
        for path in profiles:
            profile((old[path] or b'').decode('utf-8'), START + '\n' + END + '\n')
        paths = (['/private/etc/ssl/cert.pem', '/etc/ssl/cert.pem'] if sys.platform == 'darwin' else
                 ['/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt', '/etc/ssl/cert.pem'])
        explicit_bundle = os.environ.get('LUMEN_CA_BUNDLE')
        bundle = explicit_bundle or os.environ.get('CODEX_CA_CERTIFICATE')
        if bundle:
            ca = absolute(bundle)
        else:
            ca = next((Path(path) for path in paths if os.path.isfile(path)), None)
            require(ca is not None, 'A trusted CA bundle is required.')
        # CA bundles are read-only inputs, not mutation targets. Resolve standard
        # OS/enterprise certificate symlinks, then validate the actual file.
        resolved_ca = absolute(os.path.realpath(ca))
        parent = files.directory(resolved_ca.parent)
        require(parent is not None, 'Invalid trusted CA bundle.')
        fd = os.open(resolved_ca.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid in (0, os.getuid())
                    and not info.st_mode & 0o022, 'Invalid trusted CA bundle.')
        finally:
            os.close(fd)
        try:
            ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cafile=str(resolved_ca))
        except ssl.SSLError:
            raise Rejected('Invalid trusted CA bundle.') from None
        share_ca = (bool(explicit_bundle)
                    or resolved_ca not in {Path(os.path.realpath(path)) for path in paths}
                    or os.environ.get('NODE_EXTRA_CA_CERTS') == str(ca))
        if tty is None:
            tty = Terminal()
        api_key = tty.prompt('Lumen API key: ', secret=True)
        require(api_key and not any(ord(char) < 32 or ord(char) == 127 for char in api_key))
        responses = model_id(tty.prompt('Codex Responses model ID: '))
        claude = model_id(tty.prompt('Anthropic model ID: '))
        answer = tty.prompt('Replace the default Codex model? [y/N]: ').lower()
        require(answer in ('', 'y', 'yes', 'n', 'no'))
        opt_in = answer in ('y', 'yes')
        updated = codex_config(config_text, codex, {'model': responses} if opt_in else {})
        cli_updated = codex_config(cli_config_text, codex, {'model_provider': 'lumen', 'model': responses})
        quote = shlex.quote
        block = START + '\n' + '''case "$-" in *x*) _lumen_trace=1 ;; *) _lumen_trace=0 ;; esac
case "$-" in *v*) _lumen_verbose=1 ;; *) _lumen_verbose=0 ;; esac
set +x
set +v
'''
        block += '[ ! -r ' + quote(str(key)) + ' ] || . ' + quote(str(key)) + '\n'
        for name, value in {'CODEX_HOME': str(codex_home), 'CODEX_CA_CERTIFICATE': str(ca),
                            'LUMEN_MODEL': claude,
                            'ANTHROPIC_BASE_URL': anthropic}.items():
            block += 'export ' + name + '=' + quote(value) + '\n'
        if share_ca:
            block += 'export NODE_EXTRA_CA_CERTS=' + quote(str(ca)) + '\n'
        block += 'unset ANTHROPIC_API_KEY\n'
        block += 'export ANTHROPIC_AUTH_TOKEN="$LUMEN_API_KEY"\n'
        for name in ('ANTHROPIC_MODEL', 'ANTHROPIC_DEFAULT_SONNET_MODEL',
                     'ANTHROPIC_DEFAULT_OPUS_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL'):
            block += 'export ' + name + '="$LUMEN_MODEL"\n'
        # Native profile defaults survive subcommand -c flags; caller -m still wins.
        block += '''unalias codex 2>/dev/null || :
codex() {
    command codex --strict-config --profile lumen-cli "$@"
}
'''
        block += '''if [ "$_lumen_verbose" = 1 ]; then unset _lumen_verbose; set -v; else unset _lumen_verbose; fi
if [ "$_lumen_trace" = 1 ]; then unset _lumen_trace; set -x; else unset _lumen_trace; fi
'''
        block += END + '\n'
        changes = {key: ('set +x\nset +v\nexport LUMEN_API_KEY=' + quote(api_key) + '\n').encode(),
                   config: updated.encode(), cli_config: cli_updated.encode()}
        for path in profiles:
            changes[path] = profile((old[path] or b'').decode('utf-8'), block).encode()
        files.install(changes, (private, codex_home), key, profiles)
        print('Lumen CLI configured. Open a new terminal, then run:')
        print('codex')
        print('claude')
    finally:
        if tty is not None:
            tty.close()
        files.close()


try:
    run()
except Rejected as error:
    # Rejected contains only installer-owned labels, never supplied values.
    sys.stderr.write('Lumen installation failed: ' + str(error) + '\n')
    sys.exit(1)
except BaseException:
    # Never include exception text: it may contain a supplied URL or credential.
    sys.stderr.write('Lumen installation failed; check inputs, Python 3.11+, terminal, certificates, and safe writable paths.\n')
    sys.exit(1)
LUMEN_PY
