"""Atomic JSON snapshots over private-endpoint Blob Storage and managed identity."""

import os
from typing import Any
from urllib.parse import quote, urlparse

from azure.core import MatchConditions
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from opentelemetry import trace

from mdt.models import Meeting, Memory

tracer = trace.get_tracer("mdt.persistence")


class BlobStore:
    """Single active app; ETags reject stale writes rather than losing audit state."""

    def __init__(self, account_url: str, container_name: str) -> None:
        parsed = urlparse(account_url)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(
            ".blob.core.windows.net"
        ):
            raise ValueError("Blob persistence requires an HTTPS Azure Blob account endpoint.")
        self.credential = (
            ManagedIdentityCredential()
            if os.getenv("CONTAINER_APP_NAME")
            else DefaultAzureCredential()
        )
        self.client = BlobServiceClient(
            account_url,
            credential=self.credential,
            connection_timeout=10,
            read_timeout=20,
            retry_total=2,
        )
        self.container = self.client.get_container_client(container_name)
        self.etags: dict[str, str] = {}
        # Safe only because one replica is the sole writer (ETags reject others):
        # after one full listing, new meetings are counted as they are created.
        self._meeting_count: int | None = None
        try:
            self.container.get_container_properties()
        except Exception:
            self.close()
            raise

    def _read(self, name: str) -> str | None:
        try:
            download = self.container.download_blob(name)
        except ResourceNotFoundError as exc:
            if getattr(exc, "error_code", None) != "BlobNotFound":
                raise
            return None
        etag = download.properties.etag
        if not isinstance(etag, str):
            raise ValueError("Stored snapshot has no ETag.")
        self.etags[name] = etag
        content = download.readall()
        if isinstance(content, bytes):
            return content.decode("utf-8")
        if isinstance(content, str):
            return content
        raise TypeError("Blob snapshot must contain UTF-8 JSON.")

    def _write(self, name: str, payload: str, metadata: dict[str, str] | None = None) -> None:
        options: dict[str, Any] = {
            "metadata": metadata,
            "content_settings": ContentSettings(content_type="application/json"),
        }
        create = name not in self.etags
        if not create:
            options["etag"] = self.etags[name]
            options["match_condition"] = MatchConditions.IfNotModified
        with tracer.start_as_current_span(
            "mdt.persistence.save",
            attributes={"mdt.backend": "azure_blob", "mdt.record_type": name.split("/", 1)[0]},
        ):
            try:
                response = self.container.get_blob_client(name).upload_blob(
                    payload.encode("utf-8"), overwrite=not create, **options
                )
            except Exception:
                self.etags.pop(name, None)
                if create:
                    # The blob may exist despite the error; recount on next use.
                    self._meeting_count = None
                raise
        etag = response.get("etag")
        if not isinstance(etag, str):
            raise ValueError("Blob persistence returned no write ETag.")
        self.etags[name] = etag
        # A create-only upload succeeds only when the blob did not exist.
        if create and name.startswith("meetings/") and self._meeting_count is not None:
            self._meeting_count += 1

    def save(self, meeting: Meeting) -> None:
        self.save_snapshot(meeting.id, meeting.created_at, meeting.model_dump_json())

    def save_snapshot(self, meeting_id: str, created_at: str, payload: str) -> None:
        self._write(f"meetings/{meeting_id}.json", payload, {"created_at": created_at})

    def get(self, meeting_id: str) -> Meeting | None:
        payload = self._read(f"meetings/{quote(meeting_id, safe='')}.json")
        return Meeting.model_validate_json(payload) if payload is not None else None

    def latest(self) -> Meeting | None:
        latest_name: str | None = None
        latest_created = ""
        for blob in self.container.list_blobs(name_starts_with="meetings/", include=["metadata"]):
            metadata = blob.metadata
            if not metadata or not metadata.get("created_at"):
                raise ValueError("Meeting snapshot is missing its creation metadata.")
            if metadata["created_at"] > latest_created:
                latest_created = metadata["created_at"]
                latest_name = blob.name
        if latest_name is None:
            return None
        payload = self._read(latest_name)
        if payload is None:
            raise RuntimeError("Latest meeting disappeared while reading persistent state.")
        return Meeting.model_validate_json(payload)

    def count(self) -> int:
        if self._meeting_count is None:
            self._meeting_count = sum(
                1 for _ in self.container.list_blobs(name_starts_with="meetings/")
            )
        return self._meeting_count

    def ready(self) -> None:
        """One bounded data-plane call: identity, RBAC, private DNS and container."""
        pages = self.container.list_blobs(
            name_starts_with="meetings/", results_per_page=1
        ).by_page()
        next(iter(pages), None)

    @staticmethod
    def _memory_name(memory: Memory) -> str:
        return f"memories/{quote(memory.clinician_id, safe='')}/{quote(memory.id, safe='')}.json"

    def memories(self, seeds: list[Memory], clinician_id: str = "demo-clinician") -> list[Memory]:
        for seed in seeds:
            if seed.clinician_id != clinician_id:
                continue
            name = self._memory_name(seed)
            if self._read(name) is None:
                self._write(name, seed.model_dump_json())
        memories: list[Memory] = []
        prefix = f"memories/{quote(clinician_id, safe='')}/"
        for blob in self.container.list_blobs(name_starts_with=prefix):
            payload = self._read(blob.name)
            if payload is None:
                raise RuntimeError("Memory disappeared while reading persistent state.")
            memory = Memory.model_validate_json(payload)
            if memory.clinician_id != clinician_id:
                raise ValueError("Memory clinician scope does not match its storage key.")
            if memory.status != "FORGOTTEN":
                memory.status = "AVAILABLE"
            memories.append(memory)
        return sorted(memories, key=lambda memory: memory.id)

    def save_memory(self, memory: Memory) -> None:
        name = self._memory_name(memory)
        if name not in self.etags and self._read(name) is None:
            raise ValueError("Cannot update a memory that has not been initialized.")
        self._write(name, memory.model_dump_json())

    def close(self) -> None:
        self.client.close()
        self.credential.close()
