"""이미지·동영상 생성: 내 PC의 ComfyUI(127.0.0.1:8188)에 그림(Krea-2 Turbo)·영상(Wan2.2 5B)을 맡기고 결과를 받아 온다.

설치는 install_gen.ps1. 그래픽 메모리가 8GB라 생성 전에 Ollama 모델을 내리고, 끝나면 ComfyUI 메모리를 비운다.
"""
import json
import random
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from office import OfficeError
from office.config import DATA

URL = "http://127.0.0.1:8188"
ROOT = DATA / "gen" / "ComfyUI_windows_portable"
IMAGE_UNET = "krea2_turbo_fp8_scaled.safetensors"
IMAGE_CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
IMAGE_VAE = "qwen_image_vae.safetensors"
VIDEO_UNET = "wan2.2_ti2v_5B_fp16.safetensors"
VIDEO_CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VIDEO_VAE = "wan2.2_vae.safetensors"
NEEDED = {f"diffusion_models/{IMAGE_UNET}": "이미지 모델(Krea-2 Turbo)", f"text_encoders/{IMAGE_CLIP}": "이미지 글 이해(Qwen3-VL)",
          f"vae/{IMAGE_VAE}": "이미지 VAE", f"diffusion_models/{VIDEO_UNET}": "동영상 모델(Wan2.2 5B)",
          f"text_encoders/{VIDEO_CLIP}": "동영상 글 이해(umt5)", f"vae/{VIDEO_VAE}": "동영상 VAE"}
IMAGE_SIZES = {"square": (1024, 1024), "portrait": (832, 1216), "landscape": (1216, 832)}
VIDEO_SIZES = {"landscape": (832, 480), "portrait": (480, 832), "square": (640, 640)}
FRAME_SIZES = {"landscape": (1248, 720), "portrait": (720, 1248), "square": (1024, 1024)}  # 영상 첫 장면 (같은 비율, 1.5배)
FPS = 24
VIDEO_NEGATIVE = "blurry, low quality, distorted, watermark, text, subtitles, static, still frame, worst quality"
IMAGE_TIMEOUT, VIDEO_TIMEOUT = 600, 3600


