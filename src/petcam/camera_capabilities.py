"""Module alias for the canonical layered implementation."""
import sys
from .domain import camera import capabilities import capabilities as _implementation
sys.modules[__name__] = _implementation
