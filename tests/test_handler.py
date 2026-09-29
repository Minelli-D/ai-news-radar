import json
import logging
import time
from typing import Any

import pytest

from collector import handler
from collector.pipeline import RunReport, SourceReport


class Context:
    def get_remaining_time_in_millis(self) -> int:
        return 60_000


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TABLE_NAME", "ai-news-items")
    monkeypatch.setenv("BUCKET_NAME", "site-bucket")
    monkeypatch.setenv("SITE_URL", "https://d111111abcdef8.cloudfront.net")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")


def fake_run(report: RunReport, calls: list[dict[str, Any]]) -> Any:
    def run(sources: object, **kwargs: Any) -> RunReport:
        calls.append({"sources": sources, **kwargs})
        return report

    return run


def test_missing_configuration_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TABLE_NAME", raising=False)

    with pytest.raises(handler.CollectorError, match="TABLE_NAME"):
        handler.lambda_handler({}, Context())


@pytest.mark.usefixtures("env")
def test_runs_every_source_and_logs_one_summary_line(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[dict[str, Any]] = []
    report = RunReport(
        [SourceReport("openai", fetched=8, new=1)], ["news.json"], deferred=0, duration_ms=5
    )
    monkeypatch.setattr(handler, "run", fake_run(report, calls))

    with caplog.at_level(logging.INFO):
        result = handler.lambda_handler({}, Context())

    assert result == report.summary()
    [call] = calls
    assert [s.slug for s in call["sources"]] == [
        "anthropic",
        "openai",
        "deepseek",
        "google",
        "aws",
        "huggingface",
    ]
    assert call["site_url"] == "https://d111111abcdef8.cloudfront.net"
    assert 50 < call["deadline"] - time.monotonic() <= 60
    [record] = [r for r in caplog.records if r.getMessage().startswith("collector run finished")]
    assert (
        json.loads(record.getMessage().removeprefix("collector run finished ")) == report.summary()
    )
    assert record.run == report.summary()  # type: ignore[attr-defined]


@pytest.mark.usefixtures("env")
def test_raises_when_every_source_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    report = RunReport(
        [SourceReport("openai", error="HTTP 403"), SourceReport("aws", error="timed out")],
        ["news.json"],
        deferred=0,
        duration_ms=5,
    )
    monkeypatch.setattr(handler, "run", fake_run(report, []))

    with pytest.raises(handler.CollectorError, match="every source failed"):
        handler.lambda_handler({}, Context())
