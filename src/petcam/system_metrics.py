"""Module alias for the canonical layered implementation."""
import sys
from .infrastructure import system import metrics import metrics as _implementation
sys.modules[__name__] = _implementation
