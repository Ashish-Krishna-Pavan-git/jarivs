import importlib
_mod = importlib.import_module("backend.storage.dedupe")
def __getattr__(name):
    return getattr(_mod, name)
def __dir__():
    return dir(_mod)
