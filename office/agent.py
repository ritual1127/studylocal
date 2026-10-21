"""ritual's rab: 대표가 시키는 일을 도구로 직접 하는 AI 비서 (자비스처럼).

모델이 도구를 골라 부르고, 결과를 보고 다음 도구를 고르는 루프(최대 8번). 직원 팀은 do_work 도구로 부린다.
지우기·옮기기·덮어쓰기·명령 실행 도구는 없다 (되돌리기 어려운 일은 대표가 직접).
"""
import datetime as dt
import json
import threading
import traceback
from pathlib import Path
from urllib.parse import urlsplit

from office import OfficeError, llm
from office.plan import OUTPUTS, STAFF_STEPS, normalize_plan

MAX_TURNS = 8
MAX_CALLS = 4  # 한 번에 부르는 도구 수
RESULT_CHARS = 3000
NAMES = {"manager": "rab", "secretary": "비서", "deployer": "배포담당", "scanner": "스캐너", "librarian": "사서",
         "researcher": "조사원", "analyst": "분석가", "designer": "디자이너", "examiner": "출제위원", "cards": "암기담당",
         "mapper": "정리왕", "tutor": "선생님", "translator": "번역가", "coach": "코치"}
# 열기로 실행되면 프로그램을 돌리는 것과 같은 파일들 (rab은 열지 않는다)
RUNNABLE = {".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".msi", ".msp",
            ".scr", ".pif", ".lnk", ".url", ".reg", ".hta", ".cpl", ".jar", ".py", ".pyw", ".sh", ".appref-ms"}
APPS = {"메모장": "notepad", "notepad": "notepad", "계산기": "calc", "calculator": "calc", "그림판": "mspaint",
        "탐색기": "explorer", "파일 탐색기": "explorer", "설정": "ms-settings:", "작업 관리자": "taskmgr"}

RAB_SYSTEM = """너는 ritual's rab, 대표(ritual)의 AI 비서다. 아이언맨의 자비스처럼 침착하고 정확하게, 시키는 일을 도구로 직접 실행한다.
- 말로만 대답하지 말고 도구로 실제로 한다. 메시지 보내기(notify), 나중에 알리기(remind), 일정(add_schedule), 할 일 체크, 공부모드,
  파일 찾기·가져오기·열기, 새 파일 쓰기, 결재·중단(job_action), 설정 바꾸기 모두 도구가 있다.
- "내 폰으로 ○○ 보내"처럼 보낼 말이 요청에 있으면 묻지 말고 바로 notify로 그 말을 보낸다.
- 파일은 find_files로 찾아 본 뒤 결과의 경로를 그대로 쓴다. 경로를 지어내지 않는다. 폴더 이름은 바탕화면·문서·다운로드처럼 써도 된다.
- 노트·문제·암기카드·마인드맵·분석·번역·질문 답변 같은 결과물은 do_work로 직원 팀에게 맡긴다 (첨부 파일·가져온 파일은 자동으로 쓴다).
- 오늘 일정·할 일·결재 현황을 물으면 status로 확인하고 사실만 말한다. 모르는 건 지어내지 않는다.
- 지우기·옮기기·이름 바꾸기·덮어쓰기·명령 실행은 rab이 할 수 없다. 그럴 땐 할 수 없다고 말하고 open_thing으로 그 폴더를 열어 준다.
- 일이 끝나면 대표님께 존댓말로 한두 문장 보고한다 ("대표님, …했습니다")."""


class Cancelled(Exception):
    """대표가 [중단]을 눌렀다."""


def resolve_time(now: dt.datetime, minutes: int = 0, time: str = "") -> dt.datetime:
    """'10분 뒤' 또는 'HH:MM'을 실제 시각으로. 지난 시각이면 저녁의 오전 시각은 오후로, 아니면 내일로."""
    if minutes:
        at = now + dt.timedelta(minutes=minutes)
        return at.replace(second=0, microsecond=0) + (dt.timedelta(minutes=1) if at.second or at.microsecond else dt.timedelta())
    if not time:
        raise ValueError("시각이 없다")
    hour, minute = map(int, time.split(":"))
    at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if at <= now:
        at = at + dt.timedelta(hours=12) if hour < 12 and at + dt.timedelta(hours=12) > now else at + dt.timedelta(days=1)
    return at


