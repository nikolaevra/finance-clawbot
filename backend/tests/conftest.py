from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from tests.fakes import FakeSupabase

os.environ.setdefault("OPENAI_MODEL", "gpt-test")
os.environ.setdefault("OPENAI_MINI_MODEL", "gpt-test-mini")
os.environ.setdefault("OPENAI_EMBEDDING_MODEL", "text-embedding-test")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")


@pytest.fixture
def fake_supabase() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def flask_app() -> Flask:
    return Flask(__name__)


@pytest.fixture
def app_context(flask_app: Flask):
    with flask_app.app_context():
        yield


@pytest.fixture
def request_context(flask_app: Flask):
    with flask_app.test_request_context("/"):
        yield
