"""Teléfono como micrófono.

El teléfono abre una página HTTPS servida en la red local (wifi), captura el micrófono y envía
audio PCM por WebSocket. Este módulo lo reenvía a la interfaz del PC por el servidor local
(127.0.0.1), donde entra al mismo grafo de audio que el micrófono del PC.

Seguridad:
- El servidor de la red local solo existe mientras "Micrófono del teléfono" está activo
  (start/stop), y se enlaza a la IP de la red local, no a 0.0.0.0.
- Cada sesión tiene un código de emparejamiento aleatorio (incluido en el QR); sin él no se
  sirve nada. Tras demasiados intentos fallidos se cambia el código.
- HTTPS con un certificado autofirmado creado en el primer uso (RSA 2048, solo biblioteca
  estándar): los navegadores móviles exigen un contexto seguro para usar el micrófono.
"""
import base64
import datetime
import hashlib
import hmac
import json
import secrets
import socket
import ssl
import struct
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PREFERRED_PORT = 47823
MAX_PHONES = 4
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I
MAX_BAD_ATTEMPTS = 20
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


# ---------------------------------------------------------------- certificado autofirmado
def _is_probable_prime(n, rounds=40):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits):
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _is_probable_prime(c):
            return c


def _rsa_key(bits=2048, e=65537):
    while True:
        p, q = _prime(bits // 2), _prime(bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        try:
            d = pow(e, -1, phi)
        except ValueError:
            continue
        n = p * q
        if n.bit_length() == bits:
            return n, e, d, p, q


def _der(tag, body):
    n = len(body)
    if n < 0x80:
        ln = bytes([n])
    else:
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        ln = bytes([0x80 | len(b)]) + b
    return bytes([tag]) + ln + body


def _int(v):
    b = v.to_bytes(v.bit_length() // 8 + 1, "big")  # +1: el bit alto nunca marca negativo
    return _der(0x02, b)


def _seq(*items):
    return _der(0x30, b"".join(items))


def _oid(s):
    parts = [int(x) for x in s.split(".")]
    out = bytes([parts[0] * 40 + parts[1]])
    for p in parts[2:]:
        enc = [p & 0x7F]
        p >>= 7
        while p:
            enc.append(0x80 | (p & 0x7F))
            p >>= 7
        out += bytes(reversed(enc))
    return _der(0x06, out)


_NULL = b"\x05\x00"
_SHA256_RSA = _seq(_oid("1.2.840.113549.1.1.11"), _NULL)
_SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


def _name(cn):
    return _seq(_der(0x31, _seq(_oid("2.5.4.3"), _der(0x0C, cn.encode()))))


def _time(dt):
    return _der(0x18, dt.strftime("%Y%m%d%H%M%SZ").encode())  # GeneralizedTime


def _pem(label, der):
    b = base64.encodebytes(der).decode().replace("\n", "")
    lines = "\n".join(b[i:i + 64] for i in range(0, len(b), 64))
    return f"-----BEGIN {label}-----\n{lines}\n-----END {label}-----\n"


def make_self_signed(cn="Karaoke Easy (red local)", bits=2048, days=3650):
    """Crea (cert_pem, key_pem) sin dependencias externas."""
    n, e, d, p, q = _rsa_key(bits)
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    spki = _seq(_seq(_oid("1.2.840.113549.1.1.1"), _NULL),
                _der(0x03, b"\x00" + _seq(_int(n), _int(e))))
    tbs = _seq(_der(0xA0, _int(2)), _int(secrets.randbits(63) | 1), _SHA256_RSA, _name(cn),
               _seq(_time(now - datetime.timedelta(days=1)), _time(now + datetime.timedelta(days=days))),
               _name(cn), spki)
    k = (n.bit_length() + 7) // 8
    t = _SHA256_DIGESTINFO + hashlib.sha256(tbs).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    sig = pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")
    cert = _seq(tbs, _SHA256_RSA, _der(0x03, b"\x00" + sig))
    key = _seq(_int(0), _int(n), _int(e), _int(d), _int(p), _int(q),
               _int(d % (p - 1)), _int(d % (q - 1)), _int(pow(q, -1, p)))
    return _pem("CERTIFICATE", cert), _pem("RSA PRIVATE KEY", key)


def ensure_cert(folder: Path):
    """Certificado guardado en la carpeta del usuario: se crea una sola vez, así el teléfono solo
    muestra la advertencia la primera vez (el navegador recuerda la excepción)."""
    folder.mkdir(parents=True, exist_ok=True)
    crt, key = folder / "telefono.crt", folder / "telefono.key"
    if not (crt.exists() and key.exists()):
        c, k = make_self_signed()
        key.write_text(k, encoding="ascii")
        crt.write_text(c, encoding="ascii")
    return crt, key


def fingerprint(crt: Path) -> str:
    der = ssl.PEM_cert_to_DER_cert(crt.read_text(encoding="ascii"))
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, 16, 2))


