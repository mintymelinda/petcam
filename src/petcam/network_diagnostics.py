"""Module alias for the canonical layered implementation."""
import sys
from .infrastructure import network import diagnostics import diagnostics as _implementation
sys.modules[__name__] = _implementation
