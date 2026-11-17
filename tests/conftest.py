"""Test-wide settings: unit tests never call a real LLM.

Tests that exercise an LLM path pass a fake ``generate`` function explicitly.
"""

import os

os.environ.setdefault("GUJRERA_LLM_ROUTER", "false")
os.environ.setdefault("GUJRERA_RAG_LLM", "false")
os.environ.setdefault("GUJRERA_ANALYTICS_LLM", "false")
os.environ.setdefault("GUJRERA_LLM_PHRASING", "false")
