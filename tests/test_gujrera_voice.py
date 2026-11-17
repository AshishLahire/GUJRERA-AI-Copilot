"""Voice input endpoint: validation and a real (silent) transcription with Whisper small."""

from __future__ import annotations

import io
import wave

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gujrera.api.routes import router


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _silence(seconds: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


@pytest.mark.parametrize("name,data,lang", [
    ("q.txt", b"x", None),        # not audio
    ("q.wav", b"", None),         # empty
    ("q.wav", b"notaudio", None),  # undecodable
    ("q.wav", b"RIFF", "fr"),     # unsupported language
])
def test_voice_rejects_bad_input(client, name, data, lang):
    form = {"lang": lang} if lang else {}
    assert client.post("/api/gujrera/voice/transcribe", files={"file": (name, data)}, data=form).status_code == 400


def test_voice_transcribes_and_deletes_audio(client):
    pytest.importorskip("faster_whisper")
    from gujrera.api.routes import VOICE_DIR

    before = set(VOICE_DIR.glob("*")) if VOICE_DIR.exists() else set()
    res = client.post("/api/gujrera/voice/transcribe", files={"file": ("q.wav", _silence(), "audio/wav")},
                      data={"lang": "gu"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["language"] == "gu" and body["low_quality"] is True and isinstance(body["text"], str)
    after = set(VOICE_DIR.glob("*")) if VOICE_DIR.exists() else set()
    assert after == before  # the recording is not kept
