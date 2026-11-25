"""Edición Steam: sin enlaces, licencia de Steam, sin actualizador propio."""
import json
import urllib.error
import urllib.request

import pytest

from karaoke_easy import edition
from karaoke_easy import license as L

from test_license import FakeLS, Clock


@pytest.fixture
def steam(monkeypatch):
    monkeypatch.setenv("KARAOKE_EDITION", "steam")


def test_edition_default_and_override(monkeypatch):
    monkeypatch.delenv("KARAOKE_EDITION", raising=False)
    monkeypatch.setattr(edition, "_from_file", lambda: None)
    assert edition.current() == "direct" and edition.features()["url_downloads"]
    monkeypatch.setattr(edition, "_from_file", lambda: "steam")
    assert edition.is_steam()
    monkeypatch.setenv("KARAOKE_EDITION", "rara")
    assert edition.current() == "direct"  # valor desconocido: la edición normal


def _mgr(tmp_path, monkeypatch, variant="Eventos"):
    monkeypatch.setattr(L, "LS_STORE_ID", 1)
    monkeypatch.setattr(L, "LS_PRODUCT_IDS", (111,))
    clock = Clock()
    return L.LicenseManager(folder=tmp_path, client=FakeLS(variant=variant), clock=clock,
                            fingerprint="fp-test"), clock


def test_steam_license_state(steam, tmp_path, monkeypatch):
    m, clock = _mgr(tmp_path, monkeypatch)
    clock.t += 400 * 86400  # en Steam no hay prueba: nunca vence
    st = m.status()
    assert st["state"] == "steam" and st["features"]["create"] and not st["features"]["batch"]
    assert st["edition"] == "steam" and st["max_queued"] == L.MAX_QUEUED_NO_BATCH
    assert L.check_new_jobs("steam", 0, 1) is None
    assert "Eventos" in L.check_new_jobs("steam", 2, 2)


def test_steam_eventos_key_and_fallback(steam, tmp_path, monkeypatch):
    m, clock = _mgr(tmp_path, monkeypatch)
    assert m.activate("KEY")["state"] == "eventos"
    m.client.offline = True
    clock.t += L.OFFLINE_GRACE + 86400
    assert m.status()["state"] == "steam"  # sin verificar: vuelve a uso personal, no se bloquea


def test_steam_rejects_profesor_key(steam, tmp_path, monkeypatch):
    m, _ = _mgr(tmp_path, monkeypatch, variant="Profesor")
    with pytest.raises(L.LicenseError, match="solo se activa la licencia Eventos"):
        m.activate("KEY")
    assert ("deactivate", "KEY") in m.client.calls and m.status()["state"] == "steam"


def test_steam_server_rejects_urls_and_disables_updater(steam, tmp_path, monkeypatch):
    from karaoke_easy import downloads, server

    m, _ = _mgr(tmp_path, monkeypatch)
    added = []

    class Jobs:
        jobs = []

        def list(self):
            return []

        def add(self, spec):
            added.append(spec)

            class J:
                def public(self_):
                    return {"id": "1"}
            return J()

    monkeypatch.setattr(downloads, "start_update", lambda url: pytest.fail("no debe actualizar"))
    httpd, url = server.start(run_ffmpeg=lambda a: None, jobs=Jobs(), lic=m)
    try:
        def call(path, body=None):
            req = urllib.request.Request(url + path, data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())

        v = call("api/version")[1]
        assert v["edition"] == "steam" and not v["updater"] and not v["url_downloads"]
        code, r = call("api/jobs", {"inputs": ["https://www.youtube.com/watch?v=x"]})
        assert code == 400 and "Steam" in r["error"] and not added
        code, r = call("api/jobs", {"inputs": ["a.mp3", "www.example.com/b"]})
        assert code == 400 and not added
        code, r = call("api/jobs", {"inputs": [str(tmp_path / "a.mp3")]})
        assert code == 200 and len(added) == 1
        assert call("api/update")[1]["disabled"] is True
        assert call("api/update/download", {"url": "https://x/y.exe"})[1] == {"started": False, "disabled": True}
        assert call("api/license")[1]["state"] == "steam"
    finally:
        httpd.shutdown()