# ---- 도구 등록 ----
TOOLS = {}


def tool(_name: str, _label: str, _desc: str, _required: tuple = (), **props):
    """도구 등록. 밑줄 이름은 도구 인자(name 같은)와 안 겹치게."""
    def wrap(fn):
        TOOLS[_name] = {"name": _name, "label": _label, "run": fn, "spec": {"type": "function", "function": {
            "name": _name, "description": _desc,
            "parameters": {"type": "object", "properties": props, "required": list(_required)}}}}
        return fn
    return wrap


S = {"type": "string"}
I = {"type": "integer"}


def _s(args: dict, key: str, limit: int = 500) -> str:
    value = args.get(key)
    return " ".join(str(value).split())[:limit] if value not in (None, "") else ""


def _i(args: dict, key: str, default: int = 0) -> int:
    try:
        return int(args.get(key) or default)
    except (TypeError, ValueError):
        return default


@tool("find_files", "파일 찾기", "대표 PC의 허용 폴더(바탕화면·문서·다운로드·사진·OneDrive 등)에서 파일 이름으로 찾는다", ("query",),
      query={**S, "description": "파일 이름에 들어간 말"}, folder={**S, "description": "찾을 폴더 (예: 바탕화면, 다운로드), 없으면 전체"},
      kind={**S, "description": "pdf·한글·워드·엑셀·ppt·사진·문서 등"}, days={**I, "description": "최근 며칠 안에 바뀐 파일만"})
def find_files(office, job, args):
    found = office.files.find(_s(args, "query"), _s(args, "folder"), _s(args, "kind"), _i(args, "days"))
    return {"found": found} if found else {"found": [], "hint": "못 찾았어요. 다른 말이나 폴더로 다시 찾아 보세요."}


@tool("list_folder", "폴더 보기", "폴더 안의 하위 폴더와 파일 목록 (최근 바뀐 순)", ("folder",), folder=S)
def list_folder(office, job, args):
    return office.files.listing(_s(args, "folder"))


@tool("read_file", "파일 읽기", "문서·글자 파일 내용을 읽는다 (사진·스캔은 bring_file 뒤 do_work의 analysis로)", ("path",), path=S)
def read_file(office, job, args):
    path = office.files.existing(_s(args, "path"))
    return {"path": str(path), "text": office.files.read_text(path)}


@tool("bring_file", "가져오기", "파일을 이번 작업으로 가져온다 (보관함에서 열고 폰으로 받을 수 있고, 직원들이 읽을 수 있다)", ("path",), path=S)
def bring_file(office, job, args):
    office.files.need("write")
    src = office.files.existing(_s(args, "path"))
    if not src.is_file():
        raise OfficeError("폴더는 통째로 못 가져와요. 파일을 골라 주세요.")
    return office.bring(job, src)


@tool("open_thing", "열기", "대표 PC 화면에서 파일·폴더·웹 주소(https)·앱(메모장·계산기·그림판·탐색기·설정)을 연다", ("target",), target=S)
def open_thing(office, job, args):
    target = _s(args, "target")
    if urlsplit(target).scheme in ("http", "https"):
        office.opener(target)
        return {"opened": target}
    if target in APPS:
        office.opener(APPS[target])
        return {"opened": target}
    path = office.files.existing(target)
    if path.is_file() and path.suffix.lower() in RUNNABLE:
        raise OfficeError("프로그램·스크립트 파일은 rab이 열지 않아요. 대표님이 직접 열어 주세요.")
    office.opener(str(path))
    return {"opened": str(path)}


@tool("write_file", "새 파일", "새 글자 파일을 만든다 (기본 위치: 문서/ritual's rab, 있는 파일은 덮어쓰지 않고 새 이름)", ("name", "content"),
      name=S, content=S, folder={**S, "description": "만들 폴더 (없으면 기본 위치)"})
def write_file(office, job, args):
    content = str(args.get("content") or "")[:200_000]
    return {"saved": str(office.files.write(_s(args, "name", 120), content, _s(args, "folder")))}


