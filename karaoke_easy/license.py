"""Licencias: prueba gratuita, activación con Lemon Squeezy y funciones por plan.

Resumen:
  * Sin licencia: 14 días de prueba con todo. Después, la app abre y reproduce lo ya
    procesado, pero no deja crear canciones nuevas.
  * Activación: una sola vez en línea (Lemon Squeezy, máximo de equipos configurado allá).
    Luego funciona sin conexión. Se revalida en segundo plano como mucho una vez al día;
    si no hay conexión se sigue funcionando, y tras 30 días sin ninguna validación
    exitosa se pide reconectar.
  * Plan según el nombre de la variante: "Profesor" o "Eventos".

Toda la conversación con Lemon Squeezy está en `LemonSqueezy` (abajo): si su formato
cambia, solo hay que tocar esa clase. Todas las reglas de qué permite cada plan están en
`FEATURES` / `allows()` / `max_queued_jobs()`.
"""
import base64
import hashlib
import hmac
import json
import os
import platform
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import paths

# ---------------------------------------------------------------- configuración
# TODO(dueño): poner los ids reales de la tienda y del producto en Lemon Squeezy
# (Store > Settings y Products > ... > id). Mientras sean None no se filtra por ese campo.
LS_STORE_ID = None          # TODO: p. ej. 123456
LS_PRODUCT_IDS = ()         # TODO: p. ej. (654321,)  — productos de Karaoke Easy aceptados
BUY_URL = "https://karaoke-easy.lemonsqueezy.com/"  # TODO: enlace real de compra (checkout)
LS_API = "https://api.lemonsqueezy.com/v1/licenses/"

TRIAL_DAYS = 14
REVALIDATE_EVERY = 1 * 86400  # una vez al día: un bloqueo remoto llega en menos de 24 h si hay internet
OFFLINE_GRACE = 30 * 86400
HTTP_TIMEOUT = 15

# Qué permite cada estado. Cambiar aquí y nada más.
#   create : crear canciones nuevas
#   batch  : poner muchas canciones en cola (sin límite)
#   party  : modo fiesta y segunda pantalla
FEATURES = {
    "trial":      {"create": True,  "batch": True,  "party": True},
    "eventos":    {"create": True,  "batch": True,  "party": True},
    "profesor":   {"create": True,  "batch": False, "party": False},
    "reconnect":  {"create": False, "batch": False, "party": False},
    "unlicensed": {"create": False, "batch": False, "party": False},
}
MAX_QUEUED_NO_BATCH = 3  # trabajos en cola/en curso a la vez sin la función "batch"

TIER_NAMES = {"profesor": "Profesor", "eventos": "Eventos"}


class LicenseError(Exception):
    """Error con mensaje para mostrar al usuario (en español)."""


