"""Export/check/restore private encrypted approved knowledge; never publish it with code."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def private_path(name):
    path=Path(name.replace('\\','/'));parts=tuple(x.lower() for x in path.parts);base=parts[-1] if parts else ''
    private_roots={'knowledge','data','artifacts','backups','recovered','shared_memory','company_documents','whatsapp_media'}
    return bool(parts and (parts[0] in private_roots
        or base=='team-memory.enc.json' or base.endswith(('.key','.knowledge-key','.db','.sqlite','.sqlite3'))
        or any(x in base for x in ('.db-wal','.db-shm','.sqlite-wal','.sqlite-shm','.sqlite3-wal','.sqlite3-shm','memory-pairing'))
        or (base.startswith('.env') and base!='.env.example')))


def check(service,root=None):
    from belive import repository_memory as rm
    rm.configure(service)
    if not rm.ARCHIVE.is_file():raise ValueError('Private knowledge backup is missing. Run python scripts/knowledge_backup.py export before pushing.')
    archived=rm.unpack(json.loads(rm.ARCHIVE.read_text(encoding='utf-8')),rm.read_key(service))
    if archived!=rm.payload(service):raise ValueError('Knowledge changed since the last private backup. Run python scripts/knowledge_backup.py export before pushing.')
    try:
        result=subprocess.run(['git','ls-files','--cached','-z'],cwd=root or ROOT,capture_output=True,check=True)
        names=result.stdout.decode('utf-8',errors='surrogateescape').split('\0')
    except (OSError,subprocess.SubprocessError):
        raise ValueError('Git index could not be checked. The code push was stopped to keep private files off GitHub.') from None
    if any(private_path(name) for name in names if name):
        raise ValueError('Private knowledge, keys, credentials or customer-data files are staged/tracked in Git. Remove them from version control while preserving the local files before pushing.')
    return {'private_backup_current':True,'git_index_excludes_private_files':True}


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
        check(s)
        print('Private encrypted knowledge backup is current. Git index excludes private files; only committed code is ready to push.')

if __name__=='__main__':
    try:main()
    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)
