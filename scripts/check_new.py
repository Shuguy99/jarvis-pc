#!/usr/bin/env python3
"""Check all new skill files compile."""

import py_compile, os, sys

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'jarvis', 'skills')
new_skills = [
    'volume', 'timer_skill', 'clipboard', 'calculator', 'battery',
    'bluetooth', 'brightness', 'screenshot_save', 'dictaphone',
    'crypto', 'unit_converter', 'password_gen', 'git_helper',
    'code_snippets', 'email', 'self_update', 'weather_alert', 'notion_tasks',
]
errors = []
for name in new_skills:
    f = os.path.join(D, f'{name}.py')
    if not os.path.exists(f):
        errors.append(f'{name}: FILE NOT FOUND')
        continue
    try:
        py_compile.compile(f, doraise=True)
        print(f'OK  {name}')
    except py_compile.PyCompileError as e:
        errors.append(f'{name}: {e}')
        print(f'ERR {name}: {e}')

if errors:
    print(f'\n{len(errors)} errors')
    sys.exit(1)
else:
    print(f'\nAll {len(new_skills)} files OK')