# ---------------------------------------------------------------- WebSocket mínimo
def ws_accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()


def ws_handshake(handler) -> bool:
    key = handler.headers.get("Sec-WebSocket-Key")
    if not key or "websocket" not in (handler.headers.get("Upgrade") or "").lower():
        handler.send_error(400)
        return False
    handler.protocol_version = "HTTP/1.1"  # los navegadores exigen "HTTP/1.1 101"
    handler.send_response(101, "Switching Protocols")
    handler.send_header("Upgrade", "websocket")
    handler.send_header("Connection", "Upgrade")
    handler.send_header("Sec-WebSocket-Accept", ws_accept_key(key))
    handler.end_headers()
    handler.wfile.flush()
    handler.close_connection = True
    return True


def ws_read(rfile, max_len=1 << 20):
    """Lee un mensaje. Devuelve (opcode, payload) o None si se cerró."""
    h = rfile.read(2)
    if len(h) < 2:
        return None
    op, ln = h[0] & 0x0F, h[1] & 0x7F
    masked = h[1] & 0x80
    if ln == 126:
        ln = struct.unpack(">H", rfile.read(2))[0]
    elif ln == 127:
        ln = struct.unpack(">Q", rfile.read(8))[0]
    if ln > max_len:
        return None
    mask = rfile.read(4) if masked else b""
    data = rfile.read(ln)
    if len(data) < ln:
        return None
    if masked:
        data = bytes(b ^ mask[i & 3] for i, b in enumerate(data)) if ln < 64 else _unmask(data, mask)
    return op, data


def _unmask(data, mask):
    m = int.from_bytes(mask * ((len(data) + 3) // 4), "little")
    return (int.from_bytes(data, "little") ^ (m & ((1 << (8 * len(data))) - 1))).to_bytes(len(data), "little")


def ws_frame(payload: bytes, op=2) -> bytes:
    n = len(payload)
    if n < 126:
        h = bytes([0x80 | op, n])
    elif n < 65536:
        h = bytes([0x80 | op, 126]) + struct.pack(">H", n)
    else:
        h = bytes([0x80 | op, 127]) + struct.pack(">Q", n)
    return h + payload


# ---------------------------------------------------------------- red local
def lan_ip() -> str:
    """IP de la interfaz que sale a la red (no envía tráfico: UDP connect solo elige la ruta)."""
    for target in ("192.168.0.1", "10.255.255.255", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, 1))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            pass
    return "127.0.0.1"


class Hub:
    """Estado compartido: sesión activa, teléfonos conectados y oyentes del PC."""

    def __init__(self, cert_dir: Path | None = None, static_dir: Path | None = None):
        self.cert_dir = cert_dir
        self.static_dir = static_dir
        self.lock = threading.Lock()
        self.httpd = None
        self.code = None
        self.bad = 0
        self.host = None
        self.port = None
        self.phones = {}      # slot -> {"name":..., "frames": int}
        self.listeners = []   # callables(bytes) del PC (servidor local)

    # --- ciclo de vida
    @property
    def active(self):
        return self.httpd is not None

    def start(self, host=None, port=None):
        with self.lock:
            if self.httpd:
                return self.info()
            if self.cert_dir is None:
                from . import paths
                self.cert_dir = paths.user_cache() / "telefono"
            crt, key = ensure_cert(self.cert_dir)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(crt), str(key))
            self.host = host or lan_ip()
            httpd = None
            for p in ([port] if port is not None else [PREFERRED_PORT, 0]):
                try:
                    httpd = _TLSServer((self.host, p), _make_phone_handler(self), ctx)
                    break
                except OSError:
                    continue
            if httpd is None:
                raise OSError("no se pudo abrir el puerto en la red local")
            self.port = httpd.server_address[1]
            self.code = new_code()
            self.bad = 0
            self.httpd = httpd
            self.fp = fingerprint(crt)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            return self.info()

    def stop(self):
        with self.lock:
            h, self.httpd = self.httpd, None
            self.code = None
            self.phones.clear()
        if h:
            h.shutdown()
            h.server_close()
            h.close_all()
        self._notify(None)

    def url(self):
        return f"https://{self.host}:{self.port}/m?c={self.code}" if self.active else None

    def info(self):
        from . import qr
        u = self.url()
        return {"active": self.active, "url": u, "code": self.code, "host": self.host, "port": self.port,
                "fingerprint": getattr(self, "fp", None) if self.active else None,
                "qr": qr.svg(u) if u else None,
                "phones": [{"slot": s, "name": p["name"]} for s, p in sorted(self.phones.items())]}

    # --- emparejamiento
    def check_code(self, code) -> bool:
        with self.lock:
            if not self.httpd or not self.code:
                return False
            ok = hmac.compare_digest((code or "").upper().encode(), self.code.encode())
            if not ok:
                self.bad += 1
                if self.bad >= MAX_BAD_ATTEMPTS:  # alguien está probando códigos: cambiarlo
                    self.code = new_code()
                    self.bad = 0
            return ok

    def claim_slot(self, name):
        with self.lock:
            for s in range(1, MAX_PHONES + 1):
                if s not in self.phones:
                    self.phones[s] = {"name": (name or f"Teléfono {s}")[:24], "frames": 0}
                    break
            else:
                return None
        self._notify(None)
        return s

    def release_slot(self, slot):
        with self.lock:
            self.phones.pop(slot, None)
        self._notify(None)

    # --- reenvío al PC
    def add_listener(self, fn):
        with self.lock:
            self.listeners.append(fn)

    def remove_listener(self, fn):
        with self.lock:
            if fn in self.listeners:
                self.listeners.remove(fn)

    def status_msg(self):
        return json.dumps({"type": "status", "active": self.active,
                           "phones": [{"slot": s, "name": p["name"]} for s, p in sorted(self.phones.items())]})

    def _notify(self, frame):
        """frame=None: cambio de estado (texto JSON); bytes: audio del teléfono."""
        with self.lock:
            ls = list(self.listeners)
        msg = ws_frame(self.status_msg().encode(), 1) if frame is None else ws_frame(frame, 2)
        for fn in ls:
            try:
                fn(msg)
            except Exception:
                self.remove_listener(fn)

    def push_audio(self, slot, payload):
        p = self.phones.get(slot)
        if p is not None:
            p["frames"] += 1
        # [u8 ranura][7 de relleno][f64 hora de envío][int16 PCM...]  (alineado para Float64/Int16)
        self._notify(bytes([slot]) + b"\0" * 7 + payload)


