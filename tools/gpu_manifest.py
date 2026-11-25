"""Escribe KaraokeEasy-GPU-<ver>.json junto a las partes KaraokeEasy-GPU-<ver>.zip.001… (CI).

Uso: python tools/gpu_manifest.py <versión> <carpeta>
El cliente (karaoke_easy/downloads.py: start_gpu) baja cada parte, verifica su sha256, las une
y verifica el sha256 del zip completo antes de instalar.
"""
import hashlib
import json
import sys
from pathlib import Path


def build(version: str, folder: Path) -> dict:
    parts = sorted(folder.glob(f"KaraokeEasy-GPU-{version}.zip.[0-9][0-9][0-9]"))
    if not parts:
        raise SystemExit("no hay partes KaraokeEasy-GPU-<ver>.zip.NNN")
    total = hashlib.sha256()
    out = []
    for p in parts:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 22), b""):
                h.update(b)
                total.update(b)
        out.append({"name": p.name, "size": p.stat().st_size, "sha256": h.hexdigest()})
        if p.stat().st_size >= 2 * 1024 ** 3:
            raise SystemExit(f"{p.name} supera el límite de 2 GB de GitHub")
    m = {"version": version, "sha256": total.hexdigest(), "size": sum(x["size"] for x in out), "parts": out}
    (folder / f"KaraokeEasy-GPU-{version}.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    return m


if __name__ == "__main__":
    m = build(sys.argv[1], Path(sys.argv[2]))
    print(f"{len(m['parts'])} partes, {m['size'] / 1024 ** 3:.2f} GB, sha256 {m['sha256']}")
