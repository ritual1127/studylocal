// 탭 화면들: 사무실 · 보관함 · 오늘 · 일정 · 대표실 · 설정
import { DECOR, SPRITES, variant } from "./sprites.js";
import {
  DUTY, NAMES, OUTPUT_NAMES, ROLE_OF, SUBS, TEAMS, TEAM_STEP, act, ddayText, getJSON, h, keyed, minutesText, put, rich,
  store, teamOf, toast,
} from "./ui.js";

const LIGHT = { idle: "쉬는 중", working: "일하는 중", done: "끝", error: "에러" };
const BADGE = { queued: "접수", running: "진행 중", review: "결재 대기", revising: "수정 중", done: "완료",
                error: "에러", needs_input: "되물음", cancelled: "취소됨" };
const LINKS = [["analysis", "분석 보고서"], ["pdf", "PDF 노트"], ["quiz", "문제 풀기"], ["cards", "암기카드"],
               ["mindmap", "마인드맵"], ["translation", "번역"], ["csv", "카드 CSV(Anki)"], ["text", "원문"]];
const WEEK = "일월화수목금토";
const STILL = matchMedia("(prefers-reduced-motion: reduce)").matches;

const isFile = (url) => typeof url === "string" && url.startsWith("/files/");
const jobNo = (job) => (job.no ? `No.${String(job.no).padStart(4, "0")}` : `No.${job.id.slice(4, 8)}-${job.id.slice(9, 13)}`);
export const jobTitle = (job) => job.title || job.text.slice(0, 30) || "첨부 파일 작업";
const jobUrl = (id, what) => `/api/jobs/${encodeURIComponent(id)}/${what}`;
const dayLabel = (iso) => `${+iso.slice(5, 7)}/${+iso.slice(8, 10)}(${WEEK[new Date(iso + "T00:00").getDay()]})`;
const daysFrom = (today, iso) => Math.round((new Date(iso + "T00:00") - new Date(today + "T00:00")) / 86400000);

// ---- 두 번 눌러야 하는 버튼 (배포·지우기·주제 바꾸기) ----
const armed = new Map();
function arm(key, rerender) {
  if (armed.has(key)) {
    clearTimeout(armed.get(key));
    armed.delete(key);
    return true;
  }
  armed.set(key, setTimeout(() => { armed.delete(key); rerender(); }, 4000));
  rerender();
  return false;
}

async function copy(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = "복사됨!";
  } catch {
    btn.textContent = "복사 실패";
  }
  setTimeout(() => (btn.textContent = "복사"), 1500);
}

// ---- 작업 카드 ----
function resultLinks(job) {
  const r = job.results ?? {};
  return LINKS.filter(([key]) => isFile(r[key])).map(([key, label]) =>
    h("a", { class: key === "text" || key === "csv" ? "btn alt" : "btn", href: r[key], target: "_blank", rel: "noopener" }, label));
}

function stampOf(job) {
  const last = job.approvals?.at(-1);
  if (job.status === "done" && last?.action === "approve") return h("span", { class: "stamp ok", title: `${last.time} 대표 승인` }, "승인");
  if (job.status === "done" && last?.action === "auto") return h("span", { class: "stamp auto", title: "자동 승인 규칙" }, "자동승인");
  if (job.status === "revising") return h("span", { class: "stamp no" }, "반려");
  return null;
}

function answerBox(job) {
  return h("details", { class: "answer", open: job.answer.length <= 360 },
    h("summary", {}, "선생님 답변"), h("div", { class: "answer-text" }, rich(job.answer)),
    isFile(job.results?.answer) && h("a", { href: job.results.answer, target: "_blank", rel: "noopener" }, "파일로 보기"));
}

const outputsOf = (job) => (job.steps ?? []).filter((s) => OUTPUT_NAMES[s]).map((s) => OUTPUT_NAMES[s]);
const ACTIVE = ["queued", "running", "revising"];
const renaming = new Set(); // 제목을 고치는 중인 카드
const cardSig = (job, ctx) => JSON.stringify({ ...job, log: undefined }) + [...armed.keys()].filter((k) => k.endsWith(":" + job.id))
  + renaming.has(job.id) + (job.status === "queued" ? queuePos(job, ctx) : "");
const queuePos = (job, ctx) => (ctx.state()?.jobs ?? []).filter((j) => j.status === "queued").sort((a, b) => a.no - b.no)
  .findIndex((j) => j.id === job.id) + 1;

function titleRow(job, ctx) {
  if (!renaming.has(job.id)) {
    return h("div", { class: "card-title" }, h("span", { class: "no" }, jobNo(job)), job.star && h("b", { class: "star", title: "즐겨찾기" }, "★"),
      h("h3", {}, jobTitle(job)));
  }
  const input = h("input", { class: "input", value: jobTitle(job), maxlength: 80, "aria-label": "새 제목" });
  const done = () => { renaming.delete(job.id); ctx.rerender(); };
  const save = async () => {
    if (await act(jobUrl(job.id, "rename"), { title: input.value }, "제목 바꿨어요")) ctx.refresh();
    done();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) save();
    if (e.key === "Escape") done();
  });
  setTimeout(() => input.focus(), 0);
  return h("div", { class: "card-title rename" }, input, h("button", { class: "btn small", type: "button", onclick: save }, "저장"),
    h("button", { class: "btn alt small", type: "button", onclick: done }, "취소"));
}

