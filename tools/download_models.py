"""Descarga los modelos en ./models para incluirlos en el instalador.
Uso: python tools/download_models.py [modelos whisper...]   (por defecto: base small)"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["KARAOKE_MODELS"] = str(ROOT / "models")
os.environ["HF_HUB_OFFLINE"] = "0"
from karaoke_easy import paths  # noqa: E402

paths.MODELS_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TORCH_HOME"] = str(paths.TORCH_HOME)

from demucs.pretrained import get_model  # noqa: E402

get_model("htdemucs")
print("Demucs htdemucs OK ->", paths.TORCH_HOME)

import torch  # noqa: E402
from torchaudio.pipelines import MMS_FA  # noqa: E402

from karaoke_easy import aligner  # noqa: E402

if not aligner.model_file().exists():
    m = MMS_FA.get_model(with_star=False)
    torch.save({k: v.half() for k, v in m.state_dict().items()}, aligner.model_file())
    import shutil
    (paths.TORCH_HOME / "hub" / "checkpoints" / "model.pt").unlink(missing_ok=True)  # copia fp32
print("MMS_FA OK ->", aligner.model_file())

from faster_whisper import download_model  # noqa: E402

for name in sys.argv[1:] or ["base", "small"]:
    out = paths.whisper_dir(name)
    download_model(name, output_dir=str(out))
    print("Whisper", name, "OK ->", out)
