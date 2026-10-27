import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("databento")
spec = importlib.util.spec_from_file_location(
    "download", Path(__file__).resolve().parents[1] / "src" / "data" / "download.py"
)
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


def test_env_key_is_enough(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABENTO_API_KEY", "db-test")
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.databento_api_key here
    monkeypatch.setattr(download.db, "Historical", lambda: "client")
    assert download.get_client() == "client"


def test_falls_back_to_key_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".databento_api_key").write_text("db-from-file\n")
    seen = {}
    monkeypatch.setattr(download.db, "Historical", lambda: seen.setdefault("key", download.os.environ["DATABENTO_API_KEY"]))
    download.get_client()
    assert seen["key"] == "db-from-file"
