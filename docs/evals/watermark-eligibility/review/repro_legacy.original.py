import sys, types
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, '/Users/m/repo/goal-loop/tests')
from test_incumbent import ProjectCase
source = Path(__file__).with_name('legacy-goal-store.py').read_text()
old = types.ModuleType('legacy_goal_store'); exec(compile(source, 'legacy_goal_store', 'exec'), old.__dict__)
for pending in (False, True):
    q = ProjectCase(); q.setUp()
    try:
        (q.state/'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | pass | check: `true` | expected: exit=0\n\napproved: PENDING\n')
        args = ['bind','--operation-id','legacy-bind-once','--project',str(q.project)]
        rows = b'AC-1|PASS|0|old-digest|true|old evidence\n'
        if pending:
            _, operation, intent = old.mutation_retry(q.state,'bind',args,rows)
            old.mutation_journal(q.state,'begin','bind',intent=intent,operation=operation)
            journal = (q.state/'store/pending').read_bytes()
            with (q.state/'verdicts.rec').open('ab') as out: out.write(rows)
            old.mutation_journal(q.state,'finish')
            (q.state/'store/pending').write_bytes(journal)
            print('POINTER-PUBLISHED RECOVER', q.ctl('recover'))
        else:
            old.bind_mutation(str(q.state),args,rows)
        print('MIGRATE',q.ctl('migrate'))
        print('REPLAY',q.ctl('bind','--operation-id','legacy-bind-once',input=rows.decode()))
    finally:
        q.doCleanups()
