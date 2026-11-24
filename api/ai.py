"""POST /api/ai: the app's AI calls, sent to a free model API so no paid account is needed.

Request JSON:  {"prompt": "...", "json": true|false, "images": [{"mime": "image/png", "data": "<base64>"}]}
Response JSON: {"text": "...", "provider": "gemini|groq"}  or  {"error": "...", "code": "..."}

Providers, tried in order:
  1. Google Gemini, free tier (GEMINI_API_KEY; model GEMINI_MODEL). Reads images too.
  2. Groq, free tier (GROQ_API_KEY; model GROQ_MODEL). Text only. Used if Gemini is
     missing, rate-limited or down.
  3. Any OpenAI-compatible API, e.g. OpenAI itself (paid) (OPENAI_API_KEY, OPENAI_MODEL,
     optional OPENAI_BASE_URL). Only used if its key is set.
Ollama is not called from here: it runs on your own computer, so the app calls it
straight from the browser.
Set LAMAR_PASSCODE to stop strangers who find the URL from using up your free quota.
"""
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
# Used when the main model is overloaded (HTTP 503) or rate-limited. Set to "" to turn off.
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
RETRY_WAIT = 1.5  # seconds before retrying an overloaded model
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_BODY = 12 * 1024 * 1024


class ProviderError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def post_json(url, payload, headers, timeout=55):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        code = "rate_limited" if e.code == 429 else "bad_key" if e.code in (401, 403) else \
            "bad_model" if e.code == 404 else "overloaded" if e.code in (500, 503) else "provider_error"
        raise ProviderError(code, f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ProviderError("unavailable", str(e)) from e


def call_gemini(prompt, want_json, images):
    """Main model, one retry if it's overloaded, then the lighter fallback model."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ProviderError("not_configured", "GEMINI_API_KEY is not set")
    err = None
    for model, wait in ((GEMINI_MODEL, 0), (GEMINI_MODEL, RETRY_WAIT), (GEMINI_FALLBACK_MODEL, 0)):
        if not model:
            continue
        if wait:
            if err.code != "overloaded":
                continue  # retrying the same model only helps when it's overloaded
            time.sleep(wait)
        try:
            return gemini_once(key, model, prompt, want_json, images)
        except ProviderError as e:
            if e.code not in ("overloaded", "rate_limited"):
                if err and model == GEMINI_FALLBACK_MODEL and e.code == "bad_model":
                    break  # fallback alias unavailable: report the main model's problem
                raise
            err = e
    raise err


def gemini_once(key, model, prompt, want_json, images):
    parts = [{"text": prompt}] + [{"inline_data": {"mime_type": i.get("mime", "image/png"), "data": i["data"]}}
                                  for i in images]
    cfg = {"temperature": 0.4}
    if want_json:
        cfg["responseMimeType"] = "application/json"
    out = post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    {"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg},
                    {"x-goog-api-key": key})
    try:
        return "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        reason = (out.get("promptFeedback") or {}).get("blockReason") or "empty answer"
        raise ProviderError("provider_error", f"Gemini returned no text ({reason})")


def call_groq(prompt, want_json, images):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise ProviderError("not_configured", "GROQ_API_KEY is not set")
    if images:
        raise ProviderError("no_images", "Groq fallback can't read images")
    body = {"model": GROQ_MODEL, "temperature": 0.4, "messages": [{"role": "user", "content": prompt}]}
    if want_json:
        body["response_format"] = {"type": "json_object"}
        body["messages"][0]["content"] += "\n\nIf the answer is a list, wrap it as {\"items\": [...]}."
    out = post_json("https://api.groq.com/openai/v1/chat/completions", body, {"Authorization": f"Bearer {key}"})
    return unwrap(out["choices"][0]["message"]["content"], want_json)


def call_openai(prompt, want_json, images):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ProviderError("not_configured", "OPENAI_API_KEY is not set")
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        raise ProviderError("bad_model", "Set OPENAI_MODEL to a model your key can use")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": f"data:{i.get('mime', 'image/png')};base64,{i['data']}"}}
        for i in images]
    body = {"model": model, "messages": [{"role": "user", "content": content if images else prompt}]}
    if want_json:
        body["response_format"] = {"type": "json_object"}
        body["messages"][0]["content"] = (content if images else prompt)
        if not images:
            body["messages"][0]["content"] += "\n\nIf the answer is a list, wrap it as {\"items\": [...]}."
    out = post_json(f"{base}/chat/completions", body, {"Authorization": f"Bearer {key}"})
    return unwrap(out["choices"][0]["message"]["content"], want_json)


def unwrap(text, want_json):
    if want_json:
        try:
            v = json.loads(text)
            if isinstance(v, dict) and list(v.keys()) == ["items"]:
                return json.dumps(v["items"])
        except json.JSONDecodeError:
            pass
    return text


def complete(prompt, want_json=False, images=()):
    errors = []
    for name, fn in (("gemini", call_gemini), ("groq", call_groq), ("openai", call_openai)):
        try:
            return {"text": fn(prompt, want_json, list(images)), "provider": name}
        except ProviderError as e:
            errors.append((name, e))
            if e.code in ("bad_request",):
                break
    configured = [(n, e) for n, e in errors if e.code != "not_configured"]
    if not configured:
        return {"error": "No AI key is set up. Add GEMINI_API_KEY in Vercel settings and redeploy, or pick Ollama in the app.",
                "code": "not_configured"}
    name, e = configured[0]
    if any(err.code == "rate_limited" for _, err in configured):
        return {"error": "The free AI quota is used up for now. Try again later.", "code": "rate_limited"}
    if any(err.code == "overloaded" for _, err in configured):
        return {"error": "Google's free AI models are overloaded right now. Try again in a minute, "
                         "or add a free GROQ_API_KEY in Vercel as a backup.", "code": "rate_limited"}
    return {"error": f"{name}: {e}", "code": e.code}


class handler(BaseHTTPRequestHandler):
    def _send(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        need = os.environ.get("LAMAR_PASSCODE")
        if need and self.headers.get("x-lamar-passcode") != need:
            return self._send(401, {"error": "Passcode needed", "code": "passcode"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._send(400, {"error": "Request too large or empty", "code": "bad_request"})
        try:
            req = json.loads(self.rfile.read(n))
            prompt = str(req["prompt"])
        except (json.JSONDecodeError, KeyError, TypeError):
            return self._send(400, {"error": "Bad request", "code": "bad_request"})
        res = complete(prompt, bool(req.get("json")), req.get("images") or [])
        status = 200 if "text" in res else (429 if res["code"] == "rate_limited" else 502)
        self._send(status, res)
