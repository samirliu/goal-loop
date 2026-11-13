"""Posthoc explicit protocol reads, separated from mixed-command mentions.

The frozen verifier's coarse lookup heuristic also matches `cat work-plan &&
bash goal_ctl context`. Preserve that original number; use this calibrated
explicit-read measure in the final table. It never changes qualification.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import shlex


def commands(code):
    # Host exec inputs use JSON double-quoted shell literals. Variable-bound
    # actions remain explicit diagnostics for manual review, not zero reads.
    pattern=r'(?:\bcmd|"cmd")\s*:\s*("(?:[^"\\]|\\.)*")'
    return [json.loads(m.group(1)) for m in re.finditer(pattern,code)]


def reads(command):
    tokens=[];heredoc=None
    for line in command.splitlines():
        if heredoc:
            if line.strip()==heredoc:heredoc=None
            continue
        lexer=shlex.shlex(line,posix=True,punctuation_chars=';&|')
        lexer.whitespace_split=True
        tokens.extend(list(lexer));tokens.append(';')
        marker=re.search(r'<<-?\s*[\'\"]?(\w+)',line)
        if marker:heredoc=marker.group(1)
    result=[]
    for index,token in enumerate(tokens):
        if token not in ('cat','head','tail','sed','rg','grep'):
            continue
        args=[]
        for arg in tokens[index+1:]:
            if arg in (';','&&','||','|','&'):
                break
            args.append(arg)
        paths=[arg for arg in args if arg.endswith('SKILL.md') or '/references/' in arg or '/scripts/goal_' in arg]
        result.extend(paths)
    if '--help' in tokens and any('/scripts/goal_' in t for t in tokens):
        result.append('--help')
    return sorted(set(result))


def measure(root):
    calibration=[('cat .goal/work-plan.md && bash /frozen/scripts/goal_ctl.sh context',False),
                 ('cat /frozen/SKILL.md && cat TASK.md',True),
                 ('bash /frozen/scripts/goal_ctl.sh context --auto',False),
                 ('sed -n 1,20p /frozen/scripts/goal_context.py',True),
                 ("python3 - <<'PY'\nprint(\"don't parse shell in Python\")\nPY",False)]
    if any(bool(reads(command))!=expected for command,expected in calibration):
        raise RuntimeError('explicit-read calibration failed')
    rows=[]
    for planned in json.loads((root/'protocol.json').read_text())['order']:
        folder=root/str(planned['position']);manifest=json.loads((folder/'manifest.json').read_text());calls=[]
        native_start=first_tool=final=None
        visible_bytes=0
        for line in (folder/'events.jsonl').read_text().splitlines():
            event=json.loads(line);p=event['payload'];kind=p.get('type')
            if event['type']=='session_meta':native_start=p['timestamp']
            if kind in ('custom_tool_call_output','function_call_output'):
                visible_bytes+=len(str(p.get('output','')).encode())
            if kind=='message' and p.get('phase')=='final_answer':final=event['timestamp']
            if kind not in ('custom_tool_call','function_call'):continue
            first_tool=first_tool or event['timestamp']
            code=p.get('input',p.get('arguments',''));literal=commands(code)
            sources=sorted({path for command in literal for path in reads(command)})
            calls.append(dict(timestamp=event['timestamp'],explicit_protocol_sources=sources,
                              variable_commands=len(re.findall(r'\bcmd\s*:\s*(?!")\w',code))))
        epoch=lambda value:datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
        rows.append(dict(position=planned['position'],variant=planned['variant'],case=planned['case'],
            explicit_protocol_read_calls=sum(bool(c['explicit_protocol_sources']) for c in calls),calls=calls,
            host_tool_calls=len(calls),model_visible_tool_result_bytes=visible_bytes,
            first_tool_since_position_entry_seconds=epoch(first_tool)-manifest['epoch'] if first_tool else None,
            observed_native_worker_window_seconds=epoch(final)-epoch(native_start) if native_start and final else None,
            final_report_since_entry_seconds=epoch(final)-manifest['epoch'] if final else None))
    return dict(kind='posthoc diagnostics; no effect on eligibility or original costs',calibration_passed=True,
                definition='outer host call with an explicit protocol file read/search or goal CLI --help; variable action commands listed for manual review',
                rows=rows,tokens=None,money=None,server_compute=None)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=measure(a.root);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([dict(position=r['position'],reads=r['explicit_protocol_read_calls']) for r in result['rows']]))
