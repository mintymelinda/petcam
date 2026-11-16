"""Module alias for the canonical layered implementation."""
import sys
from .domain.timelapse import policy as _implementation
sys.modules[__name__] = _implementation
