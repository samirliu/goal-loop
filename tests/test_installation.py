"""Clean relocated installs keep real runtime resources without user settings writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class Installation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='goal-clean-install-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work=Path(cls.temporary.name)
        cls.source=cls.work/'source package'
        cls.config=cls.work/'clean config'
        cls.config.mkdir()
        cls.settings=cls.config/'settings.json'
        cls.settings.write_text('{"permissions":{"allow":["Read"]},"hooks":{}}\n')
        cls.run_install(ROOT,'plugin','--output',str(cls.source))
        cls.run_install(cls.source,'skill','--config-dir',str(cls.config),'--with-companion')
        cls.relocated=cls.work/'cache'/'goal-loop-host'/(ROOT/'VERSION').read_text().strip()
        cls.relocated.parent.mkdir(parents=True)
        cls.source.rename(cls.relocated)
        cls.skill=cls.config/'skills/goal-loop'

    @classmethod
    def run_install(cls, source, *args, expected=0):
        r=subprocess.run([sys.executable,'-I',str(source/'scripts/goal_install.py'),*args],
                         capture_output=True,text=True,timeout=60)
        if r.returncode!=expected:
            raise AssertionError(r.stdout+r.stderr)
        return r

    def test_plugin_payload_is_exact_and_excludes_checkout_noise(self):
        names=json.loads((ROOT/'assets/install-files.json').read_text())
        for name in names:
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).digest(),
                             hashlib.sha256((self.relocated/name).read_bytes()).digest(),name)
        for name in ['.git','.archify','.orphaned_at','.env','devtools','__pycache__']:
            self.assertFalse((self.relocated/name).exists(),name)

    def test_every_runtime_module_and_role_is_in_the_inventory(self):
        names=set(json.loads((ROOT/'assets/install-files.json').read_text()))
        for folder in ['scripts','references','assets','agents','companions','examples']:
            for path in (ROOT/folder).rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
                    self.assertIn(path.relative_to(ROOT).as_posix(),names)

    def test_generated_entry_retains_the_complete_canonical_protocol(self):
        spec=importlib.util.spec_from_file_location('install_entry',ROOT/'scripts/goal_install.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual((ROOT/'skills/goal-loop/SKILL.md').read_text(),module.plugin_entry())
        manifest=json.loads((self.relocated/'.claude-plugin/plugin.json').read_text())
        self.assertEqual(manifest['version'],(ROOT/'VERSION').read_text().strip())
        self.assertEqual(manifest['skills'],['./skills','./companions/contract-forge'])

    def test_skill_resources_and_global_roles_survive_source_relocation(self):
        self.assertFalse(self.source.exists())
        self.assertEqual((self.skill/'SKILL.md').read_bytes(),(ROOT/'SKILL.md').read_bytes())
        for role in ['goal-worker','goal-mech-worker','goal-critic','goal-checker-req','goal-adjudicator']:
            text=(self.config/'agents'/(role+'.md')).read_text()
            original=(ROOT/'agents'/(role+'.md')).read_text()
            end=original.index('\n---',4)+4
            self.assertTrue(text.startswith(original[:end]))
            self.assertIn(original[end:],text)
            self.assertIn(str(self.skill),text)
            self.assertTrue((self.skill/'agents'/(role+'.md')).is_file())
        for name in ['scripts/goal_quality.py','scripts/goal_evolve.py','scripts/goal_crew.py',
                     'scripts/goal_host.py','references/packs/visual.md','docs/transaction-state.md',
                     'docs/evals/native-host/claude-haha/w5-headless-v3/report.json']:
            self.assertTrue((self.skill/name).is_file(),name)
        self.assertTrue((self.config/'skills/contract-forge/SKILL.md').is_file())

    def test_existing_settings_and_hooks_are_not_replaced(self):
        self.assertEqual(self.settings.read_text(),'{"permissions":{"allow":["Read"]},"hooks":{}}\n')
        self.assertFalse(list(self.config.glob('.goal-install-*')))

    def test_same_name_conflict_refuses_before_changing_any_target(self):
        before=(self.config/'agents/goal-worker.md').read_bytes()
        r=self.run_install(self.relocated,'skill','--config-dir',str(self.config),expected=2)
        self.assertIn('overwrite',r.stderr)
        self.assertEqual(before,(self.config/'agents/goal-worker.md').read_bytes())

    def test_one_existing_role_does_not_leave_a_partial_install(self):
        with tempfile.TemporaryDirectory(prefix='goal-install-conflict-') as tmp:
            config=Path(tmp);(config/'agents').mkdir();card=config/'agents/goal-worker.md';card.write_text('user-owned\n')
            self.run_install(self.relocated,'skill','--config-dir',str(config),expected=2)
            self.assertEqual(card.read_text(),'user-owned\n')
            self.assertFalse((config/'skills').exists())
            self.assertEqual(list((config/'agents').iterdir()),[card])

    def test_symlinked_config_parents_cannot_write_outside_the_config(self):
        for folder in ('skills', 'agents'):
            with self.subTest(folder=folder), tempfile.TemporaryDirectory(prefix='goal-install-symlink-') as tmp:
                base=Path(tmp);config=base/'config';outside=base/'outside'
                config.mkdir();outside.mkdir();(config/folder).symlink_to(outside,target_is_directory=True)
                r=self.run_install(self.relocated,'skill','--config-dir',str(config),expected=2)
                self.assertIn('real directory',r.stderr)
                self.assertEqual(list(outside.iterdir()),[])
                self.assertEqual(list(config.iterdir()),[config/folder])

    def test_symlinked_install_lock_cannot_lock_an_unrelated_file(self):
        with tempfile.TemporaryDirectory(prefix='goal-install-lock-link-') as tmp:
            base=Path(tmp);config=base/'config';config.mkdir();outside=base/'outside';outside.write_text('keep\n')
            (config/'.goal-loop-install.lock').symlink_to(outside)
            self.run_install(self.relocated,'skill','--config-dir',str(config),expected=2)
            self.assertEqual(outside.read_text(),'keep\n')
            self.assertFalse((config/'skills').exists())
            self.assertFalse((config/'agents').exists())

    def test_missing_payload_cannot_produce_a_successful_partial_package(self):
        with tempfile.TemporaryDirectory(prefix='goal-install-missing-') as tmp:
            source=Path(tmp)/'source';(source/'scripts').mkdir(parents=True);(source/'assets').mkdir()
            shutil.copy2(ROOT/'scripts/goal_install.py',source/'scripts/goal_install.py')
            (source/'assets/install-files.json').write_text('["missing-runtime.py"]')
            target=Path(tmp)/'result'
            self.run_install(source,'plugin','--output',str(target),expected=2)
            self.assertFalse(target.exists())

    def test_installed_doctor_and_real_go_work_without_original_install_path(self):
        self.run_install(self.skill,'doctor')
        for package in [self.skill,self.relocated]:
            r=subprocess.run(['bash',str(package/'examples/quickstart-one-shot/run.sh')],
                             cwd=self.work,capture_output=True,text=True,timeout=40)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('GATE: GO ',r.stdout)

    def test_gawk_fallback_keeps_its_executable_after_the_search_loop(self):
        # Force the fallback discovery branch while using a real GNU awk.
        script='command(){ if [ "$1" = -v ] && [ "${2:-}" = gawk ]; then return 1; fi; builtin command "$@"; }; . "$1"; gawk \'BEGIN{if(match("yes",/(yes)/,a))print a[1]}\''
        r=subprocess.run(['bash','-c',script,'fallback',str(self.skill/'scripts/goal_parse.sh')],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(r.stdout.strip(),'yes')


if __name__=='__main__':
    unittest.main()
