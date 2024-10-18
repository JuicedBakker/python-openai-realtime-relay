from typing import Callable, Dict, List, Any, Optional
import asyncio

EventHandlerCallbackType = Callable[[Dict[str, Any]], None]


class RealtimeEventHandler:
    def __init__(self):
        self.event_handlers: Dict[str, List[EventHandlerCallbackType]] = {}
        self.next_event_handlers: Dict[str, List[EventHandlerCallbackType]] = {}

    def clear_event_handlers(self) -> bool:
        self.event_handlers.clear()
        self.next_event_handlers.clear()
        return True

    def on(
        self, event_name: str, callback: EventHandlerCallbackType
    ) -> EventHandlerCallbackType:
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].append(callback)
        return callback

    def on_next(
        self, event_name: str, callback: EventHandlerCallbackType
    ) -> EventHandlerCallbackType:
        if event_name not in self.next_event_handlers:
            self.next_event_handlers[event_name] = []
        self.next_event_handlers[event_name].append(callback)
        return callback

    def off(
        self, event_name: str, callback: Optional[EventHandlerCallbackType] = None
    ) -> bool:
        handlers = self.event_handlers.get(event_name, [])
        if callback:
            try:
                handlers.remove(callback)
            except ValueError:
                raise ValueError(
                    f'Could not turn off specified event listener for "{event_name}": not found as a listener'
                )
        else:
            self.event_handlers.pop(event_name, None)
        return True

    def off_next(
        self, event_name: str, callback: Optional[EventHandlerCallbackType] = None
    ) -> bool:
        next_handlers = self.next_event_handlers.get(event_name, [])
        if callback:
            try:
                next_handlers.remove(callback)
            except ValueError:
                raise ValueError(
                    f'Could not turn off specified next event listener for "{event_name}": not found as a listener'
                )
        else:
            self.next_event_handlers.pop(event_name, None)
        return True

    async def wait_for_next(
        self, event_name: str, timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        future = asyncio.get_running_loop().create_future()

        def callback(event):
            if not future.done():
                future.set_result(event)

        self.on_next(event_name, callback)

        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self.off_next(event_name, callback)

    def dispatch(self, event_name: str, event: Dict[str, Any]) -> bool:
        handlers = self.event_handlers.get(event_name, []).copy()
        for handler in handlers:
            handler(event)

        next_handlers = self.next_event_handlers.pop(event_name, [])
        for next_handler in next_handlers:
            next_handler(event)

        return True
