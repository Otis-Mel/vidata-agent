"""Lớp gọi LLM duy nhất của project. Mọi agent chỉ gọi `llm.generate(...)`.

- Provider mặc định: Gemini (SDK `google-genai`). Đổi provider/model chỉ cần sửa ở đây hoặc .env.
- Cache trên đĩa (data/.llm_cache): chạy lại eval không tốn thêm request.
- Retry với exponential backoff khi gặp lỗi tạm thời (429/503...).
- Ghi lại token, độ trễ, số lần gọi để làm bảng chi phí.

.env:
    GEMINI_API_KEY=...
    GEMINI_MODEL=...            # kiểm tra tên model hiện hành trong Google AI Studio
    LLM_MIN_INTERVAL=0          # giây giữa 2 request (tăng nếu bị rate limit, vd 4)
"""
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / ".llm_cache"
DEFAULT_MODEL = "gemini-2.5-flash"  # chỉnh bằng GEMINI_MODEL trong .env nếu tên model đã đổi
TRANSIENT = ("429", "500", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE", "timeout", "overloaded")


@dataclass
class LLMResult:
    text: str
    in_tokens: int = 0
    out_tokens: int = 0
    latency_s: float = 0.0
    cached: bool = False


class LLM:
    def __init__(self, provider=None, model=None, use_cache=True, max_retries=5, min_interval=None):
        """provider: callable(prompt, system, temperature, model) -> (text, in_tokens, out_tokens).
        Mặc định dùng Gemini; truyền provider giả để test không cần key."""
        self.model = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
        self._provider = provider or self._gemini_provider
        self._client = None
        self.use_cache = use_cache
        self.max_retries = max_retries
        self.min_interval = float(os.getenv("LLM_MIN_INTERVAL", "0")) if min_interval is None else min_interval
        self._last_call = 0.0
        self.stats = {"calls": 0, "cache_hits": 0, "retries": 0, "in_tokens": 0, "out_tokens": 0, "latency_s": 0.0}

    # ---- Gemini ----
    def _gemini_provider(self, prompt, system, temperature, model):
        from google import genai
        from google.genai import types

        if self._client is None:
            key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not key:
                raise RuntimeError("Thiếu GEMINI_API_KEY. Tạo file .env từ .env.example và điền key.")
            self._client = genai.Client(api_key=key)
        cfg = types.GenerateContentConfig(temperature=temperature, system_instruction=system)
        r = self._client.models.generate_content(model=model, contents=prompt, config=cfg)
        um = getattr(r, "usage_metadata", None)
        in_t = getattr(um, "prompt_token_count", 0) or 0
        out_t = (getattr(um, "candidates_token_count", 0) or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
        return (r.text or ""), in_t, out_t

    # ---- cache ----
    def _key(self, prompt, system, temperature):
        raw = json.dumps([self.model, system, prompt, temperature], ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def generate(self, prompt: str, system: str | None = None, temperature: float = 0.0) -> LLMResult:
        key = self._key(prompt, system, temperature)
        path = CACHE_DIR / f"{key}.json"
        if self.use_cache and path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            self.stats["calls"] += 1
            self.stats["cache_hits"] += 1
            return LLMResult(d["text"], d["in_tokens"], d["out_tokens"], d.get("latency_s", 0.0), True)

        attempt = 0
        while True:
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            t0 = time.time()
            try:
                text, in_t, out_t = self._provider(prompt, system, temperature, self.model)
                break
            except Exception as e:  # noqa: BLE001
                self._last_call = time.time()
                transient = any(s.lower() in str(e).lower() for s in TRANSIENT)
                if not transient or attempt >= self.max_retries:
                    raise
                attempt += 1
                self.stats["retries"] += 1
                time.sleep(min(60, 2 ** attempt + random.random()))
        self._last_call = time.time()
        latency = time.time() - t0

        self.stats["calls"] += 1
        self.stats["in_tokens"] += in_t
        self.stats["out_tokens"] += out_t
        self.stats["latency_s"] += latency
        if self.use_cache and text:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"text": text, "in_tokens": in_t, "out_tokens": out_t, "latency_s": latency},
                                       ensure_ascii=False),
                            encoding="utf-8")
        return LLMResult(text, in_t, out_t, latency, False)
