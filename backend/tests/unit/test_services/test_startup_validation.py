"""Regression tests for main._validate_startup_models (issue #140).

The startup hook used to re-raise on *any* exception out of
rag_service.validate_configured_models. That conflated two very different
failure modes:

  1. Operator misconfigured rag.haiku_model / rag.sonnet_model — a real bug
     we want to surface loud at boot (ConfiguredModelError).

  2. Postgres briefly unavailable during a rolling deploy or docker-compose
     boot race (OperationalError) — a transient condition that should NOT
     prevent the API from coming up.

After the fix, only ConfiguredModelError aborts startup; everything else is
logged and swallowed so the next restart (or a manual reload) gets another
shot at validating once the DB is back.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

import main
import rag_service


class TestValidateStartupModels:
    def test_happy_path_no_raise(self):
        with patch.object(rag_service, "validate_configured_models", return_value={"rag.haiku_model": "claude-haiku-x"}):
            main._validate_startup_models()  # must not raise

    def test_configured_model_error_propagates(self):
        """A bad model id is fatal — startup must crash so the operator sees it."""
        err = rag_service.ConfiguredModelError("rag.haiku_model is empty")
        with patch.object(rag_service, "validate_configured_models", side_effect=err):
            with pytest.raises(rag_service.ConfiguredModelError):
                main._validate_startup_models()

    def test_db_operational_error_is_swallowed(self):
        """Issue #140: DB momentarily unavailable must not block the API.
        Without the fix, this raised out of the startup hook and the entire
        service failed to boot during rolling deploys."""
        err = OperationalError("SELECT 1", {}, Exception("could not connect"))
        with patch.object(rag_service, "validate_configured_models", side_effect=err):
            main._validate_startup_models()  # must not raise

    def test_generic_exception_is_swallowed(self):
        """Any non-ConfiguredModelError exception (network, pool exhaustion,
        unexpected schema mismatch, etc.) is treated as transient."""
        with patch.object(rag_service, "validate_configured_models", side_effect=RuntimeError("boom")):
            main._validate_startup_models()  # must not raise

    def test_psycopg2_style_operational_error_is_swallowed(self):
        """Some call paths raise the bare psycopg2 OperationalError instead of
        the SQLAlchemy wrapper. Both must be tolerated."""
        try:
            from psycopg2 import OperationalError as PgOperationalError
        except Exception:
            pytest.skip("psycopg2 not installed in this test env")
        with patch.object(rag_service, "validate_configured_models", side_effect=PgOperationalError("server closed the connection")):
            main._validate_startup_models()  # must not raise

    def test_import_failure_is_swallowed(self):
        """Defense for partial installs / split deployments where rag_service
        is missing — startup should not be held hostage by an import error."""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "rag_service":
                raise ImportError("rag_service module unavailable")
            return real_import(name, *a, **kw)

        with patch.object(builtins, "__import__", side_effect=fake_import):
            main._validate_startup_models()  # must not raise
