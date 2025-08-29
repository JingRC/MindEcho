import importlib, sys, os
print('PY', sys.version.split('\n')[0])
print('EXE', sys.executable)
print('HAS_SPLEETER', bool(importlib.util.find_spec('spleeter')))
print('SPLEETER_MODEL_PATH', os.environ.get('SPLEETER_MODEL_PATH'))
