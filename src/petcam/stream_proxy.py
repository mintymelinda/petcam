"""Module alias for the canonical layered implementation."""
import sys
from .infrastructure import streaming import proxy import proxy as _implementation
sys.modules[__name__] = _implementation
