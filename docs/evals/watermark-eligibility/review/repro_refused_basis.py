import sys
sys.dont_write_bytecode=True
sys.path.insert(0,'/Users/m/repo/goal-loop/tests')
from test_incumbent import QualifiedWatermark
q=QualifiedWatermark();q.setUp()
try:
 q.setup_goal();(q.project/'score.txt').write_text('100\n');q.book(100)
 original=(q.state/'goal.md').read_text()
 print('BEFORE','\n'.join(l for l in (q.state/'state.rec').read_text().splitlines() if 'best_score' in l))
 (q.state/'goal.md').write_text(original.replace(' | score |',' | score revised |'))
 print('REFUSED-QUALIFICATION',q.ctl('bind','--operation-id','refused-edit',input='AC-2|PASS|1|test|floor|evidence\n'))
 print('AFTER REFUSAL','\n'.join(l for l in (q.state/'state.rec').read_text().splitlines() if 'best_score' in l))
 (q.state/'goal.md').write_text(original)
 (q.project/'score.txt').write_text('10\n');q.book(10)
 print('AFTER RESTORE','\n'.join(l for l in (q.state/'state.rec').read_text().splitlines() if 'best_score' in l))
 print('GATE',q.gate('--check'))
finally:q.doCleanups()
