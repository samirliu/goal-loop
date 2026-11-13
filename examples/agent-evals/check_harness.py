"""Model-free failure-path checks for the real-agent trial controller."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('bench', Path(__file__).with_name('bench.py'))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

GOOD = '''def merge_ranges(ranges):
    pairs = []
    for pair in ranges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError()
        a, b = pair
        if type(a) is not int or type(b) is not int or a > b:
            raise ValueError()
        if a < b:
            pairs.append([a, b])
    result = []
    for a, b in sorted(pairs):
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return result
'''


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / 'cohort'
        self.trials = [Path(p) for p in bench.prepare(root, pilot=True)]

    def configured(self, arm='plain', seconds=5):
        folder = next(p for p in self.trials if json.loads((p / 'trial.json').read_bytes())['arm'] == arm)
        config = json.loads((folder / 'trial.json').read_bytes())
        config['budget_seconds'] = seconds
        bench.save(folder / 'trial.json', config)
        (Path(config['workspace']) / 'solution.py').write_text(GOOD)
        bench.start(folder)
        return folder, Path(config['workspace'])

    def test_done_does_not_change_artifact_and_result_is_immutable(self):
        folder, work = self.configured()
        before = bench.source_files(work)
        bench.save(folder / 'DONE.json', {'complete': True})
        result = bench.monitor(folder)
        self.assertEqual(before, bench.source_files(work))
        self.assertTrue(result['accepted_within_budget'])
        snapshot = (folder / 'snapshot/solution.py').read_bytes()
        (work / 'solution.py').write_text('raise RuntimeError("late edit")\n')
        self.assertEqual(snapshot, (folder / 'snapshot/solution.py').read_bytes())
        self.assertEqual(result, bench.finish(folder))
        self.assertIsNone(result['tokens'])
        self.assertIsNone(result['money'])

    def test_timeout_retains_correctness_and_does_not_modify_artifact(self):
        folder, work = self.configured(seconds=.05)
        before = bench.source_files(work)
        result = bench.monitor(folder)
        self.assertEqual('timeout', result['terminal'])
        self.assertTrue(result['accepted'])
        self.assertFalse(result['accepted_within_budget'])
        self.assertEqual(before, bench.source_files(work))
        self.assertTrue((folder / 'STOP').exists())

    def test_protected_public_tamper_is_rejected_even_with_correct_solution(self):
        folder, work = self.configured()
        (work / 'public.py').write_text('print("PASS")\n')
        result = bench.finish(folder)
        self.assertTrue(result['quality']['ok'])
        self.assertFalse(result['protected'])
        self.assertFalse(result['accepted'])

    def test_frozen_evaluator_tamper_is_rejected(self):
        folder, _ = self.configured()
        config = json.loads((folder / 'trial.json').read_bytes())
        with Path(config['oracle']).open('a') as stream:
            stream.write('\n# changed after freeze\n')
        result = bench.finish(folder)
        self.assertFalse(result['frozen'])
        self.assertFalse(result['accepted'])

    def test_broken_native_receipt_cannot_crash_or_claim_protocol_success(self):
        folder, work = self.configured('native')
        (work / 'native-goal.json').write_text('{torn')
        result = bench.finish(folder)
        self.assertTrue(result['accepted'])
        self.assertFalse(result['protocol_compliant'])
        self.assertIsNone(result['tokens'])

    def test_actual_grader_failure_is_retained(self):
        folder, work = self.configured()
        (work / 'solution.py').write_text('raise RuntimeError("broken candidate")\n')
        result = bench.finish(folder)
        self.assertFalse(result['accepted'])
        self.assertIn('broken candidate', result['quality']['error'])
        self.assertNotEqual(0, result['grader']['result'])

    def test_actual_host_identity_cannot_be_silently_replaced(self):
        folder, _ = self.configured()
        bench.attach(folder, '/root/trial-actual')
        with self.assertRaises(ValueError):
            bench.attach(folder, '/root/different')
        result = bench.finish(folder)
        self.assertEqual('/root/trial-actual', result['host_dispatch']['agent'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
