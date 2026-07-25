import stat
import sys

import pytest

from krita_comfyui import secret_store


@pytest.fixture(autouse=True)
def _isolate_secrets_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(secret_store, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(secret_store, "SECRETS_FILE", tmp_path / "secrets.json")


class TestStore:
    def test_store_and_retrieve(self):
        secret_store.store("api_key", "sk-abc123")
        assert secret_store.retrieve("api_key") == "sk-abc123"

    def test_retrieve_missing_key(self):
        assert secret_store.retrieve("nonexistent") is None

    def test_retrieve_missing_file(self):
        assert secret_store.retrieve("api_key") is None

    def test_delete(self):
        secret_store.store("api_key", "sk-abc123")
        secret_store.delete("api_key")
        assert secret_store.retrieve("api_key") is None

    def test_delete_nonexistent(self):
        secret_store.delete("api_key")
        assert secret_store.retrieve("api_key") is None

    def test_overwrite(self):
        secret_store.store("api_key", "first")
        secret_store.store("api_key", "second")
        assert secret_store.retrieve("api_key") == "second"

    def test_multiple_keys(self):
        secret_store.store("a", "1")
        secret_store.store("b", "2")
        assert secret_store.retrieve("a") == "1"
        assert secret_store.retrieve("b") == "2"

    def test_empty_string(self):
        secret_store.store("api_key", "")
        assert secret_store.retrieve("api_key") == ""

    def test_unicode(self):
        secret_store.store("emoji", "🔑test")
        assert secret_store.retrieve("emoji") == "🔑test"

    def test_base64_encoding(self):
        secret_store.store("api_key", "sk-abc123")
        data = secret_store.SECRETS_FILE.read_text(encoding="utf-8")
        assert "sk-abc123" not in data

    def test_has_secrets_file_false(self):
        assert secret_store.has_secrets_file() is False

    def test_has_secrets_file_true(self):
        secret_store.store("api_key", "x")
        assert secret_store.has_secrets_file() is True

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions not supported on Windows")
    def test_file_permissions_posix(self):
        secret_store.store("api_key", "secret")
        mode = secret_store.SECRETS_FILE.stat().st_mode
        assert mode & stat.S_IRWXO == 0
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRUSR
        assert mode & stat.S_IWUSR
        dir_mode = secret_store.SECRETS_DIR.stat().st_mode
        assert stat.S_IMODE(dir_mode) == stat.S_IRWXU

    def test_permissions_skipped_on_windows(self, monkeypatch):
        monkeypatch.setattr(secret_store.os, "name", "nt")
        secret_store.store("api_key", "secret")
        assert secret_store.SECRETS_FILE.exists()
        assert secret_store.retrieve("api_key") == "secret"

    def test_corrupted_json(self):
        secret_store.SECRETS_FILE.write_text("{invalid", encoding="utf-8")
        assert secret_store.retrieve("api_key") is None

    def test_non_dict_json_returns_empty(self):
        secret_store.SECRETS_FILE.write_text('["a", "b"]', encoding="utf-8")
        assert secret_store.retrieve("api_key") is None