function jobCard(job, ctx) {
  const r = job.results ?? {};
  const id = job.id;
  const twice = (key, run) => () => arm(key + ":" + id, ctx.rerender) && run();
  const actions = resultLinks(job);
  for (const f of r.files ?? []) actions.push(h("a", { class: "btn alt", href: f.url, download: f.name }, `가져온 파일: ${f.name}`));
  if (isFile(r.text)) actions.push(h("button", { class: "btn alt", type: "button", onclick: () => ctx.setRef(job) }, "이 자료로 더 하기"));
  if (job.status === "review") actions.push(h("button", { class: "btn hot", type: "button", onclick: () => ctx.openTab("ceo") }, "결재하러 가기"));
  if (ACTIVE.includes(job.status)) {
    actions.push(h("button", { class: "btn no", type: "button",
      onclick: () => act(jobUrl(id, "cancel"), undefined, job.status === "queued" ? "취소했어요" : "지금 단계가 끝나면 멈출게요").then(ctx.refresh) }, "중단"));
  } else {
    const careful = job.status === "done" || job.status === "review";  // 결과가 바뀌니 두 번 눌러서
    const on = armed.has("rerun:" + id);
    actions.push(h("button", { class: on ? "btn armed" : "btn", type: "button",
      onclick: careful ? twice("rerun", () => act(jobUrl(id, "retry"), undefined, "처음부터 다시 할게요").then(ctx.refresh))
        : () => act(jobUrl(id, "retry"), undefined, "다시 시켰어요").then(ctx.refresh) },
      on ? "결과가 새로 바뀌어요. 한 번 더" : job.status === "error" ? "다시" : "처음부터 다시"));
  }
  actions.push(h("button", { class: "btn alt", type: "button", onclick: () => ctx.editAgain(job) }, "고쳐서 다시"));
  if (isFile(r.quiz) && job.status === "done") {
    const on = armed.has("deploy:" + id);
    actions.push(h("button", { class: on ? "btn armed" : "btn", type: "button",
      onclick: twice("deploy", () => act(jobUrl(id, "deploy"), undefined, "배포담당한테 넘겼어요").then(ctx.refresh)) },
      on ? "공개 링크로 올릴까요? 한 번 더 누르면 배포" : "배포"));
  }
  actions.push(h("button", { class: "btn alt", type: "button", title: "즐겨찾기",
    onclick: () => act(jobUrl(id, "star")).then(ctx.refresh) }, job.star ? "★ 빼기" : "☆ 즐겨찾기"));
  actions.push(h("button", { class: "btn alt", type: "button", onclick: () => { renaming.add(id); ctx.rerender(); } }, "제목 바꾸기"));
  if (Object.keys(r).length) {
    actions.push(h("a", { class: "btn alt", href: jobUrl(id, "zip"), download: "" }, "한 번에 받기(zip)"));
    actions.push(h("button", { class: "btn alt", type: "button", onclick: () => act(jobUrl(id, "open")) }, "폴더"));
  }
  if (!ACTIVE.includes(job.status)) {
    const on = armed.has("delete:" + id);
    actions.push(h("button", { class: on ? "btn armed" : "btn alt", type: "button",
      onclick: twice("delete", () => act(jobUrl(id, "delete"), undefined, "지웠어요").then(ctx.refresh)) }, on ? "정말 지울까요? 한 번 더" : "지우기"));
  }
  const url = typeof r.deploy_url === "string" && r.deploy_url.startsWith("https://") ? r.deploy_url : null;
  const pos = job.status === "queued" ? queuePos(job, ctx) : 0;
  const meta = [job.created, pos ? `대기 ${pos}번째` : "", job.seconds ? `${job.seconds}초 걸림` : "", job.revision ? `수정 ${job.revision}번` : "",
                job.names?.join(", ")].filter(Boolean).join(" · ");
  return h("article", { class: `card ${job.status}` },
    h("header", { class: "card-head" }, titleRow(job, ctx), h("span", { class: `badge ${job.status}` }, BADGE[job.status] ?? job.status)),
    stampOf(job),
    h("p", { class: "muted" }, meta, job.assignee && h("span", { class: "chip-team" }, `${NAMES[job.assignee]} 팀`)),
    h("p", { class: "muted cmd" }, `지시: ${job.text}`),
    job.reply && h("p", { class: "reply" }, h("b", { style: "color: var(--c1)" }, "실장님 "), job.reply),
    job.trace?.length && h("details", { class: "trace" }, h("summary", {}, `실장님 작업 기록 ${job.trace.length}개`),
      h("ol", {}, job.trace.map((t) => h("li", {}, t)))),
    job.warnings?.length && h("ul", { class: "warn" }, job.warnings.map((w) => h("li", {}, w))),
    job.error && h("p", { class: "err" }, job.error),
    job.answer && answerBox(job),
    h("div", { class: "actions" }, actions),
    url && h("p", { class: "deployed" }, h("a", { href: url, target: "_blank", rel: "noopener" }, url),
      h("button", { class: "btn alt", type: "button", onclick: (e) => copy(url, e.currentTarget) }, "복사")),
    r.deploy_error && h("p", { class: "err" }, r.deploy_error));
}

// ---- 사무실 ----
function draw(desk, frame, dy) {
  const key = `${frame}:${dy}`;
  if (desk.drawn === key) return;
  desk.drawn = key;
  desk.ctx.clearRect(0, 0, 16, 16);
  desk.sprite.frames[frame].forEach((row, y) => {
    [...row].forEach((ch, x) => {
      if (ch === ".") return;
      desk.ctx.fillStyle = desk.sprite.colors[ch];
      desk.ctx.fillRect(x, y < 14 ? y + dy : y, 1, 1); // 키보드(14~15줄)는 안 움직임
    });
  });
}

export function animateOffice(view) {
  const t = STILL ? 0 : performance.now();
  for (const desk of Object.values(view.desks)) {
    const frame = desk.state === "working" ? Math.floor(t / 300) % 2 : 0;
    const dy = desk.state === "idle" ? -(Math.floor(t / 1000) % 2) : 0;
    draw(desk, frame, dy);
  }
}

function deskEl(color, sprite, name, duty, extra = {}) {
  const say = h("p", { class: "say" });
  const bubble = h("div", { class: "bubble empty" }, say);
  const canvas = h("canvas", { class: "sprite", width: 16, height: 16, "aria-hidden": "true" });
  const light = h("i", { class: "light idle", role: "img", "aria-label": LIGHT.idle });
  const el = h(extra.tag ?? "div", { class: `desk ${extra.cls ?? ""}`, style: `--who: ${color}`, title: `${name} — ${duty}`, ...extra.props },
    bubble, canvas, extra.badge, h("div", { class: "table" }), h("p", { class: "plate" }, extra.still ? null : light, name),
    h("p", { class: "duty" }, duty));
  return { el, desk: { say, bubble, light, ctx: canvas.getContext("2d"), state: extra.still ? "still" : "idle", drawn: "", sprite } };
}

