"""토큰 발급 출처(IP + 기기 지문) 바인딩, 블랙리스트 검사, 기기 정보 파싱.

MAC 주소는 웹 환경에서 수집 불가능하므로(브라우저 JS 접근 차단, 서버는 L3 너머 클라이언트 MAC 불가),
IP + User-Agent/Accept-Language/Accept-Encoding 해시(기기 지문)로 대체한다.

검사 모드 (afterglow.conf [session] token_ip_binding_mode):
  off    — 검사 없음
  log    — 불일치 로깅만, 차단 없음
  subnet — IP가 다른 /24(IPv4) · /64(IPv6) 대역이면 차단 (기본)
  strict — IP 정확 불일치 또는 지문 불일치 시 차단
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging

_logger = logging.getLogger(__name__)


def parse_device(user_agent: str) -> tuple[str, str]:
    """User-Agent 문자열에서 (device_type, os) coarse 요약 반환.

    raw UA는 저장하지 않고 이 함수의 결과값(요약)만 세션에 기록한다.
    (Phase 1 hash-only 프라이버시 결정의 의식적 최소 확장)

    Returns:
        device_type: "desktop" | "mobile" | "tablet" | "unknown"
        os:          "macOS" | "Windows" | "iOS" | "Android" | "Linux" | "unknown"
    """
    ua = user_agent or ""
    ua_l = ua.lower()

    # OS 판별
    if "iphone" in ua_l or "ipad" in ua_l:
        os_name = "iOS"
    elif "android" in ua_l:
        os_name = "Android"
    elif "macintosh" in ua_l or "mac os x" in ua_l:
        os_name = "macOS"
    elif "windows" in ua_l:
        os_name = "Windows"
    elif "linux" in ua_l:
        os_name = "Linux"
    else:
        os_name = "unknown"

    # 기기 타입 판별
    if "ipad" in ua_l or "tablet" in ua_l:
        device_type = "tablet"
    elif "android" in ua_l and "mobile" not in ua_l:
        # Android 태블릿: UA에 "Mobile" 없이 "Android"만 포함
        device_type = "tablet"
    elif "mobile" in ua_l or "iphone" in ua_l or "mobi" in ua_l:
        device_type = "mobile"
    elif ua:
        device_type = "desktop"
    else:
        device_type = "unknown"

    return device_type, os_name


def get_origin(request) -> tuple[str, str]:
    """클라이언트 (IP, 기기지문) 반환.

    IP: rate_limit._get_real_ip 재사용 (신뢰 프록시 CIDR 기반 X-Forwarded-For 처리).
    지문: sha256(User-Agent|Accept-Language|Accept-Encoding)[:32]
    """
    from app.rate_limit import _get_real_ip  # 지연 임포트 (순환 방지)

    ip = _get_real_ip(request)
    ua = request.headers.get("User-Agent", "")
    al = request.headers.get("Accept-Language", "")
    ae = request.headers.get("Accept-Encoding", "")
    fp_raw = f"{ua}|{al}|{ae}"
    fp = hashlib.sha256(fp_raw.encode()).hexdigest()[:32]
    return ip, fp


def _same_subnet(a: str, b: str) -> bool:
    """두 IP가 같은 /24(IPv4) 또는 /64(IPv6) 대역이면 True."""
    try:
        ia = ipaddress.ip_address(a)
        ib = ipaddress.ip_address(b)
        if ia.version != ib.version:
            return False
        prefix = 24 if ia.version == 4 else 64
        net_a = ipaddress.ip_network(f"{ia}/{prefix}", strict=False)
        return ib in net_a
    except ValueError:
        return False


def check_binding(
    sess: dict,
    cur_ip: str,
    cur_fp: str,
    mode: str,
) -> tuple[str, str]:
    """IP/지문 바인딩 검사.

    Args:
        sess: Redis 세션 dict (origin_ip, origin_fp 포함)
        cur_ip: 현재 요청 IP
        cur_fp: 현재 요청 기기 지문
        mode: "off" | "log" | "subnet" | "strict"

    Returns:
        (action, reason)
          action: "ok" — 통과
                  "log" — 기록만, 차단 없음
                  "block" — 차단 (401 반환)
    """
    if mode == "off":
        return "ok", ""

    origin_ip = sess.get("origin_ip", "")
    origin_fp = sess.get("origin_fp", "")

    # A missing login origin cannot establish strict/subnet binding. Never
    # adopt the current caller as the origin of an old potentially stolen token.
    if not origin_ip and mode in {"strict", "subnet", "log"}:
        return ("block" if mode in {"strict", "subnet"} else "log"), "legacy_session"

    ip_match = cur_ip == origin_ip
    subnet_match = _same_subnet(cur_ip, origin_ip)
    fp_match = cur_fp == origin_fp

    if mode == "log":
        if not ip_match or not fp_match:
            reason = f"ip={cur_ip!r}≠{origin_ip!r} fp={'match' if fp_match else 'mismatch'}"
            return "log", reason
        return "ok", ""

    if mode == "subnet":
        if not subnet_match:
            reason = f"ip={cur_ip!r} 출처대역={origin_ip}/{'24' if ':' not in origin_ip else '64'}"
            return "block", reason
        if not fp_match:
            # 같은 서브넷이지만 지문 불일치 — 로그만 (모바일/동일 회사망 다른 기기)
            return "log", f"fp_mismatch subnet_ok ip={cur_ip!r}"
        return "ok", ""

    if mode == "strict":
        if not ip_match:
            reason = f"ip={cur_ip!r}≠{origin_ip!r}"
            return "block", reason
        if not fp_match:
            reason = f"fp_mismatch cur={cur_fp!r}≠{origin_fp!r}"
            return "block", reason
        return "ok", ""

    # 알 수 없는 모드 — 설정 오류로 간주하여 예외 발생 (fail-closed)
    # deps.py의 except Exception 핸들러가 이를 포착하여 401을 반환.
    raise ValueError(f"알 수 없는 token_ip_binding_mode: {mode!r}. 허용값: 'off', 'log', 'subnet', 'strict'")
