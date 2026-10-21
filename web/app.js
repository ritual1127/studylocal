import { SPRITES } from "./sprites.js";

const STAFF = ["manager", "scanner", "librarian", "designer", "examiner", "deployer"];
const NAMES = { manager: "실장", scanner: "스캐너", librarian: "사서", designer: "디자이너", examiner: "출제위원", deployer: "배포담당" };
const LIGHT = { idle: "쉬는 중", working: "일하는 중", done: "끝", error: "에러" };
const BADGE = { queued: "대기", running: "진행 중", done: "완료", error: "에러", needs_input: "되물음" };
const ACCEPT = [".jpg", ".jpeg", ".png", ".webp", ".pdf"];
const STILL = matchMedia("(prefers-reduced-motion: reduce)").matches;

const $ = (sel) => document.querySelector(sel);
const colorOf = (role) => `var(--c${STAFF.indexOf(role) + 1})`;
const isFile = (url) => typeof url === "string" && url.startsWith("/files/");

// 작은 DOM 도우미: 글자는 전부 텍스트 노드로 넣는다 (innerHTML 안 씀)
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value);
  }
  el.append(...kids.flat().filter(Boolean));
  return el;
}

async function post(url, body) {
  const r = await fetch(url, { method: "POST", body });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `오류가 났어 (${r.status})`);
  return data;
}

// ---- 책상과 캐릭터 ----
const desks = {};
for (const role of STAFF) {
  const say = h("p", { class: "say" });
  const bubble = h("div", { class: "bubble empty" }, say);
  const canvas = h("canvas", { class: "sprite", width: 16, height: 16, "aria-hidden": "true" });
  const light = h("i", { class: "light idle", role: "img", "aria-label": LIGHT.idle });
  $("#office").append(h("div", { class: "desk", style: `--who: ${colorOf(role)}` },
    bubble, canvas, h("div", { class: "table" }), h("p", { class: "plate" }, light, NAMES[role])));
  desks[role] = { say, bubble, light, ctx: canvas.getContext("2d"), state: "idle", drawn: "" };
}

function draw(desk, sprite, frame, dy) {
  const key = `${frame}:${dy}`;
  if (desk.drawn === key) return;
  desk.drawn = key;
  desk.ctx.clearRect(0, 0, 16, 16);
  sprite.frames[frame].forEach((row, y) => {
    [...row].forEach((ch, x) => {
      if (ch === ".") return;
      desk.ctx.fillStyle = sprite.colors[ch];
      desk.ctx.fillRect(x, y < 14 ? y + dy : y, 1, 1); // 키보드(14~15줄)는 안 움직임
    });
  });
}

function animate() {
  const t = STILL ? 0 : performance.now();
  for (const role of STAFF) {
    const desk = desks[role];
    const frame = desk.state === "working" ? Math.floor(t / 300) % 2 : 0;
    const dy = desk.state === "idle" ? -(Math.floor(t / 1000) % 2) : 0;
    draw(desk, SPRITES[role], frame, dy);
  }
}
setInterval(animate, 100);
animate();

// ---- 상태 그리기 ----
let jobs = [];
let busy = false;
let cards = new Map(); // job id → { key, el }
const armed = new Map(); // 배포 버튼을 한 번 누른 작업 → 해제 타이머
const notes = new Map(); // job id → { msg, err, sig }
const sig = (r) => `${r.deploy_url}|${r.deploy_error}`;

