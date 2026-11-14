"""Real regression artifacts cannot pass by omitting a requested test."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT/'examples/learning-regression/task.py'


class RegressionReceipts(unittest.TestCase):
    def test_real_test_receipt_is_accepted_and_corrupt_count_rejected_even_with_optimization(self):
        with tempfile.TemporaryDirectory(prefix='goal-regression-receipt-') as tmp:
            project=Path(tmp);shutil.copy2(TASK,project/'task.py')
            names=['test_store_observation.Observations.test_future_head_is_observed_by_same_store_instance']
            (project/'input-T1.json').write_text(json.dumps(dict(tests=names,tests_root=str(ROOT/'tests'))))
            work=subprocess.run([sys.executable,'-I','-B','task.py','work','T1','0'],cwd=project,capture_output=True,timeout=10)
            self.assertEqual(work.returncode,0,work.stderr)
            good=subprocess.run([sys.executable,'-I','-B','task.py','grade','T1'],cwd=project,capture_output=True,timeout=5)
            self.assertEqual(good.returncode,0,good.stderr)
            path=project/'result-T1.json';record=json.loads(path.read_bytes());record['ran']=0;path.write_text(json.dumps(record))
            for mode in ([],['-O']):
                with self.subTest(mode=mode):
                    bad=subprocess.run([sys.executable,'-I','-B',*mode,'task.py','grade','T1'],cwd=project,capture_output=True,timeout=5)
                    self.assertNotEqual(bad.returncode,0)
                    self.assertIn(b'missing or substituted tests',bad.stderr)


if __name__=='__main__':
    unittest.main()
