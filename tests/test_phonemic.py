import base64
import json
import os
import shutil
import socket
import ssl
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from karaoke_easy import phonemic, qr, server

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def cert_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("cert")
    phonemic.ensure_cert(d)
    return d


@pytest.fixture
def hub(cert_dir):
    h = phonemic.Hub(cert_dir=cert_dir, static_dir=ROOT / "ui")
    yield h
    h.stop()


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _get(url):
    try:
        with urllib.request.urlopen(url, context=_ctx(), timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _ws_connect(host, port, path, tls=True):
    s = socket.create_connection((host, port), timeout=5)
    if tls:
        s = _ctx().wrap_socket(s, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    f = s.makefile("rb")
    status = f.readline().decode()
    while f.readline() not in (b"\r\n", b""):
        pass
    return s, f, status


def _send_masked(s, payload, op=2):
    mask = os.urandom(4)
    n = len(payload)
    h = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n))
    s.sendall(h + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(payload)))


def test_cert_is_valid_and_stable(cert_dir):
    crt, key = phonemic.ensure_cert(cert_dir)
    before = crt.read_bytes()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(crt), str(key))  # falla si el certificado o la clave están mal formados
    assert phonemic.ensure_cert(cert_dir)[0].read_bytes() == before  # no se regenera
    assert len(phonemic.fingerprint(crt).split(":")) == 8


def test_inactive_refuses_connections(hub):
    assert not hub.active and hub.url() is None
    assert not hub.check_code("ABCDEF")
    info = hub.start(host="127.0.0.1", port=0)
    port = info["port"]
    hub.stop()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
    assert not hub.check_code(info["code"])


def test_pairing_code_required(hub):
    info = hub.start(host="127.0.0.1", port=0)
    assert info["url"].startswith("https://127.0.0.1:") and info["qr"].startswith("<svg")
    base = f"https://127.0.0.1:{info['port']}"
    assert _get(base + "/m?c=ZZZZZZ")[0] == 403
    assert _get(base + "/m")[0] == 403
    st, body = _get(base + "/m?c=" + info["code"])
    assert st == 200 and b"getUserMedia" in body
    assert _get(base + "/m?c=" + info["code"].lower())[0] == 200
    _, _, status = _ws_connect("127.0.0.1", info["port"], "/ws?c=WRONG1")
    assert " 403 " in status


def test_brute_force_rotates_code(hub):
    info = hub.start(host="127.0.0.1", port=0)
    for _ in range(phonemic.MAX_BAD_ATTEMPTS):
        hub.check_code("XXXXXX")
    assert hub.code != info["code"] and not hub.check_code(info["code"])


def test_two_phones_audio_reaches_listener(hub):
    info = hub.start(host="127.0.0.1", port=0)
    got = []
    hub.add_listener(got.append)
    socks = []
    for name in ("Ana", "Beto"):
        s, f, status = _ws_connect("127.0.0.1", info["port"], f"/ws?c={info['code']}&n={name}")
        assert " 101 " in status
        op, data = phonemic.ws_read(f)
        assert json.loads(data)["type"] == "hello"
        socks.append((s, f, json.loads(data)["slot"]))
    assert sorted(x[2] for x in socks) == [1, 2]
    assert [p["name"] for p in hub.info()["phones"]] == ["Ana", "Beto"]
    pcm = struct.pack("<d", 123.0) + struct.pack("<480h", *range(480))
    _send_masked(socks[1][0], pcm)
    for _ in range(50):
        audio = [m for m in got if m[0] == 0x82]
        if audio:
            break
        time.sleep(0.05)
    frame = audio[0]
    payload = frame[4:]  # cabecera: 0x82, 126, longitud (2 bytes)
    assert payload[0] == socks[1][2] and payload[8:] == pcm
    for s, f, _ in socks:
        s.close()


def test_local_relay_requires_token(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    httpd, url = server.start([], run_ffmpeg=lambda *a: None, token="secreto")
    try:
        port = httpd.server_address[1]
        _, _, status = _ws_connect("127.0.0.1", port, "/api/phonemic/ws", tls=False)
        assert " 401 " in status
        s, f, status = _ws_connect("127.0.0.1", port, "/api/phonemic/ws?t=secreto", tls=False)
        assert status.startswith("HTTP/1.1 101")
        op, data = phonemic.ws_read(f)
        assert op == 1 and json.loads(data) == {"type": "status", "active": False, "phones": []}
        s.close()
    finally:
        httpd.shutdown()


def test_ws_helpers_roundtrip():
    assert phonemic.ws_accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    import io
    for n in (5, 300, 70000):
        mask = b"\x01\x02\x03\x04"
        data = os.urandom(n)
        hdr = phonemic.ws_frame(data)[:-n]
        hdr = bytes([hdr[0], hdr[1] | 0x80]) + hdr[2:]
        op, out = phonemic.ws_read(io.BytesIO(hdr + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(data))))
        assert op == 2 and out == data


def test_qr_structure():
    m = qr.encode("https://192.168.1.23:47823/m?c=ABC234")
    assert len(m) == 29  # versión 3
    for x, y in ((0, 0), (22, 0), (0, 22)):  # patrones de posición 7x7
        assert all(m[y][x + i] and m[y + 6][x + i] and m[y + i][x] and m[y + i][x + 6] for i in range(7))
        assert not m[y + 1][x + 1] and m[y + 3][x + 3]
    assert all(m[6][i] == (i % 2 == 0) for i in range(8, 21))  # patrón de sincronía
    assert len(qr.encode("x" * 150)) == 49


@pytest.mark.skipif(not shutil.which("node"), reason="node no disponible")
def test_duel_logic_node():
    js = r"""
    const D=require(process.argv[1]);let s=1;const rnd=()=>(s=s*16807%2147483647)/2147483647;
    const P=[{name:"A"},{name:"B"},{name:"C"}];
    const same=D.makeTurns(P,["x","y","z"],"same",2,"y",rnd);
    if(same.length!==6||same.slice(0,3).some(t=>t.song!=="y")||same[3].song==="y"||new Set(same.slice(3).map(t=>t.song)).size!==1)throw "same";
    if(same.map(t=>t.player).join("")!=="012012")throw "order";
    const each=D.makeTurns(P,["x","y","z","w"],"each",1,"x",rnd);
    if(new Set(each.map(t=>t.song)).size!==3||each[0].song!=="x")throw "each";
    const r=D.ranking(P,[[50,70],[80],[60,60]]);
    if(r.map(x=>x.name).join("")!=="BAC"||r[0].avg!==80||r[0].place!==1)throw "rank";
    const t=D.ranking([{name:"A"},{name:"B"}],[[70],[70]]);if(t[1].place!==1)throw "tie";
    console.log("OK");"""
    out = subprocess.run(["node", "-e", js, str(ROOT / "ui" / "duel.js")], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "OK", out.stderr
