import functools
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from time import sleep
from typing import Any, Callable, Optional


def yield_thread() -> None:
    sleep(0)


class FileTaskExecutor:
    """A task executor that manages concurrent file operations with deduplication.

    This executor ensures that only one task per file path runs at a time, even if
    multiple tasks are submitted for the same file. It executes tasks with `concurrent`
    threads when `concurrent` >= 1, specially when `concurrent` is 1, it will execute
    tasks sequentially. When `concurrent` < 1, it will use the default setting of
    ThreadPoolExecutor.

    Args:
        concurrent (int): Number of concurrent threads to use. Defaults to 1.
    Example:
        >>> executor = FileTaskExecutor(concurrent=2)
        >>> future = executor.submit(Path("file.txt"), process_file, "file.txt")
        >>> executor.wait()  # Wait for all tasks to complete
    """

    def __init__(self, concurrent: int = 0):
        self.executor = (
            None
            if concurrent == 1
            else ThreadPoolExecutor(concurrent if concurrent > 1 else None)
        )
        self.working_map: dict[Path, Future[Any]] = {}

    def submit_chain(
        self, path: Path, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> Future[Any]:
        return self._submit(path, fn, True, *args, **kwargs)

    def submit(
        self, path: Path, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> Future[Any]:
        return self._submit(path, fn, False, *args, **kwargs)

    def _submit(
        self,
        path: Path,
        fn: Callable[..., Any],
        chain: bool,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[Any]:
        if not path.is_absolute():
            path = path.absolute()

        future: Future[Any]
        if self.executor is None:
            future = Future()
            future.set_result(fn(*args, **kwargs))
        elif not chain:
            assert path not in self.working_map, "path already in working_map"
            future = self.executor.submit(fn, *args, **kwargs)
            self.working_map[path] = future
        else:
            current = self.working_map[path]
            future = self.working_map[path] = Future()

            @functools.wraps(fn)
            def new_fn(_current: Future[Any]) -> None:
                nonlocal future, current

                assert _current == current

                try:
                    future.set_result(fn(*args, **kwargs))
                except Exception as e:
                    future.set_exception(e)

            current.add_done_callback(new_fn)

        return future

    def wait(self, path: Optional[Path] = None) -> None:
        """Wait for tasks to complete.

        If a path is specified, waits only for that specific file's task to complete.
        Otherwise, waits for all tasks to complete.

        Args:
            path (Optional[Path]): The specific file path to wait for. If None,
                waits for all tasks to complete.
        """
        if self.executor is None:
            return
        if path is not None:
            self.working_map.pop(path).result()
        else:
            for path in list(self.working_map):
                self.wait(path)

    def __contains__(self, fn: Path) -> bool:
        return self.executor is not None and fn in self.working_map


POOL = FileTaskExecutor(2)
