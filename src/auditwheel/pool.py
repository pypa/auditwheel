import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional


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

    def __init__(self, concurrent: int = 1):
        self.executor = (
            None
            if concurrent == 1
            else ThreadPoolExecutor(concurrent if concurrent > 1 else None)
        )
        self.working_map: dict[Path, Future[tuple[str, str]]] = {}

    def submit(
        self, path: Path, fn: Callable[[Any], Any], /, *args: Any, **kwargs: Any
    ) -> None:
        if not path.is_absolute():
            path = path.absolute()

        future: Future[Any]
        if self.executor is None:
            future = Future()
            future.set_result(fn(*args, **kwargs))
            return

        if path not in self.working_map:
            future = self.executor.submit(fn, *args, **kwargs)
            self.working_map[path] = future
        else:
            future = self.working_map[path]
            future.add_done_callback(lambda _: self.working_map.pop(path, None))
            future.add_done_callback(lambda _: self.submit(path, fn, *args, **kwargs))

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
        if path is not None and path in self.working_map:
            self.working_map.pop(path, None).result()
            # may have chained callback, so we need to wait again
            self.wait(path)

        while self.working_map:
            # Process one task for each for-loop
            # for map might be changed during the loop
            for path in self.working_map:
                self.wait(path)
                break


def fake_job(i: int) -> int:
    print(f"start {i}")
    time.sleep(i)
    print(f"end {i}")


if __name__ == "__main__":
    executor = FileTaskExecutor(concurrent=0)
    for i in range(10):
        executor.submit(Path(f"test{i}.txt"), fake_job, i)
    for i in range(10):
        executor.submit(Path(f"test{i}.txt"), fake_job, i)
    for i in range(10):
        executor.submit(Path(f"test{i}.txt"), fake_job, i)
    for i in range(10):
        executor.submit(Path(f"test{i}.txt"), fake_job, i)
    for i in range(10):
        executor.submit(Path(f"test{i}.txt"), fake_job, i)
    for i in range(10):
        executor.submit(Path(f"test{i}.txt"), fake_job, i)
    for i in range(10):
        executor.submit(Path(f"test{i}.txt"), fake_job, i)
    executor.wait()
