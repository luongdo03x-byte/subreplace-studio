from __future__ import annotations

from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Callable

from .protocol import WorkerCommand, WorkerEvent, WorkerEventType


class WorkerExecutionError(RuntimeError):
    def __init__(self, message: str, *, events: tuple[WorkerEvent, ...] = (), stderr: str = "") -> None:
        super().__init__(message)
        self.events = events
        self.stderr = stderr


class ProcessStageWorker:
    def __init__(self, runner_script: str | Path | None = None) -> None:
        self.runner_script = Path(runner_script) if runner_script else None
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[str] | None = None

    @property
    def active_pid(self) -> int | None:
        with self._process_lock:
            process = self._active_process
            return process.pid if process is not None and process.poll() is None else None

    def cancel(self) -> None:
        with self._process_lock:
            process = self._active_process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def run(
        self,
        command: WorkerCommand,
        *,
        on_event: Callable[[WorkerEvent], None] | None = None,
        timeout: float | None = None,
    ) -> tuple[WorkerEvent, ...]:
        if self.runner_script is not None and not self.runner_script.is_file():
            raise FileNotFoundError(self.runner_script)
        callback = on_event or (lambda _event: None)
        argv = [sys.executable, str(self.runner_script)] if self.runner_script is not None else [sys.executable, "-m", "app.workers.runner"]
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        with self._process_lock:
            self._active_process = process
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdin.write(command.to_json() + "\n")
        process.stdin.flush()
        process.stdin.close()

        stdout_queue: queue.Queue[str | None] = queue.Queue()
        stderr_chunks: list[str] = []

        def read_stdout() -> None:
            try:
                for line in process.stdout:
                    stdout_queue.put(line)
            finally:
                stdout_queue.put(None)

        def read_stderr() -> None:
            stderr_chunks.extend(process.stderr.readlines())

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        deadline = time.monotonic() + timeout if timeout is not None else None
        events: list[WorkerEvent] = []
        stdout_done = False
        failure_message: str | None = None
        while not stdout_done or process.poll() is None:
            if deadline is not None and time.monotonic() > deadline:
                process.kill()
                process.wait(timeout=2)
                raise WorkerExecutionError(
                    f"worker stage {command.stage} timed out",
                    events=tuple(events),
                    stderr="".join(stderr_chunks),
                )
            try:
                line = stdout_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if line is None:
                stdout_done = True
                continue
            if not line.strip():
                continue
            try:
                event = WorkerEvent.from_json(line)
            except Exception as exc:
                process.kill()
                process.wait(timeout=2)
                raise WorkerExecutionError(
                    f"worker emitted invalid JSONL: {exc}",
                    events=tuple(events),
                    stderr="".join(stderr_chunks),
                ) from exc
            events.append(event)
            callback(event)
            if event.type is WorkerEventType.FAILED:
                failure_message = event.message or f"worker stage {command.stage} failed"

        return_code = process.wait()
        with self._process_lock:
            if self._active_process is process:
                self._active_process = None
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        stderr = "".join(stderr_chunks).strip()
        if failure_message or return_code != 0:
            message = failure_message or stderr or f"worker stage {command.stage} exited with code {return_code}"
            raise WorkerExecutionError(message, events=tuple(events), stderr=stderr)
        if not events or events[-1].type is not WorkerEventType.COMPLETED:
            raise WorkerExecutionError(
                f"worker stage {command.stage} ended without completed event",
                events=tuple(events),
                stderr=stderr,
            )
        return tuple(events)