function officeView(ctx) {
  const floor = h("div", { class: "floor", "aria-label": "사무실" });
  const desks = {};
  const badge = h("span", { class: "door-badge", hidden: true });
  for (const team of TEAMS) {
    floor.append(h("p", { class: "team-sign", style: `--team: ${team.color}` }, h("b", {}, team.name),
      h("span", { class: "muted" }, team.roles.map((r) => NAMES[r]).join(" · "))));
    for (const role of team.roles) {
      const { el, desk } = deskEl(team.color, SPRITES[role], NAMES[role], DUTY[role], {
        tag: "button", props: { type: "button", "aria-label": `${NAMES[role]} 팀 보기 (4인 1조)`, onclick: () => ctx.openTeam(role) },
      });
      floor.append(el);
      desks[role] = desk;
    }
    if (team.extra === "door") {
      const { el, desk } = deskEl("var(--c4)", DECOR.door, "대표실", "결재·회사 현황", {
        tag: "button", cls: "door", still: true, badge,
        props: { type: "button", "aria-label": "대표실로 가기", onclick: () => ctx.openTab("ceo") },
      });
      floor.append(el);
      desks.door = desk;
    }
    if (team.extra === "plant") {
      const { el, desk } = deskEl("var(--ok)", DECOR.plant, "휴게실", "잠깐 쉬어가기", { cls: "lounge", still: true });
      floor.append(el);
      desks.plant = desk;
    }
  }
  const log = h("ol", { class: "log-list" });
  const el = h("div", { class: "view office-view" }, floor, h("section", { class: "box log" }, h("h2", {}, "업무 일지 (최근 작업)"), log));
  let logKey = null;

  function renderLog(lines) {
    const key = lines.join("\n");
    if (key === logKey) return;
    logKey = key;
    if (!lines.length) {
      log.replaceChildren(h("li", { class: "muted" }, "아직 기록이 없어. 아래 지시 칸에 일을 시켜줘!"));
      return;
    }
    log.replaceChildren(...lines.map((line) => {
      const m = /^\[(.+?)\] ([\s\S]*)$/.exec(line);
      const role = m && ROLE_OF[m[1]];
      if (!role) return h("li", {}, line);
      return h("li", {}, h("b", { style: `color: ${teamOf(role).color}` }, `[${m[1]}]`), " ", m[2]);
    }));
    log.scrollTop = log.scrollHeight;
  }

  return {
    el, desks,
    update(s) {
      for (const role of Object.keys(NAMES)) {
        const st = s.staff[role] ?? { state: "idle", say: "" };
        const desk = desks[role];
        desk.state = st.state;
        desk.light.className = `light ${st.state}`;
        desk.light.setAttribute("aria-label", LIGHT[st.state] ?? st.state);
        if (desk.say.textContent !== st.say) {
          desk.say.textContent = st.say;
          desk.say.title = st.say;
        }
        desk.bubble.classList.toggle("empty", !st.say);
      }
      const pending = s.jobs.filter((j) => j.status === "review").length;
      badge.hidden = !pending;
      badge.textContent = `결재 ${pending}`;
      renderLog(s.jobs[0]?.log ?? []);
    },
  };
}

// ---- 보관함: 최근 · 전체 기록 ----
function vaultView(ctx) {
  const FILTERS = [["all", "전체"], ["review", "결재 대기"], ["done", "완료"], ["error", "에러·취소"], ["star", "★"]];
  let filter = "all";
  let mode = store.get("ritual-vault-mode", "recent");
  let history = { jobs: [], total: 0, counts: {}, more: false };
  let fetched = 0;
  let loading = false;
  const list = h("div", { class: "jobs" });
  const more = h("button", { class: "btn alt more", type: "button", hidden: true, onclick: () => load(true) }, "더 보기");
  const summary = h("p", { class: "muted" });
  let typing = null;
  const search = h("input", { class: "input", type: "search", placeholder: "제목·지시·파일 이름으로 찾기", "aria-label": "보관함 검색",
    oninput: () => { clearTimeout(typing); typing = setTimeout(() => (mode === "history" ? load() : render()), 250); } });
  const chips = h("div", { class: "filters", role: "group", "aria-label": "보관함 거르기" });
  const modes = h("div", { class: "seg", role: "group", "aria-label": "보관함 보기" });
  function drawChips() {
    chips.replaceChildren(...FILTERS.map(([id, label]) => h("button", {
      type: "button", class: "chip-btn" + (id === filter ? " on" : ""), "aria-pressed": String(id === filter),
      onclick: () => { filter = id; drawChips(); mode === "history" ? load() : render(); },
    }, label, mode === "history" && history.counts[id] != null ? ` ${history.counts[id]}` : "")));
    modes.replaceChildren(...[["recent", "최근"], ["history", "전체 기록"]].map(([id, label]) => h("button", {
      type: "button", class: "chip-btn" + (id === mode ? " on" : ""), "aria-pressed": String(id === mode),
      onclick: () => { mode = id; store.set("ritual-vault-mode", id); drawChips(); id === "history" ? load() : render(); },
    }, label)));
  }
  drawChips();

  async function load(append = false) {
    if (loading) return;
    loading = true;
    const params = new URLSearchParams({ q: search.value.trim(), offset: append ? history.jobs.length : 0, limit: 30 });
    if (filter === "star") params.set("star", "true");
    else if (filter !== "all") params.set("status", filter);
    try {
      const page = await getJSON(`/api/history?${params}`);
      history = append ? { ...page, jobs: [...history.jobs, ...page.jobs] } : page;
      fetched = Date.now();
      drawChips();
      render();
    } catch {
      toast("기록을 못 불러왔어요", "err");
    } finally {
      loading = false;
    }
  }
  ctx.onRefresh(() => { fetched = 0; });

  const match = (j) => filter === "all" || (filter === "star" ? j.star : j.status === filter || (filter === "review" && j.status === "revising")
    || (filter === "error" && ["needs_input", "cancelled"].includes(j.status)));
  function render() {
    const s = ctx.state();
    if (!s) return;
    if (mode === "history") {
      more.hidden = !history.more;
      summary.textContent = `전체 ${history.counts.all ?? 0}건 중 ${history.total}건`;
      const groups = [];
      for (const job of history.jobs) {
        const day = job.created.slice(0, 10);
        if (!groups.length || groups.at(-1).day !== day) groups.push({ day, jobs: [] });
        groups.at(-1).jobs.push(job);
      }
      put(list, ...(groups.length ? groups.map((g) => h("section", { class: "day-group" },
        h("h3", {}, dayLabel(g.day), " ", h("span", { class: "muted" }, `${g.jobs.length}건`)), g.jobs.map((j) => jobCard(j, ctx))))
        : [h("p", { class: "empty" }, "맞는 기록이 없어요")]));
      list._keyed = null;
      return;
    }
    more.hidden = true;
    summary.textContent = "";
    const q = search.value.trim().toLowerCase();
    const jobs = s.jobs.filter((j) => match(j) && (!q || `${j.title} ${j.text} ${(j.names ?? []).join(" ")}`.toLowerCase().includes(q)));
    keyed(list, jobs, (j) => j.id, (j) => cardSig(j, ctx), (j) => jobCard(j, ctx),
      q || filter !== "all" ? "맞는 작업이 없어요" : "아직 결과가 없어요. 아래 지시 칸에 실장님께 시켜 보세요!");
  }
  const el = h("div", { class: "view" }, h("div", { class: "vault-tools" }, modes, search, chips), summary, list, more);
  return {
    el,
    show: () => mode === "history" && load(),
    update() {
      if (mode === "history" && Date.now() - fetched > 10000 && !renaming.size && !armed.size) load();
      else if (mode === "recent") render();
    },
  };
}

