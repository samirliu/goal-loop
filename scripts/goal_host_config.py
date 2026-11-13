#!/usr/bin/env python3
"""Print an opt-in native hook config. Never edit host/global settings."""
import argparse
import json
from pathlib import Path
import shlex


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backend', choices=('codex', 'claude'))
    args = parser.parse_args()
    command = shlex.join(['python3', '-I', str(Path(__file__).with_name('goal_host.py').resolve()),
                          'hook', '--backend', args.backend])
    events = ['UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'SubagentStart', 'SubagentStop', 'Stop', 'SessionEnd']
    events.append('Interrupt' if args.backend == 'codex' else 'PostToolUseFailure')
    print(json.dumps({'hooks': {event: [{'hooks': [dict(type='command', command=command,
                         timeout=1 if event == 'SessionEnd' else 5)]}] for event in events}}, indent=2))
