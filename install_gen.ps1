# ritual's rab 이미지·동영상 생성 AI 설치: ComfyUI(포터블, RTX 50 지원) + Krea-2 Turbo(이미지) + Wan2.2 TI2V 5B(동영상)
# 다시 돌려도 된다: 다 받은 파일은 건너뛰고, 받다 만 파일은 이어 받는다. 약 37GB.
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:LOCALAPPDATA 'ritual-office\gen'
$portable = Join-Path $base 'ComfyUI_windows_portable'
$models = Join-Path $portable 'ComfyUI\models'
New-Item -ItemType Directory -Force $base | Out-Null

function Get-File($url, $dest, [long]$size) {
    if ((Test-Path $dest) -and ((Get-Item $dest).Length -eq $size)) { Write-Host "있음: $(Split-Path $dest -Leaf)"; return }
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    $part = "$dest.part"  # 다 받기 전엔 다른 이름: 앱이 받다 만 파일을 설치된 걸로 보지 않게
    if (Test-Path $dest) { Move-Item -Force $dest $part }
    Write-Host "받는 중: $(Split-Path $dest -Leaf) ($([math]::Round($size / 1GB, 1))GB)"
    & curl.exe -L --fail --retry 5 --retry-delay 5 -C - -o $part $url
    if ($LASTEXITCODE -or (Get-Item $part).Length -ne $size) { throw "못 받았어요: $url" }
    Move-Item -Force $part $dest
}

# 1) ComfyUI 포터블 (파이썬·PyTorch 포함)
if (-not (Test-Path (Join-Path $portable 'run_nvidia_gpu.bat'))) {
    $archive = Join-Path $base 'ComfyUI_windows_portable_nvidia.7z'
    Get-File 'https://github.com/Comfy-Org/ComfyUI/releases/download/v0.42.1/ComfyUI_windows_portable_nvidia.7z' $archive 2018444114
    Write-Host '압축 푸는 중...'
    & "$env:WINDIR\System32\tar.exe" -xf $archive -C $base
    if ($LASTEXITCODE) { throw 'ComfyUI 압축을 못 풀었어요.' }
    Remove-Item $archive
}

# 2) 모델 (Comfy-Org가 ComfyUI용으로 묶은 공식 배포본)
$hf = 'https://huggingface.co/Comfy-Org'
Get-File "$hf/Krea-2/resolve/main/diffusion_models/krea2_turbo_fp8_scaled.safetensors" (Join-Path $models 'diffusion_models\krea2_turbo_fp8_scaled.safetensors') 13141730784
Get-File "$hf/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors" (Join-Path $models 'text_encoders\qwen3vl_4b_fp8_scaled.safetensors') 5242467968
Get-File "$hf/Krea-2/resolve/main/vae/qwen_image_vae.safetensors" (Join-Path $models 'vae\qwen_image_vae.safetensors') 253806246
Get-File "$hf/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors" (Join-Path $models 'diffusion_models\wan2.2_ti2v_5B_fp16.safetensors') 9999658848
Get-File "$hf/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors" (Join-Path $models 'vae\wan2.2_vae.safetensors') 1409400960
Get-File "$hf/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" (Join-Path $models 'text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors') 6735906897
Write-Host "설치 완료: $portable"
