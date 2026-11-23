"""Export/check/restore the encrypted, code-versioned approved-knowledge package."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['export','check','restore','runtime','install-hooks']);p.add_argument('--database',type=Path);args=p.parse_args()
    from belive import repository_memory as rm
    if args.action=='install-hooks':
        old=subprocess.run(['git','config','--local','--get','core.hooksPath'],cwd=ROOT,capture_output=True,text=True)
        if old.stdout.strip() not in {'','.githooks'}:print('Existing Git hooks preserved. Use Push BeLive with memory for knowledge backups.');return
        subprocess.run(['git','config','--local','core.hooksPath','.githooks'],cwd=ROOT,check=True);return
    if args.action=='runtime':
        try:rm.crypto()
        except ValueError:subprocess.run([sys.executable,'-m','pip','install','--target',str(ROOT/'output'/'knowledge-runtime'),'cryptography>=44'],check=True)
        return
    from belive.service import Service
    from belive.workspace import selected_database
    s=Service(args.database or selected_database())
    if args.action=='export':print(json.dumps(rm.export(s)))
    elif args.action=='restore':print(json.dumps(rm.restore(s)))
    else:
        rm.configure(s)
        if not rm.ARCHIVE.is_file():raise ValueError('Knowledge backup is missing. Run python scripts/knowledge_backup.py export, then commit it before pushing.')
        archived=rm.unpack(json.loads(rm.ARCHIVE.read_text(encoding='utf-8')),rm.read_key(s))
        if archived!=rm.payload(s):raise ValueError('Knowledge changed since the last backup. Run python scripts/knowledge_backup.py export and commit knowledge/team-memory.enc.json before pushing.')
        if subprocess.run(['git','diff','--quiet','HEAD','--','knowledge/team-memory.enc.json'],cwd=ROOT).returncode or subprocess.run(['git','ls-files','--error-unmatch','knowledge/team-memory.enc.json'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:raise ValueError('Commit the current encrypted knowledge backup before pushing.')
        print('Approved SOP, learning and source documents are included in the pushed commit.')

if __name__=='__main__':
    try:main()
    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)
