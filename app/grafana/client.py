"""
Grafana OnCall API client functions.

This module is kept for future extensions.
All currently used functions are in scheduler.py
"""
import logging
from typing import Optional, Mapping, Any, Dict
import httpx

from app.config import settings

logger = logging.getLogger(__name__)