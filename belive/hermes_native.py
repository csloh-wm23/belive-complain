"""Run the installed Hermes Python runtime with bounded JSON tool transport."""

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

_runtime_lock = threading.RLock()


def runtime_python():
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("HERMES_NOT_INSTALLED")
    directory = Path(executable).resolve().parent
    python = directory / ("python.exe" if os.name == "nt" else "python")
    if not python.is_file():
        raise RuntimeError("HERMES_PYTHON_NOT_FOUND")
    return python


def native_request(messages, settings, *, tools=None, dispatch=None, max_steps=5,
                   stop_event=None, examples=None, home=None, mode="generate"):
    """Secrets travel through stdin, never arguments, logs or saved request files."""
    if stop_event and stop_event.is_set():
        raise RuntimeError("STOPPED_BY_OPERATOR")
    from belive.settings import load_settings
    settings = settings or load_settings()
    root = Path(__file__).resolve().parent
    home = Path(home or root.parent / "data/hermes_memory/support").resolve()
    base = (settings.ollama_base_url.rstrip("/") + "/v1"
            if settings.llm_provider == "ollama" else "https://api.openai.com/v1")
    key = settings.ollama_api_key if settings.llm_provider == "ollama" else settings.llm_api_key
    request = dict(messages=messages, tools=tools or [], max_steps=max_steps,
                   examples=examples or [], mode=mode, model=settings.llm_model,
                   base_url=base, api_key=key or "local-ollama")
    env = dict(os.environ, HERMES_HOME=str(home), PYTHONIOENCODING="utf-8")
    with _runtime_lock:
        with subprocess.Popen([str(runtime_python()), str(root / "hermes_worker.py")],
                              cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
            events = queue.Queue()
            def read():
                for line in process.stdout:
                    events.put(line)
                events.put(None)
            threading.Thread(target=read, daemon=True).start()
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + max(120, max_steps * 90)
            try:
                while time.monotonic() < deadline:
                    if stop_event and stop_event.is_set():
                        raise RuntimeError("STOPPED_BY_OPERATOR")
                    try:
                        line = events.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if line is None:
                        raise RuntimeError("HERMES_WORKER_EXITED")
                    event = json.loads(line)
                    if event["type"] == "tool":
                        if dispatch is None:
                            raise RuntimeError("UNEXPECTED_HERMES_TOOL")
                        result = dispatch(event["name"], event["arguments"])
                        process.stdin.write(json.dumps(result) + "\n")
                        process.stdin.flush()
                    elif event["type"] == "result":
                        return event
                    elif event["type"] == "error":
                        raise RuntimeError(event["code"])
                raise RuntimeError("HERMES_TIMEOUT")
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)


def memory_snapshot(home=None):
    path = Path(home or Path(__file__).resolve().parents[1] / "data/hermes_memory/support") / "memories/MEMORY.md"
    return path.read_text(encoding="utf-8") if path.is_file() else "No approved examples have been loaded yet."