def new_code(n=6):
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(n))


class _TLSServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, ctx):
        self.ctx = ctx
        self._conns = set()
        super().__init__(addr, handler)

    def get_request(self):
        sock, addr = self.socket.accept()
        # el saludo TLS se hace en el hilo de cada conexión, no en el bucle de aceptación
        return self.ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr

    def process_request_thread(self, request, client_address):
        self._conns.add(request)
        try:
            request.settimeout(15)
            request.do_handshake()
            request.settimeout(None)
        except (OSError, ssl.SSLError):
            self._conns.discard(request)
            self.shutdown_request(request)
            return
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._conns.discard(request)

    def close_all(self):
        for c in list(self._conns):
            try:
                c.shutdown(socket.SHUT_RDWR)
                c.close()
            except OSError:
                pass


def _static():
    from . import server
    return server.STATIC


def _make_phone_handler(hub: Hub):
    class P(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype="text/plain; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            code = q.get("c", [""])[0]
            if u.path not in ("/m", "/ws"):
                return self._send(404, b"no encontrado")
            if not hub.check_code(code):
                return self._send(403, "Código incorrecto o sesión cerrada. Escanea de nuevo el QR del PC."
                                  .encode("utf-8"))
            if u.path == "/m":
                f = (hub.static_dir or _static()) / "phone.html"
                return self._send(200, f.read_bytes(), "text/html; charset=utf-8")
            if not ws_handshake(self):
                return
            slot = hub.claim_slot(q.get("n", [""])[0].strip())
            if slot is None:
                self.wfile.write(ws_frame(json.dumps({"type": "full"}).encode(), 1))
                self.wfile.write(ws_frame(b"", 8))
                return
            try:
                self.wfile.write(ws_frame(json.dumps({"type": "hello", "slot": slot}).encode(), 1))
                while hub.active:
                    m = ws_read(self.rfile)
                    if m is None:
                        break
                    op, data = m
                    if op == 8:
                        break
                    if op == 9:  # ping
                        self.wfile.write(ws_frame(data, 10))
                    elif op == 2 and len(data) >= 10:
                        hub.push_audio(slot, data)
                    elif op == 1 and data[:1] == b"{":  # medida de latencia: eco inmediato
                        self.wfile.write(ws_frame(data, 1))
            except (OSError, ssl.SSLError, struct.error):
                pass
            finally:
                hub.release_slot(slot)

    return P


HUB = Hub()


def serve_local_ws(handler, hub: Hub = None):
    """Se llama desde el servidor local (127.0.0.1) con el handler ya autorizado: mantiene un
    WebSocket abierto hacia la interfaz del PC y le reenvía estado y audio de los teléfonos."""
    hub = hub or HUB
    if not ws_handshake(handler):
        return
    wlock = threading.Lock()
    dead = threading.Event()

    def send(msg):
        if dead.is_set():
            raise OSError("cerrado")
        with wlock:
            handler.wfile.write(msg)
            handler.wfile.flush()

    try:
        send(ws_frame(hub.status_msg().encode(), 1))
    except OSError:
        return
    hub.add_listener(send)
    try:
        while True:
            m = ws_read(handler.rfile)
            if m is None or m[0] == 8:
                break
    except (OSError, struct.error):
        pass
    finally:
        dead.set()
        hub.remove_listener(send)
