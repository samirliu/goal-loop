#!/usr/bin/env python3
"""Archive original receipts and source snapshots; never requalify a position."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile

IGNORED={'.git','__pycache__','.pytest_cache','.hypothesis','.mypy_cache','.ruff_cache'}
REPO=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('capture',REPO/'devtools/native_eval_capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)


def add(archive,path,name):
    path=Path(path)
    if path.name in IGNORED:return
    generated='independent-acceptance' in path.parts or ('holdout-private' in path.parts and
              ('proofs' in path.parts or 'revisions' in path.parts))
    if generated and path.name in {'hypothesis','pytest-tmp','tmp'}:return
    archive.add(path,arcname=str(name),recursive=False)
    if path.is_dir() and not path.is_symlink():
        for child in sorted(path.iterdir()):add(archive,child,Path(name)/child.name)


def position(base,out,n):
    root=base/'positions'/f'{n:03d}';report=root/'capture/report.json'
    if not report.exists():return None
    original=json.loads(report.read_text());target=out/f'position-{n:03d}.tar.gz'
    if target.exists():return dict(position=n,archive=target.name,sha256=capture.sha(target),already_archived=True)
    redacted=[]
    def unknown(value,path):
        if isinstance(value,str) and value in ('[REDACTED]',capture.UNKNOWN):redacted.append(path)
        elif isinstance(value,dict):
            for key,child in value.items():unknown(child,path+'/'+key)
    for name,expected in original.get('artifacts',{}).items():
        assert capture.sanitize(capture.fingerprint(Path(name)))==expected, 'original non-redacted artifact metadata changed before export: '+name
        unknown(expected,name)
    with tarfile.open(target,'w:gz') as archive:
        for name in ['prompt.md','manifest.json','capture','work','independent-acceptance']:
            if (root/name).exists():add(archive,root/name,Path('position')/name)
    return dict(position=n,archive=target.name,sha256=capture.sha(target),
        original_report_sha256=capture.sha(report),qualified_original=original['qualified'],
        original_nonredacted_artifact_metadata_verified_before_export=True,
        redacted_original_metadata_paths_unknown=redacted,
        excluded_caches='Caches and generated pytest scratch are preserved at original local paths, omitted from committed archives. Original receipts, code, trusted fixtures and logs remain included.')


def inputs(base,out):
    target=out/'inputs.tar.gz'
    if target.exists():return dict(archive=target.name,sha256=capture.sha(target),already_archived=True)
    private=base/'holdout-private'
    with tarfile.open(target,'w:gz') as archive:
        for name in ['initial','sources','runtime-public-identity.json','holdout-readiness.json','global-staging.json']:
            add(archive,base/name,Path('study')/name)
        for name in ['grade.py','stage_case.py','corpus.json','CONTROLLER.md','requirements.lock',
                     'runtime-identity.json','runtime-files.json','research','revisions']:
            add(archive,private/name,Path('study/holdout-private')/name)
        for case in sorted((private/'cases').iterdir()):
            add(archive,case,Path('study/holdout-private/cases')/case.name)
    wheels={p.name:dict(sha256=capture.sha(p),bytes=p.stat().st_size) for p in sorted((private/'wheels').glob('*.whl'))}
    (out/'dependency-wheels.json').write_text(json.dumps(dict(
        wheels=wheels,original_local_bundle=str(private/'wheels'),
        original_public_runtime=str(base/'runtime-public'),original_private_runtime=str(private/'runtime'),
        policy='No installed environments or caches committed. Rebuild isolated CPython3.12 environment from requirements.lock; verify the exact wheel hashes. Original local offline bundle is preserved.'),indent=2)+'\n')
    return dict(archive=target.name,sha256=capture.sha(target),
        scope='Frozen business/product/grader inputs and all curator validation source/log history; excludes installed runtimes, wheels, caches and generated pytest scratch. Dependencies have separate pinned identity/hash manifest.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--position',type=int);p.add_argument('--inputs',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    records=[]
    if a.inputs:records.append(inputs(a.base,a.out))
    for n in ([a.position] if a.position else range(1,19)):
        r=position(a.base,a.out,n)
        if r:records.append(r)
    print(json.dumps(records,indent=2))
