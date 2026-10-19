"""Shell boundary tests: real Bash/Python, fake curl, no external network."""

import errno
import io
import json
import os
import select
import shutil
import subprocess
import sys
import tarfile
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[2] / "scripts" / "setup.sh"
SHA = "1234567890abcdef1234567890abcdef12345678"
API = "https://api.github.com/repos/openstack-afterglow/openstack-afterglow/commits/"
ARCHIVE = f"https://codeload.github.com/openstack-afterglow/openstack-afterglow/tar.gz/{SHA}"

# A canary distinguishes rejected archives from accidentally executed source.
# Real configuration generation and PTY qualification use the actual bundle.
MOCK_SETUP = """import os
import sys
from pathlib import Path

Path(os.environ["SETUP_RECEIPT"]).write_text("executed", encoding="utf-8")
sys.exit(int(os.environ.get("SETUP_EXIT", "0")))
"""
FAKE_CURL = """import json
import os
import shutil
import sys
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["CURL_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
# Never fall through to real curl, even for unexpected input.
expected = ["--disable", "--fail", "--location", "--show-error", "--silent",
            "--proto", "=https", "--proto-redir", "=https", "--output"]
if args[:len(expected)] != expected or len(args) != len(expected) + 2:
    sys.exit(90)
destination, url = args[-2:]
api = "https://api.github.com/repos/openstack-afterglow/openstack-afterglow/commits/"
archive = "https://codeload.github.com/openstack-afterglow/openstack-afterglow/tar.gz/" + os.environ["BUNDLE_SHA"]
if url.startswith(api):
    if os.environ.get("FAIL_DOWNLOAD") == "api":
        Path(destination).write_text("partial", encoding="utf-8")
        sys.exit(22)
    Path(destination).write_text(os.environ["API_RESPONSE"], encoding="utf-8")
elif url == archive:
    if os.environ.get("FAIL_DOWNLOAD") == "archive":
        Path(destination).write_bytes(b"partial")
        sys.exit(22)
    shutil.copyfile(os.environ["MOCK_ARCHIVE"], destination)
else:
    sys.exit(91)
"""


def write_bundle(path, extra_members=(), *, include_setup=True):
    root = f"openstack-afterglow-{SHA}"
    with tarfile.open(path, "w:gz") as bundle:
        directory = tarfile.TarInfo(root)
        directory.type = tarfile.DIRTYPE
        bundle.addfile(directory)
        files = {}
        if include_setup:
            files["setup.py"] = MOCK_SETUP
        for name, content in files.items():
            data = content.encode()
            member = tarfile.TarInfo(f"{root}/{name}")
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))
        for member, content in extra_members:
            bundle.addfile(member, io.BytesIO(content) if content is not None else None)


@pytest.fixture
def shell_case(tmp_path):
    bash = shutil.which("bash")
    assert bash, "Bash is required to test the shell entrypoint"
    rm = shutil.which("rm")
    assert rm, "rm is required for source cleanup"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # A closed PATH ensures an accidental installer/cloud/cluster command cannot
    # run, and the no-Python test cannot discover a system interpreter fallback.
    (bin_dir / "python3").symlink_to(sys.executable)
    (bin_dir / "rm").symlink_to(rm)
    curl = bin_dir / "curl"
    curl.write_text(f"#!{sys.executable}\n" + FAKE_CURL, encoding="utf-8")
    curl.chmod(0o700)
    caller = tmp_path / "caller directory"
    caller.mkdir()
    temporary = tmp_path / "temporary sources"
    temporary.mkdir()
    bundle = tmp_path / "bundle.tar.gz"
    write_bundle(bundle)
    input_file = tmp_path / "private input.toml"
    input_file.write_text('generated = "synthetic-generated-config"\n', encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    curl_log = tmp_path / "curl.jsonl"
    environment = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "TMPDIR": str(temporary),
        "LANG": "C.UTF-8",
        "CURL_LOG": str(curl_log),
        "MOCK_ARCHIVE": str(bundle),
        "BUNDLE_SHA": SHA,
        "API_RESPONSE": json.dumps({"sha": SHA}),
        "SETUP_RECEIPT": str(receipt),
    }
    return SimpleNamespace(
        bash=bash,
        bin=bin_dir,
        caller=caller,
        temporary=temporary,
        bundle=bundle,
        input=input_file,
        receipt=receipt,
        curl_log=curl_log,
        env=environment,
    )


def run_shell(case, arguments=None, *, piped=False, trace=False):
    if arguments is None:
        arguments = ["--non-interactive", "--config", str(case.input)]
    command = [case.bash]
    if trace:
        command.append("-x")
    if piped:
        command.extend(["-s", "--", *arguments])
        source = ENTRYPOINT.read_text(encoding="utf-8")
    else:
        command.extend([str(ENTRYPOINT), *arguments])
        source = ""
    return subprocess.run(
        command,
        input=source,
        text=True,
        capture_output=True,
        cwd=case.caller,
        env=case.env,
        start_new_session=True,
        timeout=15,
        check=False,
    )


