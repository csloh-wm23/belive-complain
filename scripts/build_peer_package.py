"""Build a source-only peer package; company files and credentials never enter the ZIP."""
import hashlib,json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.knowledge_backup import private_path

def main():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    target=ROOT/'artifacts'/'belive-shared-memory-client.zip';target.parent.mkdir(exist_ok=True);manifest={}
    allowed={'.py','.js','.html','.css','.svg','.json','.md','.txt','.bat','.toml','.yml','.yaml','.example'}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(names)):
            if not name or private_path(name) or name.startswith(('data/','output/','artifacts/','backups/','recovered/','.git/')) or 'memory-pairing' in name:continue
            p=ROOT/name
            if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(ROOT):continue
            if name.startswith('.env') and name!='.env.example':continue
            if p.suffix.lower() not in allowed and name not in {'.gitignore','LICENSE'} and not name.startswith('.githooks/'):continue
            data=p.read_bytes();archive.writestr(name,data);manifest[name]=hashlib.sha256(data).hexdigest()
        archive.writestr('SHARED_MEMORY_PACKAGE.json',json.dumps({'protocol':1,'files':manifest},indent=2))
    print(json.dumps({'package':str(target),'source_files':len(manifest),'contains_plaintext_company_data':False,'contains_encrypted_knowledge_backup':'knowledge/team-memory.enc.json' in manifest,'contains_credentials':False}))
if __name__=='__main__':main()