# ---------------------------------------------------------------- Lemon Squeezy
class LemonSqueezy:
    """API pública de licencias (no requiere clave de API). Cuerpo form-urlencoded,
    respuesta JSON. Los errores llegan con HTTP 4xx y {"error": "..."} en el cuerpo."""

    def __init__(self, base=LS_API, timeout=HTTP_TIMEOUT):
        self.base, self.timeout = base, timeout

    def _post(self, endpoint, data):
        req = urllib.request.Request(self.base + endpoint, data=urllib.parse.urlencode(data).encode(),
                                     headers={"Accept": "application/json",
                                              "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:  # 400/404/422: la respuesta trae el motivo
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                raise ConnectionError(f"HTTP {e.code}") from e
        # URLError / timeout / OSError se propagan: significan "sin conexión"

    def activate(self, key, instance_name):
        return self._post("activate", {"license_key": key, "instance_name": instance_name})

    def validate(self, key, instance_id):
        return self._post("validate", {"license_key": key, "instance_id": instance_id})

    def deactivate(self, key, instance_id):
        return self._post("deactivate", {"license_key": key, "instance_id": instance_id})


def _tier_from(meta) -> str | None:
    name = f"{meta.get('variant_name', '')} {meta.get('product_name', '')}".lower()
    if "eventos" in name:
        return "eventos"
    if "profesor" in name:
        return "profesor"
    return None


def _check_product(meta):
    if LS_STORE_ID is not None and meta.get("store_id") != LS_STORE_ID:
        raise LicenseError("Esta clave no es de Karaoke Easy.")
    if LS_PRODUCT_IDS and meta.get("product_id") not in LS_PRODUCT_IDS:
        raise LicenseError("Esta clave no es de Karaoke Easy.")


def _translate_error(msg: str) -> str:
    m = (msg or "").lower()
    if "activation limit" in m or "limit" in m:
        return "Esta clave ya está activada en el máximo de equipos. Desactívala en otro equipo primero."
    if "expired" in m:
        return "Esta licencia está vencida."
    if "disabled" in m or "revoked" in m or "inactive" in m:
        return "Esta licencia está desactivada."
    if "not found" in m or "invalid" in m:
        return "La clave no es válida. Revisa que esté bien copiada."
    return "No se pudo activar: " + (msg or "error desconocido")


# ---------------------------------------------------------------- huella del equipo
def machine_fingerprint() -> str:
    """Hash del MachineGuid de Windows; fuera de Windows (desarrollo/pruebas), de otros
    identificadores estables. Se puede forzar con KARAOKE_FINGERPRINT (pruebas)."""
    raw = os.environ.get("KARAOKE_FINGERPRINT")
    if not raw:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as k:
                raw = winreg.QueryValueEx(k, "MachineGuid")[0]
        except Exception:
            raw = None
    if not raw:
        for f in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                raw = open(f).read().strip()
                break
            except OSError:
                pass
    if not raw:
        import uuid
        raw = f"{platform.node()}-{uuid.getnode()}"
    return hashlib.sha256(("karaoke-easy:" + raw).encode()).hexdigest()


# ---------------------------------------------------------------- almacenamiento
# Un programa en Python no puede esconder un secreto: cualquiera puede leer el código.
# La firma HMAC (con clave derivada de la huella del equipo) solo evita ediciones casuales
# del archivo y que se copie a otro PC. Es suficiente para el objetivo: que pagar sea más
# fácil que piratear, no hacerlo imposible.
def _sig_key(fp):
    return hashlib.sha256(b"ke-license-v1|" + fp.encode()).digest()


def _sign(data: dict, fp: str) -> str:
    body = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(_sig_key(fp), body, hashlib.sha256).hexdigest()


def _write_signed(path, data, fp):
    blob = {"d": data, "s": _sign(data, fp)}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(base64.b64encode(json.dumps(blob).encode()).decode(), encoding="ascii")
    os.replace(tmp, path)


def _read_signed(path, fp):
    try:
        blob = json.loads(base64.b64decode(path.read_text(encoding="ascii")))
        if hmac.compare_digest(blob["s"], _sign(blob["d"], fp)):
            return blob["d"]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- gestor
class LicenseManager:
    def __init__(self, folder=None, client=None, clock=time.time, fingerprint=None):
        self.folder = folder or paths.user_cache()
        self.client = client or LemonSqueezy()
        self.clock = clock
        self.fp = fingerprint or machine_fingerprint()
        self.lock = threading.Lock()

    @property
    def _lic_file(self):
        return self.folder / "licencia.dat"

    @property
    def _trial_file(self):
        return self.folder / "prueba.dat"

    def _license(self):
        d = _read_signed(self._lic_file, self.fp) if self._lic_file.exists() else None
        return d if d and d.get("fp") == self.fp else None

    def _save(self, lic):
        _write_signed(self._lic_file, lic, self.fp)

    def _drop(self):
        try:
            self._lic_file.unlink()
        except OSError:
            pass

    def trial_start(self):
        d = _read_signed(self._trial_file, self.fp) if self._trial_file.exists() else None
        if not d or "start" not in d:  # primera vez (o archivo manipulado: no reiniciar a favor)
            start = self.clock() if not self._trial_file.exists() else 0
            _write_signed(self._trial_file, {"start": start}, self.fp)
            return start
        return d["start"]

    # ---- estado
    def status(self):
        now = self.clock()
        trial_start = self.trial_start()  # la prueba cuenta desde el primer uso, haya licencia o no
        lic = self._license()
        if lic:
            state = lic["tier"]
            if now - lic.get("validated_at", 0) > OFFLINE_GRACE:
                state = "reconnect"
            return self._public(state, lic=lic)
        left = TRIAL_DAYS * 86400 - (now - trial_start)
        if left > 0:
            return self._public("trial", days_left=int(-(-left // 86400)))
        return self._public("unlicensed", days_left=0)

    def _public(self, state, lic=None, days_left=None):
        labels = {"trial": "Prueba", "reconnect": "Conéctate a internet para verificar tu licencia",
                  "unlicensed": "Sin licencia"}
        out = {"state": state, "label": TIER_NAMES.get(state) or labels[state],
               "tier": lic["tier"] if lic else None, "features": dict(FEATURES[state]),
               "max_queued": max_queued_jobs(state), "buy_url": BUY_URL, "trial_days": TRIAL_DAYS}
        if days_left is not None:
            out["days_left"] = days_left
        if lic:
            k = lic["key"]
            out.update({"key_hint": "…" + k[-4:], "validated_at": lic.get("validated_at"),
                        "expires_at": lic.get("expires_at")})
        return out

    def allows(self, feature):
        return allows(self.status()["state"], feature)

    # ---- activación
    def activate(self, key):
        key = (key or "").strip()
        if not key:
            raise LicenseError("Escribe tu clave de licencia.")
        try:
            r = self.client.activate(key, f"{platform.node() or 'PC'} ({self.fp[:8]})")
        except (OSError, ConnectionError):
            raise LicenseError("No hay conexión a internet. La activación necesita conexión una sola vez.")
        if not r.get("activated"):
            raise LicenseError(_translate_error(r.get("error")))
        meta, lk, inst = r.get("meta") or {}, r.get("license_key") or {}, r.get("instance") or {}
        try:
            _check_product(meta)
            tier = _tier_from(meta)
            if not tier:
                raise LicenseError("Esta clave no corresponde a un plan de Karaoke Easy.")
        except LicenseError:  # no dejar ocupado un cupo de equipo con una clave ajena
            try:
                self.client.deactivate(key, inst.get("id"))
            except Exception:
                pass
            raise
        lic = {"key": key, "instance_id": inst.get("id"), "tier": tier, "fp": self.fp,
               "variant": meta.get("variant_name"), "expires_at": lk.get("expires_at"),
               "activated_at": self.clock(), "validated_at": self.clock(), "checked_at": self.clock()}
        with self.lock:
            self._save(lic)
        return self.status()

    def deactivate(self):
        lic = self._license()
        if not lic:
            return self.status()
        try:
            r = self.client.deactivate(lic["key"], lic["instance_id"])
        except (OSError, ConnectionError):
            raise LicenseError("No hay conexión a internet. Conéctate para liberar este equipo.")
        if not r.get("deactivated") and "not found" not in (r.get("error") or "").lower():
            raise LicenseError("No se pudo desactivar: " + (r.get("error") or "error desconocido"))
        with self.lock:
            self._drop()
        return self.status()

    # ---- revalidación
    def revalidate(self, force=False):
        """Devuelve True si se consultó el servidor. Sin conexión no cambia nada."""
        lic = self._license()
        if not lic:
            return False
        now = self.clock()
        if not force and now - lic.get("checked_at", 0) < REVALIDATE_EVERY \
                and now - lic.get("validated_at", 0) < REVALIDATE_EVERY:
            return False
        try:
            r = self.client.validate(lic["key"], lic["instance_id"])
        except (OSError, ConnectionError):
            return False  # sin conexión: seguir con lo guardado
        status = ((r.get("license_key") or {}).get("status") or "").lower()
        with self.lock:
            if r.get("valid") and status not in ("expired", "disabled", "inactive"):
                lic.update(validated_at=now, checked_at=now,
                           expires_at=(r.get("license_key") or {}).get("expires_at"))
                tier = _tier_from(r.get("meta") or {})
                if tier:
                    lic["tier"] = tier
                self._save(lic)
            elif r.get("valid") is False or status in ("expired", "disabled", "inactive"):
                self._drop()  # revocada, vencida, desactivada o instancia borrada
            else:
                lic["checked_at"] = now
                self._save(lic)
        return True

    def revalidate_in_background(self):
        def run():
            try:
                self.revalidate()
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- reglas por plan
def allows(state, feature) -> bool:
    return bool(FEATURES.get(state, FEATURES["unlicensed"]).get(feature))


def max_queued_jobs(state):
    """None = sin límite."""
    return None if allows(state, "batch") else MAX_QUEUED_NO_BATCH


def check_new_jobs(state, active_now, adding):
    """Mensaje de error (en español) si no se pueden añadir `adding` trabajos; None si sí."""
    if not allows(state, "create"):
        if state == "reconnect":
            return "Conéctate a internet para verificar tu licencia y seguir creando canciones."
        return ("Tu prueba gratuita terminó. Puedes seguir cantando las canciones que ya tienes; "
                "para crear nuevas, activa una licencia en Ajustes.")
    lim = max_queued_jobs(state)
    if lim is not None and active_now + adding > lim:
        return (f"Con el plan Profesor puedes tener hasta {lim} canciones en proceso a la vez. "
                "Espera a que terminen o pásate al plan Eventos para procesar muchas de una vez.")
    return None


_MANAGER = None


def manager() -> LicenseManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = LicenseManager()
    return _MANAGER
