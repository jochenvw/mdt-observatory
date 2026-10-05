import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from azure.core import MatchConditions
from azure.core.exceptions import (
    ResourceExistsError,
    ResourceModifiedError,
    ResourceNotFoundError,
)

from mdt import blob_store
from mdt.agents import analyze
from mdt.config import Settings
from mdt.engine import Engine
from mdt.models import Meeting, Memory, Role
from mdt.store import Persistence, Store

ACCOUNT = "https://example.blob.core.windows.net"


class FakeContainer:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.counter = 0
        self.available = True
        self.listings: list[int | None] = []

    def get_container_properties(self) -> dict[str, str]:
        if not self.available:
            error = ResourceNotFoundError("Container missing")
            error.error_code = "ContainerNotFound"
            raise error
        return {"name": "mdt-state"}

    def download_blob(self, name: str) -> Any:
        self.get_container_properties()
        if name not in self.records:
            error = ResourceNotFoundError("Blob missing")
            error.error_code = "BlobNotFound"
            raise error
        record = self.records[name]
        return SimpleNamespace(
            properties=SimpleNamespace(etag=record["etag"]),
            readall=lambda: record["payload"],
        )

    def get_blob_client(self, name: str) -> Any:
        def upload_blob(data: bytes, *, overwrite: bool, **kwargs: Any) -> dict[str, str]:
            self.get_container_properties()
            existing = self.records.get(name)
            if existing and not overwrite:
                raise ResourceExistsError(
                    "Existing snapshot cannot be overwritten without an ETag."
                )
            if overwrite:
                assert kwargs["match_condition"] == MatchConditions.IfNotModified
                if not existing or existing["etag"] != kwargs["etag"]:
                    raise ResourceModifiedError("ETag conflict")
            self.counter += 1
            etag = str(self.counter)
            self.records[name] = {
                "payload": data,
                "etag": etag,
                "metadata": kwargs.get("metadata") or {},
            }
            return {"etag": etag}

        return SimpleNamespace(upload_blob=upload_blob)

    def list_blobs(self, *, name_starts_with: str, **kwargs: Any) -> "FakePaged":
        self.get_container_properties()
        self.listings.append(kwargs.get("results_per_page"))
        return FakePaged(
            SimpleNamespace(name=name, metadata=record["metadata"])
            for name, record in self.records.items()
            if name.startswith(name_starts_with)
        )


