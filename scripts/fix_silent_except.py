"""Замена except Exception: pass на except Exception: log.debug(...).

Классификация:
- pass → log.debug("...")
- continue → log.debug("..."); continue  
- return X → log.debug("..."); return X
- Блоки с комментарием после except — добавляет лог, комментарий сохраняет
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "jarvis"


def get_context(lines: list[str], exc_line: int) -> str:
    """Извлекает контекст для лог-сообщения из кода вокруг except."""
    # Ищем try-блок выше
    try_start = exc_line - 1
    while try_start >= 0 and "try:" not in lines[try_start]:
        try_start -= 1
    
    # Содержимое между try и except
    body_lines = [lines[i].strip() for i in range(try_start + 1, exc_line) if lines[i].strip()]
    # Берем последнюю значимую строку как контекст
    ctx = ""
    for line in reversed(body_lines):
        if line and not line.startswith("#"):
            # Обрезаем длинные строки
            ctx = line[:80]
            break
    return ctx


def make_log_msg(filepath: str, line_num: int, body: str, ctx: str) -> str:
    """Генерирует подходящее log.debug сообщение."""
    module = filepath.replace("/", ".").replace(".py", "")
    short = Path(filepath).name.replace(".py", "")
    
    # Если body содержит return с текстом — это уже обработка, log.debug перед ней
    if body.startswith("return"):
        return f'log.debug("{short}: ошибка (line {line_num}), используем fallback")'
    
    if body == "continue":
        return f'log.debug("{short}: пропуск элемента (line {line_num})")'
    
    if body == "pass":
        if ctx:
            snippet = ctx[:50].replace('"', "'")
            return f'log.debug("{short}: не критичная ошибка при {snippet}")'
        return f'log.debug("{short}: не критичная ошибка (line {line_num})")'
    
    # Для self._xxx = fallback
    if body.startswith("self._"):
        attr = body.split("=")[0].strip()
        return f'log.debug("{short}: ошибка инициализации {attr}, используется fallback")'
    
    return f'log.debug("{short}: ошибка (line {line_num})")'


def process_file(filepath: str) -> int:
    """Обрабатывает один файл. Возвращает число замен."""
    path = Path(filepath)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    
    # Проверяем есть ли log = logging.getLogger в файле
    has_log = any("log = logging.getLogger" in line for line in lines)
    if not has_log:
        return 0
    
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if not re.search(r'except\s+Exception\s*:', line):
            i += 1
            continue
        
        # Пропускаем если следующий непустой line уже содержит log.
        j = i + 1
        while j < len(lines) and lines[j].strip() == '':
            j += 1
        if j >= len(lines):
            i += 1
            continue
        
        next_content = lines[j].rstrip()
        stripped = next_content.strip()
        
        # Пропускаем если уже есть логирование в блоке except
        block_end = j + 1
        while block_end < len(lines) and lines[block_end].strip() and not lines[block_end][0].isalpha() and lines[block_end].strip() not in ('pass', 'continue'):
            block_end += 1
        block_text = ''.join(lines[i+1:block_end])
        if 'log.' in block_text:
            i = j + 1
            continue
        
        # Пропускаем assistant.py:255 (face recognition — уже есть комментарий-обоснование)
        if 'assistant.py' in filepath and 'Распознавание лиц' in stripped:
            i = j + 1
            continue
        
        # Пропускаем rag.py:156 (уже имеет комментарий-обоснование + fallback логика)
        if 'rag.py' in filepath and 'Fallback' in stripped:
            i = j + 1
            continue
        
        # Определяем что делать с body
        indent = len(lines[j]) - len(lines[j].lstrip())
        indent_str = ' ' * indent
        
        if stripped == 'pass':
            ctx = get_context(lines, i)
            msg = make_log_msg(filepath, i + 1, 'pass', ctx)
            # Заменяем pass на log.debug
            lines[j] = f'{indent_str}{msg}\n'
            changes += 1
            
        elif stripped == 'continue':
            ctx = get_context(lines, i)
            msg = make_log_msg(filepath, i + 1, 'continue', ctx)
            lines[j] = f'{indent_str}{msg}\n{indent_str}continue\n'
            changes += 1
            
        elif stripped.startswith('return'):
            # Добавляем log.debug перед return
            msg = make_log_msg(filepath, i + 1, stripped, '')
            lines[j] = f'{indent_str}{msg}\n{lines[j]}'
            changes += 1
            
        elif stripped.startswith('self._') and '=' in stripped:
            # Инициализация с fallback
            msg = make_log_msg(filepath, i + 1, stripped, '')
            lines[j] = f'{indent_str}{msg}\n{lines[j]}'
            changes += 1
            
        elif stripped.startswith('count') and '=' in stripped:
            msg = make_log_msg(filepath, i + 1, stripped, '')
            lines[j] = f'{indent_str}{msg}\n{lines[j]}'
            changes += 1
            
        elif stripped.startswith('entries') and '=' in stripped:
            # fallback для glob → name matching
            msg = make_log_msg(filepath, i + 1, stripped, 'glob pattern fallback')
            lines[j] = f'{indent_str}{msg}\n{lines[j]}'
            changes += 1
        else:
            # Для прочих — просто добавляем log.debug + сохраняем оригинальный body
            msg = make_log_msg(filepath, i + 1, stripped, '')
            lines[j] = f'{indent_str}{msg}\n{lines[j]}'
            changes += 1
        
        i = j + 1
    
    if changes > 0:
        path.write_text(''.join(lines), encoding='utf-8')
        print(f'  {filepath}: {changes} replacements')
    
    return changes


def main():
    total = 0
    for py_file in sorted(ROOT.rglob('*.py')):
        rel = str(py_file.relative_to(ROOT.parent))
        total += process_file(rel)
    print(f'\nTotal: {total} silent except blocks fixed')


if __name__ == '__main__':
    main()