function render(s) {
  const status = $("#status");
  status.className = `status ${s.ollama ? "on" : "off"}`;
  status.textContent = s.ollama ? "AI 연결됨" : "Ollama 꺼짐";
  $("#model").textContent = s.model;

  for (const role of STAFF) {
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

  jobs = s.jobs;
  busy = jobs.some((j) => j.status === "queued" || j.status === "running")
    || Object.values(s.staff).some((st) => st.state === "working");
  renderJobs();
  renderLog(jobs[0]?.log ?? []);
}

function card(job) {
  const r = job.results ?? {};
  const note = notes.get(job.id);
  const actions = [];
  if (isFile(r.pdf)) actions.push(h("a", { class: "btn", href: r.pdf, target: "_blank", rel: "noopener" }, "PDF 열기"));
  if (isFile(r.quiz)) actions.push(h("a", { class: "btn", href: r.quiz, target: "_blank", rel: "noopener" }, "문제 미리보기"));
  if (isFile(r.text)) actions.push(h("a", { class: "btn alt", href: r.text, target: "_blank", rel: "noopener" }, "텍스트"));
  if (Object.keys(r).length) actions.push(h("button", { class: "btn alt", type: "button", onclick: () => act(job.id, "open") }, "폴더"));
  if (isFile(r.quiz)) {
    const on = armed.has(job.id);
    actions.push(h("button", { class: on ? "btn armed" : "btn", type: "button", onclick: () => deploy(job.id) },
      on ? "공개 링크로 올릴까? 한 번 더 누르면 배포" : "배포"));
  }
  const url = typeof r.deploy_url === "string" && r.deploy_url.startsWith("https://") ? r.deploy_url : null;
  return h("article", { class: "card" },
    h("header", { class: "card-head" },
      h("h3", {}, job.title || job.text.slice(0, 30) || "첨부 파일 작업"),
      h("span", { class: `badge ${job.status}` }, BADGE[job.status] ?? job.status)),
    h("p", { class: "muted" }, job.created),
    job.reply && h("p", { class: "reply" }, h("b", { style: `color: ${colorOf("manager")}` }, "실장 "), job.reply),
    job.warnings?.length && h("ul", { class: "warn" }, job.warnings.map((w) => h("li", {}, w))),
    job.error && h("p", { class: "err" }, job.error),
    actions.length && h("div", { class: "actions" }, actions),
    url && h("p", { class: "deployed" },
      h("a", { href: url, target: "_blank", rel: "noopener" }, url),
      h("button", { class: "btn alt", type: "button", onclick: (e) => copy(url, e.currentTarget) }, "복사")),
    r.deploy_error && h("p", { class: "err" }, r.deploy_error),
    note && note.sig === sig(r) && h("p", { class: note.err ? "err" : "muted" }, note.msg));
}

function renderJobs() {
  const list = $("#jobs");
  if (!jobs.length) {
    cards = new Map();
    list.replaceChildren(h("p", { class: "muted" }, "아직 결과가 없어. 아래에 명령을 적어줘!"));
    return;
  }
  const sameOrder = jobs.length === list.children.length
    && jobs.every((j, i) => cards.get(j.id)?.el === list.children[i]);
  const next = new Map();
  for (const job of jobs) {
    // 일지(log)는 카드에 안 보이니 비교에서 뺀다 → 진행 중에도 카드 버튼이 그대로 남음
    const key = JSON.stringify({ ...job, log: undefined }) + armed.has(job.id) + JSON.stringify(notes.get(job.id) ?? null);
    const old = cards.get(job.id);
    if (old && old.key === key) {
      next.set(job.id, old);
      continue;
    }
    const el = card(job);
    if (sameOrder) old.el.replaceWith(el);
    next.set(job.id, { key, el });
  }
  cards = next;
  if (!sameOrder) list.replaceChildren(...jobs.map((j) => next.get(j.id).el));
}

let logKey = null;
function renderLog(lines) {
  const key = lines.join("\n");
  if (key === logKey) return;
  logKey = key;
  const ol = $("#log");
  if (!lines.length) {
    ol.replaceChildren(h("li", { class: "muted" }, "아직 기록이 없어"));
    return;
  }
  ol.replaceChildren(...lines.map((line) => {
    const m = /^\[(.+?)\] ([\s\S]*)$/.exec(line);
    const role = m && STAFF.find((r) => NAMES[r] === m[1]);
    if (!role) return h("li", {}, line);
    return h("li", {}, h("b", { style: `color: ${colorOf(role)}` }, `[${m[1]}]`), " ", m[2]);
  }));
  ol.scrollTop = ol.scrollHeight;
}

// ---- 카드 버튼 ----
async function act(id, what, okMsg) {
  const r = jobs.find((j) => j.id === id)?.results ?? {};
  try {
    await post(`/api/jobs/${encodeURIComponent(id)}/${what}`);
    if (okMsg) notes.set(id, { msg: okMsg, err: false, sig: sig(r) });
    else notes.delete(id);
  } catch (e) {
    notes.set(id, { msg: e.message, err: true, sig: sig(r) });
  }
  renderJobs();
}

function deploy(id) {
  clearTimeout(armed.get(id));
  if (!armed.has(id)) {
    armed.set(id, setTimeout(() => { armed.delete(id); renderJobs(); }, 5000));
    renderJobs();
    return;
  }
  armed.delete(id);
  act(id, "deploy", "배포담당한테 넘겼어. 잠깐만!");
}

async function copy(url, btn) {
  try {
    await navigator.clipboard.writeText(url);
    btn.textContent = "복사됨!";
  } catch {
    btn.textContent = "복사 실패";
  }
  setTimeout(() => (btn.textContent = "복사"), 1500);
}

// ---- 폴링 ----
let quitting = false;
async function poll() {
  let s = null;
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (r.ok) s = await r.json();
  } catch {
    s = null;
  }
  $("#downMsg").textContent = quitting ? "퇴근 완료! 이 창은 닫아도 돼" : "사무실 서버가 꺼졌어";
  $("#down").hidden = Boolean(s);
  if (s) render(s);
  setTimeout(poll, 1000);
}
poll();