// ---- 4인 1조 팀 팝업 ----
export function teamPanel(role, ctx) {
  const s = ctx.state();
  const st = s?.staff[role] ?? { state: "idle", say: "" };
  const team = teamOf(role);
  const steps = TEAM_STEP[role];
  const recent = (s?.jobs ?? []).filter((j) => j.assignee === role || (steps ? (j.steps ?? []).some((x) => steps.includes(x))
    : role === "manager" || (role === "deployer" && j.results?.deploy_url))).slice(0, 5);
  const face = (sprite) => {
    const canvas = h("canvas", { class: "sprite", width: 16, height: 16, "aria-hidden": "true" });
    draw({ ctx: canvas.getContext("2d"), sprite, drawn: "" }, 0, 0);
    return canvas;
  };
  const busy = st.state === "working";
  const turn = Math.floor(Date.now() / 4000) % 3; // 일할 땐 하위 직원이 돌아가며 맡는다
  const members = [
    h("div", { class: "member lead" }, face(SPRITES[role]), h("b", {}, NAMES[role]), h("small", {}, `팀장 · ${DUTY[role]}`),
      h("small", { class: `state ${st.state}` }, st.say || LIGHT[st.state])),
    ...SUBS[role].map(([name, skill], i) => h("div", { class: "member" }, face(variant(SPRITES[role], i)), h("b", {}, name), h("small", {}, skill),
      h("small", { class: `state ${busy && i === turn ? "working" : "idle"}` }, busy && i === turn ? "함께 일하는 중" : "대기"))),
  ];
  return h("div", { class: "team-panel", style: `--team: ${team.color}` },
    h("h2", { id: "teamTitle" }, `${NAMES[role]} 팀`, h("span", { class: "muted" }, ` · ${team.name} · 4인 1조`)),
    h("div", { class: "members" }, members),
    h("h3", {}, "최근 작업"),
    h("ul", { class: "list" }, recent.length ? recent.map((j) => h("li", { class: "event" }, h("small", { class: "time" }, jobNo(j)),
      h("span", {}, jobTitle(j)), h("span", { class: `badge ${j.status}` }, BADGE[j.status] ?? j.status)))
      : [h("li", { class: "empty" }, "아직 이 팀 작업이 없어요")]),
    h("div", { class: "actions" }, h("button", { class: "btn", type: "button", "data-first": "", onclick: () => ctx.mention(role) },
      role === "manager" ? "실장님께 시키기" : `${NAMES[role]} 팀에 시키기`)));
}

// ---- 오늘 ----
function stat(label, value) {
  return h("div", { class: "stat" }, h("small", {}, label), h("b", {}, value));
}

function weekBars(week) {
  const top = Math.max(60, ...week.map((d) => d.minutes));
  return h("div", { class: "stat bars", "aria-label": "7일 공부 시간" }, h("small", {}, "7일 공부"),
    h("div", { class: "bar-row" }, week.map((d) => h("span", { title: `${d.date} ${d.minutes}분` },
      h("i", { style: `height: ${Math.round((d.minutes / top) * 100)}%` }), h("small", {}, WEEK[new Date(d.date + "T00:00").getDay()])))));
}

function todayView(ctx) {
  const head = h("div", { class: "view-head" });
  const stats = h("div", { class: "stats-row" });
  const events = h("ul", { class: "list" });
  const todos = h("ul", { class: "list" });
  const overdue = h("ul", { class: "list" });
  const overdueBox = h("section", { class: "box warnbox" }, h("h2", {}, "밀린 일"), overdue);
  const text = h("input", { class: "input grow", placeholder: "할 일 적고 Enter (예: 영어 단어 30개)", "aria-label": "새 할 일", maxlength: 200 });
  const time = h("input", { class: "input", type: "time", "aria-label": "알림 받을 시각 (안 적어도 돼)", title: "알림 받을 시각 (안 적어도 돼)" });
  const form = h("form", {
    class: "row-form",
    onsubmit: async (e) => {
      e.preventDefault();
      if (!text.value.trim()) return;
      if (await act("/api/todos", { text: text.value, time: time.value })) {
        text.value = "";
        time.value = "";
        ctx.refresh();
      }
    },
  }, text, time, h("button", { class: "btn", type: "submit" }, "추가"));
  const el = h("div", { class: "view" }, head, stats,
    h("section", { class: "box" }, h("h2", {}, "오늘 일정"), events),
    h("section", { class: "box" }, h("h2", {}, "오늘 할 일"), form, todos), overdueBox);

  const todoItem = (t, late, today) => h("li", { class: "todo" + (t.done ? " done" : "") },
    h("label", { class: "check" }, h("input", {
      type: "checkbox", checked: t.done,
      onchange: (e) => act(`/api/todos/${t.id}`, { done: e.target.checked }, e.target.checked ? "잘했어!" : null).then(ctx.refresh),
    }), h("span", {}, t.text)),
    late && h("small", { class: "muted" }, dayLabel(t.date)),
    t.time && h("small", { class: "time" }, t.time),
    late && h("button", { class: "btn alt small", type: "button", onclick: () => act(`/api/todos/${t.id}`, { date: today }, "오늘로 옮겼어").then(ctx.refresh) }, "오늘로"),
    h("button", { class: "x", type: "button", "aria-label": `${t.text} 지우기`, onclick: () => act(`/api/todos/${t.id}/delete`).then(ctx.refresh) }, "✕"));

  let key = "";
  return {
    el,
    update(s) {
      const p = s.planner;
      const k = JSON.stringify([p.today, p.todos, p.overdue, p.today_events, p.stats, p.dday]);
      if (k === key) return;
      key = k;
      put(head, h("h2", { class: "big" }, `${+p.today.slice(5, 7)}월 ${+p.today.slice(8)}일 (${p.weekday})`),
        p.dday && h("span", { class: "dday" }, `${p.dday.title} ${ddayText(p.dday.days)}`));
      const left = p.todos.filter((t) => !t.done).length;
      stats.replaceChildren(stat("오늘 공부", minutesText(p.stats.today)), stat("연속 공부", `${p.stats.streak}일`),
        stat("남은 할 일", `${left}개`), weekBars(p.stats.week));
      events.replaceChildren(...(p.today_events.length ? p.today_events.map((e) => h("li", { class: "event" },
        h("small", { class: "time" }, e.time || "종일"), h("span", {}, e.title), h("span", { class: `kind k-${e.kind}` }, e.kind)))
        : [h("li", { class: "empty" }, "오늘은 일정이 없어")]));
      todos.replaceChildren(...(p.todos.length ? p.todos.map((t) => todoItem(t, false, p.today))
        : [h("li", { class: "empty" }, "할 일이 없어. 위에 적거나 \"오늘 할 일에 단어 외우기 넣어줘\"라고 시켜봐")]));
      overdueBox.hidden = !p.overdue.length;
      overdue.replaceChildren(...p.overdue.map((t) => todoItem(t, true, p.today)));
    },
  };
}

