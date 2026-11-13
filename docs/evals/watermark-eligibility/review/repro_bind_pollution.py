import sys
sys.dont_write_bytecode = True
sys.path.insert(0, '/Users/m/repo/goal-loop/tests')
from test_incumbent import QualifiedWatermark
q=QualifiedWatermark();q.setUp()
try:
 (q.state/'goal.md').write_text('# Goal\n\nobjective: maximize AC-1\nhorizon-waived: focused ledger mutation check\n\n## Acceptance criteria\n\n- AC-1 | score | check: `cat score.txt` | expected: maximize\n- AC-2 | floor | check: `if test -e .goal/evidence/trip; then echo contamination >> .goal/loop-log.md; fi; grep -qx ready artifact.txt` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
 (q.project/'artifact.txt').write_text('ready\n');(q.project/'score.txt').write_text('10\n')
 q.ctl('stamp','--auto');q.book(10)
 before=(q.state/'loop-log.md').read_bytes()
 (q.state/'evidence/trip').write_text('enable broken instrument\n')
 print('BIND',q.ctl('bind','--operation-id','side-effect-check',input='AC-2|PASS|1|test|floor|evidence\n',expected=4))
 print('PENDING', (q.state/'store/pending').exists())
 print('RECOVER', q.ctl('recover'))
 print('LOG_RESTORED', before==(q.state/'loop-log.md').read_bytes())
 (q.state/'evidence/trip').unlink()
 print('GATE',q.gate('--check'))
finally:q.doCleanups()
