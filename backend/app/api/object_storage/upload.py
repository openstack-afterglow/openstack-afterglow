"""백엔드 프록시 업로드 흐름.

흐름:
  1. multipart/form-data 로 파일 수신 (FastAPI UploadFile)
  2. 컨테이너 소유권 검증 (swift.get_container_metadata)
  3. 무결성/형식 검사 (`upload_inspection.inspect_upload`)
  4. quarantine 버킷 ensure 후 boto3 streaming upload (5GB+ 자동 multipart)
  5. 저장된 객체 검증 (`verify_quarantine_object`)
  6. server-side copy → target 버킷, quarantine 원본 삭제
  7. 메타데이터 반환

브라우저 → RGW 직접 PUT 의 CORS 차단을 회피한다.

취소(cancel): 클라가 connection 을 끊으면 disconnect watcher 가 cancel_event 를
set → inspection loop 와 boto3 Callback 이 UploadCanceled raise → multipart 자동
abort → quarantine 정리.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.deps import get_os_conn_write, get_token_info
from app.api.object_storage.containers import _sanitize_object_name
from app.config import get_settings
from app.services import cache, upload_inspection
from app.services import s3 as s3_svc
from app.services import swift as swift_svc
from app.services.cache import invalidation

router = APIRouter(tags=["object-storage-upload"])
_logger = logging.getLogger(__name__)


@router.post("/{container}/upload")
async def upload_object(
    container: str,
    request: Request,
    file: UploadFile = File(...),
    prefix: str = Form(""),
    sha256: str | None = Form(None, pattern=r"^[0-9a-f]{64}$"),
    conn=Depends(get_os_conn_write),
    token_info: dict = Depends(get_token_info),
):
    """클라 → backend (form) → quarantine S3 → 검증 → target S3.

    - 검사 실패 400, 저장 불일치 502, 취소 499. 모든 실패 경로에서 quarantine 정리.
    - `sha256` 은 선택이다. 프론트엔드는 256 MiB 이하 파일에만 계산해 보낸다.
    """
    _logger.info(
        "[upload-entry] container=%s prefix=%r filename=%r content_type=%r size=%r",
        container,
        prefix,
        file.filename,
        file.content_type,
        getattr(file, "size", None),
    )

    try:
        await asyncio.to_thread(swift_svc.get_container_metadata, conn, container)
    except Exception:
        _logger.warning("컨테이너 검증 실패: container=%s", container, exc_info=True)
        raise HTTPException(status_code=404, detail="컨테이너를 찾을 수 없거나 권한 없음")

    quarantine_bucket = f"{container}-quarantine"
    raw_name = (prefix or "") + (file.filename or "")
    object_name = _sanitize_object_name(raw_name)
    # sanitize 후 의미 있는 이름이 남았는지 — `unnamed` fallback 은 명시적 거부
    if not (file.filename or "").strip() or object_name == "unnamed":
        _logger.warning("파일 이름 없음/유효치 않음: prefix=%r filename=%r", prefix, file.filename)
        raise HTTPException(status_code=400, detail="파일 이름이 비어 있거나 유효하지 않습니다")

    # 업로드 크기 cap — settings.app_max_upload_gb (기본 10GB). 클라가 헤더 위장해도
    # boto3 streaming 단계에서 추가 검증되지만 빠른 거부를 위해 사전 체크.
    settings = get_settings()
    max_bytes = settings.app_max_upload_gb * 1024**3
    incoming_size = getattr(file, "size", None)
    if incoming_size is None:
        file.file.seek(0, 2)
        incoming_size = file.file.tell()
        file.file.seek(0)
    if incoming_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"업로드 파일이 최대 허용 크기({settings.app_max_upload_gb}GB)를 초과합니다",
        )
    content_type = file.content_type or "application/octet-stream"

    cancel_event = threading.Event()

    async def _watch_disconnect() -> None:
        """request.receive() 에 block → http.disconnect 도달 시 cancel_event 활성화.

        starlette 의 request.is_disconnected() 는 timeout=0 polling 이라 신뢰성
        낮음. FastAPI 가 UploadFile 파라미터를 처리하며 body 를 모두 소비한 후
        receive() 는 http.disconnect 만 큐에 들어옴 → block + 즉시 감지.
        """
        try:
            while not cancel_event.is_set():
                message = await request.receive()
                if message.get("type") == "http.disconnect":
                    cancel_event.set()
                    _logger.info(
                        "upload cancel: client disconnected (container=%s name=%s)",
                        container,
                        object_name,
                    )
                    return
        except asyncio.CancelledError:
            pass
        except Exception:
            _logger.warning("disconnect watcher 오류", exc_info=True)

    def _do_pipeline() -> dict:
        inspection = upload_inspection.inspect_upload(
            file.file,
            file.filename or "",
            content_type,
            expected_sha256=sha256,
            should_cancel=cancel_event.is_set,
        )
        client = s3_svc.get_user_s3_client(
            token_info["token"],
            token_info["user_id"],
            token_info["project_id"],
        )
        s3_svc.ensure_bucket(client, quarantine_bucket)
        try:
            s3_svc.stream_upload_to_quarantine(
                client,
                quarantine_bucket,
                object_name,
                file.file,
                inspection.content_type,
                cancel_event=cancel_event,
                metadata={
                    "sha256": inspection.sha256,
                    "detected-content-type": inspection.detected_content_type or "unknown",
                },
            )
            if cancel_event.is_set():
                raise s3_svc.UploadCanceled("client disconnected")
            s3_svc.verify_quarantine_object(
                client,
                quarantine_bucket,
                object_name,
                expected_size=inspection.size,
                expected_md5=inspection.md5,
            )
            meta = s3_svc.move_to_target(
                client, quarantine_bucket, container, object_name, expected_size=inspection.size
            )
            return {
                **meta,
                "sha256": inspection.sha256,
                "detected_content_type": inspection.detected_content_type,
            }
        except BaseException:
            # 모든 종료 경로에서 quarantine 정리 (성공 시는 move_to_target 가 이미 삭제)
            _safe_delete_quarantine(client, quarantine_bucket, object_name)
            raise

    watch_task = asyncio.create_task(_watch_disconnect())
    try:
        meta = await asyncio.to_thread(_do_pipeline)
    except s3_svc.UploadCanceled:
        _logger.info("upload aborted: container=%s name=%s", container, object_name)
        raise HTTPException(status_code=499, detail="업로드가 취소되었습니다")
    except upload_inspection.UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except s3_svc.IntegrityError:
        _logger.error("저장 무결성 검증 실패: container=%s name=%s", container, object_name, exc_info=True)
        raise HTTPException(
            status_code=502, detail="무결성 검증 실패: 저장된 객체가 업로드 내용과 일치하지 않습니다"
        ) from None
    except HTTPException:
        raise
    except Exception:
        _logger.exception("upload 실패: container=%s name=%s", container, object_name)
        raise HTTPException(status_code=500, detail="업로드에 실패했습니다")
    finally:
        cancel_event.set()
        watch_task.cancel()

    await cache.invalidate(f"afterglow:swift:{token_info['project_id']}:*")
    await invalidation.invalidate_mutation_count("swift", token_info["project_id"])
    return {"success": True, **meta}


def _safe_delete_quarantine(client, bucket: str, key: str) -> None:
    """quarantine 객체 best-effort 삭제. 예외는 swallow."""
    try:
        s3_svc.delete_object(client, bucket, key)
    except Exception:
        _logger.warning("quarantine 정리 실패: %s/%s", bucket, key, exc_info=True)