// ---- 일정 ----
function scheduleView(ctx) {
  const opt = (value, label, on) => h("option", { value, selected: on }, label);
  const title = h("input", { class: "input grow", placeholder: "일정 이름 (예: 수학 학원, 기말고사)", "aria-label": "일정 이름", maxlength: 100 });
  const date = h("input", { class: "input", type: "date", "aria-label": "날짜" });
  const time = h("input", { class: "input", type: "time", "aria-label": "시각 (안 적어도 돼)" });
  const kind = h("select", { class: "input", "aria-label": "종류" }, opt("일정", "일정", true), opt("시험", "시험"), opt("숙제", "숙제"));
  const remind = h("select", { class: "input", "aria-label": "알림" }, opt("", "알림 없음"), opt("0", "정각에"),
    opt("10", "10분 전", true), opt("30", "30분 전"), opt("60", "1시간 전"), opt("1440", "하루 전"));
  const repeat = h("select", { class: "input", "aria-label": "반복" }, opt("none", "반복 안 함", true), opt("daily", "매일"), opt("weekly", "매주"));
  const form = h("form", {
    class: "row-form wrap",
    onsubmit: async (e) => {
      e.preventDefault();
      const body = { title: title.value, date: date.value, time: time.value, kind: kind.value,
                     remind: time.value && remind.value !== "" ? Number(remind.value) : null, repeat: repeat.value };
      if (await act("/api/events", body, `'${title.value.trim()}' 넣었어`)) {
        title.value = "";
        time.value = "";
        ctx.refresh();
      }
    },
  }, title, date, time, kind, remind, repeat, h("button", { class: "btn", type: "submit" }, "일정 넣기"));
  const list = h("div", { class: "agenda" });
  const later = h("ul", { class: "list" });
  const laterBox = h("section", { class: "box" }, h("h2", {}, "한 달 뒤"), later);
  const el = h("div", { class: "view" },
    h("section", { class: "box" }, h("h2", {}, "새 일정"), form, h("p", { class: "muted" }, "말로 해도 돼: \"다음 주 화요일 4시 영어 학원 매주\", \"기말고사 11월 20일\"")),
    h("section", { class: "box" }, h("h2", {}, "앞으로 30일"), list), laterBox);

  const delBtn = (e) => {
    const k = "event:" + e.id;
    const on = armed.has(k);
    return h("button", {
      class: on ? "btn armed small" : "x", type: "button", "aria-label": `${e.title} 지우기`,
      onclick: () => arm(k, () => { key = ""; ctx.rerender(); }) && act(`/api/events/${e.id}/delete`, undefined, "지웠어").then(ctx.refresh),
    }, on ? (e.repeat !== "none" ? "반복 전부 지울까?" : "지울까?") : "✕");
  };
  const eventRow = (e) => h("li", { class: "event" }, h("small", { class: "time" }, e.time || "종일"), h("span", {}, e.title),
    h("span", { class: `kind k-${e.kind}` }, e.kind), e.repeat !== "none" && h("small", { class: "muted" }, e.repeat === "daily" ? "매일" : "매주"),
    e.remind != null && e.time && h("small", { class: "muted" }, e.remind ? `${e.remind >= 60 ? e.remind / 60 + "시간" : e.remind + "분"} 전 알림` : "정각 알림"),
    delBtn(e));

  let key = "";
  return {
    el,
    update(s) {
      const p = s.planner;
      if (!date.value) date.value = p.today;
      const k = JSON.stringify([p.upcoming, p.events, p.today, [...armed.keys()].filter((a) => a.startsWith("event:"))]);
      if (k === key) return;
      key = k;
      const groups = new Map();
      for (const e of p.upcoming) groups.set(e.date, [...(groups.get(e.date) ?? []), e]);
      list.replaceChildren(...(groups.size ? [...groups].map(([day, items]) => {
        const n = daysFrom(p.today, day);
        return h("div", { class: "day" + (n === 0 ? " today" : "") },
          h("h3", {}, dayLabel(day), " ", h("span", { class: "muted" }, n === 0 ? "오늘" : n === 1 ? "내일" : `D-${n}`)),
          h("ul", { class: "list" }, items.map(eventRow)));
      }) : [h("p", { class: "empty" }, "30일 안에 일정이 없어")]));
      const last = p.upcoming.at(-1)?.date ?? p.today;
      const far = p.events.filter((e) => e.repeat === "none" && e.date > last && daysFrom(p.today, e.date) > 30)
        .sort((a, b) => a.date.localeCompare(b.date));
      laterBox.hidden = !far.length;
      later.replaceChildren(...far.map((e) => h("li", { class: "event" }, h("small", { class: "time" }, dayLabel(e.date)),
        h("span", {}, e.title), h("span", { class: `kind k-${e.kind}` }, e.kind), delBtn(e))));
    },
  };
}

