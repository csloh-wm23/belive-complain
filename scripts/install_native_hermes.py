"""Install the official pinned Hermes Agent core in an isolated project-local environment."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VERSION='v0.23.3'
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    from belive.hermes_native import runtime_python
    if args.check:
        runtime_python();return
    base=ROOT/'data'/'native_hermes';source=base/'source';base.mkdir(parents=True,exist_ok=True)
    git=shutil.which('git')
    if not git:raise ValueError('Install Git for Windows, then run Install Hermes Agent again.')
    env={**os.environ,'GCM_INTERACTIVE':'Never','GIT_TERMINAL_PROMPT':'0','UV_PYTHON_INSTALL_DIR':str(base/'python'),'UV_CACHE_DIR':str(base/'cache'),'UV_PROJECT_ENVIRONMENT':str(source/'.venv')}
    if source.exists():
        if not (source/'.git').is_dir():raise ValueError('Existing runtime source folder preserved; choose a clean installation folder.')
        tag=subprocess.check_output([git,'describe','--tags','--exact-match'],cwd=source,env=env,text=True).strip()
        if tag!=VERSION or subprocess.check_output([git,'status','--porcelain'],cwd=source,env=env).strip():raise ValueError('Existing Hermes source was modified or is another version. It was not overwritten.')
    else:subprocess.run([git,'clone','--depth','1','--branch',VERSION,'https://github.com/NousResearch/hermes-agent.git',str(source)],env=env,check=True)
    bootstrap=base/'bootstrap';bootstrap.mkdir(exist_ok=True)
    sys.path.insert(0,str(bootstrap))
    try:import uv
    except ImportError:
        subprocess.run([sys.executable,'-m','pip','install','--target',str(bootstrap),'uv==0.13.5'],env=env,check=True)
        import uv
    binary=uv.find_uv_bin()
    subprocess.run([binary,'sync','--frozen','--no-dev','--python','3.14'],cwd=source,env=env,check=True)
    python=source/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    probe_env={**env,'HERMES_HOME':str(base/'probe')}
    subprocess.run([str(python),'-c','from run_agent import AIAgent; from tools.memory_tool import MemoryStore; print("Official Hermes AIAgent and MemoryStore imports passed")'],cwd=source,env=probe_env,check=True)
    commit=subprocess.check_output([git,'rev-parse','HEAD'],cwd=source,env=env,text=True).strip()
    (ROOT/'data'/'hermes-runtime.json').write_text(json.dumps({'python':str(python),'source':str(source),'version':VERSION,'commit':commit},indent=2),encoding='utf-8')
    print('Native Hermes Agent installed. Restart BeLive, then run the native engine connection check.')

if __name__=='__main__':
    try:main()
    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)
