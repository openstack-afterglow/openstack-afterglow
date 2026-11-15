"""Read-only administrator diagnostics for the automatic-backup principal."""

from fastapi import APIRouter, Depends, Response

from app.api.common.errors import public_service_error
from app.api.deps import require_admin
from app.services import backup_account_reconciler

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/backup-system-account")
async def backup_account_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        return await backup_account_reconciler.status()
    except Exception:
        raise public_service_error(503, "backup_system_account_status_unavailable") from None


@router.get("/backup-system-account/report")
async def backup_account_report(response: Response):
    """Enumerate intended native writes; this endpoint never performs them."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return await backup_account_reconciler.read_report()
    except Exception:
        raise public_service_error(503, "backup_system_account_report_unavailable") from None