// ---- 대표실 ----
function ceoView(ctx) {
  const kpis = h("div", { class: "kpis" });
  const inbox = h("div", { class: "jobs" });
  const org = h("div", { class: "org" });
  const rules = h("div", { class: "rules" });
  const history = h("div", { class: "history" });
  const el = h("div", { class: "view ceo" },
    h("div", { class: "view-head" }, h("h2", { class: "big" }, "대표실"), h("span", { class: "muted" }, "결과물은 대표가 승인해야 완료돼")),
    kpis,
    h("section", { class: "box" }, h("h2", {}, "결재함"), inbox),
    h("section", { class: "box" }, h("h2", {}, "조직도 · 직원별 실적"), org),
    h("section", { class: "box" }, h("h2", {}, "자동 승인 규칙"),
      h("p", { class: "muted" }, "켠 종류는 실장이 대표 대신 바로 승인해 (결재 이력엔 '자동 승인'으로 남아)"), rules),
    h("section", { class: "box" }, h("h2", {}, "결재 이력"), history));
  const drafts = new Map();
  let ceo = null;
  let fetched = 0;
  let loading = false;

  async function load() {
    if (loading) return;
    loading = true;
    try {
      ceo = await getJSON("/api/ceo");
      fetched = Date.now();
      drawCompany();
    } catch {
      // 다음 주기에 다시
    } finally {
      loading = false;
    }
  }

  function reviewCard(job) {
    const comment = h("textarea", { class: "input", rows: 2, maxlength: 500, "aria-label": `${jobTitle(job)} 결재 의견`,
      placeholder: "의견 (반려할 땐 뭘 고칠지 꼭 적어줘)", oninput: (e) => drafts.set(job.id, e.target.value) });
    comment.value = drafts.get(job.id) ?? "";
    const lastReject = [...(job.approvals ?? [])].reverse().find((a) => a.action === "reject");
    const decide = async (what) => {
      const msg = what === "approve" ? `승인했어: ${jobTitle(job)}` : "반려했어. 직원들이 다시 고칠게";
      if (await act(jobUrl(job.id, what), { comment: comment.value }, msg)) {
        drafts.delete(job.id);
        ctx.refresh();
        load();
      }
    };
    return h("article", { class: "card review-card" },
      h("header", { class: "card-head" },
        h("div", { class: "card-title" }, h("span", { class: "no" }, jobNo(job)), h("h3", {}, jobTitle(job))),
        h("span", { class: "badge review" }, job.revision ? `수정본 ${job.revision}` : "결재 대기")),
      h("p", { class: "muted" }, [job.created, outputsOf(job).join("·"), job.names?.join(", "), job.seconds ? `${job.seconds}초` : ""]
        .filter(Boolean).join(" · ")),
      job.error && h("p", { class: "err" }, job.error),
      lastReject && h("p", { class: "muted" }, `지난 반려 의견: ${lastReject.comment}`),
      job.answer && answerBox(job),
      h("div", { class: "actions" }, resultLinks(job)),
      comment,
      h("div", { class: "actions" },
        h("button", { class: "btn ok", type: "button", onclick: () => decide("approve") }, "승인"),
        h("button", { class: "btn no", type: "button", onclick: () => decide("reject") }, "반려")));
  }

  function drawCompany() {
    if (!ceo) return;
    const st = ceo.stats;
    kpis.replaceChildren(stat("오늘 처리", `${st.today_done}건`), stat("결재 대기", `${st.pending}건`),
      stat("승인율", st.approval_rate == null ? "—" : `${st.approval_rate}%`), stat("자동 승인", `${st.auto_approved}건`),
      stat("이번 주 공부", minutesText(st.study_week)), stat("누적 작업", `${st.total}건`));
    const top = Math.max(1, ...Object.values(st.staff));
    org.replaceChildren(h("p", { class: "org-ceo" }, "대표 ritual"), ...TEAMS.map((team) => h("div", { class: "org-team", style: `--team: ${team.color}` },
      h("h3", {}, team.name),
      h("ul", {}, team.roles.map((role) => h("li", {},
        h("b", {}, NAMES[role]), h("small", { class: "muted" }, DUTY[role]),
        h("span", { class: "meter", "aria-hidden": "true" }, h("i", { style: `width: ${Math.round((st.staff[role] / top) * 100)}%` })),
        h("small", {}, `${st.staff[role]}건`)))))));
    rules.replaceChildren(...Object.entries(OUTPUT_NAMES).map(([kind, label]) => h("label", { class: "switch" },
      h("input", {
        type: "checkbox", checked: ceo.auto[kind],
        onchange: async (e) => {
          const res = await act("/api/auto", { [kind]: e.target.checked }, `${label}: ${e.target.checked ? "자동 승인" : "대표 결재"}`);
          if (res) ceo.auto = res;
          else e.target.checked = !e.target.checked;
        },
      }), h("span", {}, label))));
    const ACTION = { approve: "승인", reject: "반려", auto: "자동 승인" };
    history.replaceChildren(...(ceo.history.length ? ceo.history.map((a) => h("p", { class: `hist ${a.action}` },
      h("small", { class: "muted" }, a.time), h("b", {}, ACTION[a.action] ?? a.action), h("span", {}, a.title),
      a.comment && h("small", { class: "muted" }, `“${a.comment}”`)))
      : [h("p", { class: "empty" }, "아직 결재 기록이 없어")]));
  }

  return {
    el,
    show: load,
    update(s) {
      const pending = s.jobs.filter((j) => j.status === "review");
      keyed(inbox, pending, (j) => j.id, (j) => JSON.stringify({ ...j, log: undefined }), reviewCard,
        "결재할 게 없어. 오늘도 평화로운 회사!");
      if (Date.now() - fetched > 5000) load();
    },
  };
}

// ---- 설정 ----
const SHORTCUTS = [["Alt + 1~6", "탭 바꾸기 (사무실·보관함·오늘·일정·대표실·설정)"], ["Alt + S", "나눠 보기 켜고 끄기"],
                   ["↑ / ↓", "지시 칸이 비었을 때 이전 지시 불러오기"],
                   ["Alt + G", "공부모드"], ["/", "지시 칸으로"], ["Enter", "보내기 (Shift + Enter = 줄바꿈)"], ["Esc", "창 닫기"]];

