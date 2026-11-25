import functools
import hashlib
import http.server
import json
import threading
import time
import zipfile

import pytest

from karaoke_easy import downloads, gpu, jobs, paths


# ---------------- detección ----------------
def test_parse_nvidia_smi():
    out = "NVIDIA GeForce RTX 3060, 560.94, 12288\nNVIDIA GeForce GTX 1050 Ti, 472.12, 4096\n"
    g = gpu.parse_nvidia_smi(out)
    assert g[0] == {"name": "NVIDIA GeForce RTX 3060", "driver": "560.94", "memory_mb": 12288}
    assert g[1]["driver"] == "472.12"
    assert gpu.parse_nvidia_smi("") == []
    assert gpu.parse_nvidia_smi("NVIDIA-SMI has failed because it couldn't communicate with the driver") == []


def test_parse_wmi_and_driver_version():
    assert gpu.wmi_driver_to_nvidia("32.0.15.6094") == "560.94"
    assert gpu.wmi_driver_to_nvidia("31.0.15.2833") == "528.33"
    assert gpu.wmi_driver_to_nvidia("") is None
    one = json.dumps({"Name": "NVIDIA GeForce RTX 4070", "AdapterCompatibility": "NVIDIA",
                      "DriverVersion": "32.0.15.6094", "AdapterRAM": 4293918720})
    g = gpu.parse_wmi(one)
    assert g == [{"name": "NVIDIA GeForce RTX 4070", "driver": "560.94", "memory_mb": 4095}]
    many = json.dumps([{"Name": "Intel(R) UHD Graphics 630", "AdapterCompatibility": "Intel Corporation",
                        "DriverVersion": "27.20.100.8681"},
                       {"Name": "NVIDIA GeForce GTX 1660", "AdapterCompatibility": "NVIDIA", "DriverVersion": "31.0.15.2833"}])
    assert [x["name"] for x in gpu.parse_wmi(many)] == ["NVIDIA GeForce GTX 1660"]
    assert gpu.parse_wmi("no json") == []


def test_driver_ok():
    assert gpu.driver_ok("528.33") and gpu.driver_ok("560.94") and gpu.driver_ok("1000.1")
    assert not gpu.driver_ok("472.12") and not gpu.driver_ok(None) and not gpu.driver_ok("528.32")


def test_parse_selftest():
    out = "ruido de librerías\nGPU_SELFTEST {\"ok\": true, \"device\": \"RTX 3060\", \"version\": \"1.2.3\"}\n"
    assert gpu.parse_selftest(out)["device"] == "RTX 3060"
    assert gpu.parse_selftest("nada") is None


# ---------------- selección ----------------
G = [{"name": "NVIDIA GeForce RTX 3060", "driver": "560.94"}]
OK = {"ok": True, "version": "1.0.0", "device": "NVIDIA GeForce RTX 3060"}


@pytest.mark.parametrize("enabled,gpus,exe,test,ver,use,why", [
    (True, G, "x.exe", OK, "1.0.0", True, None),
    (True, [], "x.exe", OK, "1.0.0", False, "No se detectó"),
    (True, [{"name": "GTX", "driver": "472.12"}], "x.exe", OK, "1.0.0", False, "muy antiguo"),
    (True, G, None, None, "1.0.0", False, "no está instalado"),
    (False, G, "x.exe", OK, "1.0.0", False, "Desactivado"),
    (True, G, "x.exe", None, "1.0.0", False, "Comprobando"),
    (True, G, "x.exe", OK, "1.1.0", False, "otra versión"),
    (True, G, "x.exe", {"ok": False, "error": "CUDA no está disponible"}, "1.0.0", False, "CUDA no está disponible"),
])
def test_decide(enabled, gpus, exe, test, ver, use, why):
    u, w = gpu.decide(enabled, gpus, exe, test, ver)
    assert u is use
    assert (w is None) if why is None else (why in w)


def _selector(monkeypatch, tmp_path, test=OK, version="1.0.0"):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(paths, "app_version", lambda: version)
    s = gpu.Selector()
    s.gpus, s.exe, s.test = G, tmp_path / "KaraokeEngine-GPU.exe", test
    return s


def test_selector_fails_twice_then_cpu(monkeypatch, tmp_path):
    s = _selector(monkeypatch, tmp_path)
    assert s.choice()[0] is True
    assert s.public()["using"] == "gpu" and "RTX 3060" in s.public()["device_name"]
    s.job_result(False, "CUDA out of memory")
    assert s.choice()[0] is True  # un fallo aislado (canción larga) no la desactiva
    s.job_result(False, "CUDA out of memory")
    use, why, _ = s.choice()
    assert not use and "out of memory" in why
    assert s.public()["using"] == "cpu"
    assert json.loads((tmp_path / "KaraokeEasy" / "gpu_estado.json").read_text(encoding="utf-8"))["using"] == "cpu"