def downloads(case):
    if not case.curl_log.exists():
        return []
    return [json.loads(line) for line in case.curl_log.read_text(encoding="utf-8").splitlines()]


def assert_clean(case):
    assert list(case.temporary.iterdir()) == []


@pytest.mark.parametrize("stage", ["api", "archive"])
def test_download_failure_never_executes_partial_source(shell_case, stage):
    case = shell_case
    case.env["FAIL_DOWNLOAD"] = stage
    result = run_shell(case, piped=True)
    assert result.returncode != 0
    assert "download failed" in result.stderr
    assert len(downloads(case)) == (1 if stage == "api" else 2)
    assert not case.receipt.exists()
    assert_clean(case)


@pytest.mark.parametrize(
    "response",
    [
        "not-json",
        "{}",
        "[]",
        '{"sha": null}',
        '{"sha": 123}',
        '{"sha": "dev"}',
        '{"sha": "' + "g" * 40 + '"}',
        '{"sha": "' + SHA + '\\n"}',
    ],
)
def test_invalid_api_revision_does_not_download_archive(shell_case, response):
    case = shell_case
    case.env["API_RESPONSE"] = response
    result = run_shell(case)
    assert result.returncode != 0
    assert "Invalid GitHub revision response" in result.stderr
    assert len(downloads(case)) == 1
    assert not case.receipt.exists()
    assert_clean(case)


@pytest.mark.parametrize("ref", ["", "dev\n", "dev\x7f"])
def test_invalid_ref_fails_without_logging_value_or_downloading(shell_case, ref):
    case = shell_case
    case.env["AFTERGLOW_SETUP_REF"] = ref
    result = run_shell(case)
    assert result.returncode != 0
    assert "Invalid source ref" in result.stderr
    assert downloads(case) == []
    assert not case.receipt.exists()
    assert_clean(case)


@pytest.mark.parametrize(
    "kind",
    [
        "traversal",
        "absolute",
        "backslash",
        "symlink",
        "hardlink",
        "fifo",
        "device",
        "wrong-root",
        "duplicate",
    ],
)
def test_unsafe_archive_is_rejected_before_setup_executes(shell_case, kind):
    case = shell_case
    root = f"openstack-afterglow-{SHA}"
    name = {
        "traversal": f"{root}/../../escaped",
        "absolute": str(case.caller / "escaped"),
        "backslash": f"{root}/..\\escaped",
        "wrong-root": "untrusted-root/escaped",
        "duplicate": f"{root}/setup.py",
    }.get(kind, f"{root}/unsafe")
    member = tarfile.TarInfo(name)
    content = b"untrusted"
    if kind in ("symlink", "hardlink", "fifo", "device"):
        member.type = {
            "symlink": tarfile.SYMTYPE,
            "hardlink": tarfile.LNKTYPE,
            "fifo": tarfile.FIFOTYPE,
            "device": tarfile.CHRTYPE,
        }[kind]
        member.linkname = str(case.caller)
        content = None
    else:
        member.size = len(content)
    write_bundle(case.bundle, [(member, content)])
    result = run_shell(case)
    assert result.returncode != 0
    assert "Unsafe or invalid GitHub source archive" in result.stderr
    assert not case.receipt.exists()
    assert list(case.caller.iterdir()) == []
    assert not (case.caller.parent / "escaped").exists()
    assert_clean(case)


@pytest.mark.parametrize("kind", ["corrupt", "missing-setup"])
def test_incomplete_bundle_never_runs_setup(shell_case, kind):
    case = shell_case
    if kind == "corrupt":
        case.bundle.write_bytes(b"not a tar archive")
    else:
        write_bundle(case.bundle, include_setup=False)
    result = run_shell(case)
    assert result.returncode != 0
    assert "Unsafe or invalid GitHub source archive" in result.stderr
    assert not case.receipt.exists()
    assert_clean(case)


def test_no_python_fails_before_network_or_source_creation(shell_case):
    case = shell_case
    (case.bin / "python3").unlink()
    result = run_shell(case, piped=True)
    assert result.returncode != 0
    assert "Python >=3.11" in result.stderr
    assert downloads(case) == []
    assert not case.receipt.exists()
    assert_clean(case)


def test_unusable_python_fails_before_network(shell_case):
    case = shell_case
    python = case.bin / "python3"
    python.unlink()
    python.write_text(f"#!{case.bash}\nexit 1\n", encoding="utf-8")
    python.chmod(0o700)
    result = run_shell(case)
    assert result.returncode != 0
    assert "Python >=3.11" in result.stderr
    assert downloads(case) == []
    assert_clean(case)


def test_missing_curl_fails_without_creating_source(shell_case):
    case = shell_case
    (case.bin / "curl").unlink()
    result = run_shell(case)
    assert result.returncode != 0
    assert "curl is required" in result.stderr
    assert not case.receipt.exists()
    assert_clean(case)


