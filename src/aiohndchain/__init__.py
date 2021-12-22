import asyncio
# from collections import defaultdict
from contextlib import asynccontextmanager
from typing import MutableSequence, Coroutine, Callable, Any, Optional, AsyncGenerator, Tuple


class AIOHandlerChain:
    """
    p
    """
    def __init__(self, *, event=asyncio.Event(), lock=asyncio.Lock()):
        self._handlers: MutableSequence[Callable[(type(self), ...), Coroutine[Any, Any, Any]]] = []
        self._lock = lock
        self._evt = event
        self._before = asyncio.Condition(lock)
        self._after = asyncio.Condition(lock)
        self._ctxargs = []
        self._ctxkwargs = {}
        self._ctxres: Optional[bool] = None

    def _ctxhandle(self, res: Optional[bool] = None) -> (bool, list, dict):
        _res = True
        if self._ctxres is None and res is not None:
            self._ctxres = res
            _res = res
        elif self._ctxres is False:
            _res = False
        return _res, self._ctxargs, self._ctxkwargs

    def debug_print(self, msg: str):
        pass

    def add_handler(self, afunc: Callable[(Any, ), Coroutine[Any, Any, Any]]) -> bool:
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
    async def wait_and_handle(self, *, before=False) -> AsyncGenerator[Any, Callable[(Optional[bool], ), Tuple[bool, list, dict]]]:
        _cond = self._before if before else self._after
        self.debug_print("wait_and_handle: before try")
        try:
            await _cond.acquire()
            self.debug_print("wait_and_handle: lock acquired, waiting...")
            await _cond.wait()
            self.debug_print("wait_and_handle: wait complete")
            yield self._ctxhandle
        finally:
            _cond.release()

    async def __call__(self, *args, **kwargs):
        await self.emit(*args, **kwargs)

    async def emit(self, *args, **kwargs):
        self._ctxres = res = None
        self._ctxargs.clear()
        self._ctxkwargs.clear()
        try:
            async with self._before:
                self.debug_print("emit: notifying _before")
                self._before.notify_all()
            self.debug_print("emit: checkout lock")
            while self._lock.locked():
                self.debug_print("emit: locked, waiting...")
                async with self._lock:
                    pass
                self.debug_print("emit: unlocked, continuing?")
            self._ctxargs.extend(args)
            self._ctxkwargs.update(kwargs)
            self.debug_print("emit: updated context args")
            if self._ctxres is not False:
                self.debug_print("emit: _ctxres is not False")
                async with self._lock:
                    self.debug_print("emit: handler lock acquired")
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
            else:
                self.debug_print("emit: _ctxres is False")
                self._ctxargs.clear()
                self._ctxkwargs.clear()
            async with self._after:
                self.debug_print("emit: notifying _after")
                self._after.notify_all()
            while self._lock.locked():
                self.debug_print("emit: after lock wait...")
                async with self._lock:
                    pass
            self._evt.set()
            self._evt.clear()
            self.debug_print("emit: end phase")
            if self._ctxres is not False:
                self.debug_print("emit: checkout lock at the end")
                async with self._lock:
                    pass
                self.debug_print('emit: lock passed')
            if isinstance(self._ctxres, bool):
                res = self._ctxres
            if res is not False:
                self.debug_print('emit: execute success')
                await self.on_success()
            else:
                self.debug_print('emit: execute failure')
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
