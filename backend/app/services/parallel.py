"""독립적인 blocking 조회를 스레드로 동시에 실행하는 최소 유틸리티.

OpenStack API 호출은 대기 시간이 지배적이라 직렬 fan-out 이 응답 시간을 그대로 합산한다.
토폴로지처럼 서로 의존하지 않는 조회가 여러 개인 경로에서만 사용한다.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

_MAX_WORKERS = 8


def run_parallel(*calls: Callable[[], Any], max_workers: int | None = None) -> list[Any]:
    """``calls`` 를 동시에 실행하고 입력 순서대로 결과를 반환한다.

    예외는 호출 순서대로 재발생한다 — 앞선 호출이 실패하면 그 예외가 그대로 올라간다.
    호출이 하나뿐이면 스레드를 만들지 않는다. ``max_workers`` 는 호출자별 상한이며
    (기본 ``_MAX_WORKERS``) 이를 넘기지 않는다. 같은 호스트의 공유 소켓 풀을 쓰는 경로는
    요청 하나의 동시성을 낮춰 풀 고갈과 연결 폭증을 피한다.
    """
    if not calls:
        return []
    if len(calls) == 1:
        return [calls[0]()]
    workers = min(len(calls), _MAX_WORKERS, max_workers or _MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="afterglow-fanout") as ex:
        futures = [ex.submit(call) for call in calls]
        return [future.result() for future in futures]
