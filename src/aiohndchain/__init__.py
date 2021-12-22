import asyncio
# from collections import defaultdict
from contextlib import asynccontextmanager
from typing import MutableSequence, Coroutine, Callable, Any, Optional, AsyncGenerator


class AIOHandlerChain:
    def __init__(self, *, event=asyncio.Event(), lock=asyncio.Lock()):
        self._handlers: MutableSequence[Callable[(type(self), ...), Coroutine[Optional[bool]]]] = []
        self._lock = lock
        self._evt = event
        self._before = asyncio.Condition(lock)
        self._after = asyncio.Condition(lock)
        self._ctxres: Optional[bool] = None

    def _ctxhandle(self, res: Optional[bool] = None) -> bool:
        if res is None:
            if self._ctxres is None:
                self._ctxres = res
        else:
            pass

    def add_handler(self, afunc: Callable[(Any, ), Coroutine[Any]]) -> bool:
        if afunc not in self._handlers:
            self._handlers.insert(0, afunc)
            return True
        return False

    def remove_handler(self, afunc: Callable) -> bool:
        if afunc in self._handlers:
            self._handlers.remove(afunc)
            return True
        return False

    @asynccontextmanager
    async def wait_and_handle(self) -> AsyncGenerator[Any, Callable[(Optional[bool], ), None]]:
        try:
            await self._after.acquire()
            await self._after.wait()
            yield self._ctxhandle
        finally:
            self._after.release()

    async def emit(self, *args, **kwargs):
        self._ctxres = res = None
        try:
            self._before.notify_all()
            while self._before.locked():
                async with self._before:
                    pass
            if self._ctxres is not False:
                async with self._lock:
                    for hndid in range(len(self._handlers)):
                        handler = self._handlers[hndid]
                        try:
                            self._ctxres = _res = await handler(self, *args, **kwargs)
                            if isinstance(_res, bool) and not res:
                                res = _res
                                if not _res:
                                    break
                        except Exception as exc:
                            await self.on_handler_error(hndid, exc)
            self._after.notify_all()
            while self._after.locked():
                async with self._after:
                    pass
            self._evt.set()
            self._evt.clear()
            if self._ctxres is not False:
                async with self._lock:
                    pass
            if isinstance(self._ctxres, bool):
                res = self._ctxres
            if res:
                await self.on_success()
            else:
                await self.on_failure()
        except Exception as exc:
            await self.on_error(exc)

    async def on_success(self):
        # override
        pass

    async def on_failure(self):
        # override
        pass

    async def on_error(self, exc: Exception):
        # override
        pass

    async def on_handler_error(self, hndid: int, exc: Exception):
        # override
        pass
