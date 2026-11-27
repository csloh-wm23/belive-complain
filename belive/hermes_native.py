"""Run the installed Hermes Python runtime with bounded JSON tool transport."""

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import contextvars
import atexit
import hashlib
from collections import OrderedDict
from contextlib import contextmanager

_scope=contextvars.ContextVar('belive_native_hermes_scope',default='')
@contextmanager
def conversation_scope(value):
    token=_scope.set(value)
    try:yield
    finally:_scope.reset(token)

def runtime_info():
    path=Path(__file__).resolve().parents[1]/'data'/'hermes-runtime.json'
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

_runtime_lock = threading.RLock()
_workers=OrderedDict()


class _NativeWorker:
    def __init__(self,python,script,root,env):
        self.process=subprocess.Popen([str(python),str(script)],cwd=root,env=env,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.events=queue.Queue();self.used=time.monotonic()
        def read():
            try:
                for line in self.process.stdout:self.events.put(line)
            finally:self.events.put(None)
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()

    def close(self):
        if self.process.poll() is None:self.process.terminate()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        for stream in (self.process.stdin,self.process.stdout):
            if stream:
                try:stream.close()
                except OSError:pass


def close_workers():
    with _runtime_lock:
        for worker in _workers.values():worker.close()
        _workers.clear()


atexit.register(close_workers)


def _worker_key(home,python,request):
    # Keep each customer's profile, provider credentials and tool allowlist isolated.
    config={k:request.get(k) for k in ('model','base_url','api_key','tools','runtime_version','runtime_commit')}
    return str(home),str(python),hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()


def runtime_python():
    configured=os.getenv('BELIVE_HERMES_PYTHON','').strip() or runtime_info().get('python','')
    if configured:
        candidate=Path(configured)
        if not candidate.is_file():raise RuntimeError('HERMES_NOT_INSTALLED')
        return candidate
    executable = shutil.which("hermes")
    if not executable and os.name == "nt":
        roots = []
        if os.environ.get("USERPROFILE"):
            roots.append(Path(os.environ["USERPROFILE"]) / "AppData/Local")
        if os.environ.get("LOCALAPPDATA"):
            roots.append(Path(os.environ["LOCALAPPDATA"]))
        executable = next((str(root / "hermes/bin/hermes.exe") for root in roots
                           if (root / "hermes/bin/hermes.exe").is_file()), None)
    if not executable:
        raise RuntimeError("HERMES_NOT_INSTALLED")
    # Do not resolve this path on packaged Windows hosts: filesystem
    # virtualization can expand it beyond Python's import path limit.
    directory = Path(executable).parent
    candidates = [directory / ("python.exe" if os.name == "nt" else "python")]
    if os.name == "nt":
        candidates.extend((directory.parent / "installs").glob(
            "*/environments/*/venv/Scripts/python.exe"))
    available = [path for path in candidates if path.is_file()]
    if not available:
        raise RuntimeError("HERMES_PYTHON_NOT_FOUND")
    return max(available, key=lambda path: path.stat().st_mtime)


def native_request(messages, settings, *, tools=None, dispatch=None, max_steps=5,
                   stop_event=None, examples=None, home=None, mode="generate", response_schema=None,observer=None,role='',max_output_tokens=2500,keep_warm=False):
    """Secrets travel through stdin, never arguments, logs or saved request files."""
    if stop_event and stop_event.is_set():
        raise RuntimeError("STOPPED_BY_OPERATOR")
    from belive.settings import load_settings
    settings = settings or load_settings()
    root = Path(__file__).resolve().parent
    home = Path(home or root.parent / "data/hermes_memory/support").resolve()
    scope=_scope.get()
    if scope:
        import hashlib
        home=home/'conversations'/hashlib.sha256(scope.encode()).hexdigest()[:24]
    base = (settings.ollama_base_url.rstrip("/") + "/v1"
            if settings.llm_provider == "ollama" else "https://openrouter.ai/api/v1" if settings.llm_provider=='openrouter' else "https://api.openai.com/v1")
    key = settings.ollama_api_key if settings.llm_provider == "ollama" else settings.llm_api_key
    request = dict(messages=messages, tools=tools or [], max_steps=max_steps,
                   examples=examples or [], mode=mode, model=settings.llm_model,
                   base_url=base, api_key=key or "local-ollama", response_schema=response_schema,
                   max_tokens=max(128,min(2500,int(max_output_tokens))))
    env = dict(os.environ, HERMES_HOME=str(home), PYTHONIOENCODING="utf-8",HERMES_DISABLE_TELEMETRY='1')
    request['runtime_version']=runtime_info().get('version','installed Hermes');request['runtime_commit']=runtime_info().get('commit','')
    started=time.monotonic()
    with _runtime_lock:
        queue_ms=round((time.monotonic()-started)*1000)
        python=runtime_python();cache_key=_worker_key(home,python,request)
        for old_key,old in list(_workers.items()):
            if old.process.poll() is not None or time.monotonic()-old.used>300 or (old_key[0]==str(home) and old_key!=cache_key):
                _workers.pop(old_key).close()
        worker=_workers.pop(cache_key,None) if keep_warm else None
        reused=worker is not None
        if worker is None:worker=_NativeWorker(python,root/'hermes_worker.py',root.parent,env)
        process=worker.process;events=worker.events;success=False
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + max(120, max_steps * 90)
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
                    event.update(elapsed_ms=round((time.monotonic()-started)*1000),queue_ms=queue_ms,reused_worker=reused)
                    if event.get('engine')!='hermes-native' or event.get('agent_class')!='run_agent.AIAgent':raise RuntimeError('HERMES_EXECUTION_UNVERIFIED')
                    if observer:observer({k:event.get(k) for k in ('engine','agent_class','version','commit','api_calls','executed_tools','memory_entries','native_memory_loaded','elapsed_ms','queue_ms','reused_worker')}|{'role':role,'mode':mode,'provider':settings.llm_provider,'model':settings.llm_model,'scope_hash':__import__('hashlib').sha256(scope.encode()).hexdigest()[:24] if scope else ''})
                    success=True
                    return event
                elif event["type"] == "error":
                    code=event['code']
                    if event.get('missing_module'):code+=':'+event['missing_module']
                    raise RuntimeError(code)
            raise RuntimeError("HERMES_TIMEOUT")
        finally:
            if keep_warm and success and process.poll() is None:
                worker.used=time.monotonic();_workers[cache_key]=worker
                while len(_workers)>4:_workers.popitem(last=False)[1].close()
            else:worker.close()


def memory_snapshot(home=None):
    path = Path(home or Path(__file__).resolve().parents[1] / "data/hermes_memory/support") / "memories/MEMORY.md"
    return path.read_text(encoding="utf-8") if path.is_file() else "No approved examples have been loaded yet."