def test_selector_respects_setting(monkeypatch, tmp_path):
    s = _selector(monkeypatch, tmp_path)
    from karaoke_easy import settings
    settings.save({"use_gpu": False})
    assert s.choice()[:2] == (False, "Desactivado en Ajustes")


def test_find_engine_locations(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("KARAOKE_GPU_ENGINE", raising=False)
    monkeypatch.setattr(gpu, "app_root", lambda: tmp_path / "app")
    assert gpu.find_engine() is None
    dl = tmp_path / "KaraokeEasy" / "gpu" / gpu.GPU_EXE
    dl.parent.mkdir(parents=True)
    dl.write_bytes(b"x")
    assert gpu.find_engine() == dl
    steam = tmp_path / "app" / "gpu" / gpu.GPU_EXE  # DLC de Steam: tiene prioridad
    steam.parent.mkdir(parents=True)
    steam.write_bytes(b"x")
    assert gpu.find_engine() == steam


@pytest.mark.parametrize("state,step,retry", [
    ("error", "separate", True), ("error", "lyrics", True), ("error", None, True),
    ("error", "prepare", False), ("error", "video", False), ("done", "finish", False)])
def test_should_retry_on_cpu(state, step, retry):
    assert gpu.should_retry_on_cpu(state, step) is retry
    assert gpu.should_retry_on_cpu(state, step, cancelled=True) is False


# ---------------- fallback a CPU dentro de la cola ----------------
class _FakeSel:
    def __init__(self, use=True):
        self.use, self.results = use, []

    def choice(self):
        return (True, None, "gpu.exe") if self.use else (False, "No se detectó una tarjeta NVIDIA", None)

    def job_result(self, ok, error=None):
        self.results.append(ok)


def _manager(monkeypatch, outcomes):
    calls = []

    def fake_spawn(self, j, base_cmd, device="auto", env=None):
        calls.append((base_cmd, device, env))
        state, step, err = outcomes[len(calls) - 1]
        j.state, j.step, j.error = state, step, err
    monkeypatch.setattr(jobs.JobManager, "_spawn", fake_spawn)
    m = jobs.JobManager.__new__(jobs.JobManager)  # sin el hilo de la cola
    return m, calls


def test_gpu_failure_retries_on_cpu(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    sel = _FakeSel()
    monkeypatch.setattr(gpu, "SELECTOR", sel)
    m, calls = _manager(monkeypatch, [("error", "separate", "CUDA out of memory"), ("done", "finish", None)])
    j = jobs.Job({"input": "a.mp3", "output_dir": str(tmp_path)})
    m._run(j)
    assert j.state == "done" and j.engine == "cpu"
    assert calls[0][0] == ["gpu.exe", "--worker"] and calls[0][1] == "cuda" and "KARAOKE_MODELS" in calls[0][2]
    assert calls[1][0] is None and calls[1][1] == "cpu"
    assert sel.results == [False]
    assert any("Repitiendo con el procesador" in x for x in j.log)


def test_gpu_success_no_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(gpu, "SELECTOR", _FakeSel())
    m, calls = _manager(monkeypatch, [("done", "finish", None)])
    j = jobs.Job({"input": "a.mp3", "output_dir": str(tmp_path)})
    m._run(j)
    assert len(calls) == 1 and j.engine == "gpu" and j.public()["engine"] == "gpu"


def test_input_error_on_gpu_not_retried(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(gpu, "SELECTOR", _FakeSel())
    m, calls = _manager(monkeypatch, [("error", "prepare", "no existe el archivo")])
    j = jobs.Job({"input": "a.mp3", "output_dir": str(tmp_path)})
    m._run(j)
    assert len(calls) == 1 and j.state == "error"


def test_no_gpu_uses_cpu(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(gpu, "SELECTOR", _FakeSel(use=False))
    m, calls = _manager(monkeypatch, [("done", "finish", None)])
    j = jobs.Job({"input": "a.mp3", "output_dir": str(tmp_path)})
    m._run(j)
    assert calls == [(None, "auto", None)] and j.engine == "cpu"
    assert any("procesador" in x for x in j.log)


# ---------------- pack dividido + sha256 ----------------
def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _make_pack(folder, version="1.0.0", part_size=700, corrupt=False):
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(gpu.GPU_EXE, b"MZ" + b"e" * 1500)
        z.writestr("_internal/torch/lib/cublas64_12.dll", b"c" * 1500)
        z.writestr("_internal/VERSION", version)
    data = buf.getvalue()
    parts = []
    for i in range(0, len(data), part_size):
        chunk = data[i:i + part_size]
        name = f"KaraokeEasy-GPU-{version}.zip.{len(parts) + 1:03d}"
        (folder / name).write_bytes(chunk if not (corrupt and not parts) else b"X" + chunk[1:])
        parts.append({"name": name, "size": len(chunk), "sha256": _sha(chunk)})
    (folder / f"KaraokeEasy-GPU-{version}.json").write_text(json.dumps(
        {"version": version, "sha256": _sha(data), "size": len(data), "parts": parts}), encoding="utf-8")
    return len(parts)


def _serve(folder):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(folder))
    h.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _wait(d, timeout=20):
    t0 = time.time()
    while d.state in ("running", "extracting") and time.time() - t0 < timeout:
        time.sleep(0.05)
    return d.state


@pytest.fixture
def gpu_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(downloads, "GPU", downloads.Download())
    refreshed = []
    monkeypatch.setattr(gpu.SELECTOR, "refresh", lambda wait=False: refreshed.append(1))
    srv = tmp_path / "srv"
    srv.mkdir()
    return srv, refreshed


def test_gpu_pack_download_reassemble_install(gpu_env):
    srv, refreshed = gpu_env
    assert _make_pack(srv) >= 3
    httpd = _serve(srv)
    try:
        downloads.start_gpu(f"http://127.0.0.1:{httpd.server_address[1]}/KaraokeEasy-GPU-1.0.0.json", version="1.0.0")
        assert _wait(downloads.GPU) == "done", downloads.GPU.error
        target = paths.user_cache() / "gpu"
        assert (target / gpu.GPU_EXE).read_bytes().startswith(b"MZ")
        assert (target / "_internal" / "torch" / "lib" / "cublas64_12.dll").exists()
        assert not (paths.user_cache() / "descarga_gpu").exists()
        assert refreshed  # se vuelve a comprobar el motor tras instalar
    finally:
        httpd.shutdown()


def test_gpu_pack_corrupt_part_rejected(gpu_env):
    srv, _ = gpu_env
    _make_pack(srv, corrupt=True)
    httpd = _serve(srv)
    try:
        downloads.start_gpu(f"http://127.0.0.1:{httpd.server_address[1]}/KaraokeEasy-GPU-1.0.0.json", version="1.0.0")
        assert _wait(downloads.GPU) == "error"
        assert "sha256" in downloads.GPU.error
        assert not (paths.user_cache() / "gpu").exists()
    finally:
        httpd.shutdown()


def test_gpu_pack_wrong_version_rejected(gpu_env):
    srv, _ = gpu_env
    _make_pack(srv, version="0.9.0")
    (srv / "KaraokeEasy-GPU-1.0.0.json").write_bytes((srv / "KaraokeEasy-GPU-0.9.0.json").read_bytes())
    httpd = _serve(srv)
    try:
        downloads.start_gpu(f"http://127.0.0.1:{httpd.server_address[1]}/KaraokeEasy-GPU-1.0.0.json", version="1.0.0")
        assert _wait(downloads.GPU) == "error" and "otra versión" in downloads.GPU.error
    finally:
        httpd.shutdown()


def test_reassemble_detects_bad_total_sha(tmp_path):
    a, b = tmp_path / "x.001", tmp_path / "x.002"
    a.write_bytes(b"hola ")
    b.write_bytes(b"mundo")
    out = downloads.reassemble([a, b], tmp_path / "x.zip", _sha(b"hola mundo"))
    assert out.read_bytes() == b"hola mundo"
    with pytest.raises(ValueError):
        downloads.reassemble([b, a], tmp_path / "y.zip", _sha(b"hola mundo"))
    assert not (tmp_path / "y.zip").exists()


def test_check_manifest_rejects_bad_names():
    good = {"sha256": "a" * 64, "parts": [{"name": "KaraokeEasy-GPU-1.0.0.zip.001", "sha256": "b" * 64}]}
    assert downloads.check_manifest(good)
    for bad in ({"sha256": "a" * 64, "parts": [{"name": "../../x.zip.001", "sha256": "b" * 64}]},
                {"sha256": "zz", "parts": good["parts"]}, {"sha256": "a" * 64, "parts": []}):
        with pytest.raises(ValueError):
            downloads.check_manifest(bad)


def test_install_rejects_traversal(tmp_path):
    z = tmp_path / "m.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../malo.txt", "x")
    with pytest.raises(ValueError):
        downloads.install_gpu_zip(z, tmp_path / "gpu")


def test_ci_manifest_tool_matches_client(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("gpu_manifest", paths.app_dir() / "tools" / "gpu_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = b"PK" + bytes(range(256)) * 20
    for i in range(3):
        (tmp_path / f"KaraokeEasy-GPU-2.0.0.zip.{i + 1:03d}").write_bytes(data[i * 2000:(i + 1) * 2000])
    m = mod.build("2.0.0", tmp_path)
    assert m["sha256"] == _sha(data) and len(downloads.check_manifest(m, "2.0.0")) == 3
    files = [tmp_path / p["name"] for p in m["parts"]]
    assert downloads.reassemble(files, tmp_path / "out.zip", m["sha256"]).read_bytes() == data
