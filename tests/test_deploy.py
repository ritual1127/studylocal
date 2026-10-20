import shutil, subprocess
import pytest
from office import OfficeError
from office.deploy import parse_deploy_url, deploy_site, publish_quiz
from office.quiz import save_quiz, validate_quiz
from test_quiz import RAW

ERR = ("🔍  Inspect: https://vercel.com/ritual/ritual-quiz/AbC [2s]\n"
       "✅  Production: https://ritual-quiz-k2j3h4-ritual.vercel.app [2s]\n"
       "🔗  Aliased: https://ritual-quiz.vercel.app [2s]\n")

def test_parse_prefers_short_alias():
    assert parse_deploy_url("https://ritual-quiz-k2j3h4-ritual.vercel.app\n", ERR) == "https://ritual-quiz.vercel.app"

def test_parse_without_urls():
    with pytest.raises(OfficeError):
        parse_deploy_url("", "Error: something")

def test_deploy_without_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(OfficeError, match="npm i -g vercel"):
        deploy_site(tmp_path)

def test_deploy_login_error(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: "vercel.cmd")
    fake = lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "Error: No existing credentials found. Please run `vercel login`")
    with pytest.raises(OfficeError, match="vercel login"):
        deploy_site(tmp_path, run=fake)

def test_deploy_success_runs_prod(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(shutil, "which", lambda name: "vercel.cmd")
    def fake(cmd, **kw):
        seen.update(cmd=cmd, cwd=kw["cwd"])
        return subprocess.CompletedProcess(cmd, 0, "https://ritual-quiz-k2j3h4-ritual.vercel.app\n", ERR)
    assert deploy_site(tmp_path, run=fake) == "https://ritual-quiz.vercel.app"
    assert seen["cmd"] == ["vercel.cmd", "deploy", "--prod", "--yes"] and seen["cwd"] == tmp_path

def test_publish_copies_quiz_and_lists_it(tmp_path):
    job = tmp_path / "jobs" / "j1"
    save_quiz(job, validate_quiz(RAW))
    site = tmp_path / "ritual-quiz"
    publish_quiz(job, "j1", site)
    assert (site / "q" / "j1" / "index.html").exists()
    index = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="q/j1/"' in index and "세포 퀴즈" in index
