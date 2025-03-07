from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional


class FileTaskExecutor:
    def __init__(self, concurrent: bool = False):
        self.executor = ThreadPoolExecutor() if concurrent else None
        self.working_map: dict[Path, Future[tuple[str, str]]] = {}

    def submit(
        self, path: Path, fn: Callable[[Any], Any], /, *args: Any, **kwargs: Any
    ) -> Future[Any]:
        future: Future[Any]
        if self.executor is None:
            future = Future()
            future.set_result(fn(*args, **kwargs))
            return future
        assert path not in self.working_map
        future = self.executor.submit(fn, *args, **kwargs)
        future.add_done_callback(lambda f: self.working_map.pop(path))
        self.working_map[path] = future
        return future

    def wait(self, path: Optional[Path] = None) -> None:
        if self.executor is None:
            return
        if path is not None:
            if path in self.working_map:
                self.working_map.pop(path).result()
            return

        for path in self.working_map:
            self.wait(path)
