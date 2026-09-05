"""Put the repo root on sys.path so research scripts can import the
top-level trading modules (data_loader, smc_engine, backtest_engine, ...)
when run as `python3 research/<script>.py` from the repo root.

Import this first, before importing any top-level module:
    import _paths  # noqa: F401
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
