"""Module alias for the canonical layered implementation."""
import sys
from .infrastructure.streaming import proxy as _implementation
sys.modules[__name__] = _implementation
