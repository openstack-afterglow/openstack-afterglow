"""Unit and integration tests for DailySizeHandler and logging configuration."""

import logging
import multiprocessing
from datetime import date
from pathlib import Path

from app import config as app_config
from app.utils.daily_size_handler import DailySizeHandler


def _make_logger(handler: logging.Handler, name: str = "test_logger") -> logging.Logger:
    logger = logging.getLogger(f"{name}_{id(handler)}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger


def test_same_day_base_and_suffix_allocation(tmp_path: Path):
    d = date(2026, 8, 31)
    handler = DailySizeHandler(
        log_directory=tmp_path,
        max_bytes=100,
        date_provider=lambda: d,
    )
    logger = _make_logger(handler)

    # Base file record: 30 bytes
    record_30 = logging.LogRecord("test", logging.INFO, "", 0, "A" * 20, (), None)
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger.handle(record_30)  # writes "A"*20 + "\n" = 21 bytes
    base_file = tmp_path / "backend-2026-08-31.log"
    assert base_file.exists()
    assert base_file.stat().st_size == 21

    # Fill remaining capacity of base file up to 80 bytes
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "B" * 58, (), None))  # + 59 bytes = 80 bytes
    assert base_file.stat().st_size == 80

    # Next write of 30 bytes exceeds 100 bytes (80 + 30 = 110 > 100) -> rotate to -01
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "C" * 29, (), None))  # 30 bytes
    suffix_01 = tmp_path / "backend-2026-08-31-01.log"
    assert suffix_01.exists()
    assert suffix_01.stat().st_size == 30
    assert base_file.stat().st_size == 80  # unchanged

    # Another write of 80 bytes exceeds 100 bytes (30 + 80 = 110 > 100) -> rotate to -02
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "D" * 79, (), None))  # 80 bytes
    suffix_02 = tmp_path / "backend-2026-08-31-02.log"
    assert suffix_02.exists()
    assert suffix_02.stat().st_size == 80

    handler.close()


def test_exact_boundary_capacity(tmp_path: Path):
    d = date(2026, 8, 31)
    handler = DailySizeHandler(
        log_directory=tmp_path,
        max_bytes=100,
        date_provider=lambda: d,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = _make_logger(handler)

    # 60 bytes
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "X" * 59, (), None))
    # 40 bytes -> exact 100 bytes
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "Y" * 39, (), None))

    base_file = tmp_path / "backend-2026-08-31.log"
    assert base_file.stat().st_size == 100
    assert not (tmp_path / "backend-2026-08-31-01.log").exists()

    # Next 1 byte record -> 100 + 2 = 102 > 100 -> rotates to -01
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "Z", (), None))
    suffix_01 = tmp_path / "backend-2026-08-31-01.log"
    assert suffix_01.exists()
    assert suffix_01.stat().st_size == 2
    assert base_file.stat().st_size == 100

    handler.close()


def test_oversized_first_record(tmp_path: Path):
    d = date(2026, 8, 31)
    handler = DailySizeHandler(
        log_directory=tmp_path,
        max_bytes=50,
        date_provider=lambda: d,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = _make_logger(handler)

    # Single oversized record of 200 bytes on empty active file
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "O" * 199, (), None))

    base_file = tmp_path / "backend-2026-08-31.log"
    assert base_file.exists()
    assert base_file.stat().st_size == 200
    assert not (tmp_path / "backend-2026-08-31-01.log").exists()

    # Subsequent record when current size 200 > 0 -> rotates to -01
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "N" * 9, (), None))
    suffix_01 = tmp_path / "backend-2026-08-31-01.log"
    assert suffix_01.exists()
    assert suffix_01.stat().st_size == 10

    handler.close()


def test_date_rollover(tmp_path: Path):
    current_date = date(2026, 8, 31)
    handler = DailySizeHandler(
        log_directory=tmp_path,
        max_bytes=100,
        date_provider=lambda: current_date,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = _make_logger(handler)

    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "Day1", (), None))
    file_day1 = tmp_path / "backend-2026-08-31.log"
    assert file_day1.exists()

    # Advance date to 2026-09-01
    current_date = date(2026, 9, 1)
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "Day2", (), None))
    file_day2 = tmp_path / "backend-2026-09-01.log"
    assert file_day2.exists()
    assert file_day2.read_text(encoding="utf-8").strip() == "Day2"

    handler.close()