@tool("copy_file", "복사", "파일·폴더를 다른 폴더로 복사한다 (원본은 그대로, 같은 이름이 있으면 새 이름)", ("path", "to_folder"),
      path=S, to_folder=S)
def copy_file(office, job, args):
    src = office.files.existing(_s(args, "path"))
    return {"copied": str(office.files.copy(src, office.files.resolve(_s(args, "to_folder"))))}


@tool("make_folder", "새 폴더", "허용 폴더 안에 새 폴더를 만든다", ("path",), path=S)
def make_folder(office, job, args):
    return {"made": str(office.files.make_folder(_s(args, "path")))}


@tool("do_work", "직원 팀", "직원 팀에게 결과물을 만들게 한다. 첨부·가져온 파일, topic(조사 주제), work(문학 작품), files(PC 파일 경로)로 자료를 만든다",
      ("outputs",), outputs={"type": "array", "items": {"type": "string", "enum": list(OUTPUTS)}},
      files={"type": "array", "items": S}, topic=S, work=S, question=S, count=I, target_lang=S,
      use_last={"type": "boolean", "description": "방금 작업의 자료를 쓴다"}, title=S)
def do_work(office, job, args):
    for path in [p for p in args.get("files") or [] if isinstance(p, str)][:10]:
        office.files.need("write")
        src = office.files.existing(path)
        if src.is_file() and src.name not in job.names:
            office.bring(job, src)
    outputs = [o for o in args.get("outputs") or [] if o in OUTPUTS]
    if job.assignee in STAFF_STEPS:  # 대표가 지정한 팀의 일만
        allowed = STAFF_STEPS[job.assignee]
        outputs = [o for o in outputs if o in allowed] or [o for o in allowed if o in OUTPUTS][:1]
    count = _i(args, "count")
    raw = {"steps": outputs, "topic": _s(args, "topic"), "work_query": _s(args, "work"), "question": _s(args, "question"),
           "question_count": count or 10, "card_count": count or 15, "target_lang": _s(args, "target_lang"),
           "use_last": args.get("use_last") is True, "title": _s(args, "title", 60)}
    plan = normalize_plan(raw, bool(job.files), bool(job.ref))
    if job.assignee in ("librarian", "researcher") and not outputs:  # 자료만 모으는 팀
        plan.steps = [s for s in plan.steps if s in ("literature", "research")] or plan.steps
    if plan.error:
        return {"error": plan.error}
    if not plan.steps:
        return {"error": "만들 결과물(outputs)을 골라 주세요."}
    office.run_plan(job, plan)
    status = "결재 대기" if job.outputs and not all(office.auto.get(s) for s in job.outputs) else "완료"
    return {"status": status, "title": job.title, "results": sorted(k for k in job.results if k != "text")}


@tool("notify", "알림", "대표에게 시스템 알림으로 메시지를 보낸다", ("message",),
      message=S, to={"type": "string", "enum": ["phone", "pc", "both"], "description": "phone=폰, pc=PC, both=둘 다"})
def notify(office, job, args):
    message = _s(args, "message", 300)
    if not message:
        raise OfficeError("보낼 말이 없어요.")
    to = args.get("to") if args.get("to") in ("phone", "pc") else None
    errors = office.notifier.send("rab", message, only=to)
    if errors:
        raise OfficeError(" / ".join(errors))
    return {"sent": {"phone": "폰", "pc": "PC"}.get(to, "PC·폰"), "message": message}


@tool("remind", "나중에 알림", "몇 분 뒤나 정한 시각에 알림을 보낸다 (할 일로 등록됨)", ("message",),
      message=S, minutes={**I, "description": "몇 분 뒤"}, time={**S, "description": "HH:MM (24시간)"})
