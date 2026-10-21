import datetime
import json
import queue
import secrets
import shutil
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

from office import Material, OfficeError
from office.analyst import make_analysis_page
from office.cards import make_cards_page
from office.coach import make_study_plan
from office.config import OUTPUT
from office.deploy import deploy_site, publish_quiz
from office.literature import fetch_literature
from office.llm import clip
from office.mindmap import make_mindmap_page
from office.note import make_pdf
from office.notify import Notifier
from office.plan import NEEDS_MATERIAL, OUTPUTS, route as plan_route
from office.planner import Planner
from office.quiz import make_quiz_page
from office.research import research
from office.scan import scan
from office.secretary import parse_schedule
from office.translator import make_translation_page
from office.tutor import answer_question

ROLES = {"manager": "실장", "secretary": "비서", "deployer": "배포담당",
         "scanner": "스캐너", "librarian": "사서", "researcher": "조사원", "analyst": "분석가",
         "designer": "디자이너", "examiner": "출제위원", "cards": "암기담당", "mapper": "정리왕",
         "tutor": "선생님", "translator": "번역가", "coach": "코치"}
# 결과 단계 → (직원, 시작 말, 끝 말, 결과 이름)
OUTPUT_STAFF = {"analysis": ("analyst", "자료 분석할게", "분석 보고서 다 썼어!", "analysis"),
                "pdf": ("designer", "노트 꾸밀게", "PDF 다 꾸몄어!", "pdf"),
                "quiz": ("examiner", "문제 {question_count}개 낼게", "문제 다 냈어!", "quiz"),
                "cards": ("cards", "암기카드 {card_count}장 만들게", "암기카드 다 만들었어!", "cards"),
                "mindmap": ("mapper", "마인드맵 그릴게", "마인드맵 다 그렸어!", "mindmap"),
                "translate": ("translator", "번역할게", "번역 끝!", "translation"),
                "answer": ("tutor", "질문 읽어볼게", "답 적어놨어!", "answer")}
STEP_ROLE = {"scan": "scanner", "literature": "librarian", "research": "researcher", "schedule": "secretary",
             "plan": "coach", "focus": "coach", **{step: info[0] for step, info in OUTPUT_STAFF.items()}}
AUTO_DEFAULT = {"analysis": False, "pdf": False, "quiz": False, "cards": False, "mindmap": False,
                "translate": False, "answer": True}  # 답변만 실장이 바로 승인, 나머지는 대표 결재
MAX_JOBS = 20
MAX_ANSWER = 6000
CRASH_MSG = "예상 못 한 오류가 났어. 로그: %LOCALAPPDATA%\\ritual-office\\office.log"
NO_MATERIAL = "이전 자료를 못 찾았어. 프린트를 올리거나 작품·주제 이름을 알려줘."
PENDING = ("review", "revising")


def _now() -> str:
    return f"{datetime.datetime.now():%Y-%m-%d %H:%M}"


@dataclass
class Job:
    id: str
    text: str
    files: list[str]
    status: str = "queued"  # queued | running | review(결재 대기) | revising(수정 중) | done | error | needs_input
    title: str = ""
    reply: str = ""
    error: str | None = None
    log: list[str] = field(default_factory=list)
    results: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created: str = ""
    ref: str = ""                                       # 고른 이전 작업 (그 자료로 더 하기)
    steps: list[str] = field(default_factory=list)      # 실장이 고른 단계 (반려되면 결과 단계를 다시 한다)
    options: dict = field(default_factory=dict)
    answer: str = ""
    approvals: list[dict] = field(default_factory=list)  # 결재 기록: action(approve|reject|auto), by, time, comment
    revision: int = 0
    finished: str = ""
    seconds: int = 0                                    # 마지막으로 일한 시간
    names: list[str] = field(default_factory=list)      # 올린 파일의 원래 이름 (보여주기만, 경로엔 안 씀)

    @property
    def outputs(self) -> list[str]:
        return [s for s in self.steps if s in OUTPUTS]


