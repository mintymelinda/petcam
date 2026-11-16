"""Module alias for the canonical layered implementation."""
from importlib import import_module
import sys

_implementation = import_module(".security.sessions", __package__)
sys.modules[__name__] = _implementation
