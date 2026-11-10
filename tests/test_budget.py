import os, subprocess, tempfile, time, unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
class Budget(unittest.TestCase):
 def test_executor_nonzero_still_checks_gate(self):
  for code in (1,2,3,4,125):
   with self.subTest(code=code), tempfile.TemporaryDirectory() as d:
    p=Path(d); ctl=R/'scripts/goal_ctl.sh'
    subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
    (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `test -s a.txt` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
    subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
    mock=p/'mock'; mock.write_text('#!/bin/bash\necho artifact > a.txt\nbash "$PROBE_CTL" close-iteration --project . --task T1 --files a.txt --checks-pass 1 --checks-fail 0 --checks-unverifiable 0 --progress yes --exit-signal yes --adversarial clear --adversarial-note reviewed >/dev/null\nexit "$PROBE_RC"\n'); mock.chmod(0o755)
    env=dict(os.environ,CLAUDE_BIN=str(mock),PROBE_CTL=str(ctl),PROBE_RC=str(code))
    r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--wallclock=20','--max-iterations=1','--project',d],env=env,capture_output=True,timeout=25)
    self.assertEqual(r.returncode,0, r.stdout+r.stderr); self.assertIn(b'GATE: GO',r.stdout+r.stderr)
 def test_supervisor_setup_failure_is_state_error(self):
  for code in (0,1,2,3,4,125):
   with self.subTest(code=code), tempfile.TemporaryDirectory() as d:
    p=Path(d); ctl=R/'scripts/goal_ctl.sh'
    subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
    (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
    subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
    bindir=p/'bin'; bindir.mkdir(); py=bindir/'python3'; py.write_text(f'#!/bin/bash\nexit {code}\n'); py.chmod(0o755)
    env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'])
    r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--wallclock=20','--max-iterations=1','--project',d],env=env,capture_output=True,timeout=25)
    self.assertEqual(r.returncode,4, r.stdout+r.stderr); self.assertIn(b'executor-unavailable',r.stdout+r.stderr)
 def test_missing_executor_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ctl=R/'scripts/goal_ctl.sh'
   subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   env=dict(os.environ,CLAUDE_BIN=str(p/'missing-executor'))
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--wallclock=20','--max-iterations=1','--project',d],env=env,capture_output=True,timeout=25)
   self.assertEqual(r.returncode,4); self.assertIn(b'executor-unavailable',r.stdout+r.stderr)
 def test_resume_cannot_override_live_owner(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); subprocess.run(['bash',str(R/'scripts/goal_ctl.sh'),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('placeholder')
   (p/'.goal/lock').write_text(f'{os.getpid()}\n{int(time.time())}\n')
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--resume','--wallclock=5','--project',d],capture_output=True,timeout=10)
   self.assertEqual(r.returncode,4); self.assertIn(b'live-lock',r.stderr); self.assertTrue((p/'.goal/lock').exists())
 def test_expired_contract_prevents_any_worker(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); subprocess.run(['bash',str(R/'scripts/goal_ctl.sh'),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(R/'scripts/goal_ctl.sh'),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   state=p/'.goal/state.rec'; state.write_text(state.read_text().replace('deadline=0','deadline=1'))
   mock=p/'mock'; mock.write_text('#!/bin/bash\necho x >> "$PROBE_CALLS"\n'); mock.chmod(0o755)
   env=dict(os.environ,CLAUDE_BIN=str(mock),PROBE_CALLS=str(p/'.goal/calls'))
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--wallclock=30','--project',d],env=env,capture_output=True,timeout=10)
   self.assertEqual(r.returncode,3); self.assertFalse((p/'.goal/calls').exists())
 def test_deadline_limits_workers_and_resume(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); subprocess.run(['bash',str(R/'scripts/goal_ctl.sh'),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(R/'scripts/goal_ctl.sh'),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   mock=p/'mock'; mock.write_text('#!/bin/bash\necho x >> "$PROBE_CALLS"\n(sleep 3; echo leaked > "$PROBE_LEAK") &\nwait\n');mock.chmod(0o755)
   env=dict(os.environ,CLAUDE_BIN=str(mock),PROBE_CALLS=str(p/'.goal/calls'),PROBE_LEAK=str(p/'.goal/leak'))
   args=['bash',str(R/'scripts/goal_loop.sh'),'--continue','--max-iterations=2','--wallclock=2','--project',d]
   start=time.monotonic(); subprocess.run(args,env=env,capture_output=True,timeout=25); elapsed=time.monotonic()-start
   calls=(p/'.goal/calls').read_text().count('x')
   self.assertEqual(calls,1); self.assertLess(elapsed,5)
   subprocess.run(args+['--resume'],env=env,capture_output=True,timeout=10)
   self.assertEqual((p/'.goal/calls').read_text().count('x'),1)
   time.sleep(3.2); self.assertFalse((p/'.goal/leak').exists())
 def test_wall_clock_regression_does_not_extend_budget(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ctl=R/'scripts/goal_ctl.sh'
   subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   bindir=p/'bin'; bindir.mkdir()
   clock=bindir/'date'; clock.write_text('#!/bin/bash\nif [ "$1" = +%s ]; then\n  if [ -f "$CLOCK_COUNTER" ]; then echo 900; else echo x > "$CLOCK_COUNTER"; echo 1000; fi\nelse /bin/date "$@"; fi\n'); clock.chmod(0o755)
   mock=p/'mock'; mock.write_text('#!/bin/bash\necho x >> "$PROBE_CALLS"\n'); mock.chmod(0o755)
   env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'],CLOCK_COUNTER=str(p/'.goal/clock-counter'),CLAUDE_BIN=str(mock),PROBE_CALLS=str(p/'.goal/calls'))
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--wallclock=1','--max-iterations=1','--project',d],env=env,capture_output=True,timeout=15)
   self.assertIn(b'clock-regressed',r.stdout+r.stderr)
   self.assertFalse((p/'.goal/calls').exists())
 def test_resume_rejects_persisted_clock_rollback(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ctl=R/'scripts/goal_ctl.sh'
   subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   high=str(int(time.time())+100000); deadline=str(int(high)+100)
   (p/'.goal/runner.clock').write_text(high+'\n'); (p/'.goal/runner.deadline').write_text(deadline+'\n')
   mock=p/'mock'; mock.write_text('#!/bin/bash\necho x >> "$PROBE_CALLS"\n'); mock.chmod(0o755)
   env=dict(os.environ,CLAUDE_BIN=str(mock),PROBE_CALLS=str(p/'.goal/calls'))
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--resume','--wallclock=10','--project',d],env=env,capture_output=True,timeout=10)
   self.assertEqual(r.returncode,4); self.assertIn(b'clock-regressed',r.stdout+r.stderr)
   self.assertFalse((p/'.goal/calls').exists())
   self.assertEqual((p/'.goal/runner.clock').read_text(),high+'\n')
   self.assertEqual((p/'.goal/runner.deadline').read_text(),deadline+'\n')
 def test_wallclock_leading_zeros_are_decimal(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ctl=R/'scripts/goal_ctl.sh'
   subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--dry-run','--wallclock=08','--max-iterations=1','--project',d],capture_output=True,timeout=12)
   self.assertEqual(r.returncode,3,r.stdout+r.stderr)
   self.assertNotIn(b'value too great for base',r.stdout+r.stderr)
 def test_supervisor_ignores_ambient_python_startup(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ctl=R/'scripts/goal_ctl.sh'
   subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   mods=p/'mods'; mods.mkdir()
   (mods/'sitecustomize.py').write_text("import os\nopen(os.environ['GOAL_SITE_MARKER'],'w').write('loaded')\n")
   mock=p/'mock'; mock.write_text('#!/bin/bash\nexit 0\n'); mock.chmod(0o755)
   env=dict(os.environ,PYTHONPATH=str(mods),GOAL_SITE_MARKER=str(p/'.goal/loaded'),CLAUDE_BIN=str(mock))
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--wallclock=5','--max-iterations=1','--project',d],env=env,capture_output=True,timeout=12)
   self.assertEqual(r.returncode,3,r.stdout+r.stderr)
   self.assertFalse((p/'.goal/loaded').exists())
 def test_budget_temp_symlinks_do_not_overwrite_user_files(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ctl=R/'scripts/goal_ctl.sh'
   subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   for name in ('clock','deadline'):
    target=p/('valuable-'+name); target.write_text('do not overwrite\n')
    (p/'.goal'/('runner.'+name+'.tmp')).symlink_to(target)
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--dry-run','--wallclock=5','--max-iterations=1','--project',d],capture_output=True,timeout=12)
   self.assertEqual(r.returncode,3,r.stdout+r.stderr)
   for name in ('clock','deadline'):
    self.assertEqual((p/('valuable-'+name)).read_text(),'do not overwrite\n')
    self.assertTrue((p/'.goal'/('runner.'+name+'.tmp')).is_symlink())
 def test_owner_sigkill_stops_owned_process_group(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ctl=R/'scripts/goal_ctl.sh'
   subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   mock=p/'mock'; mock.write_text('#!/bin/bash\n(sleep 2; echo leaked > "$PROBE_LEAK") &\necho ready > "$PROBE_READY"\nwait\n'); mock.chmod(0o755)
   env=dict(os.environ,CLAUDE_BIN=str(mock),PROBE_LEAK=str(p/'.goal/leak'),PROBE_READY=str(p/'.goal/ready'))
   runner=subprocess.Popen(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--wallclock=10','--project',d],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    end=time.monotonic()+5
    while not (p/'.goal/ready').exists() and time.monotonic()<end: time.sleep(0.02)
    self.assertTrue((p/'.goal/ready').exists(),'executor did not start')
    runner.kill(); runner.wait(timeout=5)
    time.sleep(2.5)
    self.assertFalse((p/'.goal/leak').exists(),'orphan process wrote after owner died')
   finally:
    if runner.poll() is None: runner.kill(); runner.wait(timeout=5)
 def test_executor_exit_stops_background_children(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); ctl=R/'scripts/goal_ctl.sh'
   subprocess.run(['bash',str(ctl),'init','--project',d],check=True,capture_output=True)
   (p/'.goal/goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n- AC-1 | ok | check: `true` | expected: exit=0\n\n## Approval\n\napproved: PENDING\n')
   subprocess.run(['bash',str(ctl),'stamp','--project',d,'--auto'],check=True,capture_output=True)
   mock=p/'mock'; mock.write_text('#!/bin/bash\n(sleep 2; echo leaked > "$PROBE_LEAK") &\nexit 0\n'); mock.chmod(0o755)
   env=dict(os.environ,CLAUDE_BIN=str(mock),PROBE_LEAK=str(p/'.goal/leak'))
   r=subprocess.run(['bash',str(R/'scripts/goal_loop.sh'),'--continue','--wallclock=5','--max-iterations=1','--project',d],env=env,capture_output=True,timeout=10)
   self.assertEqual(r.returncode,3,r.stdout+r.stderr)
   time.sleep(2.5)
   self.assertFalse((p/'.goal/leak').exists(),'background child survived executor')
if __name__=='__main__': unittest.main()
