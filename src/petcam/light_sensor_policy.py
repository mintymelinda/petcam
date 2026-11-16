"""Module alias for the canonical layered implementation."""
import sys
from .features.light_sensor import policy as _implementation
sys.modules[__name__] = _implementation