def krea_workflow(prompt: str, width: int, height: int, seed: int, count: int = 1) -> dict:
    """Krea-2 Turbo: 8단계, cfg 1, 부정 프롬프트는 0으로 (ComfyUI 공식 템플릿 image_krea2_turbo_t2i의 연결)."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": IMAGE_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": IMAGE_CLIP, "type": "krea2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": IMAGE_VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": count}},
        "7": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
                                                   "latent_image": ["6", 0], "seed": seed, "steps": 8, "cfg": 1.0,
                                                   "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "rab_image"}},
    }


def wan_workflow(prompt: str, width: int, height: int, frames: int, seed: int, steps: int = 20, start: str = "") -> dict:
    """Wan2.2 TI2V 5B (ComfyUI 공식 템플릿의 연결). start = ComfyUI output 폴더의 첫 장면 그림 → 그 그림을 움직인다."""
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": VIDEO_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": VIDEO_CLIP, "type": "wan", "device": "default"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": VIDEO_NEGATIVE, "clip": ["3", 0]}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VIDEO_VAE}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["6", 0], "width": width, "height": height,
                                                                  "length": frames, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "positive": ["4", 0], "negative": ["5", 0],
                                                   "latent_image": ["7", 0], "seed": seed, "steps": steps, "cfg": 5.0,
                                                   "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["6", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": float(FPS)}},
        "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": "rab_video", "format": "auto",
                                                     "format.codec": "auto"}},
    }
    if start:
        graph["12"] = {"class_type": "LoadImageOutput", "inputs": {"image": f"{start} [output]"}}
        graph["7"]["inputs"]["start_image"] = ["12", 0]
    return graph


def http(method: str, path: str, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:  # 예: 모델 파일 이름이 틀려서 일을 거절 → 이유를 그대로 보여 준다
        detail = e.read().decode("utf-8", "replace")
        try:
            info = json.loads(detail)
            detail = f"{info.get('error', {}).get('message', '')} {json.dumps(info.get('node_errors') or {}, ensure_ascii=False)}"
        except (ValueError, AttributeError):
            pass
        raise OfficeError(f"ComfyUI가 일을 거절했어요 ({e.code}): {detail.strip()[:300]}") from e
    return raw if path.startswith("/view") else (json.loads(raw) if raw else {})


def start_comfy() -> subprocess.Popen:
    log = (DATA / "comfy.log").open("ab")
    return subprocess.Popen([str(ROOT / "python_embeded" / "python.exe"), "-s", str(ROOT / "ComfyUI" / "main.py"),
                             "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch"],
                            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def unload_ollama() -> None:
    """그래픽 메모리 8GB: 그림·영상 전에 올라가 있는 Ollama 모델을 다 내린다 (다음 대화 때 다시 올라옴)."""
    from office import llm

    try:
        with urllib.request.urlopen(llm.OLLAMA_URL + "/api/ps", timeout=10) as resp:
            names = [m["name"] for m in json.load(resp).get("models", [])]
        for name in names:
            llm._post("/api/generate", {"model": name, "keep_alive": 0}, 30)
    except (OSError, ValueError, KeyError):
        pass


class Comfy:
    def __init__(self, root: Path = ROOT, http=http, start=start_comfy, sleep=time.sleep, unload_llm=unload_ollama):
        self.root, self.http, self.start_server, self.sleep, self.unload_llm = Path(root), http, start, sleep, unload_llm
        self.proc = None  # 우리가 켠 ComfyUI (퇴근할 때 끈다)

    def missing(self) -> list[str]:
        out = [] if (self.root / "run_nvidia_gpu.bat").exists() else ["ComfyUI"]
        return out + [name for path, name in NEEDED.items() if not (self.root / "ComfyUI" / "models" / path).exists()]

    def up(self) -> bool:
        try:
            self.http("GET", "/system_stats")
            return True
        except (OSError, ValueError):
            return False

    def ensure(self) -> None:
        missing = self.missing()
        if missing:
            raise OfficeError(f"이미지·동영상 AI가 아직 설치되지 않았어요 ({', '.join(missing)}). "
                              "install_gen.ps1을 실행해 주세요.")
        if self.up():
            return
        self.proc = self.start_server()
        for _ in range(120):  # 처음 켤 땐 1~2분 걸린다
            self.sleep(1)
            if self.up():
                return
        raise OfficeError("ComfyUI가 안 켜졌어요. %LOCALAPPDATA%\\ritual-office\\comfy.log를 확인해 주세요.")

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def run(self, workflow: dict, out_dir: Path, check, timeout: int = IMAGE_TIMEOUT) -> list[Path]:
        """일을 맡기고, 끝날 때까지 기다렸다가 결과 파일을 out_dir에 받는다. check()는 [중단]이면 예외를 낸다."""
        self.ensure()
        self.unload_llm()
        prompt_id = self.http("POST", "/prompt", {"prompt": workflow, "client_id": uuid.uuid4().hex})["prompt_id"]
        try:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    check()
                except BaseException:
                    self.http("POST", "/interrupt")
                    raise
                done = self.http("GET", f"/history/{prompt_id}").get(prompt_id)
                if done:
                    break
                if time.monotonic() > deadline:
                    self.http("POST", "/interrupt")
                    raise OfficeError("생성이 너무 오래 걸려서 멈췄어요.")
                self.sleep(1)
            status = done.get("status") or {}
            if status.get("status_str") == "error":
                detail = next((m[1].get("exception_message", "") for m in status.get("messages") or []
                               if m and m[0] == "execution_error"), "")
                raise OfficeError(f"생성 중 오류가 났어요: {detail.strip()[:200] or '알 수 없는 오류'}")
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            saved = []
            for node in (done.get("outputs") or {}).values():
                for item in [i for v in node.values() if isinstance(v, list) for i in v if isinstance(i, dict) and i.get("filename")]:
                    query = urllib.parse.urlencode({"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                                                    "type": item.get("type", "output")})
                    target = out_dir / Path(item["filename"]).name
                    target.write_bytes(self.http("GET", f"/view?{query}"))
                    saved.append(target)
            if not saved:
                raise OfficeError("생성은 끝났는데 결과 파일이 없어요.")
            return saved
        finally:
            try:
                self.http("POST", "/free", {"unload_models": True, "free_memory": True})  # 다음 대화(Ollama)를 위해 비운다
            except (OSError, ValueError):
                pass

    def image(self, prompt: str, out_dir: Path, check, count: int = 1, shape: str = "square") -> list[Path]:
        width, height = IMAGE_SIZES.get(shape, IMAGE_SIZES["square"])
        return self.run(krea_workflow(prompt, width, height, random.randrange(2**31), max(1, min(4, count))), out_dir, check)

    def video(self, prompt: str, out_dir: Path, check, seconds: int = 3, shape: str = "landscape") -> list[Path]:
        """[영상, 첫 장면]. Krea-2가 첫 장면을 그리고 Wan2.2가 움직인다 (글→영상만 하면 뭉개지고 과하게 날카로움)."""
        shape = shape if shape in VIDEO_SIZES else "landscape"
        width, height = VIDEO_SIZES[shape]
        first = self.run(krea_workflow(prompt, *FRAME_SIZES[shape], random.randrange(2**31)), out_dir, check)[0]
        frames = max(1, min(5, seconds)) * FPS + 1
        graph = wan_workflow(prompt, width, height, frames, random.randrange(2**31), start=first.name)
        return [*self.run(graph, out_dir, check, VIDEO_TIMEOUT), first]
