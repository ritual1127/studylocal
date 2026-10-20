import base64
import json
import time
import urllib.error
import urllib.request

from office import OfficeError
from office.config import OLLAMA_URL, MODEL, NUM_CTX, MAX_INPUT_CHARS

_up_cache = (0.0, False)


def _post(path: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(OLLAMA_URL + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def chat(system: str, user: str, *, images: list[bytes] | None = None,
         schema: dict | None = None, temperature: float = 0.2) -> str:
    message = {"role": "user", "content": user}
    if images:
        message["images"] = [base64.b64encode(img).decode("ascii") for img in images]
    payload = {"model": MODEL, "stream": False, "think": False, "keep_alive": "10m",
               "options": {"num_ctx": NUM_CTX, "temperature": temperature},
               "messages": [{"role": "system", "content": system}, message]}
    if schema is not None:
        payload["format"] = schema
    timeout_msg = "AI 응답이 10분을 넘겼어. 다시 시도해줘."
    try:
        return _post("/api/chat", payload, 600)["message"]["content"]
    except urllib.error.HTTPError as e:  # URLError보다 먼저 (하위 클래스)
        if e.code == 404:
            raise OfficeError(f"모델 {MODEL}이(가) 없어. 터미널에서 `ollama pull {MODEL}` 해줘.") from e
        body = e.read().decode("utf-8", "replace")[:200]
        raise OfficeError(f"Ollama 오류 {e.code}: {body}") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise OfficeError(timeout_msg) from e
        raise OfficeError("Ollama가 꺼져 있어. 작업 표시줄에서 Ollama를 켜줘.") from e
    except TimeoutError as e:
        raise OfficeError(timeout_msg) from e
    except ConnectionError as e:
        raise OfficeError("Ollama가 꺼져 있어. 작업 표시줄에서 Ollama를 켜줘.") from e


def chat_json(system: str, user: str, schema: dict, *, images: list[bytes] | None = None,
              temperature: float = 0.2) -> dict:
    for _ in range(2):
        try:
            return json.loads(chat(system, user, images=images, schema=schema, temperature=temperature))
        except json.JSONDecodeError:
            continue
    raise OfficeError("AI가 형식에 안 맞는 답을 했어. 다시 시도해줘.")


def is_up() -> bool:
    global _up_cache
    checked, up = _up_cache
    if time.monotonic() - checked < 5:
        return up
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/version", timeout=2):
            up = True
    except (OSError, ValueError):
        up = False
    _up_cache = (time.monotonic(), up)
    return up


def clip(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "\n\n(이하 생략)"