def remind(office, job, args):
    message, minutes, time = _s(args, "message", 200), _i(args, "minutes"), _s(args, "time")
    if not message:
        raise OfficeError("무엇을 알려 드릴지 알려 주세요.")
    try:
        at = resolve_time(office.planner.now(), minutes=minutes if 0 < minutes <= 1440 else 0, time=time)
    except ValueError:
        raise OfficeError("몇 분 뒤(minutes)나 몇 시(time, 예: 21:30)인지 알려 주세요.") from None
    office.planner.add_todo(message, date=at.date().isoformat(), time=f"{at:%H:%M}")
    return {"at": f"{at:%Y-%m-%d %H:%M}", "message": message}


@tool("add_schedule", "일정", "일정·시험·숙제(정해진 날짜) 또는 할 일(todo=true)을 등록한다", ("title",),
      title=S, date={**S, "description": "YYYY-MM-DD"}, time={**S, "description": "HH:MM, 없으면 빈칸"},
      kind={"type": "string", "enum": ["일정", "시험", "숙제"]}, remind_minutes=I,
      repeat={"type": "string", "enum": ["none", "daily", "weekly"]}, todo={"type": "boolean"})
def add_schedule(office, job, args):
    title, date, time = _s(args, "title", 100), _s(args, "date"), _s(args, "time")
    if args.get("todo") is True:
        return {"todo": office.planner.add_todo(title, date, time)}
    remind_at = args.get("remind_minutes")
    remind_at = remind_at if isinstance(remind_at, int) and not isinstance(remind_at, bool) else (10 if time else None)
    return {"event": office.planner.add_event(title, date, time, args.get("kind") or "일정", remind_at, args.get("repeat") or "none")}


@tool("status", "현황", "오늘(today: 할 일·일정·시험·공부) 또는 작업(jobs: 결재 대기·진행 중·최근) 현황을 본다", ("what",),
      what={"type": "string", "enum": ["today", "jobs"]})
def status(office, job, args):
    return office.jobs_summary(job) if args.get("what") == "jobs" else office.today_summary()


@tool("job_action", "결재·작업", "사무실 작업을 승인·반려·중단·처음부터 다시 한다", ("action",),
      action={"type": "string", "enum": ["approve", "reject", "cancel", "rerun"]},
      job={**S, "description": "latest(방금 것)·all(전부)·작업 번호"}, comment={**S, "description": "결재 의견 (반려면 고칠 점)"})
def job_action(office, job, args):
    return office.act_on_jobs(job, args.get("action"), _s(args, "job", 40) or "latest", _s(args, "comment"))


@tool("todo_done", "할 일 체크", "할 일을 했다고 체크한다", ("text",), text={**S, "description": "할 일 이름 (일부만 맞아도 됨)"})
def todo_done(office, job, args):
    return office.check_todo(_s(args, "text", 200))


@tool("focus", "공부모드", "공부모드(집중 타이머)를 켜거나 끈다", ("action",),
      action={"type": "string", "enum": ["start", "stop"]}, minutes=I, task=S)
def focus(office, job, args):
    if args.get("action") == "stop":
        return {"stopped": True, "studied_minutes": office.planner.stop_focus()}
    minutes = _i(args, "minutes", 25)
    return {"started": office.planner.start_focus(minutes if 1 <= minutes <= 180 else 25, _s(args, "task", 100))}


@tool("change_setting", "설정", "설정을 바꾼다: ai(fast·careful), pc·phone·job_done(on·off), briefing(HH:MM 또는 off)", ("key", "value"),
      key={"type": "string", "enum": ["ai", "pc", "phone", "job_done", "briefing"]}, value=S)
def change_setting(office, job, args):
    key, value = args.get("key"), _s(args, "value", 20).lower()
    if key == "ai":
        mode = {"fast": "fast", "빠름": "fast", "careful": "careful", "꼼꼼": "careful"}.get(value)
        if not mode:
            raise OfficeError("AI 모드는 fast(빠름)·careful(꼼꼼) 중 하나예요.")
        office.notifier.update({"ai": mode})
        llm.mode = mode
        threading.Thread(target=llm.warm, daemon=True, name="office-warm").start()
        return {"ai": mode}
    if key in ("pc", "phone", "job_done"):
        on = value in ("on", "true", "켜", "켜기", "yes")
        if not on and value not in ("off", "false", "꺼", "끄기", "no"):
            raise OfficeError("on(켜기)·off(끄기)로 알려 주세요.")
        return {key: office.notifier.update({key: on})[key]}
    if key == "briefing":
        return {"briefing": office.notifier.update({"briefing": "" if value in ("off", "끄기", "꺼") else value})["briefing"]}
    raise OfficeError("바꿀 수 없는 설정이에요.")


