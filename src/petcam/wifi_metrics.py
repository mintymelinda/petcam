"""Module alias for the canonical layered implementation."""
import sys
from .infrastructure.network import wifi_metrics as _implementation
sys.modules[__name__] = _implementation
