"""Module alias for the canonical layered implementation."""
import sys
from .application import camera_configuration import camera_configuration as _implementation
sys.modules[__name__] = _implementation
