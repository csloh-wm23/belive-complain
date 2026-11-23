"""Import a locally reviewed, page-grounded company PDF manifest into BeLive."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from belive.company_sop import import_reviewed,normalize
from belive.service import Service
from belive.workspace import selected_database

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--database',type=Path);parser.add_argument('--confirmed',action='store_true')
    args=parser.parse_args()
    if not args.confirmed:parser.error('--confirmed is required after reviewing the source and guidance')
    try:from pypdf import PdfReader
    except ImportError:raise SystemExit('Run using the bundled PDF Python runtime, or install pypdf for this import tool. The BeLive server needs no extra package.')
    pages=[normalize(p.extract_text() or '') for p in PdfReader(args.pdf).pages]
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    result=import_reviewed(Service(args.database or selected_database()),args.pdf,pages,manifest['sections'],manifest.get('issues',[]),confirmed=True,actor='User-supplied company reference; support extraction reviewed')
    print(json.dumps(result))
if __name__=='__main__':main()
