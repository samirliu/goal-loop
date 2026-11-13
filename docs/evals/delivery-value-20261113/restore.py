#!/usr/bin/env python3
"""Restore payload plus exact git-backed source snapshots, without model calls."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
    here=Path(__file__).resolve().parent;repo=here.parents[2]
    identity=json.loads((here/'intervention.json').read_text())
    archived=json.loads((here/'archive.json').read_text())
    if hashlib.sha256((here/'native-evidence.tar.xz').read_bytes()).hexdigest()!=archived['sha256']:
        raise RuntimeError('archive digest differs')
    a.output.mkdir(parents=True,exist_ok=False)
    with tarfile.open(here/'native-evidence.tar.xz') as archive:
        archive.extractall(a.output,filter='data')
    for name,value in json.loads((a.output/'PAYLOAD-MANIFEST.json').read_text()).items():
        path=a.output/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=value['sha256'] or path.stat().st_mode&0o777!=value['mode']:
            raise RuntimeError('payload bytes/mode differ: '+name)
    # Existing repository objects supply the unchanged historical evidence;
    # the payload contains only new raw trials and explicit source overlays.
    source=subprocess.run(['git','archive',identity['base_commit']],cwd=repo,capture_output=True,check=True).stdout
    for name in ('native','validation'):
        trial=a.output/name;protocol=json.loads((trial/'protocol.json').read_text())
        for variant in protocol['source']:
            target=trial/'sources'/variant;target.mkdir(parents=True)
            with tarfile.open(fileobj=io.BytesIO(source)) as archive:
                archive.extractall(target,filter='data')
            overlay=a.output/'overlays'/name/variant
            if overlay.exists():
                for path in overlay.rglob('*'):
                    if path.is_file():
                        destination=target/path.relative_to(overlay);destination.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(path,destination)
        spec=importlib.util.spec_from_file_location('restored_delivery',trial/'frozen/evaluate_delivery.py')
        driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
        for variant,expected in protocol['source'].items():
            if driver.tree(trial/'sources'/variant)!=expected:
                raise RuntimeError('restored source identity differs: '+name+'/'+variant)
        print(name+': restored source bytes/modes match the frozen protocol')


if __name__=='__main__':main()
