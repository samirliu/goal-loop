#!/usr/bin/env python3
"""Check clean installs with a local cc-haha CLI and its actual Bun loaders.

Administrative CLI calls, loader inspection and synthetic hook replay only;
never starts an inference session or changes the user's real configuration.
Keep --output outside the checkout. Requires the harness source tree and Bun.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROLES = {'goal-worker', 'goal-mech-worker', 'goal-critic', 'goal-checker-req', 'goal-adjudicator'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def check(harness, output, bun):
    require(not output.exists() and not output.is_symlink(), 'choose a fresh --output directory')
    require(not output.is_relative_to(ROOT), '--output must be outside the checkout')
    cli = harness/'bin/claude-haha'
    require(cli.is_file(), 'missing harness CLI: '+str(cli))
    output.mkdir(parents=True)
    project = output/'project'; project.mkdir()
    config = output/'plugin config'
    env = {**os.environ, 'CLAUDE_CONFIG_DIR': str(config),
           'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'DISABLE_TELEMETRY': '1'}
    env.pop('CLAUDE_CODE_USE_NATIVE_FILE_SEARCH', None)
    receipts = []

    def run(name, argv, *, extra=None, stdin=None):
        result = subprocess.run([str(x) for x in argv], cwd=project,
                                env={**env, **(extra or {})}, input=stdin,
                                text=True, capture_output=True, timeout=60)
        (output/(name+'.stdout')).write_text(result.stdout)
        (output/(name+'.stderr')).write_text(result.stderr)
        receipts.append(dict(name=name, argv=[str(x) for x in argv], exit=result.returncode))
        (output/'commands.json').write_text(json.dumps(receipts, indent=2)+'\n')
        require(result.returncode == 0, name+' failed; see '+str(output))
        return result.stdout

    version = (ROOT/'VERSION').read_text().strip()
    package = output/'source package'
    run('build', [sys.executable, '-I', ROOT/'scripts/goal_install.py', 'plugin', '--output', package])
    skill_config = output/'skill config'; skill_config.mkdir()
    sentinel = '{"permissions":{"allow":["Read"]},"hooks":{}}\n'
    (skill_config/'settings.json').write_text(sentinel)
    run('skill-install', [sys.executable, '-I', package/'scripts/goal_install.py', 'skill',
                          '--config-dir', skill_config, '--with-companion'])
    host_version = run('host-version', [cli, '--version']).strip()
    run('validate-plugin', [cli, 'plugin', 'validate', package/'.claude-plugin/plugin.json'])
    run('validate-marketplace', [cli, 'plugin', 'validate', package])
    run('marketplace-add', [cli, 'plugin', 'marketplace', 'add', package])
    run('plugin-install', [cli, 'plugin', 'install', 'goal-loop-host@goal-loop'])
    run('plugin-list', [cli, 'plugin', 'list'])

    def imp(module):
        return json.dumps(str(harness/'src'/module))

    def roles_intact(agents):
        for agent in agents:
            role = agent['name'].split(':')[-1]
            if role not in ROLES:
                continue
            text = (ROOT/'agents'/(role+'.md')).read_text()
            model = re.search(r'^model: (.+)$', text, re.M)[1]
            tools = re.search(r'^tools: (.+)$', text, re.M)[1].split(', ')
            body = text[text.index('\n---', 4)+4:].strip()
            require(agent['model'] == model and agent['tools'] == tools, role+' model/tools changed')
            require(body in agent['prompt'], role+' protocol changed')

    probe = output/'plugin-probe.ts'
    probe.write_text(
        'import {setInlinePlugins} from '+imp('bootstrap/state.ts')+';\n'
        'import {getPluginSkills} from '+imp('utils/plugins/loadPluginCommands.ts')+';\n'
        'import {loadPluginAgents} from '+imp('utils/plugins/loadPluginAgents.ts')+';\n'
        'import {loadAllPluginsCacheOnly} from '+imp('utils/plugins/pluginLoader.ts')+';\n'
        'setInlinePlugins(process.argv[2] ? [process.argv[2]] : []);\n'
        'const plugins=await loadAllPluginsCacheOnly(); const skills=[];\n'
        'for(const s of await getPluginSkills()) skills.push({name:s.name,prompt:await s.getPromptForCommand("install-probe",{})});\n'
        'const agents=(await loadPluginAgents()).map(a=>({name:a.agentType,tools:a.tools,model:a.model,prompt:a.getSystemPrompt()}));\n'
        'console.log(JSON.stringify({skills,agents,plugins:plugins.enabled.map(p=>({name:p.name,path:p.path,hooks:p.hooksConfig||p.hooks})),errors:plugins.errors}));\n'
        'process.exit(0);\n')

    def plugin_probe(label, path=None):
        extra = {} if path is None else {'CLAUDE_CONFIG_DIR': str(output/(label+' config'))}
        data = json.loads(run(label, [bun, 'run', probe, *([] if path is None else [path])], extra=extra))
        require(not data['errors'], label+' loader errors')
        require({s['name'] for s in data['skills']} == {'goal-loop-host:goal-loop', 'goal-loop-host:contract-forge'}, label+' skills missing')
        require({a['name'] for a in data['agents']} == {'goal-loop-host:'+r for r in ROLES}, label+' roles missing')
        roles_intact(data['agents'])
        plugin = data['plugins'][0]
        require(len(plugin['hooks']) == 8, label+' hooks missing')
        text = '\n'.join(p.get('text', '') for s in data['skills'] if s['name']=='goal-loop-host:goal-loop' for p in s['prompt'])
        require(plugin['path'].rstrip('/') in text and '${CLAUDE_PLUGIN_ROOT}' not in text, label+' resource root not rendered')
        canonical = (ROOT/'SKILL.md').read_text()
        canonical = canonical[canonical.index('\n---', 4)+4:]
        require(canonical in text, label+' canonical protocol changed')
        return data

    plugin_probe('persistent-loader')
    records = json.loads((config/'plugins/installed_plugins.json').read_text())
    cache = Path(records['plugins']['goal-loop-host@goal-loop'][0]['installPath'])
    require(cache.name == version, 'host did not create expected version cache')
    relocated = output/'relocated plugin'/version; relocated.parent.mkdir()
    package.rename(relocated)
    plugin_probe('version-cache-loader', cache)
    data = plugin_probe('relocated-loader', relocated)
    run('plugin-agents', [cli, '--plugin-dir', relocated, 'agents'],
        extra={'CLAUDE_CONFIG_DIR': str(output/'cli inline config')})

    skill_probe = output/'skill-probe.ts'
    skill_probe.write_text(
        'import {getSkillDirCommands} from '+imp('skills/loadSkillsDir.ts')+';\n'
        'import {getAgentDefinitionsWithOverrides} from '+imp('tools/AgentTool/loadAgentsDir.ts')+';\n'
        'const skills=[]; for(const s of await getSkillDirCommands(process.cwd())) if(["goal-loop","contract-forge"].includes(s.name)) skills.push({name:s.name,prompt:await s.getPromptForCommand("install-probe",{})});\n'
        'const a=await getAgentDefinitionsWithOverrides(process.cwd());\n'
        'console.log(JSON.stringify({skills,agents:a.activeAgents.filter(a=>a.agentType.startsWith("goal-")).map(a=>({name:a.agentType,tools:a.tools,model:a.model,prompt:a.getSystemPrompt()})),failedFiles:a.failedFiles}));\n'
        'process.exit(0);\n')
    skill_env = {'CLAUDE_CONFIG_DIR': str(skill_config)}
    default = json.loads(run('skill-default-loader', [bun, 'run', skill_probe], extra=skill_env))
    missing_default = sorted(ROLES - {a['name'] for a in default['agents']})
    run('skill-default-agents', [cli, 'agents'], extra=skill_env)
    native_env = {**skill_env, 'CLAUDE_CODE_USE_NATIVE_FILE_SEARCH': '1'}
    native = json.loads(run('skill-native-loader', [bun, 'run', skill_probe], extra=native_env))
    require(ROLES <= {a['name'] for a in native['agents']}, 'skill native discovery missing roles')
    require({'goal-loop', 'contract-forge'} <= {s['name'] for s in native['skills']}, 'skill discovery incomplete')
    require(not native.get('failedFiles'), 'skill agent parse failed')
    roles_intact(native['agents'])
    agent_list = run('skill-native-agents', [cli, 'agents'], extra=native_env)
    require(all(r in agent_list for r in ROLES), 'native CLI roles missing')
    require((skill_config/'settings.json').read_text() == sentinel, 'skill settings changed')
    for label, root in [('skill', skill_config/'skills/goal-loop'), ('plugin', relocated)]:
        run(label+'-doctor', [sys.executable, '-I', root/'scripts/goal_install.py', 'doctor'])
        require('GATE: GO ' in run(label+'-go', ['bash', root/'examples/quickstart-one-shot/run.sh']), label+' real GO missing')
        run(label+'-companion', ['bash', root/'companions/contract-forge/tests/run_fixtures.sh'])

    # Replay declared commands with fixtures, not a claim of live host delivery.
    hook_project = output/'hook project'; hook_project.mkdir()
    hook_env = {'CLAUDE_PLUGIN_ROOT': str(relocated)}
    events = list(data['plugins'][0]['hooks'])
    for event in events:
        command = data['plugins'][0]['hooks'][event][0]['hooks'][0]['command']
        payload = dict(hook_event_name=event, session_id='installation-replay', cwd=str(hook_project),
                       prompt='/goal-loop-host:goal-loop verify installed resources',
                       tool_name='Read', tool_input={'file_path': str(hook_project/'sample.txt')})
        run('hook-'+event, ['/bin/sh', '-c', command], extra=hook_env, stdin=json.dumps(payload))
        if event == 'UserPromptSubmit':
            run('hook-enter', [sys.executable, '-I', relocated/'scripts/goal_host.py', 'enter', hook_project, '60', '--context'])
    prompts = list((hook_project/'.goal/evidence/host').glob('prompt-*.json'))
    require(len(prompts) == 1 and 'verify installed resources' in prompts[0].read_text(), 'namespaced prompt not captured')
    summary = dict(host=host_version, version=version, persistent_install=True,
                   version_cache_and_relocation=True, plugin_skills=2, plugin_roles=5, hook_commands_replayed=events,
                   standalone_roles_missing_by_default=missing_default, standalone_with_native_file_search=True,
                   installed_go=['skill', 'plugin'], companion_fixtures=['skill', 'plugin'], settings_preserved=True,
                   inference_tested=False, live_hook_delivery_tested=False)
    (output/'report.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bun', default=shutil.which('bun'))
    args = parser.parse_args()
    require(args.bun, 'Bun is required')
    print(json.dumps(check(args.harness_root.resolve(), args.output.absolute(), args.bun), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print('INSTALL CHECK: ERROR '+str(exc), file=sys.stderr)
        sys.exit(1)
