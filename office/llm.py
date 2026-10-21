import base64
import json
import time
import urllib.error
import urllib.request

from office import OfficeError
from office.config import KEEP_ALIVE, MAX_INPUT_CHARS, MODELS, NUM_CTX, OLLAMA_URL

_up_cache = (0.0, False)
mode = "fast"  # 설정의 AI 모드 (fast | careful), 서버가 바꾼다


def model() -> str:
    return MODELS[mode]


def _options() -> dict:
    # ponytail: 꼼꼼 모드는 레이어를 전부 GPU에 (Ollama 추정이 보수적이라 16%를 CPU에 둠). 메모리가 모자라 500이 나면 기본 배치로 다시
    return {"num_ctx": NUM_CTX, **({"num_gpu": 99} if mode == "careful" else {})}


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
    name = model()
    payload = {"model": name, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
               "options": {**_options(), "temperature": temperature},
               "messages": [{"role": "system", "content": system}, message]}
    if schema is not None:
        payload["format"] = schema
    timeout_msg = "AI 응답이 10분을 넘겼어. 다시 시도해줘."
    try:
        try:
            return _post("/api/chat", payload, 600)["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code != 500 or payload["options"].pop("num_gpu", None) is None:
                raise
            return _post("/api/chat", payload, 600)["message"]["content"]  # 그래픽 메모리가 모자람 → Ollama가 나눠 싣게
    except urllib.error.HTTPError as e:  # URLError보다 먼저 (하위 클래스)
        if e.code == 404:
            raise OfficeError(f"모델 {name}이(가) 없어. 터미널에서 `ollama pull {name}` 해줘.") from e
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


def warm() -> None:
    """모델을 미리 GPU에 올려 둔다 (첫 작업이 로딩을 기다리지 않게). 옵션이 다르면 Ollama가 다시 올리므로 같은 옵션으로."""
    try:
        _post("/api/chat", {"model": model(), "messages": [], "keep_alive": KEEP_ALIVE, "options": _options()}, 120)
    except (OSError, ValueError):
        pass


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
