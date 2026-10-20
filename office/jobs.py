import datetime
import json
import queue
import secrets
import threading
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

from office import Material, OfficeError
from office.config import OUTPUT
from office.deploy import deploy_site, publish_quiz
from office.literature import fetch_literature
from office.note import make_pdf
from office.plan import route as plan_route
from office.quiz import make_quiz_page
from office.scan import scan

ROLES = {"manager": "실장", "scanner": "스캐너", "librarian": "사서",
         "designer": "디자이너", "examiner": "출제위원", "deployer": "배포담당"}
MAX_JOBS = 20
CRASH_MSG = "예상 못 한 오류가 났어. 로그: %LOCALAPPDATA%\\ritual-office\\office.log"


@dataclass
class Job:
    id: str
    text: str
    files: list[str]
    status: str = "queued"  # queued | running | done | error | needs_input
    title: str = ""
    reply: str = ""
    error: str | None = None
    log: list[str] = field(default_factory=list)
    results: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created: str = ""


def merge(materials: list[Material], title: str) -> Material:
    return Material(title=title or materials[0].title,
                    markdown="\n\n---\n\n".join(m.markdown for m in materials),
                    sources=[s for m in materials for s in m.sources],
                    original=next((m.original for m in materials if m.original), None),
                    warnings=[w for m in materials for w in m.warnings])


class Office:
    def __init__(self, root: Path = OUTPUT, *, route=plan_route, steps: dict | None = None, deploy=deploy_site):
        self.root = Path(root)
        self.jobs_dir = self.root / "jobs"
        self.site_dir = self.root / "ritual-quiz"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.route, self.deploy = route, deploy
        self.steps = steps or {"scan": scan, "literature": fetch_literature, "pdf": make_pdf, "quiz": make_quiz_page}
        self.jobs: dict[str, Job] = {}
        self.staff = {role: {"name": name, "state": "idle", "say": ""} for role, name in ROLES.items()}
        self.queue: queue.Queue = queue.Queue()
        self.lock = threading.Lock()  # ponytail: 전역 잠금 하나, 작업이 하나씩만 돌아서 충분

    # ---- 접수 ----
    def new_job_dir(self) -> tuple[str, Path]:
        job_id = f"{datetime.datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        (self.jobs_dir / job_id / "inputs").mkdir(parents=True)
        return job_id, self.jobs_dir / job_id

    def submit(self, job_id: str, text: str, files: list[Path]) -> None:
        job = Job(id=job_id, text=text, files=[str(f) for f in files],
                  created=f"{datetime.datetime.now():%Y-%m-%d %H:%M}")
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
        self.queue.put(("deploy", job_id))

    # ---- 일꾼 ----
    def run_next(self, block: bool = False) -> bool:
        try:
            kind, job_id = self.queue.get(block=block)
        except queue.Empty:
            return False
        (self._run_deploy if kind == "deploy" else self._run_job)(self.jobs[job_id])
        return True

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="office-worker").start()

    def _loop(self) -> None:
        while True:
            self.run_next(block=True)

    # ---- 상태 ----
    def snapshot(self) -> dict:
        with self.lock:
            jobs = list(self.jobs.values())[::-1][:MAX_JOBS]
            out = []
            for job in jobs:
                data = asdict(job)
                data["files"] = [Path(f).name for f in job.files]
                out.append(data)
            return {"staff": {role: dict(s) for role, s in self.staff.items()}, "jobs": out}

    def load_history(self) -> None:
        for path in sorted(self.jobs_dir.glob("*/job.json"))[-MAX_JOBS:]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = Job(**{k: data[k] for k in Job.__dataclass_fields__ if k in data})
            except (OSError, ValueError, TypeError, KeyError):
                continue
            if job.status in ("queued", "running"):
                job.status, job.error = "error", "프로그램이 꺼져서 중단됐어."
            with self.lock:
                self.jobs.setdefault(job.id, job)

    def _set(self, job: Job, role: str, state: str, say: str = "") -> None:
        with self.lock:
            self.staff[role] = {"name": ROLES[role], "state": state, "say": say}
            if say:
                job.log.append(f"[{ROLES[role]}] {say}")

    def _update(self, job: Job, **fields) -> None:
        with self.lock:
            results = fields.pop("results", None)
            for key, value in fields.items():
                setattr(job, key, value)
            if results:
                job.results.update(results)

    def _sayer(self, job: Job, role: str):
        return lambda msg: self._set(job, role, "working", msg)

    def _url(self, path: Path) -> str:
        return "/files/" + Path(path).relative_to(self.root).as_posix()

    def _save(self, job: Job) -> None:
        with self.lock:
            data = json.dumps(asdict(job), ensure_ascii=False, indent=1)
        (self.jobs_dir / job.id / "job.json").write_text(data, encoding="utf-8")

    # ---- 일 처리 ----
    def _run_job(self, job: Job) -> None:
        job_dir = self.jobs_dir / job.id
        role = "manager"
        try:
            with self.lock:
                job.status = "running"
                for r in self.staff:
                    self.staff[r] = {"name": ROLES[r], "state": "idle", "say": ""}
            self._set(job, "manager", "working", "명령 읽는 중")
            plan = self.route(job.text, bool(job.files))
            if plan.error:
                self._update(job, status="needs_input", reply=plan.error)
                self._set(job, "manager", "done", plan.error)
                return
            self._update(job, reply=plan.reply)
            self._set(job, "manager", "working" if plan.steps else "done", plan.reply)
            if not plan.steps:
                self._update(job, status="done")
                return

            materials = []
            if "scan" in plan.steps:
                role = "scanner"
                self._set(job, role, "working", "프린트 읽을게")
                m = self.steps["scan"]([Path(f) for f in job.files], say=self._sayer(job, role))
                materials.append(m)
                self._set(job, role, "done", f"다 읽었어 ({len(m.markdown):,}자)")
            if "literature" in plan.steps:
                role = "librarian"
                self._set(job, role, "working", f"'{plan.work_query}' 찾아볼게")
                m = self.steps["literature"](plan.work_query, say=self._sayer(job, role))
                materials.append(m)
                self._set(job, role, "done", f"'{m.title}' 가져왔어")
            material = merge(materials, plan.title)
            (job_dir / "source.txt").write_text(material.markdown, encoding="utf-8")
            self._update(job, title=material.title, warnings=list(material.warnings),
                         results={"text": self._url(job_dir / "source.txt")})

            if "pdf" in plan.steps:
                role = "designer"
                self._set(job, role, "working", "노트 꾸밀게")
                path = self.steps["pdf"](material, job_dir, say=self._sayer(job, role))
                self._update(job, results={"pdf": self._url(path)})
                self._set(job, role, "done", "PDF 다 꾸몄어!")
            if "quiz" in plan.steps:
                role = "examiner"
                self._set(job, role, "working", f"문제 {plan.question_count}개 낼게")
                path = self.steps["quiz"](material, plan.question_count, job_dir, say=self._sayer(job, role))
                self._update(job, results={"quiz": self._url(path)})
                self._set(job, role, "done", "문제 다 냈어!")
            self._update(job, status="done")
            self._set(job, "manager", "done", "다 됐어! 결과 보관함 확인해")
        except OfficeError as e:
            self._update(job, status="error", error=str(e))
            self._set(job, role, "error", str(e))
        except Exception:
            traceback.print_exc()
            self._update(job, status="error", error=CRASH_MSG)
            self._set(job, role, "error", "예상 못 한 오류가 났어")
        finally:
            self._save(job)

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
