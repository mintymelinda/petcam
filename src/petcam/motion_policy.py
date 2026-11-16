"""Module alias for the canonical layered implementation."""
import sys
from .domain.motion import policy as _implementation
sys.modules[__name__] = _implementation
