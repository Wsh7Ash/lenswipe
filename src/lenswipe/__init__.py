"""lenswipe — offline metadata inventory and wiper for JPEG/PNG/WebP."""

__version__ = "1.0.0"

from .inspect import Inventory, scan_bytes, scan_file

__all__ = ["Inventory", "scan_bytes", "scan_file", "__version__"]