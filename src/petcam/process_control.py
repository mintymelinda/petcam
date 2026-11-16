"""Module alias for the canonical layered implementation."""
import sys
from .infrastructure.system import processes as _implementation
sys.modules[__name__] = _implementation
