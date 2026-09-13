"""Wait for Splunk management port and KV store after restart."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from splunk_client import SplunkRestClient, SplunkRestError

T = TypeVar("T")


def wait_for_kv(client: SplunkRestClient, timeout_sec: float = 120.0) -> None:
    deadline = time.time() + timeout_sec
    path = client.app_path("storage/collections/config/stig_collections")
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            client.get_json(path)
            return
        except SplunkRestError as err:
            last_err = err
            if err.status == 503:
                time.sleep(5)
                continue
            raise
        except Exception as err:
            last_err = err
            time.sleep(3)
    raise TimeoutError(f"KV store not ready after {timeout_sec}s: {last_err}")


def retry_on_503(fn: Callable[[], T], attempts: int = 12, delay_sec: float = 5.0) -> T:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return fn()
        except SplunkRestError as err:
            last = err
            if err.status == 503:
                time.sleep(delay_sec)
                continue
            raise
    raise last or RuntimeError("retry_on_503 failed")
