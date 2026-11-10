"""Bambuddy plugin for OrcaSlicer."""

__version__ = "0.3.2"  # x-release-please-version

try:
    import orca
except ImportError:  # imported outside OrcaSlicer, e.g. by the test suite
    orca = None

if orca is not None:
    from .plugin import BambuddyPlugin as BambuddyPlugin