def merge(materials: list[Material], title: str) -> Material:
    return Material(title=next((m.title for m in materials if m.title), "") or title or "공부 자료",
                    markdown="\n\n---\n\n".join(m.markdown for m in materials),
                    sources=[s for m in materials for s in m.sources],
                    original=next((m.original for m in materials if m.original), None),
                    warnings=[w for m in materials for w in m.warnings])


class Office:
    def __init__(self, root: Path = OUTPUT, *, route=plan_route, steps: dict | None = None, deploy=deploy_site,
                 planner: Planner | None = None, notifier: Notifier | None = None):
        self.root = Path(root)
        self.jobs_dir = self.root / "jobs"
        self.site_dir = self.root / "ritual-quiz"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.route, self.deploy = route, deploy
        self.steps = steps or {"scan": scan, "literature": fetch_literature, "research": research,
                               "analysis": make_analysis_page, "pdf": make_pdf, "quiz": make_quiz_page,
                               "cards": make_cards_page, "mindmap": make_mindmap_page,
                               "translate": make_translation_page, "answer": answer_question,
                               "schedule": parse_schedule, "plan": make_study_plan}
        self.planner = planner or Planner(self.root / "planner.json")
        self.notifier = notifier or Notifier(self.root / "settings.json")
        self.jobs: dict[str, Job] = {}
        self.staff = {role: {"name": name, "state": "idle", "say": ""} for role, name in ROLES.items()}
        self.active = "manager"  # 지금 일하는 직원 (에러가 나면 이 직원 책상에 빨간불)
        self.queue: queue.Queue = queue.Queue()
        self.lock = threading.Lock()  # ponytail: 전역 잠금 하나, 작업이 하나씩만 돌아서 충분
        self.auto_path = self.root / "auto_approve.json"
        try:
            saved = json.loads(self.auto_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        saved = saved if isinstance(saved, dict) else {}
        self.auto = {k: saved[k] if isinstance(saved.get(k), bool) else v for k, v in AUTO_DEFAULT.items()}

    # ---- 접수 ----
    def new_job_dir(self) -> tuple[str, Path]:
        job_id = f"{datetime.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        (self.jobs_dir / job_id / "inputs").mkdir(parents=True)
        return job_id, self.jobs_dir / job_id

    def submit(self, job_id: str, text: str, files: list[Path], ref: str = "", names: list[str] | None = None) -> None:
        job = Job(id=job_id, text=text, files=[str(f) for f in files], ref=ref, created=_now(),
                  names=list(names or [Path(f).name for f in files]))
        with self.lock:
            self.jobs[job_id] = job
        self.queue.put(("job", job_id))

    def submit_deploy(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise OfficeError("그런 작업이 없어.")
            if "quiz" not in job.results:
                raise OfficeError("배포할 문제 웹이 없어.")
            if job.status != "done":
                raise OfficeError("대표 승인이 끝난 작업만 배포할 수 있어.")
        self.queue.put(("deploy", job_id))

    def _get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise OfficeError("그런 작업이 없어.")
        return job

    def retry(self, job_id: str) -> None:
        with self.lock:
            job = self._get(job_id)
            if job.status != "error":
                raise OfficeError("에러 난 작업만 다시 할 수 있어.")
            job.status, job.error, job.reply, job.answer = "queued", None, "", ""
            job.log, job.results, job.warnings, job.steps, job.options = [], {}, [], [], {}
        self.queue.put(("job", job_id))

    def delete(self, job_id: str) -> None:
        with self.lock:
            job = self._get(job_id)
            if job.status in ("queued", "running", "revising"):
                raise OfficeError("일하는 중인 작업은 못 지워. 끝나고 지워줘.")
            del self.jobs[job_id]
        shutil.rmtree(self.jobs_dir / job_id, ignore_errors=True)

    # ---- 대표 결재 ----
    def _waiting(self, job_id: str) -> Job:
        job = self._get(job_id)
        if job.status != "review":
            raise OfficeError("결재 대기 중인 작업이 아니야.")
        return job

    def approve(self, job_id: str, comment: str = "") -> None:
        with self.lock:
            job = self._waiting(job_id)
            job.status, job.error, job.finished = "done", None, _now()
            job.approvals.append({"action": "approve", "by": "대표", "time": _now(), "comment": str(comment).strip()[:500]})
        self._save(job)

    def reject(self, job_id: str, comment: str) -> None:
        comment = str(comment or "").strip()[:500]
        if not comment:
            raise OfficeError("뭘 고칠지 적어줘.")
        with self.lock:
            job = self._waiting(job_id)
            job.status, job.error = "revising", None
            job.revision += 1
            job.approvals.append({"action": "reject", "by": "대표", "time": _now(), "comment": comment})
        self._save(job)
        self.queue.put(("revise", job_id))

    def set_auto(self, changes: dict) -> dict:
        with self.lock:
            new = dict(self.auto)
            for key, value in changes.items():
                if key not in new:
                    raise OfficeError("그런 결과물 종류는 없어.")
                if not isinstance(value, bool):
                    raise OfficeError("켜기/끄기 값이 이상해.")
                new[key] = value
            tmp = self.auto_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(new, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.auto_path)
            self.auto = new
            return dict(new)

    # ---- 일꾼 ----
    def run_next(self, block: bool = False) -> bool:
        try:
            kind, job_id = self.queue.get(block=block)
        except queue.Empty:
            return False
        job = self.jobs.get(job_id)
        if job is not None:  # 그사이 지운 작업은 건너뛴다
            {"deploy": self._run_deploy, "revise": self._run_revise}.get(kind, self._run_job)(job)
        return True

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="office-worker").start()

    def _loop(self) -> None:
        while True:
            self.run_next(block=True)

    # ---- 상태 ----
    def snapshot(self) -> dict:
        with self.lock:
            jobs = list(self.jobs.values())[::-1]
            shown = jobs[:MAX_JOBS] + [j for j in jobs[MAX_JOBS:] if j.status in PENDING]
            out = []
            for job in shown:
                data = asdict(job)
                data["files"] = [Path(f).name for f in job.files]
                out.append(data)
            return {"staff": {role: dict(s) for role, s in self.staff.items()}, "jobs": out, "auto": dict(self.auto)}

    def load_history(self) -> None:
        paths = sorted(self.jobs_dir.glob("*/job.json"))
        for i, path in enumerate(paths):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = Job(**{k: data[k] for k in Job.__dataclass_fields__ if k in data})
            except (OSError, ValueError, TypeError, KeyError):
                continue
            if job.id != path.parent.name or (i < len(paths) - MAX_JOBS and job.status not in PENDING):
                continue  # 오래된 작업은 결재 대기만 불러온다
            if job.status in ("queued", "running"):
                job.status, job.error = "error", "프로그램이 꺼져서 중단됐어."
            elif job.status == "revising":
                job.status, job.error = "review", "프로그램이 꺼져서 수정이 중단됐어. 다시 반려하면 다시 고쳐."
            with self.lock:
                self.jobs.setdefault(job.id, job)

    def stats(self) -> dict:
        """대표실 회사 현황: 지난 기록 전부 + 지금 메모리에 있는 최신 상태."""
        jobs = {}
        for path in self.jobs_dir.glob("*/job.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                jobs[data["id"]] = data
            except (OSError, ValueError, KeyError, TypeError):
                continue
        with self.lock:
            jobs.update({job.id: asdict(job) for job in self.jobs.values()})
        today = datetime.date.today().isoformat()
        actions = [a.get("action") for j in jobs.values() for a in j.get("approvals") or []]
        decided = actions.count("approve") + actions.count("reject")
        staff = dict.fromkeys(ROLES, 0)
        for j in jobs.values():
            if j.get("status") == "queued":
                continue
            staff["manager"] += 1
            if j.get("status") in ("done", *PENDING):
                for role in {STEP_ROLE[s] for s in j.get("steps") or [] if s in STEP_ROLE}:
                    staff[role] += 1
            if (j.get("results") or {}).get("deploy_url"):
                staff["deployer"] += 1
        week = self.planner.view()["stats"]["week"]
        return {"total": len(jobs), "pending": sum(j.get("status") in PENDING for j in jobs.values()),
                "today_done": sum(j.get("status") == "done" and (j.get("finished") or "")[:10] == today
                                  for j in jobs.values()),
                "approval_rate": round(100 * actions.count("approve") / decided) if decided else None,
                "auto_approved": actions.count("auto"), "rejected": actions.count("reject"),
                "staff": staff, "study_week": sum(d["minutes"] for d in week)}

    def material_of(self, job_id: str) -> Material | None:
        if job_id not in self.jobs:  # 경로는 아는 작업 번호로만 만든다
            return None
        folder = self.jobs_dir / job_id
        try:
            data = json.loads((folder / "material.json").read_text(encoding="utf-8"))
            return Material(**{k: data[k] for k in Material.__dataclass_fields__ if k in data})
        except (OSError, ValueError, TypeError):
            pass
        try:
            text = (folder / "source.txt").read_text(encoding="utf-8")  # 1단계 작업은 글자만 남아 있다
        except OSError:
            return None
        return Material(title=self.jobs[job_id].title, markdown=text) if text.strip() else None

    def _last_material(self, current: str) -> Material | None:
        with self.lock:
            ids = list(self.jobs)[::-1]
        return next((m for job_id in ids if job_id != current and (m := self.material_of(job_id))), None)

    def _set(self, job: Job, role: str, state: str, say: str = "") -> None:
        with self.lock:
            self.staff[role] = {"name": ROLES[role], "state": state, "say": say}
            if state == "working":
                self.active = role
            if say:
                job.log.append(f"[{ROLES[role]}] {say}")

    def _update(self, job: Job, **fields) -> None:
        with self.lock:
            results = fields.pop("results", None)
            for key, value in fields.items():
                setattr(job, key, value)
            if results:
                job.results.update(results)

    def _begin(self, job: Job, status: str) -> float:
        with self.lock:
            job.status = status
            self.active = "manager"
            for r in self.staff:
                self.staff[r] = {"name": ROLES[r], "state": "idle", "say": ""}
        return time.monotonic()

    def _sayer(self, job: Job, role: str):
        return lambda msg: self._set(job, role, "working", msg)

    def _url(self, path: Path) -> str:
        return "/files/" + Path(path).relative_to(self.root).as_posix()

    def _save(self, job: Job) -> None:
        with self.lock:
            data = json.dumps(asdict(job), ensure_ascii=False, indent=1)
        (self.jobs_dir / job.id / "job.json").write_text(data, encoding="utf-8")

    def _notify(self, job: Job) -> None:
        title = job.title or job.text[:30] or "첨부 파일 작업"
        if job.status == "review":
            message = (f"수정 실패: {title}", job.error) if job.error else (f"결재 요청: {title}", "대표실에서 승인하거나 반려해줘")
        elif not self.notifier.settings.get("job_done"):
            return
        elif job.status == "done" and job.outputs:
            message = (f"작업 완료: {title}", job.reply or "결과 보관함 확인해")
        elif job.status == "error":
            message = (f"작업 실패: {title}", job.error or "")
        else:
            return
        try:
            self.notifier.send(*message)
        except Exception:  # 알림이 안 가도 작업은 끝난 것
            traceback.print_exc()

    def _fail(self, job: Job, exc: Exception, status: str) -> None:
        if isinstance(exc, OfficeError):
            self._update(job, status=status, error=str(exc))
            self._set(job, self.active, "error", str(exc))
        else:
            traceback.print_exc()
            self._update(job, status=status, error=CRASH_MSG)
            self._set(job, self.active, "error", "예상 못 한 오류가 났어")

    # ---- 일 처리 ----
    def _run_job(self, job: Job) -> None:
        job_dir = self.jobs_dir / job.id
        started = self._begin(job, "running")
        try:
            self._set(job, "manager", "working", "명령 읽는 중")
            plan = self.route(job.text, bool(job.files), has_ref=bool(job.ref))
            if plan.error:
                self._ask(job, plan.error)
                return
            self._update(job, reply=plan.reply, title=plan.title, steps=list(plan.steps),
                         options={"question_count": plan.question_count, "card_count": plan.card_count,
                                  "question": plan.question, "target_lang": plan.target_lang})
            self._set(job, "manager", "working" if plan.steps else "done", plan.reply)
            if not plan.steps:
                self._settle(job)
                return

            materials = []
            if job.ref or plan.use_last:
                previous = self.material_of(job.ref) if job.ref else self._last_material(job.id)
                if previous:
                    materials.append(previous)
                    self._set(job, "manager", "working", f"'{previous.title}' 자료 다시 꺼냈어")
            if "scan" in plan.steps:
                self._set(job, "scanner", "working", "파일 읽을게")
                m = self.steps["scan"]([Path(f) for f in job.files], say=self._sayer(job, "scanner"))
                materials.append(m)
                self._set(job, "scanner", "done", f"다 읽었어 ({len(m.markdown):,}자)")
            if "literature" in plan.steps:
                self._set(job, "librarian", "working", f"'{plan.work_query}' 찾아볼게")
                m = self.steps["literature"](plan.work_query, say=self._sayer(job, "librarian"))
                materials.append(m)
                self._set(job, "librarian", "done", f"'{m.title}' 가져왔어")
            if "research" in plan.steps:
                self._set(job, "researcher", "working", f"'{plan.topic}' 조사할게")
                m = self.steps["research"](plan.topic, say=self._sayer(job, "researcher"))
                materials.append(m)
                self._set(job, "researcher", "done", f"'{m.title}' 조사 끝")
            if not materials and any(s in NEEDS_MATERIAL for s in plan.steps):
                self._ask(job, NO_MATERIAL)
                return
            material = merge(materials, plan.title) if materials else None
            if material:
                (job_dir / "source.txt").write_text(material.markdown, encoding="utf-8")
                (job_dir / "material.json").write_text(json.dumps(asdict(material), ensure_ascii=False), encoding="utf-8")
                self._update(job, title=material.title, warnings=list(material.warnings),
                             results={"text": self._url(job_dir / "source.txt")})

            today = self.planner.now().date()
            if "schedule" in plan.steps:
                self._set(job, "secretary", "working", "일정 정리할게")
                text = job.text + (f"\n\n[첨부 자료]\n{clip(material.markdown, 3000)}" if material else "")
                out = self.steps["schedule"](text, today)
                for event in out["events"]:
                    self.planner.add_event(**event)
                for todo in out["todos"]:
                    self.planner.add_todo(**todo)
                self._set(job, "secretary", "done",
                          out["reply"] or f"일정 {len(out['events'])}개, 할 일 {len(out['todos'])}개 넣었어")
            if "plan" in plan.steps:
                self._set(job, "coach", "working", "공부 계획 짜볼게")
                exams = [e for e in self.planner.view()["events"] if e["kind"] == "시험" and e["date"] >= today.isoformat()]
                out = self.steps["plan"](job.text, today, exams, material)
                for todo in out["todos"]:
                    self.planner.add_todo(todo["text"], date=todo["date"])
                self._set(job, "coach", "done", f"할 일 {len(out['todos'])}개로 계획 짰어! {out['reply']}".strip())
            if "focus" in plan.steps:
                running = self.planner.start_focus(plan.focus_minutes, task=plan.title)
                self._set(job, "coach", "done", f"{running['minutes']}분 공부모드 시작! 끝나면 알려줄게")

            self._make_outputs(job, material)
            self._settle(job)
        except Exception as e:
            self._fail(job, e, "error")
        finally:
            self._update(job, seconds=round(time.monotonic() - started))
            self._save(job)
            self._notify(job)

    def _ask(self, job: Job, message: str) -> None:
        self._update(job, status="needs_input", reply=message)
        self._set(job, "manager", "done", message)

    def _make_outputs(self, job: Job, material: Material | None, feedback: str = "") -> None:
        job_dir, o = self.jobs_dir / job.id, job.options
        for step in job.outputs:
            role, start, end, key = OUTPUT_STAFF[step]
            self._set(job, role, "working", start.format(**o))
            kw = {"say": self._sayer(job, role), "feedback": feedback}
            if step in ("analysis", "pdf", "mindmap"):
                path = self.steps[step](material, job_dir, **kw)
            elif step == "quiz":
                path = self.steps[step](material, o["question_count"], job_dir, **kw)
            elif step == "cards":
                path = self.steps[step](material, o["card_count"], job_dir, **kw)
            elif step == "translate":
                path = self.steps[step](material, o["target_lang"], job_dir, **kw)
            else:
                path = self.steps[step](o["question"] or job.text, material, job_dir, **kw)
            results = {key: self._url(path)}
            if step == "cards" and (path.parent / "cards.csv").exists():
                results["csv"] = self._url(path.parent / "cards.csv")
            self._update(job, results=results)
            if step == "answer":
                self._update(job, answer=path.read_text(encoding="utf-8")[:MAX_ANSWER])
            self._set(job, role, "done", end)

    def _settle(self, job: Job) -> None:
        """결과물이 있으면 결재 대기 (자동 승인 규칙이면 바로 완료), 없으면 완료."""
        if job.outputs and not all(self.auto.get(s) for s in job.outputs):
            self._update(job, status="review")
            self._set(job, "manager", "done", "대표님께 결재 올렸어!")
            return
        with self.lock:
            if job.outputs:
                job.approvals.append({"action": "auto", "by": "실장", "time": _now(), "comment": "자동 승인 규칙"})
            job.status, job.finished = "done", _now()
        if job.steps:
            self._set(job, "manager", "done", "다 됐어! 결과 보관함 확인해" if job.outputs else "다 됐어!")

    def _run_revise(self, job: Job) -> None:
        feedback = job.approvals[-1]["comment"]
        started = self._begin(job, "revising")
        try:
            self._set(job, "manager", "working", f"대표님 수정 요청: {feedback}")
            self._make_outputs(job, self.material_of(job.id), feedback)
            self._update(job, status="review")
            self._set(job, "manager", "done", f"{job.revision}번째 수정 끝! 다시 결재 올렸어")
        except Exception as e:
            self._fail(job, e, "review")  # 고치다 실패해도 이전 결과물로 결재는 할 수 있다
        finally:
            self._update(job, seconds=round(time.monotonic() - started))
            self._save(job)
            self._notify(job)

    def _run_deploy(self, job: Job) -> None:
        try:
            self._set(job, "deployer", "working", "배포 준비 중")
            publish_quiz(self.jobs_dir / job.id, job.id, self.site_dir)
            self._set(job, "deployer", "working", "Vercel에 올리는 중")
            base = self.deploy(self.site_dir)
            with self.lock:
                job.results["deploy_url"] = f"{base}/q/{job.id}/"
                job.results.pop("deploy_error", None)
            self._set(job, "deployer", "done", "배포 완료!")
        except OfficeError as e:
            self._update(job, results={"deploy_error": str(e)})
            self._set(job, "deployer", "error", str(e))
        except Exception:
            traceback.print_exc()
            self._update(job, results={"deploy_error": CRASH_MSG})
            self._set(job, "deployer", "error", "예상 못 한 오류가 났어")
        finally:
            self._save(job)
