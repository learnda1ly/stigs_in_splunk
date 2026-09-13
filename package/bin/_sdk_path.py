"""Ensure vendored splunk-sdk (lib/splunklib) is importable in bin/ handlers."""

from __future__ import annotations

import os
import sys

_APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
_LIB = os.path.join(_APP_ROOT, "lib")

if os.path.isdir(_LIB) and _LIB not in sys.path:
    sys.path.insert(0, _LIB)
