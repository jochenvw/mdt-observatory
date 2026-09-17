import asyncio
import logging
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from mdt import engine as engine_module
from mdt.agents import analyze
from mdt.config import Settings
from mdt.engine import Engine
from mdt.models import Role
from mdt.store import Store


async def test_role_spans_and_logs_exclude_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(engine_module, "tracer", provider.get_tracer("mdt.test"))
    caplog.set_level(logging.INFO, logger="mdt")
    settings = Settings(db_path=str(tmp_path / "telemetry.db"), step_delay=0)
    engine = Engine(Store(settings.db_path), settings, analyze)
    meeting = await engine.start("rehearsal")
    await asyncio.gather(*list(engine.tasks))
    spans = exporter.get_finished_spans()
    assert len(spans) == 7
    assert {span.attributes["mdt.role"] for span in spans if span.attributes} == {
        role.value for role in Role
    }
    private_guidance = "SYNTHETIC_PRIVATE_NOTE: review growth kinetics."
    await engine.steer(meeting.id, Role.RADIOLOGY, private_guidance)
    await asyncio.gather(*list(engine.tasks))
    assert private_guidance not in caplog.text
    for span in exporter.get_finished_spans():
        assert span.name == "mdt.role.analyze"
        assert span.attributes and set(span.attributes) == {"mdt.role", "mdt.mode"}
    await engine.close()
    provider.shutdown()
