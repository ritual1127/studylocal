# ritual의 공부 사무실 설치: 프로그램 확인 → 모델 → 파이썬 환경·아이콘 → vercel → 바탕화면 바로가기
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\ritual-office\venv"

foreach ($tool in 'uv', 'ollama', 'npm') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "${tool}이(가) 없어. 먼저 설치해줘." }
}

if (-not (ollama list | Select-String -SimpleMatch 'qwen3.5')) {
    ollama pull qwen3.5
    if ($LASTEXITCODE) { throw 'qwen3.5 모델을 못 받았어.' }
}

Push-Location $root
try {
    uv sync
    if ($LASTEXITCODE) { throw 'uv sync가 실패했어.' }
    uv run python -m office.assets
    if ($LASTEXITCODE) { throw '로고·아이콘을 못 만들었어.' }
} finally {
    Pop-Location
}

if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
    npm i -g vercel
    if ($LASTEXITCODE) { throw 'vercel 설치가 실패했어.' }
}

$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ritual의 공부 사무실.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$shortcut.TargetPath = "$env:UV_PROJECT_ENVIRONMENT\Scripts\pythonw.exe"
$shortcut.Arguments = "`"$root\launch.pyw`""
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$root\web\icon.ico"
$shortcut.Description = 'ritual의 공부 사무실'
$shortcut.Save()

Write-Host '설치 완료. 배포 기능을 쓰려면 터미널에서 vercel login 을 한 번 해줘.'
