import importlib
_mod = importlib.import_module("backend.collectors.scraper")
def __getattr__(name):
    return getattr(_mod, name)
def __dir__():
    return dir(_mod)
