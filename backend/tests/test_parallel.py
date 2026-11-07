"""run_parallel keeps its ordered-exception contract and honours a per-caller worker cap."""

import threading
import time

import pytest

from app.services.parallel import run_parallel


def _tracked(delay=0.02):
    state = {"inflight": 0, "peak": 0}
    lock = threading.Lock()

    def call(value):
        def run():
            with lock:
                state["inflight"] += 1
                state["peak"] = max(state["peak"], state["inflight"])
            time.sleep(delay)
            with lock:
                state["inflight"] -= 1
            return value

        return run

    return state, call


def test_results_keep_input_order_under_a_worker_cap():
    state, call = _tracked()
    assert run_parallel(*(call(i) for i in range(10)), max_workers=3) == list(range(10))
    assert 2 <= state["peak"] <= 3


def test_default_cap_is_unchanged_and_a_caller_cap_cannot_raise_it():
    state, call = _tracked()
    run_parallel(*(call(i) for i in range(20)))
    assert 2 <= state["peak"] <= 8
    state, call = _tracked()
    run_parallel(*(call(i) for i in range(20)), max_workers=64)
    assert state["peak"] <= 8


def test_earliest_call_exception_wins_regardless_of_finish_order():
    def slow_fail():
        time.sleep(0.05)
        raise ValueError("first")

    def fast_fail():
        raise KeyError("second")

    with pytest.raises(ValueError, match="first"):
        run_parallel(slow_fail, fast_fail, max_workers=2)
