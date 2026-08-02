"""scheduler.py — Compatibility shim: delegates to backend/scheduler/scheduler.py."""
from backend.scheduler.scheduler import *

if __name__ == "__main__":
    from backend.scheduler.scheduler import main
    main()
