from __future__ import annotations

from fastapi import HTTPException
from openstack.exceptions import ConflictException, HttpException, NotFoundException


def public_service_error(status_code: int, code: str) -> HTTPException:
    """A reviewed fixed 5xx code that the central sanitizer returns verbatim to clients."""
    error = HTTPException(status_code=status_code, detail=code)
    error._afterglow_safe_public_detail = True
    return error


def openstack_error_to_http(exc: Exception, is_admin: bool = False) -> HTTPException:
    """OpenStack 예외 → HTTPException 변환 유틸리티.

    5xx 로 매핑되는 경우 OpenStack 내부 URL/엔드포인트가 클라이언트에 노출되지 않도록
    일반 메시지로 치환한다(CLAUDE.md §6). 운영 디버깅을 위해 관리자(is_admin=True)에게는
    원본 메시지를 그대로 전달한다. 4xx 는 사용자에게 유의미하므로 원본을 유지.
    """
    if isinstance(exc, NotFoundException):
        return HTTPException(status_code=404, detail="리소스를 찾을 수 없습니다")
    if isinstance(exc, ConflictException):
        return HTTPException(status_code=409, detail="충돌이 발생했습니다")
    if isinstance(exc, HttpException):
        # openstacksdk HttpException 의 상태 코드는 `status_code` 속성에 담긴다
        # (생성자 인자명은 http_status 이나 인스턴스 속성은 status_code).
        status = getattr(exc, "status_code", None) or 500
        if status >= 500 and not is_admin:
            return HTTPException(status_code=status, detail="작업 실패")
        return HTTPException(status_code=status, detail=str(exc))
    return HTTPException(status_code=500, detail="작업 실패")