function settingsView(ctx) {
  const box = h("div", { class: "settings" });
  const el = h("div", { class: "view" }, box);
  let data = null;
  let remote = null;
  let boot = null;
  let perms = null;
  let facts = null;

  async function load() {
    try {
      [data, remote, boot, perms, { facts }] = await Promise.all([getJSON("/api/settings"), getJSON("/api/remote"),
        getJSON("/api/startup"), getJSON("/api/permissions"), getJSON("/api/memory")]);
      draw();
    } catch {
      box.replaceChildren(h("p", { class: "err" }, "설정을 못 불러왔어."));
    }
  }
  async function save(changes, msg) {
    const res = await act("/api/settings", changes, msg);
    if (res) data = res;
    draw();
    ctx.refresh();
  }
  const section = (title, ...kids) => h("section", { class: "box" }, h("h2", {}, title), ...kids);
  const toggle = (label, on, set) => h("label", { class: "switch" },
    h("input", { type: "checkbox", checked: on, onchange: (e) => set(e.target.checked) }), h("span", {}, label));

  function phoneBox(s) {
    const server = h("input", { class: "input grow", value: s.server, "aria-label": "ntfy 서버 주소" });
    const on = armed.has("topic");
    return section("폰 알림 연결 (ntfy)",
      h("ol", { class: "steps" }, h("li", {}, "폰에 ntfy 앱 설치 (Play 스토어·App Store에서 'ntfy')"),
        h("li", {}, "앱에서 + 누르고 아래 주제 이름을 그대로 붙여넣기"), h("li", {}, "[테스트 알림]으로 확인")),
      h("p", { class: "code-row" }, h("code", {}, s.topic),
        h("button", { class: "btn alt small", type: "button", onclick: (e) => copy(s.topic, e.currentTarget) }, "복사")),
      h("p", { class: "muted" }, "주제 이름이 비밀번호 역할이야. 남한테 보여주지 마."),
      h("div", { class: "actions" },
        h("button", {
          class: on ? "btn armed" : "btn alt", type: "button",
          onclick: () => arm("topic", draw) && save({ new_topic: true }, "새 주제로 바꿨어. 앱에서 다시 구독해줘"),
        }, on ? "옛 주제는 끊겨. 한 번 더 누르면 바꿔" : "주제 바꾸기")),
      h("form", { class: "row-form", onsubmit: (e) => { e.preventDefault(); save({ server: server.value }, "서버 주소 저장했어"); } },
        server, h("button", { class: "btn alt", type: "submit" }, "서버 저장")));
  }

  async function setRemote(changes, msg) {
    const res = await act("/api/remote", changes, msg);
    if (res) remote = res;
    draw();
    if (res?.starting) setTimeout(load, 4000); // 터널 주소가 나오면 다시 그린다
  }

  function remoteBox() {
    const r = remote;
    const choice = (value, label, desc) => h("label", { class: "radio" + (r.mode === value ? " on" : "") },
      h("input", { type: "radio", name: "remote", value, checked: r.mode === value,
        onchange: () => setRemote({ mode: value }, { off: "폰 연결 껐어", lan: "같은 와이파이에서 폰으로 들어올 수 있어", tunnel: "어디서나 연결 켜는 중… 주소가 나오면 폰으로도 보내줄게" }[value]) }),
      h("b", {}, label), h("small", { class: "muted" }, desc));
    const on = armed.has("token");
    return section("폰으로 일 시키기",
      h("div", { class: "radios" },
        choice("off", "끔", "기본. 이 PC에서만 써"),
        choice("lan", "같은 와이파이", "집 공유기 안에서만. 처음에 Windows 방화벽 창이 뜨면 '허용'"),
        choice("tunnel", "어디서나", "Cloudflare 임시 터널. 켤 때마다 주소가 바뀌고 폰 알림으로 보내줘")),
      r.error && h("p", { class: "err" }, r.error),
      r.starting && h("p", { class: "muted" }, "터널 여는 중… (처음엔 프로그램을 내려받느라 조금 걸려)"),
      r.link && h("div", { class: "remote-link" },
        h("img", { class: "qr", src: `/api/remote/qr?t=${Date.now()}`, alt: "폰 카메라로 찍으면 들어가는 QR", width: 180, height: 180 }),
        h("div", { class: "remote-text" },
          h("p", {}, "폰 카메라로 QR을 찍거나 링크를 열어. 한 번 들어가면 90일 동안 기억해."),
          h("p", { class: "code-row" }, h("code", {}, r.link),
            h("button", { class: "btn alt small", type: "button", onclick: (e) => copy(r.link, e.currentTarget) }, "복사")),
          h("p", { class: "muted" }, "이 링크가 열쇠야. 남한테 보내지 마. 잃어버렸으면 열쇠를 바꿔."),
          h("button", {
            class: on ? "btn armed" : "btn alt", type: "button",
            onclick: () => arm("token", draw) && setRemote({ new_token: true }, "열쇠를 바꿨어. 옛 링크는 이제 안 열려"),
          }, on ? "폰에서 다시 QR을 찍어야 해. 한 번 더 누르면 바꿔" : "열쇠 바꾸기"))));
  }

  async function setPerms(changes, msg) {
    const res = await act("/api/permissions", changes, msg);
    if (res) perms = res;
    draw();
  }

  const FOLDER_NAMES = { Desktop: "바탕화면", Documents: "문서", Downloads: "다운로드", Pictures: "사진", Music: "음악", Videos: "동영상",
                         OneDrive: "OneDrive" };
  function permsBox() {
    const extra = h("input", { class: "input grow", placeholder: "더 허용할 폴더 경로 (예: D:\\학교 자료)", "aria-label": "허용할 폴더 경로" });
    return section("실장님 권한",
      h("p", {}, "실장님은 아래 폴더 안에서만 파일을 찾고·읽고·가져오고·새로 만들어요. AppData·.ssh·시스템 폴더는 늘 막혀 있어요."),
      h("p", { class: "muted" }, "지우기·옮기기·이름 바꾸기·덮어쓰기·명령 실행은 실장님이 못 해요. 시키면 그 폴더를 열어 드려요 (대표님이 직접)."),
      toggle("파일 읽기 (찾기·폴더 보기·내용 읽기)", perms.read, (v) => setPerms({ read: v }, v ? "읽기 권한 켰어요" : "읽기 권한 껐어요")),
      toggle("파일 만들기·가져오기 (새 파일 쓰기·복사·새 폴더·사무실로 가져오기)", perms.write,
        (v) => setPerms({ write: v }, v ? "만들기 권한 켰어요" : "만들기 권한 껐어요")),
      h("div", { class: "rules" }, Object.entries(perms.folders).map(([key, path]) => h("label", { class: "switch", title: path },
        h("input", { type: "checkbox", checked: !perms.off.includes(key),
          onchange: (e) => setPerms({ off: e.target.checked ? perms.off.filter((k) => k !== key) : [...perms.off, key] }) }),
        h("span", {}, FOLDER_NAMES[key] ?? key)))),
      perms.extra.length && h("ul", { class: "list" }, perms.extra.map((path) => h("li", { class: "event" }, h("span", {}, path),
        h("button", { class: "x", type: "button", "aria-label": `${path} 빼기`,
          onclick: () => setPerms({ extra: perms.extra.filter((p) => p !== path) }, "폴더를 뺐어요") }, "✕")))),
      h("form", { class: "row-form", onsubmit: (e) => { e.preventDefault(); if (extra.value.trim()) setPerms({ extra: [...perms.extra, extra.value.trim()] }, "폴더를 허용했어요"); } },
        extra, h("button", { class: "btn alt", type: "submit" }, "폴더 추가")));
  }

  function memoryBox() {
    const input = h("input", { class: "input grow", maxlength: 300, "aria-label": "실장님이 기억할 것",
      placeholder: "실장님이 기억할 것 (예: 수학 학원은 매주 화요일 6시)" });
    return section("실장님 기억",
      h("p", { class: "muted" }, "대화하면서 실장님이 기억한 것이에요. 매번 지시할 때 참고하고, 최근 대화 6번도 함께 봐요. 말로 \"기억해\" · \"잊어\"라고 해도 돼요."),
      h("ul", { class: "list" }, facts.length ? facts.map((f) => h("li", { class: "event" }, h("small", { class: "time" }, f.created.slice(5)),
        h("span", {}, f.text), h("button", { class: "x", type: "button", "aria-label": `${f.text} 잊기`,
          onclick: () => act(`/api/memory/${f.id}/delete`, undefined, "잊었어요").then(load) }, "✕")))
        : [h("li", { class: "empty" }, "아직 기억한 게 없어요")]),
      h("form", { class: "row-form", onsubmit: async (e) => {
        e.preventDefault();
        if (input.value.trim() && await act("/api/memory", { text: input.value }, "기억했어요")) load();
      } }, input, h("button", { class: "btn alt", type: "submit" }, "기억하기")));
  }

  function resetBox() {
    const RESETS = [["staff", "직원 자리 정리", "말풍선·에러 불을 끄고 다 쉬는 중으로"], ["queue", "대기열 비우기", "대기 중인 작업을 전부 취소"],
                    ["stop", "모두 중단", "대기·진행 중인 작업을 전부 멈춤"], ["vault", "보관함 정리", "완료·에러·취소 작업을 지움 (★와 결재 대기는 남음)"],
                    ["todos", "완료한 할 일 지우기", "체크한 할 일만"], ["settings", "설정 기본값", "알림·AI 모드를 처음대로 (폰 주제는 그대로)"]];
    const button = ([what, label, desc]) => {
      const on = armed.has("reset:" + what);
      return h("div", { class: "reset-row" }, h("button", { class: on ? "btn armed" : "btn alt", type: "button",
        onclick: () => arm("reset:" + what, draw) && act("/api/reset", { what }).then((res) => {
          if (res) toast(`${label}: ${res.count}개`, "ok");
          ctx.refresh();
          load();
        }) }, on ? `${label}? 한 번 더` : label), h("small", { class: "muted" }, desc));
    };
    const layout = armed.has("reset:layout");
    return section("초기화", ...RESETS.map(button),
      h("div", { class: "reset-row" }, h("button", { class: layout ? "btn armed" : "btn alt", type: "button",
        onclick: () => {
          if (!arm("reset:layout", draw)) return;
          for (const key of ["ritual-layout", "ritual-welcomed", "ritual-history", "ritual-vault-mode"]) store.set(key, null);
          location.reload();
        } }, layout ? "화면 배치·안내 초기화? 한 번 더" : "화면 배치·안내 초기화"), h("small", { class: "muted" }, "탭 배치, 처음 안내, 지시 기록")));
  }

  function draw() {
    if (!data) return;
    const s = data.settings;
    const st = ctx.state();
    const briefing = h("input", { class: "input", type: "time", value: s.briefing, "aria-label": "아침 브리핑 시각",
      onchange: (e) => save({ briefing: e.target.value }, e.target.value ? `아침 브리핑 ${e.target.value}` : "아침 브리핑 껐어") });
    const mode = (value, label, desc) => h("label", { class: "radio" + (s.ai === value ? " on" : "") },
      h("input", { type: "radio", name: "ai", value, checked: s.ai === value,
        onchange: () => save({ ai: value }, value === "fast" ? "빠름 모드: 4B 모델" : "꼼꼼 모드: 9.7B 모델 (처음 한 번 올리는 데 몇 초 걸려)") }),
      h("b", {}, label), h("small", { class: "muted" }, desc));
    put(box,
      section("AI 모드", h("div", { class: "radios" },
        mode("fast", "빠름", "qwen3.5 4B · 노트 10초 · 기본"), mode("careful", "꼼꼼", "qwen3.5 9.7B · 노트 16초 · 어려운 자료")),
        h("p", { class: "muted" }, `지금 모델: ${st?.model ?? "?"} · Ollama ${st?.ollama ? "켜짐" : "꺼짐"}`)),
      section("알림",
        toggle("PC 알림 (Windows 알림 센터)", s.pc, (v) => save({ pc: v }, v ? "PC 알림 켰어" : "PC 알림 껐어")),
        toggle("폰 알림 (ntfy 앱)", s.phone, (v) => save({ phone: v }, v ? "폰 알림 켰어. 아래 주제를 ntfy 앱에서 구독해줘" : "폰 알림 껐어")),
        toggle("결과물 다 되면 알려주기 (결재 요청은 늘 보내)", s.job_done, (v) => save({ job_done: v })),
        boot && toggle("윈도우 켤 때 사무실도 켜기 (창 없이 · 알림·폰 연결을 받으려면 켜 둬)", boot.on, async (v) => {
          const res = await act("/api/startup", { on: v }, v ? "윈도우 켤 때 자동으로 켜질 거야" : "자동 시작 껐어");
          if (res) boot = res;
          draw();
        }),
        h("label", { class: "row" }, h("span", {}, "아침 브리핑"), briefing,
          h("button", { class: "btn alt small", type: "button", onclick: () => save({ briefing: "" }, "아침 브리핑 껐어") }, "끄기")),
        h("div", { class: "actions" }, h("button", {
          class: "btn", type: "button",
          onclick: async () => {
            const res = await act("/api/settings/test");
            if (res) toast(res.errors.length ? res.errors.join(" / ") : "테스트 알림 보냈어. PC·폰을 확인해봐", res.errors.length ? "err" : "ok");
            load();
          },
        }, "테스트 알림"))),
      s.phone && phoneBox(s),
      remote && remoteBox(),
      facts && memoryBox(),
      perms && permsBox(),
      section("최근 알림", h("ul", { class: "list" }, data.history.length ? data.history.map((n) => h("li", {},
        h("small", { class: "muted" }, n.time), " ", h("b", {}, n.title), " ", n.body,
        n.errors.length ? h("small", { class: "err" }, ` (${n.errors.join(", ")})`) : null)) : [h("li", { class: "empty" }, "아직 보낸 알림이 없어")])),
      section("데이터", h("p", {}, "작업·일정·설정을 zip 하나로 받아. 되돌릴 땐 output 폴더에 풀면 돼."),
        h("a", { class: "btn", href: "/api/backup", download: "" }, "백업 받기")),
      resetBox(),
      section("단축키", h("dl", { class: "keys" }, SHORTCUTS.flatMap(([k, v]) => [h("dt", {}, h("kbd", {}, k)), h("dd", {}, v)]))),
      section("정보", h("p", {}, `ritual's rab v${st?.version ?? ""}`),
        h("p", { class: "muted" }, "AI는 전부 이 PC 안(Ollama)에서 돌아. 인터넷은 위키 자료·폰 알림·배포 때만 써.")));
  }
  return { el, show: load, update() {} };
}

export function createViews(ctx) {
  return { office: officeView(ctx), vault: vaultView(ctx), today: todayView(ctx), schedule: scheduleView(ctx),
           ceo: ceoView(ctx), settings: settingsView(ctx) };
}
