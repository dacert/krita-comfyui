import json
import types
import urllib.request
from urllib.parse import quote

import pytest

from krita_comfyui.comfy_client.comfy_http_client import ComfyHttpClient


def _mock_response(content: bytes | str, status=200):
    """Return a simple object mimicking urllib's HTTPResponse with context manager support."""
    if isinstance(content, str):
        content = content.encode("utf-8")

    class MockResp:
        def __init__(self, data, st):
            self.data = data
            self.status = st

        # context‑manager protocol
        def __enter__(self):  # pragma: no cover
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):  # pragma: no cover
            pass

        def read(self):
            return self.data

    return MockResp(content, status)


@pytest.fixture
def client():
    return ComfyHttpClient(server="http://127.0.0.1:8000")


# ---------- Helper for patching urllib.request.urlopen ----------
@pytest.fixture(autouse=True)
def mock_urlopen(monkeypatch):
    """Patch urllib.request.urlopen to capture the request and return a fake response."""

    def _urlopen(request, timeout=None):
        # For GET requests request is a str; for POST it is a Request object
        if isinstance(request, urllib.request.Request):
            url = request.full_url
            data = request.data or b""
        else:
            url = request
            data = None

        # Store the last call for introspection in tests
        _urlopen.last_call = {"url": url, "data": data}  # ty:ignore[unresolved-attribute]

        # Default fake response
        return _mock_response(json.dumps({"ok": True}))

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    yield _urlopen


# ---------- Tests for upload_file ----------
@pytest.mark.parametrize(
    "kwargs,expected_in_body",
    [
        (
            {
                "path": "images",
                "file_name": "test.png",
                "file_bytes": b"dummy image data",
                "subfolder": "cats",
                "ref": "ref.png",
                "ref_subfolder": "refs",
                "overwrite": True,
            },
            ["original_ref", "overwrite", "subfolder"],
        ),
        (
            {
                "path": "images",
                "file_name": "noopt.png",
                "file_bytes": b"",
            },
            [],
        ),
    ],
)
def test_upload_file_variants(mock_urlopen, client, kwargs, expected_in_body):
    response = client.upload_file(**kwargs)
    assert isinstance(response, dict) and response["ok"] is True

    body = mock_urlopen.last_call["data"].decode("latin1")
    # Clean up boundary lines
    parts = [p for p in body.split("\r\n") if p.strip() and not p.startswith("--")]
    cleaned = "\n".join(parts)

    # Verify mandatory part
    assert 'Content-Disposition: form-data; name="image"; filename="' in cleaned

    # Optional fields must be present/absent as expected
    for field in expected_in_body:
        assert field in cleaned


# ---------- Tests for fetching lists ----------
def test_get_workflows_list(mock_urlopen, client):
    result = client.get_workflows_list()
    assert isinstance(result, dict)
    # The URL should start with the server address and path `/api/userdata`
    expected_prefix = f"{client.server_address}/api/userdata"
    assert mock_urlopen.last_call["url"].startswith(expected_prefix)

    # Check query parameters
    url = mock_urlopen.last_call["url"]
    assert "dir=workflows" in url
    assert "recurse=True" in url
    assert "split=False" in url
    assert "full_info=True" in url


def test_get_workflow(mock_urlopen, client):
    name = "sample workflow"
    client.get_workflow(name)
    # URL should be percent‑encoded
    encoded_name = quote(name)
    expected_path = f"/api/userdata/workflows%2F{encoded_name}"
    assert mock_urlopen.last_call["url"].endswith(expected_path)


# ---------- Tests for caching ----------
def test_object_info_caching(monkeypatch, mock_urlopen, client):
    # First call populates cache
    first = client.get_object_info()
    second = client.get_object_info()
    assert first is second  # cached value reused

    # Ensure urlopen was called only once
    assert mock_urlopen.last_call["url"].endswith("/api/object_info")

    # Simulate a second network call that should not happen
    def side_effect(request, timeout=None):
        raise RuntimeError("Unexpected second call")

    monkeypatch.setattr(urllib.request, "urlopen", side_effect)
    cached = client.get_object_info()
    assert cached is first  # still returns the cached value


