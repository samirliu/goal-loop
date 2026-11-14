#!/usr/bin/env python3
"""Bind visual acceptance to a calibrated judged AC and its actual view evidence.

This checks declared coverage and evidence integrity, not image semantics.
The cold reviewer still has to judge fidelity against the original request.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
VISUAL = re.compile(r'(?:逼真|写实|栩栩如生|美观|精美).{0,24}(?:场景|模型|建筑|教堂|网页|画面|效果)|'
                    r'(?:场景|模型|建筑|网页|画面).{0,16}(?:逼真|写实|美观|精美)|'
                    r'(?:构建|创建|制作|交付)[^\n]{0,120}3\s*d\s*场景|'
                    r'photo[- ]?real(?:istic|ism)?\s+(?:3d|reconstruction|render|scene|model|building)|'
                    r'visually (?:faithful|accurate|polished)|'
                    r'(?:realistic|faithful) (?:3d|reconstruction|render|scene)', re.I)
DECLARATION = re.compile(r'quality: visual (AC-[0-9]+) views=([^\s|]+)')
VIEW = re.compile(r'[\w.-]{1,64}')
SHA = re.compile(r'[0-9a-f]{64}')


class QualityError(ValueError):
    pass


def require(value, message):
    if not value:
        raise QualityError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_file(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute()
            and not any(p in ('', '.', '..') for p in name.split('/')) and '\\' not in name,
            'quality-evidence-path: use a project-relative file')
    path = root
    for part in name.split('/'):
        path = path/part
        require(not path.is_symlink(), 'quality-evidence-path: symlink refused')
    require(stat.S_ISREG(path.stat().st_mode), 'quality-evidence-path: regular file required')
    return path.read_bytes()


def requests(root):
    """Use original host-observed text when available; never invent missing text."""
    folder = root/'.goal/evidence/host'
    require(not folder.is_symlink(), 'quality-request: symlink host directory')
    runner = root/'.goal/runner.json'
    origin = json.loads(runner.read_bytes()).get('origin', {}) if runner.exists() else {}
    rows, seen = [], set()
    for path in [*sorted(folder.glob('prompt-*.json')), *sorted(folder.glob('session-*.json'))]:
        envelope = json.loads(read_file(root, path.relative_to(root).as_posix()))
        require(set(envelope) == {'payload', 'sha256'} and digest(encode(envelope['payload'])) == envelope['sha256'],
                'quality-request: corrupt host receipt')
        row = envelope['payload']
        session = row.get('origin', {}).get('session', row.get('session'))
        if row.get('project') != str(root) or (origin.get('session') and session != origin['session']):
            continue
        text = row.get('request')
        if text is not None:
            require(isinstance(text, str) and text.strip(), 'quality-request: invalid original request')
            identity = digest(text.encode())
            if identity not in seen:
                rows.append(dict(source=path.relative_to(root).as_posix(), text=text, sha256=identity))
                seen.add(identity)
    return rows


def inspect(project):
    root = Path(project).resolve(strict=True)
    goal = root/'.goal/goal.md'
    text = goal.read_text().replace('\r', '') if goal.exists() else ''
    # Only the brief, not commands, comments, calibration descriptions or
    # mentions in the rest of the contract, supplies automatic intent hints.
    clean = re.sub(r'<!--[\s\S]*?-->', '', text)
    objectives = re.findall(r'^## (?:Objective|Request)\s*\n([\s\S]*?)(?=^## |\Z)', clean, re.M)
    original = requests(root)
    signals = [dict(source='.goal/goal.md#Objective', text=VISUAL.search(part)[0]) for part in objectives if VISUAL.search(part)]
    signals += [dict(source=row['source'], text=VISUAL.search(row['text'])[0]) for row in original if VISUAL.search(row['text'])]
    lines = re.findall(r'^quality:.*$', clean, re.M)
    result = dict(required=bool(signals or lines), signals=signals, original_requests=original, declaration=None)
    if lines:
        require(len(lines) == 1, 'quality-contract: declare one visual quality AC')
        match = DECLARATION.fullmatch(lines[0])
        require(match is not None, 'quality-contract: use quality: visual AC-N views=view1,view2')
        views = match[2].split(',')
        require(views and len(set(views)) == len(views) and all(VIEW.fullmatch(v) for v in views),
                'quality-contract: unique named views required')
        result['declaration'] = dict(ac=match[1], views=views)
    return result, text


def contract(project):
    root = Path(project).resolve(strict=True)
    info, text = inspect(root)
    if not info['required']:
        return info, b''
    spec = info['declaration']
    require(spec is not None, 'quality-contract-required: visual intent needs quality: visual AC-N views=... and a calibrated judged AC')
    rows = re.findall(r'^- '+re.escape(spec['ac'])+r'\s*\|.*$', text, re.M)
    require(len(rows) == 1, 'quality-contract: quality AC must exist exactly once')
    row = re.sub(r'`[^`]*`', '', rows[0])
    require(re.search(r'\bexpected:\s*judged\s*$', row), 'quality-contract: quality AC must be judged, not a proxy exit code')
    anchors = {}
    for kind in ('good', 'bad'):
        match = re.search(r'\bcalib:[^|]*\b'+kind+r'\s*=\s*([^ |]+)', row)
        require(match is not None, 'quality-contract: quality AC needs good and bad calibration anchors')
        anchors[kind] = dict(path=match[1], sha256=digest(read_file(root, match[1])))
    require(anchors['good']['sha256'] != anchors['bad']['sha256'], 'quality-contract: good and bad anchors have identical bytes')
    # Approval changes at stamp; the original objective, declaration and
    # host-observed request must not change the qualification after stamp.
    clean = re.sub(r'<!--[\s\S]*?-->', '', text)
    objectives = re.findall(r'^## (?:Objective|Request)\s*\n([\s\S]*?)(?=^## |\Z)', clean, re.M)
    frozen = dict(declaration=spec, objectives=objectives, original_requests=info['original_requests'], anchors=anchors)
    return info, encode(frozen)


def review(project, evidence):
    root = Path(project).resolve(strict=True)
    info, _ = contract(root)
    if not info['required']:
        return
    value = json.loads(read_file(root, evidence))
    validate_review(root, info['declaration']['views'], value)


def validate_review(root, views, value):
    """Additional observations are retained, but cannot override core findings."""
    require(isinstance(value, dict) and {'version', 'views', 'findings', 'summary'} <= set(value)
            and type(value['version']) is int and value['version'] == 1, 'quality-review: invalid review record')
    require(isinstance(value['findings'], list) and all(isinstance(x, str) and x.strip() for x in value['findings']),
            'quality-review: findings must list unresolved goal-related defects')
    require(not value['findings'], 'quality-open-findings: '+str(value['findings']))
    require(value.get('verdict', 'PASS') == 'PASS' and value.get('completion_eligible', True) is True,
            'quality-review-conflict: review does not grant a quality PASS')
    require(isinstance(value['summary'], str) and value['summary'].strip(), 'quality-review: missing observed comparison')
    require(isinstance(value['views'], dict) and set(value['views']) == set(views),
            'quality-review: cover every declared view exactly')
    artifacts, images = set(), set()
    for name, item in value['views'].items():
        require(isinstance(item, dict) and {'artifact', 'sha256'} <= set(item)
                and isinstance(item['sha256'], str) and SHA.fullmatch(item['sha256']), 'quality-review: invalid view evidence '+name)
        require(item.get('verdict', 'PASS') == 'PASS', 'quality-review-conflict: declared view did not pass: '+name)
        data = read_file(root, item['artifact'])
        require(data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')) or
                (data.startswith(b'RIFF') and data[8:12] == b'WEBP'), 'quality-review: actual image required for '+name)
        require(digest(data) == item['sha256'], 'quality-review: changed view evidence '+name)
        require(item['artifact'] not in artifacts and item['sha256'] not in images,
                'quality-review: one image cannot stand in for different views')
        artifacts.add(item['artifact'])
        images.add(item['sha256'])


def context(project):
    try:
        info, frozen = contract(project)
        info['error'] = None
        info['frozen_sha256'] = digest(frozen) if frozen else None
    except QualityError as exc:
        try:
            info, _ = inspect(project)
        except QualityError:
            info = dict(required=True, signals=[], original_requests=[], declaration=None)
        info.update(error=str(exc), frozen_sha256=None)
    if info['required']:
        info['guidance'] = 'Read references/packs/visual.md. Judge the original request against actual views and references; pixel statistics are smoke checks. Bind the cold review JSON as the quality AC artifact.'
        info['review_template'] = dict(version=1, views={v:dict(artifact=None, sha256=None) for v in
            (info['declaration'] or {}).get('views', [])}, findings=None, summary=None)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'review', 'context'))
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--evidence')
    args = parser.parse_args()
    if args.command == 'freeze':
        _, frozen = contract(args.project)
        if frozen:
            print('quality='+digest(frozen)+';', end='')
    elif args.command == 'review':
        review(args.project, args.evidence)
    else:
        print(json.dumps(context(args.project), ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('QUALITY: ERROR '+str(exc), file=sys.stderr)
        sys.exit(2)
