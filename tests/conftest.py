"""
tests/conftest.py
-----------------
Root-level pytest configuration, loaded before any test module.

Loads .env so DATABASE_URL and other secrets are available to all tests
without relying on modules like agents/workflow.py calling load_dotenv()
as a side-effect of being imported. This makes the test suite order-
independent: integration tests that need Postgres work whether or not an
LLM module has been imported before them.

load_dotenv(override=False) never overwrites env vars already set in the
shell or by CI — explicit env vars always win over the .env file.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=False)
