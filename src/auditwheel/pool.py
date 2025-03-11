"""
Concurrent support of auditwheel.
This can sppedup `auditwheel show` and `auditwheel repair`
where they have external shell invocation/io operations
that do no depends on each other and can be parallelized.

If `j=1`, there'll be no concurrency at all and each call is synchronous,
which is same as not using this pool.
"""

import contextlib
import functools
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional


class FileTaskExecutor:
    """A task executor that manages parallel jobs assiciated with a file.

    This executor ensures that only one task per file path runs at a time.
    Multiple tasks submitted for the same file will be executed in order.
    It executes tasks with `concurrent` threads when `concurrent` >= 1.
    Specially when `concurrent` is 1, it will execute tasks sequentially.
    When `concurrent` < 1, it will use the default setting of
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
        """
        Submit a task to be executed (after any existing task) for the file.
        """
        return self._submit(path, fn, True, *args, **kwargs)

    def submit(
        self, path: Path, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> Future[Any]:
        """
        Submit a task to be executed when no task running for the file,
        otherwise raise an error.
        """
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
        elif chain and path in self.working_map:
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
        else:
            if not chain:
                assert path not in self.working_map, (
                    "task assiciated with path is already running"
                )
            future = self.executor.submit(fn, *args, **kwargs)
            self.working_map[path] = future

        return future

    def wait(self, path: Optional[Path] = None) -> None:
        """Wait for tasks to complete.

        If a path is specified, waits only for that specific file's task to complete.
        Otherwise, waits for all tasks to complete.

        Args:
            path (Optional[Path]): The specific file path to wait for. If None,
                waits for all tasks to complete.
        """
        if self.executor is None or (path is not None and path not in self.working_map):
            return
        if path is not None:
            with contextlib.suppress(Exception):
                self.working_map.pop(path).result()
        else:
            for path in list(self.working_map):
                self.wait(path)


DEFAULT_POOL = FileTaskExecutor(1)
