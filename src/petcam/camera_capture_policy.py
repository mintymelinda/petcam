"""Module alias for the canonical layered implementation."""
import sys
from .domain import camera import capture_policy import capture_policy as _implementation
sys.modules[__name__] = _implementation
