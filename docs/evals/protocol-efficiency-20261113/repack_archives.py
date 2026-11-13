#!/usr/bin/env python3
"""Remove generated caches/scratch from archives; preserve originals and bytes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

CACHES={'.git','__pycache__','.pytest_cache','.hypothesis','.mypy_cache','.ruff_cache'}


def omit(name):
    parts=Path(name).parts
    if CACHES.intersection(parts):return True
    generated='independent-acceptance' in parts or ('holdout-private' in parts and
              ('proofs' in parts or 'revisions' in parts))
    return generated and bool({'hypothesis','pytest-tmp','tmp'}.intersection(parts))


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def inventory(archive):
    records={}
    with tarfile.open(archive,'r:gz') as source:
        for m in source:
            if omit(m.name):continue
            data=source.extractfile(m).read() if m.isfile() else None
            records[m.name]=dict(type=m.type.decode(),mode=m.mode,size=m.size,link=m.linkname,
                sha256=hashlib.sha256(data).hexdigest() if data is not None else None)
    return records


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archives',required=True,type=Path)
    p.add_argument('--preserve',required=True,type=Path);p.add_argument('--record',required=True,type=Path)
    a=p.parse_args();assert not a.preserve.exists(),'Never overwrite original archives'
    a.preserve.mkdir(parents=True);records=[]
    for path in sorted(a.archives.glob('*.tar.gz')):
        before=sha(path);expected=inventory(path);original=a.preserve/path.name
        path.rename(original);omitted=[]
        with tarfile.open(original,'r:gz') as source,tarfile.open(path,'w:gz') as target:
            for m in source:
                if omit(m.name):
                    omitted.append(dict(name=m.name,size=m.size));continue
                data=source.extractfile(m).read() if m.isfile() else None
                target.addfile(m,io.BytesIO(data) if data is not None else None)
        actual=inventory(path)
        assert actual==expected,'Retained source/receipt/input/log bytes or modes changed'
        record=dict(archive=path.name,original_local_path=str(original),original_sha256=before,
            final_sha256=sha(path),original_bytes=original.stat().st_size,final_bytes=path.stat().st_size,
            retained_members=len(actual),retained_inventory_sha256=hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest(),
            retained_source_receipts_inputs_logs_unchanged=True,omitted_generated_members=omitted)
        records.append(record)
        print(json.dumps({k:record[k] for k in ['archive','original_bytes','final_bytes','retained_members']}),flush=True)
    a.record.write_text(json.dumps(dict(kind='Archive packaging only; original evaluation eligibility/timing/source/graders unchanged',
        originals_preserved=True,original_software_caches_preserved=True,records=records),indent=2)+'\n')
