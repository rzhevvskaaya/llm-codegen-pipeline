"""
pytest configuration.

Sets PYTHONPATH so tests can import `pipeline` without installation.
"""
import sys
import os

# Add src/ to path so `import pipeline` works from any working directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Set a dummy API key so Settings() doesn't raise during import in unit tests
os.environ.setdefault("LLM_API_KEY", "test-key-unit-tests-only")
