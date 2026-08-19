"""
Carrier Adapters Package

Exports the CarrierAdapter interface and all concrete implementations.
"""

from .interface import CarrierAdapter, CarrierError, LabelResult
from .manual_adapter import ManualCarrierAdapter
from .dhl_adapter import DhlAdapter, build_dhl_adapter

__all__ = [
    "CarrierAdapter",
    "CarrierError",
    "LabelResult",
    "ManualCarrierAdapter",
    "DhlAdapter",
    "build_dhl_adapter",
]
