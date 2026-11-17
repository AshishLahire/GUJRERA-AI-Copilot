"""Download and load Whisper ASR model once, printing progress and final cache path."""

from __future__ import annotations

import sys
from pathlib import Path
from faster_whisper import download_model, WhisperModel

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from factcheck.config import get_settings


def main() -> int:
    settings = get_settings()
    model_name = settings.WHISPER_MODEL
    device = settings.WHISPER_DEVICE
    compute_type = settings.WHISPER_COMPUTE_TYPE

    print(f"=== Downloading Whisper ASR Model '{model_name}' ===")
    print(f"Target settings: device={device}, compute_type={compute_type}")
    print("Downloading weights (one-time setup)...")
    cache_path = download_model(model_name)
    print(f"Model cache path: {cache_path}")

    print("Verifying model initialization in memory...")
    model = WhisperModel(cache_path, device=device, compute_type=compute_type)
    print(f"Model verified and loaded successfully.")
    print(f"Supported languages count: {len(model.supported_languages)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
