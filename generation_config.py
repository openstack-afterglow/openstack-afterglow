"""Shared, standard-library-only configuration and private artifact I/O.

Precedence: base, sorted sibling overrides (excluding the public frontend
projection), then explicit overrides in argument order. Namespace selection never
chooses an operator's public domain; deployment profiles require --override.
Existing source text is never serialized or normalized merely by loading it.
"""

import os
import re
import secrets
import tempfile
import tomllib
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
CONFIG_EXAMPLE = SOURCE_DIR / "afterglow.conf.example"


def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def config_override_paths(config_path: Path) -> list[Path]:
    paths = {
        path.resolve()
        for path in config_path.parent.glob(f"{config_path.stem}.*{config_path.suffix}")
        if path.is_file() and path.stat().st_size
        and path.name != "afterglow.frontend.conf"
        and path.resolve() != config_path.resolve()
    }
    gpu_path = config_path.parent / "config.gpu.toml"
    if gpu_path.is_file() and gpu_path.stat().st_size:
        paths.add(gpu_path.resolve())
    return sorted(paths)


def prepare_config(config_path: Path) -> str:
    """Return exact existing text, or the canonical template with a new app key.

    Never rotate a configured key, including an invalid key: validation must fail
    until the operator explicitly replaces it. Only first initialization creates
    a key; the example's other placeholders remain untouched.
    """
    if config_path.exists():
        return config_path.read_bytes().decode("utf-8")
    text = CONFIG_EXAMPLE.read_text(encoding="utf-8")
    return text.replace('secret_key = "change-me-in-production"',
                        f'secret_key = "{secrets.token_hex(32)}"', 1)


def merge_config(config_path: Path, base_text: str,
                 extra_override_paths: list[Path] | None = None) -> dict:
    cfg = tomllib.loads(base_text)
    # Explicit paths are intentionally applied again if also auto-discovered:
    # --override z --override a must leave a as the final authority.
    for path in [*config_override_paths(config_path), *(extra_override_paths or [])]:
        with path.open("rb") as stream:
            _deep_merge(cfg, tomllib.load(stream))
    return cfg


def load_config(config_path: Path,
                extra_override_paths: list[Path] | None = None) -> dict:
    text = prepare_config(config_path)
    cfg = merge_config(config_path, text, extra_override_paths)
    if not config_path.exists():
        write_files({config_path: text})
    return cfg




def private_setting(path: str) -> bool:
    """Conservative UI/argv classification; not an artifact projection policy."""
    lowered = path.lower()
    return bool(re.search(r"password|secret|token|private|encryption|hmac|ingest_key|keyring|amqp_url|redis_url|database_url|db_url", lowered)
                or lowered in {"database.url", "monitoring.infrastructure_topology_observers"})


def write_files(contents: dict[Path, str], backup_paths: set[Path] | None = None) -> None:
    """Stage all bytes before replacement; rollback on ordinary write failures.

    Files and backups are 0600 even under a permissive umask. A process crash
    cannot truncate any individual file; cross-file crash atomicity is not
    promised. A private .bak snapshot preserves the prior config on success.
    """
    normalized = {Path(os.path.abspath(path)): value for path, value in contents.items()}
    if len(normalized) != len(contents):
        raise ValueError("Output paths must be distinct")
    previous: dict[Path, bytes | None] = {}
    modes: dict[Path, int] = {}
    staged: dict[Path, str] = {}
    replaced: list[Path] = []
    for path in normalized:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Refusing non-regular output path")
    for source in backup_paths or set():
        source = Path(os.path.abspath(source))
        if source.is_file():
            backup = source.with_name(source.name + ".bak")
            if backup in normalized or backup.is_symlink() or (backup.exists() and not backup.is_file()):
                raise ValueError("Unsafe backup path")
            normalized[backup] = source.read_bytes().decode("utf-8")
    try:
        for path, content in normalized.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            previous[path] = path.read_bytes() if path.exists() else None
            if path.exists():
                modes[path] = path.stat().st_mode & 0o777
            fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".afterglow-")
            staged[path] = temporary
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for path, temporary in staged.items():
            os.replace(temporary, path)
            replaced.append(path)
    except BaseException:
        for path in reversed(replaced):
            old = previous[path]
            if old is None:
                path.unlink()
            else:
                fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".afterglow-rollback-")
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(old)
                    os.chmod(temporary, modes[path])
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
        raise
    finally:
        for temporary in staged.values():
            if os.path.exists(temporary):
                os.unlink(temporary)
