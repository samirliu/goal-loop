#!/usr/bin/env python3
"""Replay frozen business acceptance offline. Never rescues original eligibility."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()


def unpack(archive,target):
    # Only the controlled source/evidence archive is read; forbid traversal or
    # escaping links, retain original modes, ignore stored ownership identities.
    target=target.resolve()
    with tarfile.open(archive,'r:gz') as t:
        def check(member,destination):
            # Historical pytest scratch can contain absolute test symlinks.
            # Keep it byte-for-byte in the archive; only operational frozen
            # inputs are needed to run a NEW independent business check.
            parts=Path(member.name).parts
            if archive.name=='inputs.tar.gz':
                if parts[:3]==('study','holdout-private','revisions'):return None
                if len(parts)>4 and parts[:3]==('study','holdout-private','cases') and parts[4] in ('proofs','evidence'):return None
            path=(target/member.name).resolve()
            if not path.is_relative_to(target):raise ValueError('archive path escapes replay directory')
            if member.isdev() or member.isfifo():raise ValueError('non-file archive entry')
            if member.issym():
                if not (path.parent/member.linkname).resolve().is_relative_to(target):raise ValueError('archive symlink escapes replay directory')
            if member.islnk() and not (target/member.linkname).resolve().is_relative_to(target):raise ValueError('archive hardlink escapes replay directory')
            member.uid=member.gid=None;member.uname=member.gname=None
            return member
        t.extractall(target,filter=check)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archives',type=Path,default=Path(__file__).with_name('archives'))
    p.add_argument('--position',type=int,required=True)
    p.add_argument('--dest',type=Path,required=True,help='New directory; all replay work stays here')
    p.add_argument('--python312',type=Path,required=True,help='Existing CPython3.12 interpreter')
    p.add_argument('--wheels',type=Path,required=True,help='Original preserved offline bundle or an independently fetched exact-hash bundle')
    a=p.parse_args()
    assert 1<=a.position<=18 and not a.dest.exists()
    version=subprocess.check_output([str(a.python312),'-B','-c','import sys;print("%d.%d"%sys.version_info[:2])'],text=True).strip()
    assert version=='3.12','Replay requires the recorded CPython3.12 family'
    wheel_record=json.loads((a.archives/'dependency-wheels.json').read_text())
    for name,entry in wheel_record['wheels'].items():
        assert digest(a.wheels/name)==entry['sha256'],'dependency wheel hash mismatch: '+name
    checksums=Path(__file__).with_name('SHA256SUMS')
    if checksums.exists():
        expected={line.split('  ',1)[1]:line.split('  ',1)[0] for line in checksums.read_text().splitlines() if '  ' in line}
        for name in ['inputs.tar.gz',f'position-{a.position:03d}.tar.gz']:
            key='archives/'+name
            assert key in expected and digest(a.archives/name)==expected[key],'archive hash differs: '+name
    started=time.monotonic();a.dest.mkdir(parents=True)
    unpack(a.archives/'inputs.tar.gz',a.dest)
    unpack(a.archives/f'position-{a.position:03d}.tar.gz',a.dest)
    private=a.dest/'study/holdout-private';runtime=private/'runtime'
    subprocess.run([str(a.python312),'-m','venv',str(runtime)],check=True)
    python=runtime/'bin/python'
    subprocess.run([str(python),'-m','pip','install','--no-index','--find-links',str(a.wheels),'-r',str(private/'requirements.lock')],check=True)
    original=json.loads((a.dest/'position/capture/report.json').read_text())
    manifest=json.loads((a.dest/'position/manifest.json').read_text())
    independent=next(c for c in manifest['checks'] if c['name']=='independent')
    args=independent['argv'];case=args[args.index('--case')+1]
    command=[str(python),'-B',str(private/'grade.py'),'--case',case,'--project',str(a.dest/'position/work'),
             '--log-dir',str(a.dest/'business-replay')]
    result=subprocess.run(command,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    record=dict(kind='posthoc independent business replay only; no model calls and no original timing/eligibility changes',
        position=a.position,case=case,command=command,returncode=result.returncode,
        elapsed_seconds=time.monotonic()-started,original_qualified=original['qualified'],
        original_elapsed_seconds=original['elapsed_seconds'],
        protocol_receipts='Original native events/audit/Gate are archived. Their historical host deadlines are not reset or requalified by this replay.',
        extraction='Historical curator proof/evidence scratch remains in the archive; it is not extracted or rerun. Frozen operational grader/validator/business files are extracted.',
        dependencies='Exact recorded wheel hashes, freshly installed isolated runtime; current OS/host timing is not the original timing.')
    (a.dest/'replay-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2));raise SystemExit(result.returncode)
