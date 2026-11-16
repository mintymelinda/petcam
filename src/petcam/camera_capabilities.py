"""Module alias for the canonical layered implementation."""
import sys
from .domain.camera import capabilities as _implementation
sys.modules[__name__] = _implementation
