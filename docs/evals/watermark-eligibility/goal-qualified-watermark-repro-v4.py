import json,pathlib,subprocess,sys
p=pathlib.Path('/tmp/goal-qualified-watermark-repro-v4-20261111');p.mkdir(exist_ok=False)
scripts=pathlib.Path('/Users/m/repo/goal-loop/scripts');events=[]
def run(cmd,expected=0):
 r=subprocess.run(cmd+['--project',str(p)],capture_output=True,text=True,timeout=20)
 events.append(dict(command=cmd,rc=r.returncode,stdout=r.stdout,stderr=r.stderr))
 if r.returncode!=expected: raise RuntimeError(events[-1])
 return r.stdout.strip()
def ctl(*a,**kw): return run(['bash',str(scripts/'goal_ctl.sh'),*a],**kw)
def store(*a): return run([sys.executable,'-I',str(scripts/'goal_store.py'),'incumbent',*a])
def book(score,claim):
 return ctl('close-iteration','--task','T1','--files','artifact.txt,score.txt','--checks-pass','1','--checks-fail','0','--checks-unverifiable','0','--progress','yes','--exit-signal',claim,'--adversarial','clear','--adversarial-note','read floor result','--no-gate','--strategy','baseline','--score',str(score))
ctl('init')
(p/'.goal/goal.md').write_text('# Goal\n\n## Objective\n\nobjective: maximize AC-1\nhorizon-waived: exact readiness floor for this focused counterexample\n\n## Acceptance criteria\n\n- AC-1 | score | check: `cat score.txt` | expected: maximize\n- AC-2 | floor | check: `grep -qx ready artifact.txt` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
(p/'artifact.txt').write_text('ready\n');(p/'score.txt').write_text('10\n');ctl('stamp','--auto');book(10,'no')
base=store('save','--intermediate','--file','artifact.txt','--file','score.txt')
(p/'artifact.txt').write_text('broken\n');(p/'score.txt').write_text('100\n');book(100,'no')
candidate=store('candidate','--base',base);store('restore','--base',base,'--candidate',candidate);book(10,'yes')
run(['bash',str(scripts/'goal_gate.sh'),'--check'],expected=0)
(p/'events.json').write_text(json.dumps(events,indent=2)+'\n')
print(json.dumps(events[-1]))
