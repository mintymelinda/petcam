"""Module alias for the canonical layered implementation."""
import sys
from .application import capture_status as _implementation
sys.modules[__name__] = _implementation
