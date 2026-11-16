"""Module alias for the canonical layered implementation."""
import sys
from .security import sessions import sessions as _implementation
sys.modules[__name__] = _implementation
