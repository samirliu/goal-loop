"""Black-box checks derived solely from TASK.md."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class PublicRequirements(unittest.TestCase):
    def cli(self, command, rows='', *flags, path='-'):
        return subprocess.run([sys.executable, '-m', 'logtool', command, path, *flags], input=rows, text=True, capture_output=True)

    def test_stats_and_query(self):
        rows = [dict(service='a', status=200, latency_ms=9, extra={'x': 1}), dict(service='b', status=500, latency_ms=1), dict(service='a', status=599, latency_ms=3)]
        data = '\n' + '\n\n'.join(map(json.dumps, rows)) + '\n'
        p = self.cli('stats', data)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), dict(count=3, errors=2, p50_ms=3, p95_ms=9, services={'a':2,'b':1}))
        p = self.cli('query', data, '--service', 'a', '--min-status', '200')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(list(map(json.loads,p.stdout.splitlines())), [rows[0], rows[2]])
        p = self.cli('stats', data, '--service', 'b')
        self.assertEqual(json.loads(p.stdout), dict(count=1,errors=1,p50_ms=1,p95_ms=1,services={'b':1}))
        self.assertEqual(self.cli('query', data, '--service', 'absent').stdout, '')

    def test_empty_and_quantiles(self):
        self.assertEqual(json.loads(self.cli('stats', '\n  \n').stdout), dict(count=0,errors=0,p50_ms=None,p95_ms=None,services={}))
        data = '\n'.join(json.dumps(dict(service='a',status=200,latency_ms=n)) for n in range(1,21))
        p = self.cli('stats',data)
        self.assertEqual(json.loads(p.stdout)['p50_ms'],10)
        self.assertEqual(json.loads(p.stdout)['p95_ms'],19)

    def test_invalid_is_atomic_and_before_filter(self):
        good = json.dumps(dict(service='valid',status=200,latency_ms=1))
        base = dict(service='bad', status=200, latency_ms=1)
        invalid = ['{', 'null', '[]', '1', 'true']
        for key, values in [('service',['',None,2,False]),('status',[True,False,99,600,200.0,'200',None]),('latency_ms',[True,False,-1,'1',None,float('nan'),float('inf'),float('-inf')])]:
            for value in values:
                invalid.append(json.dumps(dict(base,**{key:value})))
            missing = base.copy(); del missing[key]
            invalid.append(json.dumps(missing))
        for value in invalid:
            for command in ['stats','query']:
                with self.subTest(value=value, command=command):
                    p = self.cli(command,good+'\n\n'+value+'\n','--service','valid')
                    self.assertEqual(p.returncode,2)
                    self.assertEqual(p.stdout,'')
                    self.assertRegex(p.stderr,r'\b3\b')

    def test_file_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'input.jsonl'
            path.write_text('{"service":"服务","status":100,"latency_ms":0}\n',encoding='utf-8')
            p = self.cli('query',path=str(path))
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(p.stdout)['service'],'服务')
            p = self.cli('stats',path=str(Path(tmp)/'missing'))
            self.assertEqual(p.returncode,2)
            self.assertEqual(p.stdout,'')

if __name__ == '__main__':
    unittest.main()