def test_interactive_pipe_without_controlling_tty_fails_before_download(shell_case):
    case = shell_case
    result = run_shell(case, [], piped=True)
    assert result.returncode != 0
    assert "requires /dev/tty" in result.stderr
    assert downloads(case) == []
    assert not case.receipt.exists()
    assert_clean(case)


def test_forwarded_arguments_after_separator_do_not_enable_noninteractive(shell_case):
    case = shell_case
    result = run_shell(case, ["--", "--non-interactive"], piped=True)
    assert result.returncode != 0
    assert "requires /dev/tty" in result.stderr
    assert downloads(case) == []
    assert_clean(case)


def test_setup_exit_status_is_preserved_and_source_cleaned(shell_case):
    case = shell_case
    case.env["SETUP_EXIT"] = "7"
    result = run_shell(case)
    assert result.returncode == 7
    assert case.receipt.exists()
    assert_clean(case)


def test_inherited_trace_does_not_disclose_inputs_on_download_failure(shell_case):
    case = shell_case
    private_value = "synthetic-private-value-never-print"
    private_input = case.caller / "input.toml"
    original = f'generated = "{private_value}"\n'
    private_input.write_text(original, encoding="utf-8")
    case.env["FAIL_DOWNLOAD"] = "archive"
    arguments = ["--non-interactive", "--config", "input.toml", "opaque-argument-never-print"]
    result = run_shell(case, arguments, piped=True, trace=True)
    assert result.returncode != 0
    assert private_value not in result.stdout + result.stderr
    assert arguments[-1] not in result.stdout + result.stderr
    assert private_input.read_text(encoding="utf-8") == original
    assert not case.receipt.exists()
    assert_clean(case)


def test_actual_bundled_setup_completes_piped_terminal_and_cleans_source(shell_case):
    """Regression: rebinding Bash fd0 left the shell reading the terminal forever."""
    pytest.importorskip("fcntl")
    pytest.importorskip("termios")
    root = ENTRYPOINT.parents[1]
    sys.path.insert(0, str(root))
    import config2helm
    import generate_k8s

    case = shell_case
    files = {
        name: (root / name).read_text()
        for name in (
            "setup.py",
            "generation_config.py",
            "generate_k8s.py",
            "config2helm.py",
            "afterglow.conf.example",
        )
    }
    files.update({"helm/afterglow/" + name: value for name, value in config2helm.chart_sources().items()})
    files.update(
        {
            "deploy/k8s-template/" + name: value
            for name, value in generate_k8s.render_artifacts(
                {"app": {"secret_key": "synthetic-bundle-key-" + "a" * 40}, "gpu": {"devices": []}},
                "afterglow",
            ).items()
        }
    )
    with tarfile.open(case.bundle, "w:gz") as bundle:
        for name, content in files.items():
            encoded = content.encode()
            member = tarfile.TarInfo(f"openstack-afterglow-{SHA}/{name}")
            member.size = len(encoded)
            bundle.addfile(member, io.BytesIO(encoded))
    master, slave = os.openpty()
    launcher = (
        "import fcntl,os,sys,termios; "
        "fcntl.ioctl(int(sys.argv[1]),termios.TIOCSCTTY,0); "
        "os.execve(sys.argv[2],[sys.argv[2],'-s','--'],os.environ)"
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-c", launcher, str(slave), case.bash],
        stdin=subprocess.PIPE,
        stdout=slave,
        stderr=slave,
        pass_fds=(slave,),
        start_new_session=True,
        cwd=case.caller,
        env=case.env,
    )
    os.close(slave)
    transcript = bytearray()
    cursor = 0
    try:
        process.stdin.write(ENTRYPOINT.read_bytes())
        process.stdin.close()
        for prompt, answer in (
            (b"Choice: ", b"4\n"),
            (b"Save configuration and generate both artifacts? [y/N]: ", b"y\n"),
        ):
            deadline = time.monotonic() + 15
            while prompt not in transcript[cursor:]:
                assert time.monotonic() < deadline, "Actual setup prompt timed out"
                if select.select([master], [], [], 0.1)[0]:
                    transcript.extend(os.read(master, 65536))
            cursor = transcript.index(prompt, cursor) + len(prompt)
            os.write(master, answer)
        deadline = time.monotonic() + 30
        while process.poll() is None:
            assert time.monotonic() < deadline, "Piped setup did not finish after generation"
            if select.select([master], [], [], 0.1)[0]:
                try:
                    transcript.extend(os.read(master, 65536))
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    break
        assert process.wait(timeout=5) == 0
        config = tomllib.loads((case.caller / "afterglow.conf").read_text())
        assert len(config["app"]["secret_key"]) >= 32
        assert config["app"]["secret_key"].encode() not in transcript
        assert (case.caller / "generated/k8s/kustomization.yaml").is_file()
        assert (case.caller / "generated/helm/afterglow/values-local.yaml").is_file()
        assert_clean(case)
    finally:
        os.close(master)
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
