"""Read-only managed backup account report; native writes belong to the elected loop.

From backend: uv run python scripts/backup_system_account.py --report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


async def _report() -> int:
    from app.services.backup_account_reconciler import read_report

    result = await read_report()
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["complete"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only backup account, role and quota report")
    parser.add_argument("--report", action="store_true", default=True, help="Report intended changes only (default)")
    parser.parse_args(argv)
    try:
        return asyncio.run(_report())
    except Exception:
        # Native exceptions can include request headers or secrets. Never print them.
        print(json.dumps({"mode": "report", "complete": False, "reason": "report_unavailable"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
