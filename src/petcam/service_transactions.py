"""Module alias for the canonical layered implementation."""
import sys
from .application import service_transactions as _implementation
sys.modules[__name__] = _implementation
