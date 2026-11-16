"""Module alias for the canonical layered implementation."""
import sys
from .domain import timelapse import policy import policy as _implementation
sys.modules[__name__] = _implementation
