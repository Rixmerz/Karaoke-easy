import json
import urllib.request

import pytest

from karaoke_easy import license as L

DAY = 86400


class FakeLS:
    """Respuestas con la forma documentada de la API de licencias de Lemon Squeezy."""

    def __init__(self, variant="Profesor", product_id=111, store_id=1, offline=False):
        self.variant, self.product_id, self.store_id, self.offline = variant, product_id, store_id, offline
        self.validate_resp = None
        self.calls = []

    def _meta(self):
        return {"store_id": self.store_id, "product_id": self.product_id, "variant_id": 9,
                "variant_name": self.variant, "product_name": "Karaoke Easy"}

    def activate(self, key, name):
        self.calls.append(("activate", key))
        if self.offline:
            raise OSError("sin red")
        if key == "FULL":
            return {"activated": False, "error": "This license key has reached the activation limit.",
                    "license_key": {"status": "active", "activation_limit": 2, "activation_usage": 2}, "meta": self._meta()}
        return {"activated": True, "error": None, "instance": {"id": "inst-1", "name": name},
                "license_key": {"status": "active", "expires_at": None, "activation_limit": 2, "activation_usage": 1},
                "meta": self._meta()}

    def validate(self, key, iid):
        self.calls.append(("validate", key))
        if self.offline:
            raise OSError("sin red")
        return self.validate_resp or {"valid": True, "error": None, "license_key": {"status": "active"},
                                      "instance": {"id": iid}, "meta": self._meta()}

    def deactivate(self, key, iid):
        self.calls.append(("deactivate", key))
        if self.offline:
            raise OSError("sin red")
        return {"deactivated": True, "error": None}


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def mk(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LS_STORE_ID", 1)
    monkeypatch.setattr(L, "LS_PRODUCT_IDS", (111,))

    def make(**kw):
        clock = Clock()
        ls = FakeLS(**kw)
        return L.LicenseManager(folder=tmp_path, client=ls, clock=clock, fingerprint="fp-test"), ls, clock
    return make


def test_activate_ok_then_offline(mk):
    m, ls, clock = mk(variant="Eventos")
    st = m.activate("  KEY-123  ")
    assert st["state"] == "eventos" and st["features"]["batch"] and st["key_hint"] == "…-123"
    ls.offline = True
    clock.t += 10 * DAY
    assert m.revalidate() is False  # sin red: no cambia nada
    assert m.status()["state"] == "eventos"


def test_wrong_product_rejected_and_freed(mk):
    m, ls, _ = mk(product_id=999)
    with pytest.raises(L.LicenseError, match="no es de Karaoke Easy"):
        m.activate("KEY")
    assert ("deactivate", "KEY") in ls.calls
    assert m.status()["state"] == "trial"


def test_unknown_variant_rejected(mk):
    m, _, _ = mk(variant="Otra cosa")
    with pytest.raises(L.LicenseError):
        m.activate("KEY")


def test_activation_limit(mk):
    m, _, _ = mk()
    with pytest.raises(L.LicenseError, match="máximo de equipos"):
        m.activate("FULL")


def test_activate_without_network(mk):
    m, _, _ = mk(offline=True)
    with pytest.raises(L.LicenseError, match="conexión"):
        m.activate("KEY")


def test_offline_grace_then_reconnect(mk):
    m, ls, clock = mk()
    m.activate("KEY")
    ls.offline = True
    clock.t += 29 * DAY
    m.revalidate()
    assert m.status()["state"] == "profesor"
    clock.t += 2 * DAY
    m.revalidate()
    st = m.status()
    assert st["state"] == "reconnect" and not st["features"]["create"]
    ls.offline = False
    assert m.revalidate() is True
    assert m.status()["state"] == "profesor"


def test_revalidation_at_most_weekly(mk):
    m, ls, clock = mk()
    m.activate("KEY")
    clock.t += 3 * DAY
    assert m.revalidate() is False
    clock.t += 5 * DAY
    assert m.revalidate() is True
    assert [c for c in ls.calls if c[0] == "validate"] == [("validate", "KEY")]


@pytest.mark.parametrize("resp", [
    {"valid": False, "error": "license_key not found.", "license_key": {"status": "disabled"}},
    {"valid": True, "error": None, "license_key": {"status": "expired"}},
    {"valid": True, "error": None, "license_key": {"status": "disabled"}},
])
def test_revoked_drops_to_unlicensed(mk, resp):
    m, ls, clock = mk()
    m.status()  # primer uso: empieza la prueba
    m.activate("KEY")
    clock.t += 20 * DAY  # prueba también vencida
    ls.validate_resp = resp
    m.revalidate()
    assert m.status()["state"] == "unlicensed"


def test_trial_expiry(mk):
    m, _, clock = mk()
    st = m.status()
    assert st["state"] == "trial" and st["days_left"] == 14 and st["features"]["create"]
    clock.t += 13.5 * DAY
    assert m.status()["days_left"] == 1
    clock.t += 1 * DAY
    st = m.status()
    assert st["state"] == "unlicensed" and not st["features"]["create"]


def test_tampered_license_file_ignored(mk, tmp_path):
    m, _, _ = mk(variant="Profesor")
    m.activate("KEY")
    f = tmp_path / "licencia.dat"
    import base64
    blob = json.loads(base64.b64decode(f.read_text()))
    blob["d"]["tier"] = "eventos"
    f.write_text(base64.b64encode(json.dumps(blob).encode()).decode())
    assert m.status()["state"] == "trial"
    other = L.LicenseManager(folder=tmp_path, client=FakeLS(), clock=Clock(), fingerprint="otro-pc")
    assert other._license() is None


def test_deactivate(mk):
    m, ls, _ = mk()
    m.activate("KEY")
    assert m.deactivate()["state"] == "trial"
    assert ("deactivate", "KEY") in ls.calls


def test_gating_rules():
    assert L.check_new_jobs("unlicensed", 0, 1) and "prueba" in L.check_new_jobs("unlicensed", 0, 1)
    assert L.check_new_jobs("reconnect", 0, 1)
    assert L.check_new_jobs("profesor", 0, 3) is None
    assert "Eventos" in L.check_new_jobs("profesor", 2, 2)
    assert L.check_new_jobs("eventos", 50, 50) is None
    assert L.check_new_jobs("trial", 50, 50) is None
    assert not L.allows("profesor", "party") and L.allows("eventos", "party")


def test_lemonsqueezy_client_reads_error_body(monkeypatch):
    import io
    import urllib.error

    def fake(req, timeout):
        assert req.full_url.endswith("/activate") and b"license_key=K" in req.data
        raise urllib.error.HTTPError(req.full_url, 400, "Bad", {}, io.BytesIO(b'{"activated":false,"error":"bad key"}'))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert L.LemonSqueezy().activate("K", "pc")["error"] == "bad key"


def test_server_endpoints_and_gating(mk, tmp_path):
    from karaoke_easy import server

    m, _, clock = mk()
    m.status()

    class Jobs:
        jobs = []

        def list(self):
            return []

        def add(self, spec):
            raise AssertionError("no debería crear trabajos")

    clock.t += 20 * DAY
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
        import urllib.error
        assert call("api/license")[1]["state"] == "unlicensed"
        code, r = call("api/jobs", {"inputs": ["a.mp3"]})
        assert code == 403 and r["license"]
        code, r = call("api/license/activate", {"key": "FULL"})
        assert code == 400 and "máximo" in r["error"]
        code, r = call("api/license/activate", {"key": "KEY"})
        assert code == 200 and r["state"] == "profesor"
        code, r = call("api/jobs", {"inputs": ["a", "b", "c", "d"]})
        assert code == 403 and "Eventos" in r["error"]
        assert call("api/license/deactivate", {})[1]["state"] == "unlicensed"
    finally:
        httpd.shutdown()