# ---------- Tests for API conversion ----------
def test_get_workflow_api(monkeypatch, mock_urlopen, client):
    """Ensure to_api_format is called with correct arguments."""
    dummy_raw = {"foo": "bar"}
    dummy_obj_info = {"nodes": []}

    # Patch get_workflow and get_object_info on the client instance
    monkeypatch.setattr(client, "get_workflow", lambda n: dummy_raw)
    monkeypatch.setattr(client, "get_object_info", lambda: dummy_obj_info)

    # Replace the real to_api_format function with a spy.
    import krita_comfyui.comfy_client.comfy_http_client as chc

    spy = types.SimpleNamespace()

    def fake_to_api(raw, obj):
        spy.called_with = (raw, obj)
        return {"converted": True}

    monkeypatch.setattr(chc, "to_api_format", fake_to_api)

    result = client.get_workflow_api("any")
    assert result == {"converted": True}
    # Verify that the spy received the expected arguments
    assert spy.called_with == (dummy_raw, dummy_obj_info)


# ---------- Tests for queue_prompt ----------
def test_queue_prompt(mock_urlopen, client):
    prompt = {"nodes": []}
    client_id = "test-client"
    client.queue_prompt(prompt, client_id)
    # Ensure POST payload
    body = mock_urlopen.last_call["data"]
    sent = json.loads(body.decode("utf-8"))
    assert sent == {"prompt": prompt, "client_id": client_id}
    assert mock_urlopen.last_call["url"].endswith("/prompt")


# ---------- Tests for get_settings ----------
def test_get_settings(mock_urlopen, client):
    client.get_settings()
    url = mock_urlopen.last_call["url"]
    assert url.endswith("/api/settings")
    # Timeout argument should be 2 seconds
    assert mock_urlopen.last_call.get("timeout") is None  # our mock ignores timeout


# ---------- Tests for internal helpers ----------
def test_encode_multipart_formdata(mock_urlopen, client):
    fields = {"type": "input", "overwrite": "true"}
    files = [("image", "img.png", b"abc123")]
    body, content_type = client._encode_multipart_formdata(fields, files)

    # Body should be multipart with boundary
    decoded = body.decode("latin1")
    assert "--" in decoded  # boundary present
    assert 'Content-Disposition: form-data; name="image"; filename="img.png"' in decoded
    assert "abc123" in decoded
    assert content_type.startswith("multipart/form-data; boundary=")


def test_encode_multipart_formdata_non_bytes(monkeypatch, mock_urlopen, client):
    """Verify that non‑bytes file data is converted correctly."""
    fields = {}
    files = [("file", "txt.txt", b"hello")]
    body, _ = client._encode_multipart_formdata(fields, files)
    assert b"hello" in body


# ---------- Edge cases ----------
def test_fetch_json_invalid(mock_urlopen, client):
    # Simulate invalid JSON
    def bad_response(request, timeout=None):
        return _mock_response("not json")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(urllib.request, "urlopen", bad_response)
    with pytest.raises(json.JSONDecodeError):
        client._fetch_json("http://dummy")
    monkeypatch.undo()


def test_post_json_invalid(mock_urlopen, client):
    # Simulate server returning non‑JSON
    def bad_response(request, timeout=None):
        return _mock_response(b"not json")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(urllib.request, "urlopen", bad_response)
    with pytest.raises(json.JSONDecodeError):
        client._post_json("http://dummy", {"x": 1})
    monkeypatch.undo()


# ---------- Tear‑down ----------
@pytest.fixture(autouse=True)
def cleanup(tmp_path_factory):
    # Nothing to clean up in this test suite, but placeholder for future use
    yield
