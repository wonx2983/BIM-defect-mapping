"""Bounded blocking work; capacity remains occupied until a cancelled worker exits."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import BoundedSemaphore
from app.core.exceptions import AppException

_slots = BoundedSemaphore(2)
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="inspection")


async def run_blocking(fn, *args, **kwargs):
    if not _slots.acquire(blocking=False):
        raise AppException("Processing capacity is busy. Retry shortly.", "BUSY", 503)
    def work():
        try:
            return fn(*args, **kwargs)
        finally:
            _slots.release()
    future = asyncio.get_running_loop().run_in_executor(_pool, work)
    return await asyncio.shield(future)
