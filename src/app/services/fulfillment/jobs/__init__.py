"""
Fulfillment Jobs Package

ARQ task definitions for background label generation.
"""

from .create_label_job import create_label

__all__ = ["create_label"]
