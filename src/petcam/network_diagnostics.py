"""Module alias for the canonical layered implementation."""
import sys
from .infrastructure.network import diagnostics as _implementation
sys.modules[__name__] = _implementation
