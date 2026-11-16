"""Module alias for the canonical layered implementation."""
from importlib import import_module
import sys

_implementation = import_module(".domain.camera.capture_modes", __package__)
sys.modules[__name__] = _implementation