class FakePaged(list[Any]):
    """Eager stand-in for azure.core.paging.ItemPaged."""

    def by_page(self) -> Any:
        return iter([iter(self)])


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> FakeContainer:
    container = FakeContainer()
    client = MagicMock()
    client.get_container_client.return_value = container
    monkeypatch.setattr(blob_store, "BlobServiceClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(blob_store, "DefaultAzureCredential", MagicMock())
    monkeypatch.setattr(blob_store, "ManagedIdentityCredential", MagicMock())
    return container


def test_roundtrip_latest_count_and_restart(cloud: FakeContainer) -> None:
    first = blob_store.BlobStore(ACCOUNT, "mdt-state")
    assert first.latest() is None
    assert first.get("missing") is None
    assert first.count() == 0
    old = Meeting(id="older", created_at="2026-09-16T10:00:00+00:00")
    recent = Meeting(id="recent", created_at="2026-09-16T11:00:00+00:00")
    first.save(recent)
    first.save(old)
    assert first.count() == 2
    assert first.latest() == recent
    old.round = 2
    first.save(old)
    assert first.latest() == recent
    first.close()
    second = blob_store.BlobStore(ACCOUNT, "mdt-state")
    assert second.get(old.id) == old
    assert second.latest() == recent
    second.close()


def test_stale_writer_cannot_destroy_audit(cloud: FakeContainer) -> None:
    one = blob_store.BlobStore(ACCOUNT, "mdt-state")
    two = blob_store.BlobStore(ACCOUNT, "mdt-state")
    meeting = Meeting(id="meeting")
    one.save(meeting)
    stale = two.get(meeting.id)
    assert stale
    meeting.round = 2
    one.save(meeting)
    stale.round = 3
    with pytest.raises(ResourceModifiedError):
        two.save(stale)
    assert one.get(meeting.id).round == 2
    one.close()
    two.close()


def test_unread_existing_snapshot_is_not_overwritten(cloud: FakeContainer) -> None:
    one = blob_store.BlobStore(ACCOUNT, "mdt-state")
    two = blob_store.BlobStore(ACCOUNT, "mdt-state")
    one.save(Meeting(id="same"))
    with pytest.raises(ResourceExistsError):
        two.save(Meeting(id="same", round=99))
    one.close()
    two.close()


def test_dossier_is_written_once_and_legacy_blobs_load(cloud: FakeContainer) -> None:
    store = blob_store.BlobStore(ACCOUNT, "mdt-state")
    meeting = Meeting(id="split", created_at="2026-09-16T10:00:00+00:00", case={"id": "C"})
    store.save(meeting)
    meeting.round = 2
    store.save(meeting)
    static = cloud.records["meeting-static/split.json"]
    assert static["etag"] == "1", "the unchanged dossier is not rewritten per event"
    assert b'"case"' not in cloud.records["meetings/split.json"]["payload"]
    legacy = Meeting(id="legacy", created_at="2026-09-16T11:00:00+00:00", case={"id": "L"})
    cloud.records["meetings/legacy.json"] = {
        "payload": legacy.model_dump_json().encode(),
        "etag": "legacy",
        "metadata": {"created_at": legacy.created_at},
    }
    store.close()
    reopened = blob_store.BlobStore(ACCOUNT, "mdt-state")
    assert reopened.count() == 2, "dossier records are not counted as meetings"
    assert reopened.get("split") == meeting
    assert reopened.latest() == legacy
    legacy.round = 1
    reopened.save(legacy)
    assert reopened.get("legacy") == legacy
    reopened.close()


def test_explicit_memory_and_persistent_forget(cloud: FakeContainer) -> None:
    store = blob_store.BlobStore(ACCOUNT, "mdt-state")
    seed = Memory(
        id="preference",
        role=Role.RADIOLOGY,
        category="CLINICIAN_PREFERENCE",
        text="Inspect the growth trajectory.",
        source="Synthetic clinician note",
        date="2026-09-16",
    )
    memories = store.memories([seed])
    assert memories[0].status == "AVAILABLE"
    memories[0].status = "USED"
    store.save_memory(memories[0])
    assert store.memories([seed])[0].status == "AVAILABLE"
    memories[0].status = "FORGOTTEN"
    memories[0].text = ""
    memories[0].source = ""
    store.save_memory(memories[0])
    store.close()
    restored = blob_store.BlobStore(ACCOUNT, "mdt-state")
    assert restored.memories([seed])[0].status == "FORGOTTEN"
    assert restored.memories([seed])[0].text == ""
    assert restored.memories([seed], clinician_id="someone-else") == []
    restored.close()


def _seed() -> Memory:
    return Memory(
        id="preference",
        role=Role.RADIOLOGY,
        category="CLINICIAN_PREFERENCE",
        text="Inspect the growth trajectory.",
        source="Synthetic clinician note",
        date="2026-09-16",
    )


def _open(backend: str, tmp_path: Path) -> Persistence:
    if backend == "blob":
        return blob_store.BlobStore(ACCOUNT, "mdt-state")
    return Store(str(tmp_path / "contract.db"))


@pytest.mark.parametrize("backend", ["sqlite", "blob"])
def test_save_memory_rejects_uninitialized_memory(
    backend: str, cloud: FakeContainer, tmp_path: Path
) -> None:
    store = _open(backend, tmp_path)
    with pytest.raises(ValueError, match="not been initialized"):
        store.save_memory(_seed())
    store.close()


@pytest.mark.parametrize("backend", ["sqlite", "blob"])
def test_forget_persists_across_reload(
    backend: str, cloud: FakeContainer, tmp_path: Path
) -> None:
    store = _open(backend, tmp_path)
    memory = store.memories([_seed()])[0]
    memory.status = "FORGOTTEN"
    memory.text = ""
    memory.source = ""
    store.save_memory(memory)
    store.close()
    restored = _open(backend, tmp_path)
    reloaded = restored.memories([_seed()])[0]
    assert (reloaded.status, reloaded.text, reloaded.source) == ("FORGOTTEN", "", "")
    restored.close()


def test_missing_container_is_not_empty_success(cloud: FakeContainer) -> None:
    cloud.available = False
    with pytest.raises(ResourceNotFoundError):
        blob_store.BlobStore(ACCOUNT, "mdt-state")


def test_disappeared_container_is_not_missing_meeting(cloud: FakeContainer) -> None:
    store = blob_store.BlobStore(ACCOUNT, "mdt-state")
    cloud.available = False
    with pytest.raises(ResourceNotFoundError):
        store.get("missing")
    with pytest.raises(ResourceNotFoundError):
        store.ready()
    store.close()


def test_readiness_lists_one_page(cloud: FakeContainer) -> None:
    store = blob_store.BlobStore(ACCOUNT, "mdt-state")
    for index in range(5):
        store.save(Meeting(id=f"meeting-{index}"))
    cloud.listings.clear()
    store.ready()
    assert cloud.listings == [1]
    store.close()


def test_count_cache_tracks_new_meetings_and_restart(cloud: FakeContainer) -> None:
    store = blob_store.BlobStore(ACCOUNT, "mdt-state")
    store.save(Meeting(id="before-count"))
    assert store.count() == 1
    listed = len(cloud.listings)
    meeting = Meeting(id="counted")
    store.save(meeting)
    meeting.round = 2
    store.save(meeting)
    assert store.count() == 2
    assert len(cloud.listings) == listed, "cached count must not relist"
    cloud.available = False
    with pytest.raises(ResourceNotFoundError):
        store.save(Meeting(id="failed"))
    cloud.available = True
    assert store.count() == 2
    store.close()
    restarted = blob_store.BlobStore(ACCOUNT, "mdt-state")
    assert restarted.count() == 2
    restarted.close()


async def test_blob_retention_limit_uses_the_cached_count(
    cloud: FakeContainer, tmp_path: Path
) -> None:
    from mdt.engine import Conflict

    settings = Settings(db_path=str(tmp_path / "unused.db"), step_delay=0, max_meetings=2)
    engine = Engine(blob_store.BlobStore(ACCOUNT, "mdt-state"), settings, analyze)
    for _ in range(2):
        await engine.start("rehearsal")
        while engine.tasks:
            await asyncio.gather(*list(engine.tasks))
    with pytest.raises(Conflict, match="retention limit"):
        await engine.start("rehearsal")
    await engine.close()


def test_corrupt_creation_metadata_is_visible(cloud: FakeContainer) -> None:
    store = blob_store.BlobStore(ACCOUNT, "mdt-state")
    store.save(Meeting(id="corrupt"))
    cloud.records["meetings/corrupt.json"]["metadata"] = {}
    with pytest.raises(ValueError, match="creation metadata"):
        store.latest()
    store.close()


def test_production_uses_managed_identity(
    cloud: FakeContainer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONTAINER_APP_NAME", "mdt-observatory-vnet")
    store = blob_store.BlobStore(ACCOUNT, "mdt-state")
    blob_store.ManagedIdentityCredential.assert_called_once()
    blob_store.DefaultAzureCredential.assert_not_called()
    store.close()


@pytest.mark.parametrize("url", ["", "http://example.blob.core.windows.net", "https://example.com"])
def test_blob_endpoint_configuration_is_explicit(url: str) -> None:
    with pytest.raises(ValueError, match="HTTPS Azure Blob"):
        blob_store.BlobStore(url, "mdt-state")


async def test_complete_workflow_with_blob_persistence(cloud: FakeContainer) -> None:
    import asyncio

    store = blob_store.BlobStore(ACCOUNT, "mdt-state")
    engine = Engine(store, Settings(step_delay=0), analyze)

    async def settle() -> None:
        while engine.tasks:
            await asyncio.gather(*list(engine.tasks))

    meeting = await engine.start("rehearsal")
    await settle()
    await engine.steer(
        meeting.id,
        Role.RADIOLOGY,
        "I reviewed all nine liver sites, vessel margins and the lung nodule. The sites are "
        "mapped, the margins and remnant are adequate, and the nodule is not suspicious.",
    )
    await settle()
    await engine.followup(meeting.id)
    await settle()
    current = engine.get(meeting.id)
    for role in Role:
        if role not in current.concurrences:
            await engine.concur(meeting.id, role, "Reviewed", current.plan.version)
    assert current.phase == "DECISION_CAPTURED"
    exported = current.model_dump()
    await engine.close()
    restored = blob_store.BlobStore(ACCOUNT, "mdt-state")
    assert restored.latest().model_dump() == exported
    restored.close()


async def test_memory_write_failure_pauses_the_meeting(cloud: FakeContainer) -> None:
    import asyncio

    from mdt.engine import PersistenceFailure

    engine = Engine(blob_store.BlobStore(ACCOUNT, "mdt-state"), Settings(step_delay=0), analyze)
    meeting = await engine.start("rehearsal")
    await asyncio.gather(*list(engine.tasks))
    memory_id = engine.get(meeting.id).memories[0].id
    cloud.available = False
    with pytest.raises(PersistenceFailure):
        await engine.memory(meeting.id, memory_id, "forget")
    assert engine.get(meeting.id).phase == "ERROR"
    assert engine.persistence_failed
    cloud.available = True
    await engine.retry(meeting.id)
    await asyncio.gather(*list(engine.tasks))
    assert engine.get(meeting.id).phase == "TARGETED_DISCUSSION"
    assert not engine.persistence_failed
    await engine.close()
