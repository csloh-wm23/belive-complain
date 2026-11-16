"""Start or verify the Windows Ollama endpoint used by the BeLive demo."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen

HOST = "127.0.0.1:11435"
MODEL = "qwen3.5:4b"


def installed_models():
    with urlopen(f"http://{HOST}/api/tags", timeout=2) as response:
        return {item["name"] for item in json.load(response)["models"]}


def main():
    try:
        models = installed_models()
    except URLError:
        exe = shutil.which("ollama")
        if not exe:
            exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
            if not exe.is_file():
                raise SystemExit("Install Ollama for Windows first.")
        env = dict(os.environ, OLLAMA_HOST=HOST, OLLAMA_VULKAN="1", OLLAMA_CONTEXT_LENGTH="8192")
        subprocess.Popen([str(exe), "serve"], env=env,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(15):
            time.sleep(1)
            try:
                models = installed_models()
                break
            except URLError:
                continue
        else:
            raise SystemExit(f"Ollama did not start on {HOST}.")
    if MODEL not in models:
        raise SystemExit("Run ollama pull qwen3.5:4b to download the demo model.")
    print(f"{MODEL} is available at http://{HOST}. Start BeLive and run its AI connection check.")


if __name__ == "__main__":
    main()
