"""Real gate entry preparation consumes the existing batch envelope."""
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CTL, GATE = ROOT/'scripts/goal_ctl.sh', ROOT/'scripts/goal_gate.sh'


class GateEntryBudget(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='goal-gate-entry-')
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.state = self.project/'.goal'
        self.call(CTL, 'init', expected=0)

    def call(self, script, *args, expected=None, env=None, pass_fds=()):
        result = subprocess.run(['bash', str(script), *args, '--project', str(self.project)],
                                capture_output=True, text=True, env=env, pass_fds=pass_fds, timeout=12)
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        return result

    def contract(self, *, budgeted=True, checks=5, duration=1, check_timeout=10, durations=None):
        rows = []
        for index in range(checks):
            delay = duration if durations is None else durations[index]
            command = ('if test -f .goal/evidence/armed; then '
                       'printf "%s|%s\\n" "${GOAL_GATE_MONOTONIC_START:-missing}" '
                       '"${GOAL_RUNNER_MONOTONIC_END:-missing}" >> .goal/evidence/context; '
                       'sleep '+str(delay)+'; echo '+str(index)+' >> .goal/evidence/completed; fi; true')
            rows.append('- AC-%s | bounded | check: `%s` | expected: exit=0' % (index+1, command))
        (self.state/'goal.md').write_text('# Goal\n\n## Acceptance criteria\n\n'+'\n'.join(rows)+
            '\n\n## Budgets\n\ncheck_timeout='+str(check_timeout)+'\n\n## Approval\n\napproved: PENDING\n')
        self.call(CTL, 'stamp', '--auto', *(['--time-budget=1'] if budgeted else []), expected=0)
        if budgeted:
            time.sleep(1.1)
        (self.state/'evidence/armed').touch()

    def slow_real_view_reader(self, seconds=2):
        """Delay the real imported verify_views; retain its real lock/exec path."""
        marker = self.state/'evidence/slow-view-read.json'
        env = dict(os.environ, GATE_ENTRY_READ_MARKER=str(marker), GATE_ENTRY_READ_DELAY=str(seconds))
        return self.python_probe(env), marker

    def python_probe(self, env):
        """One shim for both real access/limit paths, with independent entry IO."""
        probe = self.state/'entry-probe'; probe.mkdir(exist_ok=True)
        wrapper = probe/'entry_probe.py'
        wrapper.write_text(
            'import importlib.util,json,os,sys,time\nfrom pathlib import Path\n'
            'def record(path,row):\n'
            ' fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)\n'
            ' try: os.write(fd,(json.dumps(row)+"\\n").encode())\n'
            ' finally: os.close(fd)\n'
            'spec=importlib.util.spec_from_file_location("actual_entry_module",sys.argv[1])\n'
            'actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)\n'
            'if Path(sys.argv[1]).name == "goal_tree_digest.py":\n'
            ' began=time.monotonic(); value=actual.fingerprint(*(actual.items(arg) for arg in sys.argv[2:6]))\n'
            ' record(os.environ["GATE_ENTRY_PHASE_LOG"],dict(phase="fingerprint",start=began,end=time.monotonic()))\n'
            ' print(value)\n'
            'elif sys.argv[2] == "access-exec":\n'
            ' store=actual; real=store.verify_views\n'
            ' def slow(state):\n'
            '  marker=Path(os.environ["GATE_ENTRY_READ_MARKER"])\n'
            '  if marker.exists(): return real(state)\n'
            '  began=time.monotonic()\n'
            '  time.sleep(float(os.environ["GATE_ENTRY_READ_DELAY"]))\n'
            '  value=real(state)\n'
            '  marker.write_text(json.dumps({"started":began,"finished":time.monotonic(),"real_views_verified":True}))\n'
            '  return value\n'
            ' if "GATE_ENTRY_READ_DELAY" in os.environ: store.verify_views=slow\n'
            ' verify=store.verify_views; flock=store.fcntl.flock\n'
            ' def measured_view(state):\n'
            '  began=time.monotonic(); value=verify(state)\n'
            '  record(os.environ["GATE_ENTRY_PHASE_LOG"],dict(phase="ledger-verification",start=began,end=time.monotonic()))\n'
            '  return value\n'
            ' def measured_lock(*args):\n'
            '  began=time.monotonic(); value=flock(*args)\n'
            '  record(os.environ["GATE_ENTRY_PHASE_LOG"],dict(phase="lock",start=began,end=time.monotonic()))\n'
            '  return value\n'
            ' store.verify_views=measured_view; store.fcntl.flock=measured_lock\n'
            ' record(os.environ["GATE_ENTRY_ACCESS_LOG"],{"entered":time.monotonic(),'
            '"inherited":os.environ.get("GOAL_ACCESS_FD") is not None})\n'
            ' store._access_exec(sys.argv[3:])\n'
            'elif sys.argv[2] == "gate-limit":\n'
            ' runner=actual\n'
            ' cap, expired = runner.gate_limit(sys.argv[3])\n'
            ' row={"origin":os.environ.get("GOAL_GATE_MONOTONIC_START"),'
            '"inherited_cap":os.environ.get("GOAL_RUNNER_MONOTONIC_END"),'
            '"cap":cap,"expired":expired,"observed":time.monotonic()}\n'
            ' record(os.environ["GATE_ENTRY_LIMIT_LOG"],row)\n'
            ' print("%s %s" % ("none" if cap is None else "%.9f" % cap,int(expired)))\n')
        bindir = probe/'bin'; bindir.mkdir(exist_ok=True)
        wrapped = shlex.quote(sys.executable)+' -I '+shlex.quote(str(wrapper))+' "${@:2}"'
        shim = bindir/'python3'
        shim.write_text('#!/bin/bash\nif [ "${1:-}" = -I ]; then\n case "${2:-}:${3:-}" in\n '+
            shlex.quote(str(ROOT/'scripts/goal_store.py')+':access-exec')+
            ') if [ "${5:-}" = gate ]; then exec '+wrapped+'; fi ;;\n '+
            shlex.quote(str(ROOT/'scripts/goal_runner.py')+':gate-limit')+') exec '+wrapped+' ;;\n '+
            shlex.quote(str(ROOT/'scripts/goal_tree_digest.py'))+':*) exec '+wrapped+' ;;\n esac\nfi\nexec '+
            shlex.quote(sys.executable)+' "$@"\n')
        shim.chmod(0o755)
        path = [p for p in env['PATH'].split(os.pathsep) if p != str(bindir)]
        return dict(env, PATH=os.pathsep.join([str(bindir), *path]),
                    GATE_ENTRY_ACCESS_LOG=str(self.state/'evidence/access-entry.jsonl'),
                    GATE_ENTRY_LIMIT_LOG=str(self.state/'evidence/gate-limits.jsonl'),
                    GATE_ENTRY_PHASE_LOG=str(self.state/'evidence/entry-phases.jsonl'))

    def contexts(self):
        path = self.state/'evidence/context'
        return [line.split('|') for line in path.read_text().splitlines()] if path.exists() else []

    def observe_gate_limits(self, env):
        """Record real limits; a named check need not have been dispatched."""
        return self.python_probe(env)

    def gate_limits(self):
        path = self.state/'evidence/gate-limits.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def observation(self, result, started, **extra):
        completed = self.state/'evidence/completed'
        access_log = self.state/'evidence/access-entry.jsonl'
        access = [json.loads(line) for line in access_log.read_text().splitlines()] if access_log.exists() else []
        phase_log = self.state/'evidence/entry-phases.jsonl'
        phases = [json.loads(line) for line in phase_log.read_text().splitlines()] if phase_log.exists() else []
        fresh = [row['entered'] for row in access if not row['inherited']]
        finished = time.monotonic()
        spans = []
        for path in (self.state/'evidence/runtime').glob('*.json'):
            span = json.loads(path.read_bytes())['payload']
            if span.get('start_monotonic', 0) >= started:
                spans.append({k: span.get(k) for k in ('kind', 'label', 'start_monotonic', 'elapsed', 'result', 'state')})
        value = dict(case=self.id(), started_monotonic=started, elapsed=finished-started, returncode=result.returncode,
                     fresh_access_entries=fresh, access_elapsed=finished-fresh[0] if len(fresh) == 1 else None,
                     contexts=self.contexts(), limits=self.gate_limits(),
                     completed=completed.read_text().splitlines() if completed.exists() else [],
                     stdout=result.stdout, stderr=result.stderr, phases=phases, spans=spans, **extra)
        print('GATE_ENTRY_OBSERVATION '+json.dumps(value, sort_keys=True), file=sys.stderr, flush=True)
        return value

    def test_slow_real_view_preflight_spends_the_same_settlement(self):
        self.contract()
        env, marker = self.slow_real_view_reader()
        started = time.monotonic()
        result = self.call(GATE, '--verify', env=env)
        read = json.loads(marker.read_bytes())
        observed = self.observation(result, started, view_read=read)
        self.assertTrue(read['real_views_verified'])
        self.assertGreaterEqual(read['finished']-read['started'], 2)
        self.assertEqual(result.returncode, 2, observed)
        self.assertEqual(len(observed['fresh_access_entries']), 1, observed)
        self.assertLess(observed['access_elapsed'], 4.2, observed)

    def test_fresh_future_origin_and_supervision_marker_cannot_grant_time(self):
        self.contract()
        env, marker = self.slow_real_view_reader()
        future = str(time.monotonic()+3600)
        env.update(GOAL_GATE_MONOTONIC_START=future, GOAL_GATE_SUPERVISED='1',
                   GOAL_GATE_SHELL_EPOCH=str(time.time()+3600))
        env = self.observe_gate_limits(env)
        started = time.monotonic()
        result = self.call(GATE, '--verify', env=env)
        read = json.loads(marker.read_bytes())
        observed = self.observation(result, started, injected_origin=future, view_read=read)
        self.assertEqual(result.returncode, 2, observed)
        self.assertEqual(len(observed['fresh_access_entries']), 1, observed)
        self.assertLess(observed['access_elapsed'], 4.2, observed)
        self.assertTrue(observed['limits'], observed)
        for limit in observed['limits']:
            origin = limit['origin']
            self.assertNotEqual(origin, future, observed)
            self.assertGreaterEqual(float(origin), observed['fresh_access_entries'][0], observed)
            self.assertLessEqual(float(origin), read['started'], observed)
            self.assertLessEqual(limit['cap'], float(origin)+3, observed)

    def borrowed_reader(self, origin, cap):
        fd = os.open(self.state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        self.addCleanup(os.close, fd)
        env = dict(os.environ, GOAL_ACCESS_FD=str(fd), GOAL_ACCESS_OWNER_PID=str(os.getpid()),
                   GOAL_ACCESS_MODE='read', GOAL_GATE_MONOTONIC_START=str(origin),
                   GOAL_RUNNER_MONOTONIC_END=str(cap))
        return fd, env

    def test_borrowed_reader_preserves_time_spent_before_nested_gate(self):
        self.contract()
        entered = time.monotonic()
        fd, env = self.borrowed_reader(entered, entered+8)
        env = self.observe_gate_limits(env)
        # This is real elapsed preparation under the retained SH lock. No
        # clock, inherited FD validation or subprocess exec is replaced.
        time.sleep(2)
        result = self.call(GATE, '--verify', env=env, pass_fds=(fd,))
        observed = self.observation(result, entered)
        self.assertEqual(result.returncode, 2, observed)
        self.assertLess(observed['elapsed'], 4.2, observed)
        self.assertTrue(observed['limits'], observed)
        for limit in observed['limits']:
            self.assertEqual(limit['origin'], str(entered), observed)
            self.assertLessEqual(limit['cap'], entered+3, observed)

    def test_borrowed_nested_gate_keeps_shorter_global_cap(self):
        self.contract(checks=2, duration=3, check_timeout=10)
        entered = time.monotonic()
        inherited = entered+2.5
        fd, env = self.borrowed_reader(entered, inherited)
        env = self.observe_gate_limits(env)
        result = self.call(GATE, '--verify', env=env, pass_fds=(fd,))
        observed = self.observation(result, entered, inherited_cap=inherited)
        self.assertEqual(result.returncode, 2, observed)
        self.assertLess(observed['elapsed'], 4.2, observed)
        self.assertTrue(observed['limits'], observed)
        self.assertEqual(observed['completed'], [], observed)
        for limit in observed['limits']:
            self.assertEqual(limit['origin'], str(entered), observed)
            self.assertLessEqual(limit['cap'], inherited, observed)

    def test_unbudgeted_batch_has_only_individual_check_timeouts(self):
        self.contract(budgeted=False, checks=4, durations=(1.1, 1.1, 1.1, 3.5), check_timeout=2)
        started = time.monotonic()
        result = self.call(GATE, '--verify')
        observed = self.observation(result, started)
        self.assertEqual(result.returncode, 2, observed)
        self.assertGreater(observed['elapsed'], 3, observed)
        self.assertEqual(observed['completed'], ['0', '1', '2'], observed)
        self.assertEqual(len(observed['contexts']), 4, observed)
        self.assertTrue(all(cap == 'missing' for _, cap in observed['contexts']), observed)
        self.assertIn('124', result.stdout+result.stderr, observed)

    def test_python_startup_delay_spends_the_same_settlement(self):
        self.contract()
        bindir=self.state/'startup-bin';bindir.mkdir()
        marker=self.state/'evidence/startup-delay'
        shim=bindir/'python3'
        shim.write_text('#!/bin/bash\ncase "${2:-}" in */goal_store.py) '
                        'if [ ! -e "$GATE_STARTUP_DELAY_MARKER" ]; then touch "$GATE_STARTUP_DELAY_MARKER"; sleep 1.6; fi ;; esac\n'
                        'exec '+shlex.quote(sys.executable)+' "$@"\n')
        shim.chmod(0o755)
        env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'],GATE_STARTUP_DELAY_MARKER=str(marker))
        started=time.monotonic()
        result=self.call(GATE,'--verify',env=env)
        observed=self.observation(result,started,startup_delay_marker=marker.exists())
        self.assertTrue(marker.exists(),observed)
        self.assertEqual(result.returncode,2,observed)
        self.assertLess(observed['elapsed'],4.2,observed)

    def test_expired_green_claim_with_state_reader_process_latency(self):
        """28/76 with repeatable process-start pressure, not random CPU load."""
        self.contract(checks=1, duration=0)
        (self.project/'answer').write_text('landed')
        self.call(CTL, 'close-iteration', '--operation-id', 'green-latency', '--task', 'T1',
                  '--files', 'answer', '--checks-pass', '1', '--checks-fail', '0',
                  '--checks-unverifiable', '0', '--exit-signal', 'yes', '--no-gate',
                  '--adversarial', 'clear', '--adversarial-note', 'fixture command and landed answer reviewed', expected=0)
        bindir = self.state/'lookup-bin'; bindir.mkdir()
        grep = subprocess.check_output(['which', 'grep'], text=True).strip()
        shim = bindir/'grep'
        shim.write_text('#!/bin/bash\n'
                        'if [ "${1:-}" = -E ]; then\n'
                        ' case "${2:-}" in ^*=) printf "%s\\n" "$2" >> "$LOOKUP_LOG"; sleep .12 ;; esac\n'
                        'fi\nexec '+shlex.quote(grep)+' "$@"\n')
        shim.chmod(0o755)
        marker = self.state/'evidence/lookups'
        env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'], LOOKUP_LOG=str(marker))
        env = self.observe_gate_limits(env)
        for name in ('context', 'completed'):
            (self.state/'evidence'/name).unlink(missing_ok=True)
        started = time.monotonic()
        result = self.call(GATE, '--check', env=env)
        observed = self.observation(result, started, delayed_lookups=marker.read_text().splitlines() if marker.exists() else [])
        self.assertEqual(result.returncode, 0, observed)
        self.assertIn('GATE: GO ', result.stdout, observed)
        self.assertIn('time-budget-exhausted', result.stdout, observed)
        self.assertLess(observed['elapsed'], 4.2, observed)

    def test_expired_green_claim_with_ac_reader_process_latency(self):
        """The finite window includes repeated AC field process startup too."""
        self.contract(checks=1, duration=0)
        (self.project/'answer').write_text('landed')
        self.call(CTL, 'close-iteration', '--operation-id', 'ac-latency', '--task', 'T1', '--files', 'answer',
                  '--checks-pass', '1', '--checks-fail', '0', '--checks-unverifiable', '0',
                  '--exit-signal', 'yes', '--no-gate', '--adversarial', 'clear',
                  '--adversarial-note', 'fixture command and landed answer reviewed', expected=0)
        bindir=self.state/'ac-bin';bindir.mkdir()
        sed=subprocess.check_output(['which','sed'],text=True).strip()
        shim=bindir/'sed'
        shim.write_text('#!/bin/bash\ncase "${2:-}" in *check:*|*expected:*|*external:*|*metric:*|*sd:*|*var:*|*probe:*|*window:*) '
                        'printf "%s\\n" "$2" >> "$AC_PROCESS_LOG"; sleep .18 ;; esac\nexec '+shlex.quote(sed)+' "$@"\n')
        shim.chmod(0o755)
        marker=self.state/'evidence/ac-processes'
        env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'],AC_PROCESS_LOG=str(marker))
        started=time.monotonic()
        result=self.call(GATE,'--check',env=env)
        observed=self.observation(result,started,delayed_ac_processes=marker.read_text().splitlines() if marker.exists() else [])
        self.assertEqual(result.returncode,0,observed)
        self.assertIn('GATE: GO ',result.stdout,observed)
        self.assertLess(observed['elapsed'],4.2,observed)


if __name__ == '__main__':
    unittest.main()
