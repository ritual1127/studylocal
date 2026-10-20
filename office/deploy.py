import html
import json
import re
import shutil
import subprocess
from pathlib import Path

from office import OfficeError, fill
from office.config import GALMURI_CSS

URL = re.compile(r"https://[a-z0-9.-]+\.vercel\.app")


def write_site_index(site_dir: Path) -> None:
    items = []
    for quiz_json in sorted((site_dir / "q").glob("*/quiz.json"), reverse=True):  # slug = 시간순 id
        slug = quiz_json.parent.name
        title = json.loads(quiz_json.read_text(encoding="utf-8")).get("title") or "문제"
        items.append(f'<li><a href="q/{html.escape(slug)}/"><span>{html.escape(title)}</span>'
                     f'<small>{html.escape(slug[:8])}</small></a></li>')
    (site_dir / "index.html").write_text(
        fill("site_index.html", galmuri_css=GALMURI_CSS, list="".join(items) or "<li class=\"empty\">아직 문제가 없어</li>"),
        encoding="utf-8")


def publish_quiz(job_dir: Path, slug: str, site_dir: Path) -> None:
    shutil.copytree(job_dir / "quiz", site_dir / "q" / slug, dirs_exist_ok=True)
    write_site_index(site_dir)


def parse_deploy_url(stdout: str, stderr: str) -> str:
    urls = URL.findall(stdout + "\n" + stderr)
    if not urls:
        raise OfficeError("배포 주소를 못 찾았어.")
    return min(urls, key=len)  # 가장 짧은 주소 = 프로젝트 기본 주소 (배포별 주소는 로그인 벽)


def deploy_site(site_dir: Path, run=subprocess.run) -> str:
    vercel = shutil.which("vercel")
    if not vercel:
        raise OfficeError("Vercel CLI가 없어. 터미널에서 npm i -g vercel 하고 vercel login 해줘.")
    result = run([vercel, "deploy", "--prod", "--yes"], cwd=site_dir, capture_output=True, text=True,
                 encoding="utf-8", errors="replace", timeout=300)
    if result.returncode != 0:
        err = result.stderr or ""
        if "login" in err.lower() or "credentials" in err.lower():
            raise OfficeError("Vercel 로그인이 필요해. 터미널에서 vercel login 해줘.")
        last = (err.strip().splitlines() or ["알 수 없는 오류"])[-1]
        raise OfficeError(f"배포 실패: {last}")
    return parse_deploy_url(result.stdout or "", result.stderr or "")
