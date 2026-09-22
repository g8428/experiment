import py_compile, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
try:
    py_compile.compile('server.py', doraise=True)
    print('server.py syntax OK')
except py_compile.PyCompileError as e:
    print(f'SYNTAX ERROR: {e}')
