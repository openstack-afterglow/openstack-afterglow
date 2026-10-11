"""Library catalog used by retained file-storage management."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from fastapi import APIRouter, Depends

from app.api.deps import get_os_conn, get_token_info
from app.models.storage import LibraryConfig
from app.services import libraries as lib_svc
from app.services import manila
from app.services.keystone import get_service_project_connection

router = APIRouter()
_logger = logging.getLogger(__name__)


@router.get("", response_model=list[LibraryConfig])
async def list_libraries(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    token_info: dict = Depends(get_token_info),
):
    """사용 가능한 라이브러리 목록 (사전 빌드 파일 스토리지 가용 여부 포함).
    non-admin은 visibility=public 라이브러리만 반환.
    prebuilt share는 service 프로젝트 소유 public share이므로 service conn + include_public=True로 조회한다.
    """
    is_admin = token_info.get("is_system_admin", False)
    catalog = lib_svc.get_all()

    # 사전 빌드된 파일 스토리지 목록에서 library_name 매핑
    # service conn + include_public=True: 일반 프로젝트에서도 public prebuilt share가 보이도록
    try:
        svc_conn = await asyncio.to_thread(get_service_project_connection)
        prebuilt_file_storages = await asyncio.to_thread(
            manila.list_file_storages,
            svc_conn,
            {"union_type": "prebuilt"},
            include_public=True,
        )
        prebuilt_map = {s.library_name: s.id for s in prebuilt_file_storages if s.library_name}
    except Exception:
        _logger.warning("prebuilt file-storage 목록을 조회할 수 없습니다", exc_info=True)
        prebuilt_map = {}

    result = []
    for lib in catalog:
        # non-admin은 private 라이브러리 제외
        if not is_admin and lib.visibility == "private":
            continue
        file_storage_id = prebuilt_map.get(lib.id)
        result.append(
            LibraryConfig(
                **lib.model_dump(exclude={"file_storage_id", "available_prebuilt"}),
                file_storage_id=file_storage_id,
                available_prebuilt=file_storage_id is not None,
            )
        )
    return result
