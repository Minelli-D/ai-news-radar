from datetime import UTC, datetime

import pytest

from collector import models

# The fixtures were captured on 2026-09-25; freeze "now" so date clamping is deterministic.
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(models, "utcnow", lambda: NOW)
