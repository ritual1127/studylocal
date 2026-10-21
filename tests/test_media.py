import json

import pytest

from office import OfficeError
from office.media import Comfy, krea_workflow, wan_workflow


class FakeHTTP:
    """ComfyUI 흉내: /prompt 받으면 몇 번 뒤 /history에 결과를 낸다."""
    def __init__(self, outputs, polls=2):
        self.outputs, self.polls, self.calls = outputs, polls, []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/system_stats":
            return {"system": {}}
        if path == "/prompt":
            return {"prompt_id": "p1"}
        if path.startswith("/history/"):
            self.polls -= 1
            return {} if self.polls > 0 else {"p1": {"outputs": self.outputs, "status": {"status_str": "success"}}}
        if path.startswith("/view"):
            return b"IMAGEBYTES"
        if path in ("/free", "/interrupt"):
            return {}
        raise AssertionError(path)


def make(tmp_path, http, installed=True):
    root = tmp_path / "ComfyUI_windows_portable"
    if installed:
        for sub in ("ComfyUI/models/diffusion_models/krea2_turbo_fp8_scaled.safetensors",
                    "ComfyUI/models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors", "ComfyUI/models/vae/qwen_image_vae.safetensors",
                    "ComfyUI/models/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
                    "ComfyUI/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                    "ComfyUI/models/vae/wan2.2_vae.safetensors", "run_nvidia_gpu.bat"):
            (root / sub).parent.mkdir(parents=True, exist_ok=True)
            (root / sub).write_bytes(b"x")
    return Comfy(root=root, http=http, start=lambda: None, sleep=lambda s: None, unload_llm=lambda: None)


def test_workflows_are_wired():
    f = krea_workflow("a cat", 1024, 768, seed=7, count=2)
    kinds = {n["class_type"] for n in f.values()}
    assert {"UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "ConditioningZeroOut", "EmptyLatentImage", "KSampler",
            "VAEDecode", "SaveImage"} <= kinds  # ComfyUI 공식 Krea-2 Turbo 템플릿과 같은 연결
    assert next(n for n in f.values() if n["class_type"] == "CLIPLoader")["inputs"]["type"] == "krea2"
    sampler = next(n for n in f.values() if n["class_type"] == "KSampler")["inputs"]
    assert sampler["steps"] == 8 and sampler["seed"] == 7 and sampler["cfg"] == 1.0
    latent = next(n for n in f.values() if n["class_type"] == "EmptyLatentImage")["inputs"]
    assert (latent["width"], latent["height"], latent["batch_size"]) == (1024, 768, 2)
    w = wan_workflow("a wave", 832, 480, frames=49, seed=3)
    assert {"UNETLoader", "CLIPLoader", "VAELoader", "Wan22ImageToVideoLatent", "CreateVideo", "SaveVideo"} <= {n["class_type"] for n in w.values()}
    assert next(n for n in w.values() if n["class_type"] == "Wan22ImageToVideoLatent")["inputs"]["length"] == 49
    for graph in (f, w):  # 모든 연결이 있는 노드를 가리킨다
        for node in graph.values():
            for value in node["inputs"].values():
                if isinstance(value, list):
                    assert value[0] in graph


def test_run_queues_polls_downloads_and_frees(tmp_path):
    http = FakeHTTP({"7": {"images": [{"filename": "rab_image_00001_.png", "subfolder": "", "type": "output"}]}})
    comfy = make(tmp_path, http)
    files = comfy.run(krea_workflow("x", 512, 512, seed=1, count=1), tmp_path / "job", check=lambda: None)
    assert [p.name for p in files] == ["rab_image_00001_.png"] and files[0].read_bytes() == b"IMAGEBYTES"
    paths = [c[1] for c in http.calls]
    assert paths[0] == "/system_stats" and "/prompt" in paths and paths[-1] == "/free"  # 다 쓰면 그래픽 메모리를 비운다


def test_cancel_interrupts_comfy(tmp_path):
    http = FakeHTTP({}, polls=99)
    comfy = make(tmp_path, http)

    class Stop(Exception):
        pass
    ticks = []

    def check():
        ticks.append(1)
        if len(ticks) > 2:
            raise Stop()
    with pytest.raises(Stop):
        comfy.run(krea_workflow("x", 512, 512, seed=1, count=1), tmp_path / "job", check=check)
    assert ("POST", "/interrupt", None) in http.calls and http.calls[-1][1] == "/free"


def test_missing_install_explains(tmp_path):
    comfy = make(tmp_path, FakeHTTP({}), installed=False)
    assert comfy.missing()
    with pytest.raises(OfficeError, match="install_gen"):
        comfy.run(krea_workflow("x", 512, 512, seed=1, count=1), tmp_path / "job", check=lambda: None)


def test_comfy_error_is_reported(tmp_path):
    class Broken(FakeHTTP):
        def __call__(self, method, path, body=None):
            if path.startswith("/history/"):
                return {"p1": {"outputs": {}, "status": {"status_str": "error", "messages": [["execution_error", {"exception_message": "CUDA out of memory"}]]}}}
            return super().__call__(method, path, body)
    comfy = make(tmp_path, Broken({}))
    with pytest.raises(OfficeError, match="out of memory"):
        comfy.run(krea_workflow("x", 512, 512, seed=1, count=1), tmp_path / "job", check=lambda: None)


def test_close_stops_the_comfy_we_started(tmp_path):
    class Proc:
        stopped = False

        def poll(self):
            return None

        def terminate(self):
            self.stopped = True

    class Down(FakeHTTP):
        started = False

        def __call__(self, method, path, body=None):
            if path == "/system_stats" and not self.started:
                raise OSError("connection refused")
            return super().__call__(method, path, body)
    http, proc = Down({"9": {"images": [{"filename": "a.png"}]}}), Proc()

    def start():
        http.started = True
        return proc
    comfy = make(tmp_path, http)
    comfy.start_server = start
    comfy.run(krea_workflow("x", 512, 512, seed=1, count=1), tmp_path / "job", check=lambda: None)
    comfy.close()
    assert proc.stopped  # 퇴근하면 우리가 켠 ComfyUI도 끈다


def test_rejected_prompt_explains_why(tmp_path, monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from office import media

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.dumps({"error": {"message": "Prompt outputs failed validation"},
                               "node_errors": {"1": {"errors": [{"details": "unet_name: 'krea2_turbo_fp8_scaled.safetensors' not in []"}]}}})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(media, "URL", f"http://127.0.0.1:{server.server_address[1]}")
    try:
        with pytest.raises(OfficeError, match="krea2_turbo_fp8_scaled"):
            media.http("POST", "/prompt", {"prompt": {}})
    finally:
        server.shutdown()