// ---- 퇴근 ----
let quitTimer = null;
$("#quit").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  if (busy && !quitTimer) {
    btn.textContent = "일하는 중이야! 한 번 더 누르면 퇴근";
    quitTimer = setTimeout(() => { quitTimer = null; btn.textContent = "퇴근"; }, 4000);
    return;
  }
  clearTimeout(quitTimer);
  quitting = true;
  btn.disabled = true;
  await fetch("/api/shutdown", { method: "POST" }).catch(() => {});
});

// ---- 명령 바 ----
const files = [];
const showError = (msg) => ($("#barError").textContent = msg);

function addFiles(list) {
  const rejected = [];
  for (const f of list) {
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (ACCEPT.includes(ext)) files.push(f);
    else rejected.push(f.name);
  }
  showError(rejected.length ? `사진(jpg·png·webp)이나 PDF만 받을 수 있어: ${rejected.join(", ")}` : "");
  renderChips();
}

function renderChips() {
  $("#chips").replaceChildren(...files.map((f, i) => h("span", { class: "chip" },
    h("span", { title: f.name }, f.name),
    h("button", { type: "button", "aria-label": `${f.name} 빼기`, onclick: () => { files.splice(i, 1); renderChips(); } }, "✕"))));
}

$("#attach").addEventListener("click", () => $("#pick").click());
$("#pick").addEventListener("change", (e) => {
  addFiles(e.target.files);
  e.target.value = "";
});

$("#text").addEventListener("keydown", (e) => {
  // 한글 조합 중 Enter는 글자 확정이라 보내지 않는다
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault();
    $("#bar").requestSubmit();
  }
});

$("#bar").addEventListener("submit", async (e) => {
  e.preventDefault();
  const send = $("#send");
  if (send.disabled) return;
  const form = new FormData();
  form.append("text", $("#text").value);
  for (const f of files) form.append("files", f);
  send.disabled = true;
  try {
    await post("/api/command", form);
    $("#text").value = "";
    files.length = 0;
    renderChips();
    showError("");
  } catch (err) {
    showError(err instanceof TypeError ? "사무실 서버에 못 보냈어." : err.message);
  } finally {
    send.disabled = false;
  }
});

// 창 어디에 끌어다 놓아도 첨부
const hasFiles = (e) => e.dataTransfer?.types?.includes("Files");
let dragDepth = 0;
addEventListener("dragenter", (e) => {
  if (!hasFiles(e)) return;
  dragDepth += 1;
  $("#drop").hidden = false;
});
addEventListener("dragleave", (e) => {
  if (!hasFiles(e)) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) $("#drop").hidden = true;
});
addEventListener("dragover", (e) => {
  if (hasFiles(e)) e.preventDefault();
});
addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  $("#drop").hidden = true;
  addFiles(e.dataTransfer.files);
});
