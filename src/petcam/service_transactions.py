"""Module alias for the canonical layered implementation."""
from importlib import import_module
import sys

_implementation = import_module(".application.service_transactions", __package__)
sys.modules[__name__] = _implementation
