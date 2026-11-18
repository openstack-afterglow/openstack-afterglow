#!/usr/bin/env python3
"""Run every Lumen SDK example whose required environment variables are set."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = {
    "python": {"openai": ROOT / "python/openai_example.py", "anthropic": ROOT / "python/anthropic_example.py",
               "gemini": ROOT / "python/gemini_example.py"},
    "node": {"openai": ROOT / "node/openai.mjs", "anthropic": ROOT / "node/anthropic.mjs",
             "gemini": ROOT / "node/gemini.mjs"},
}
CASES = [
    ("openai", "list", ()), ("openai", "chat", ("LUMEN_OPENAI_MODEL",)),
    ("openai", "responses", ("LUMEN_OPENAI_MODEL",)), ("openai", "stream", ("LUMEN_OPENAI_MODEL",)),
    ("openai", "embed", ("LUMEN_OPENAI_EMBED_MODEL",)), ("openai", "image", ("LUMEN_IMAGE_MODEL",)),
    ("openai", "providers", tuple(f"LUMEN_{name}_{kind}" for name in ("CLAUDE", "GEMINI")
                                  for kind in ("MODEL", "PROVIDER"))),
    ("anthropic", "list", ()), ("anthropic", "message", ("LUMEN_CLAUDE_MODEL",)),
    ("anthropic", "stream", ("LUMEN_CLAUDE_MODEL",)),
    ("gemini", "list", ()), ("gemini", "generate", ("LUMEN_GEMINI_MODEL",)),
    ("gemini", "stream", ("LUMEN_GEMINI_MODEL",)), ("gemini", "embed", ("LUMEN_GEMINI_EMBED_MODEL",)),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=["python", "node", "all"], default="all")
    args = parser.parse_args()
    missing = [name for name in ("LUMEN_API_KEY", "LUMEN_BASE_URL") if not os.environ.get(name)]
    if missing:
        print(f"Set {', '.join(missing)} first.", file=sys.stderr)
        return 2
    languages = ("python", "node") if args.language == "all" else (args.language,)
    failed = 0
    with tempfile.TemporaryDirectory(prefix="lumen-sdk-smoke-") as output:
        for language in languages:
            for family, operation, required in CASES:
                label = f"{language} {family} {operation}"
                absent = [name for name in required if not os.environ.get(name)]
                if absent:
                    print(f"SKIP {label}: set {', '.join(absent)}")
                    continue
                runtime = sys.executable if language == "python" else "node"
                print(f"RUN  {label}", flush=True)
                result = subprocess.run([runtime, str(FILES[language][family]), operation], cwd=output, check=False)
                if result.returncode:
                    failed += 1
                    print(f"FAIL {label}: exit {result.returncode}", file=sys.stderr)
                else:
                    print(f"PASS {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
