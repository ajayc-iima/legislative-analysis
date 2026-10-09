"""NVIDIA NIM clients for the reply-PDF trial.

Key handling: read once from NVIDIA_API_KEY/NIM_API_KEY env, else from the
legacy framework config (path only — the value is never printed or logged).
Every call returns (ok, payload, error, ms) so trials record failures
instead of crashing.
"""

import base64
import io
import json
import os
import time
from pathlib import Path

import requests

LEGACY_KEY_PATHS = [
    r"D:\ISB\Legislative Preparedness\.venv\mgla_config.json",
    r"D:\ISB\Legislative Preparedness\mgla_config.json",
]

CV_BASE = "https://ai.api.nvidia.com/v1/cv"
CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
EMBED_URL = "https://integrate.api.nvidia.com/v1/embeddings"

TIMEOUT = 60  # measured slow calls (vision-11b) take ~20s; anything beyond a minute is hung


def load_key(explicit=""):
    """API key from explicit arg, env, or legacy config. Never logged."""
    if explicit:
        return explicit
    key = os.environ.get("NVIDIA_API_KEY", "") or os.environ.get("NIM_API_KEY", "")
    if key:
        return key
    for path in LEGACY_KEY_PATHS:
        try:
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as handle:
                    value = json.load(handle).get("api_key", "")
                if value:
                    return value
        except (OSError, ValueError):
            pass
    return ""


def image_b64(png_bytes):
    return base64.b64encode(png_bytes).decode("ascii")


def _post(url, key, payload, timeout=TIMEOUT):
    started = time.time()
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "Accept": "application/json"},
            json=payload, timeout=timeout)
    except Exception as exc:
        return False, None, f"transport: {exc}", int(1000 * (time.time() - started))
    ms = int(1000 * (time.time() - started))
    if response.status_code != 200:
        return False, None, f"HTTP {response.status_code}: {response.text[:300]}", ms
    try:
        return True, response.json(), "", ms
    except ValueError as exc:
        return False, None, f"bad json: {exc}", ms


def cv_model(key, model, png_bytes, timeout=TIMEOUT):
    """Computer-vision NIM shape (ocr-v1 proven): {input: [{type, url: data:...}]}."""
    return _post(f"{CV_BASE}/{model}", key,
                 {"input": [{"type": "image_url",
                             "url": f"data:image/png;base64,{image_b64(png_bytes)}"}]},
                 timeout=timeout)


def chat_vl(key, model, png_bytes, prompt, tools=None, max_tokens=2048, timeout=TIMEOUT):
    """OpenAI-compatible chat shape for vision-language models."""
    content = [{"type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64(png_bytes)}"}},
               {"type": "text", "text": prompt}]
    payload = {"model": model, "messages": [{"role": "user", "content": content}],
               "temperature": 0, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
    return _post(CHAT_URL, key, payload, timeout=timeout)


def parse_document(key, png_bytes, tool="markdown_no_bbox", timeout=TIMEOUT):
    """nemotron-parse: markdown for one page image (image-only content).

    Returns (ok, markdown_text, error, ms): the transcription arrives in
    tool_calls[0].function.arguments, not in message content.
    """
    import json as _json
    ok, payload, error, ms = _post(
        CHAT_URL, key,
        {"model": "nvidia/nemotron-parse",
         "tools": [{"type": "function", "function": {"name": tool}}],
         "messages": [{"role": "user", "content": [
             {"type": "image_url",
              "image_url": {"url": f"data:image/png;base64,{image_b64(png_bytes)}"}}]}],
         "temperature": 0.0},
        timeout=timeout)
    if not ok:
        return ok, "", error, ms
    try:
        calls = (payload.get("choices") or [{}])[0].get("message", {}).get("tool_calls") or []
        text = "".join(
            (call.get("function") or {}).get("arguments", "") for call in calls)
        return True, text, "", ms
    except (KeyError, IndexError, TypeError) as exc:
        return False, "", f"unexpected parse response: {exc}", ms


def embed_text(key, text, input_type="passage", timeout=TIMEOUT):
    """Text embeddings via llama-nemotron-embed-vl (2048-dim).

    String input + input_type is the working shape; returns
    (ok, vector, error, ms).
    """
    ok, payload, error, ms = _post(
        EMBED_URL, key,
        {"model": "nvidia/llama-nemotron-embed-vl-1b-v2",
         "input_type": input_type, "input": text, "encoding_format": "float"},
        timeout=timeout)
    if not ok:
        return ok, [], error, ms
    try:
        return True, (payload.get("data") or [{}])[0].get("embedding", []), "", ms
    except (KeyError, IndexError, TypeError) as exc:
        return False, [], f"unexpected embed response: {exc}", ms


def render_page(pdf_path, page=0, dpi=200, max_bytes=1_800_000):
    """Render one PDF page to PNG bytes, downscaling only if over max_bytes.

    Keep max_bytes generous: OCR accuracy collapses on thumbnails, and the
    CV endpoints accept multi-MB payloads. Downscaling is a last resort.
    """
    import pymupdf
    with pymupdf.open(pdf_path) as doc:
        pix = doc[page].get_pixmap(dpi=dpi)
        data = pix.tobytes("png")
    if len(data) <= max_bytes:
        return data
    from PIL import Image
    scale = 0.85
    while len(data) > max_bytes and scale > 0.3:
        image = Image.open(io.BytesIO(data))
        size = (int(image.width * scale), int(image.height * scale))
        buffer = io.BytesIO()
        image.resize(size).save(buffer, format="PNG", optimize=True)
        data = buffer.getvalue()
        scale -= 0.15
    return data


def page_text_layer(pdf_path, page=0):
    """Native text layer length (0 for pure scans)."""
    import pymupdf
    with pymupdf.open(pdf_path) as doc:
        return len(doc[page].get_text().strip())