def test_restart_highest_suffix_resume(tmp_path: Path):
    d = date(2026, 8, 31)
    base_file = tmp_path / "backend-2026-08-31.log"
    suffix_01 = tmp_path / "backend-2026-08-31-01.log"

    base_file.write_bytes(b"X" * 100)
    suffix_01.write_bytes(b"Y" * 40)

    handler = DailySizeHandler(
        log_directory=tmp_path,
        max_bytes=100,
        date_provider=lambda: d,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = _make_logger(handler)

    # 30 bytes write -> should append to suffix_01 (40 + 30 = 70 <= 100)
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "Z" * 29, (), None))
    assert suffix_01.stat().st_size == 70
    assert not (tmp_path / "backend-2026-08-31-02.log").exists()

    handler.close()


def test_restart_highest_suffix_full(tmp_path: Path):
    d = date(2026, 8, 31)
    base_file = tmp_path / "backend-2026-08-31.log"
    suffix_01 = tmp_path / "backend-2026-08-31-01.log"

    base_file.write_bytes(b"X" * 100)
    suffix_01.write_bytes(b"Y" * 100)  # full!

    handler = DailySizeHandler(
        log_directory=tmp_path,
        max_bytes=100,
        date_provider=lambda: d,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = _make_logger(handler)

    # 30 bytes write -> since suffix_01 is full (100 >= 100), allocates -02
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "Z" * 29, (), None))
    suffix_02 = tmp_path / "backend-2026-08-31-02.log"
    assert suffix_02.exists()
    assert suffix_02.stat().st_size == 30

    handler.close()


def test_preexisting_suffix_gaps(tmp_path: Path):
    d = date(2026, 8, 31)
    base_file = tmp_path / "backend-2026-08-31.log"
    suffix_03 = tmp_path / "backend-2026-08-31-03.log"

    base_file.write_bytes(b"X" * 100)
    suffix_03.write_bytes(b"Y" * 100)  # -01 and -02 missing!

    handler = DailySizeHandler(
        log_directory=tmp_path,
        max_bytes=100,
        date_provider=lambda: d,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = _make_logger(handler)

    # High index is 3 (full). Rotation must allocate fresh higher suffix -04, not fill gap -01/-02.
    logger.handle(logging.LogRecord("test", logging.INFO, "", 0, "N" * 29, (), None))
    suffix_04 = tmp_path / "backend-2026-08-31-04.log"
    assert suffix_04.exists()
    assert not (tmp_path / "backend-2026-08-31-01.log").exists()

    handler.close()


def _worker_log_task(log_dir: str, num_records: int) -> None:
    handler = DailySizeHandler(
        log_directory=log_dir,
        max_bytes=500,
        date_provider=lambda: date(2026, 8, 31),
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = _make_logger(handler, name="worker")
    for i in range(num_records):
        logger.info("M" * 40)
    handler.close()


def test_concurrent_process_safety(tmp_path: Path):
    num_workers = 4
    records_per_worker = 20

    processes = []
    for _ in range(num_workers):
        p = multiprocessing.Process(target=_worker_log_task, args=(str(tmp_path), records_per_worker))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()
        assert p.exitcode == 0

    # Total written lines across all files for 2026-08-31
    total_lines = 0
    for p in tmp_path.glob("backend-2026-08-31*.log"):
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        total_lines += len(lines)

    assert total_lines == num_workers * records_per_worker


def test_config_and_env_precedence(monkeypatch, tmp_path: Path):
    # 1. Defaults
    app_config.get_settings.cache_clear()
    settings_default = app_config.Settings()
    assert settings_default.log_directory == "logs"
    assert settings_default.log_max_bytes == 52428800

    # 2. TOML file overriding defaults
    conf_file = tmp_path / "afterglow.conf"
    conf_file.write_text(
        """
[logging]
log_directory = "/custom/toml/logs"
max_bytes = 10485760
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "_config_candidates", lambda: [conf_file])
    app_config.get_settings.cache_clear()
    app_config.load_raw_toml.cache_clear()

    flat = app_config._load_toml()
    assert flat["log_directory"] == "/custom/toml/logs"
    assert flat["log_max_bytes"] == 10485760

    # 3. Env var overriding TOML
    monkeypatch.setenv("LOG_DIRECTORY", "/env/override/logs")
    monkeypatch.setenv("LOG_MAX_BYTES", "20971520")

    app_config.get_settings.cache_clear()
    settings_env = app_config.get_settings()
    assert settings_env.log_directory == "/env/override/logs"
    assert settings_env.log_max_bytes == 20971520


def test_permission_and_os_error_fail_open(tmp_path: Path, monkeypatch):
    invalid_dir = tmp_path / "uncreatable_dir"

    def mock_mkdir(*args, **kwargs):
        raise PermissionError("Permission denied for test")

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)

    handler = DailySizeHandler(
        log_directory=invalid_dir,
        max_bytes=100,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = _make_logger(handler)

    # Should not raise exception despite PermissionError in mkdir
    logger.info("This should fail-open silently")
    handler.close()