@tool("wiki", "위키 조사", "위키백과에서 주제를 찾아 요약을 본다 (사실 확인용)", ("topic",), topic=S)
def wiki(office, job, args):
    m = office.steps["research"](_s(args, "topic", 100), say=lambda msg: None)
    return {"title": m.title, "summary": m.markdown[:1500], "source": m.sources[:1]}


class Agent:
    def __init__(self, office, chat=None):
        self.office = office
        self.llm = chat or llm.chat_tools

    def specs(self) -> list[dict]:
        return [t["spec"] for t in TOOLS.values()]

    def context(self, job) -> str:
        now = self.office.planner.now()
        lines = [f"지금: {now:%Y-%m-%d %H:%M} ({'월화수목금토일'[now.weekday()]}요일)",
                 "허용 폴더: " + ", ".join(sorted(self.office.files.folders)) + " (그 밖은 못 건드림)"]
        if job.names:
            lines.append("첨부 파일: " + ", ".join(job.names) + " (do_work가 알아서 읽음)")
        if job.ref:
            lines.append("대표가 고른 이전 자료가 있다 (do_work가 알아서 씀)")
        if job.assignee:
            lines.append(f"대표가 이 일을 {NAMES[job.assignee]} 팀에 맡겼다. 결과물은 그 팀 일로만 만든다.")
        return "\n".join(lines)

    def run(self, job, text: str) -> str:
        messages = [{"role": "system", "content": RAB_SYSTEM + "\n\n" + self.context(job)}, {"role": "user", "content": text}]
        for _ in range(MAX_TURNS):
            self.office.checkpoint(job)
            msg = self.llm(messages, self.specs())
            calls = [c for c in msg.get("tool_calls") or [] if isinstance(c, dict)]
            messages.append({"role": "assistant", "content": msg.get("content") or "", **({"tool_calls": calls} if calls else {})})
            if not calls:
                return (msg.get("content") or "").strip() or "대표님, 처리했습니다."
            for c in calls[:MAX_CALLS]:
                fn = c.get("function") or {}
                name, args = str(fn.get("name") or ""), fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                result = self.use(job, name, args if isinstance(args, dict) else {})
                messages.append({"role": "tool", "tool_name": name,
                                 "content": json.dumps(result, ensure_ascii=False, default=str)[:RESULT_CHARS]})
        return "대표님, 도구를 여러 번 써도 끝나지 않아 여기서 멈췄습니다. 조금 더 구체적으로 말씀해 주세요."

    def use(self, job, name: str, args: dict) -> dict:
        t = TOOLS.get(name)
        if t is None:
            return {"error": f"'{name}' 도구는 없어요. 목록에 있는 도구만 쓸 수 있어요."}
        brief = ", ".join(f"{v}" for v in args.values() if isinstance(v, (str, int)) and str(v))[:60]
        self.office.say(job, f"{t['label']}{': ' + brief if brief else ''}")
        try:
            out = t["run"](self.office, job, args)
            self.office.trace(job, f"{t['label']}{' · ' + brief if brief else ''} ✓")
            return out
        except Cancelled:
            raise
        except OfficeError as e:
            self.office.trace(job, f"{t['label']} ✗ {e}")
            return {"error": str(e)}
        except Exception as e:  # 도구 하나가 터져도 rab은 대표에게 보고할 수 있게
            traceback.print_exc()
            self.office.trace(job, f"{t['label']} ✗ 오류")
            return {"error": f"도구 오류 ({type(e).__name__})"}


def bring_copy(src: Path, inputs: Path) -> Path:
    inputs.mkdir(parents=True, exist_ok=True)
    target = inputs / src.name
    n = 2
    while target.exists():
        target = inputs / f"{src.stem} ({n}){src.suffix}"
        n += 1
    import shutil
    shutil.copy2(src, target)
    return target
