"""Document storage: local disk (unconfigured dev) vs R2/S3-compatible
object storage (round 10 -- Render's free tier gives the orchestrator
service an ephemeral filesystem, confirmed live: every redeploy silently
wiped previously uploaded documents while the hash-chained event log kept
referencing them forever). Same honest-degrade shape as every other
credential in this system: unset R2 env vars and store_document()/
read_document() fall back to local disk, exactly as before this round.
"""
from __future__ import annotations

import io

import boto3
import pytest
from botocore.exceptions import ClientError

from satyapramana_store.extract import ingest


@pytest.fixture(autouse=True)
def _clear_r2_env(monkeypatch):
    """Every test starts from a clean, unconfigured state -- explicit, not
    whatever happened to be in the environment when the suite ran."""
    for var in ("SATYAPRAMANA_R2_ACCESS_KEY_ID", "SATYAPRAMANA_R2_SECRET_ACCESS_KEY",
                "SATYAPRAMANA_R2_ENDPOINT", "SATYAPRAMANA_R2_BUCKET"):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(ingest, f"_{var.removeprefix('SATYAPRAMANA_')}", None)


def _configure_r2(monkeypatch):
    monkeypatch.setattr(ingest, "_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(ingest, "_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(ingest, "_R2_ENDPOINT", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setattr(ingest, "_R2_BUCKET", "test-bucket")


# --- unconfigured: local disk, unchanged from before this round -----------------

def test_r2_client_is_none_when_unconfigured():
    assert ingest._r2_client() is None


def test_store_and_read_document_falls_back_to_local_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "DOCUMENT_DIR", tmp_path)
    digest, ref = ingest.store_document(b"%PDF-1.4 fake", "BIDDER-A", "doc.pdf")
    assert not ref.startswith("r2://")
    assert ingest.read_document(ref) == b"%PDF-1.4 fake"


def test_read_document_missing_local_file_is_none_not_an_error(tmp_path):
    assert ingest.read_document(str(tmp_path / "nonexistent.pdf")) is None


# --- configured: real R2/S3-compatible calls, mocked at the boto3 client level ---

class _FakeS3:
    """Minimal stand-in for boto3's S3 client -- exercises the exact two
    calls store_document/read_document actually make, nothing more."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.put_calls = []

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.put_calls.append((Bucket, Key, ContentType))
        self.objects[Key] = Body

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}


def test_store_document_uploads_to_r2_when_configured(monkeypatch):
    _configure_r2(monkeypatch)
    fake = _FakeS3()
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: fake)

    digest, ref = ingest.store_document(b"%PDF-1.4 real content", "BIDDER-A", "doc.pdf")
    assert ref.startswith("r2://BIDDER-A/")
    assert ref.endswith("-doc.pdf")
    assert fake.put_calls == [("test-bucket", ref.removeprefix("r2://"), "application/pdf")]
    assert fake.objects[ref.removeprefix("r2://")] == b"%PDF-1.4 real content"


def test_read_document_fetches_from_r2_when_ref_is_an_r2_key(monkeypatch):
    _configure_r2(monkeypatch)
    fake = _FakeS3()
    fake.objects["BIDDER-A/abc-doc.pdf"] = b"real bytes"
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: fake)

    assert ingest.read_document("r2://BIDDER-A/abc-doc.pdf") == b"real bytes"


def test_read_document_r2_not_found_is_none_not_a_guess(monkeypatch):
    _configure_r2(monkeypatch)
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: _FakeS3())
    assert ingest.read_document("r2://BIDDER-A/never-uploaded.pdf") is None


def test_read_document_r2_unexpected_error_is_not_silently_swallowed(monkeypatch):
    _configure_r2(monkeypatch)

    class _BrokenS3(_FakeS3):
        def get_object(self, *, Bucket, Key):
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "GetObject")

    monkeypatch.setattr(boto3, "client", lambda *a, **kw: _BrokenS3())
    with pytest.raises(ClientError):
        ingest.read_document("r2://BIDDER-A/doc.pdf")


def test_store_document_round_trips_a_real_pdf_through_r2(monkeypatch):
    """The real end-to-end shape: store, then read back the exact same
    bytes -- the actual property that matters (a document survives)."""
    _configure_r2(monkeypatch)
    fake = _FakeS3()
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: fake)

    original = b"%PDF-1.4\n%real pdf bytes here\n%%EOF"
    _, ref = ingest.store_document(original, "GST-BIDDER-01", "gst.pdf")
    assert ingest.read_document(ref) == original
