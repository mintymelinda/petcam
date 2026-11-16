"""Module alias for the canonical layered implementation."""
import sys
from .domain import camera import capture_modes import capture_modes as _implementation
sys.modules[__name__] = _implementation
