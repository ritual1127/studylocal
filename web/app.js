import { $, NAMES, act, ddayText, h, minutesText, put, store, toast } from "./ui.js";
import { animateOffice, createViews, jobTitle, teamPanel } from "./views.js";

const TABS = [["office", "사무실"], ["vault", "보관함"], ["today", "오늘"], ["schedule", "일정"], ["ceo", "대표실"], ["settings", "설정"]];
const MAX_UPLOAD = 50_000_000;

let state = null;
let ref = null; // [이 자료로 더 하기]로 고른 작업
let teamRole = null; // 팝업으로 보고 있는 팀
const refreshHooks = [];
const ctx = {
  state: () => state, rerender, openTab, setRef, editAgain, openTeam, mention,
  refresh: () => { refreshHooks.forEach((fn) => fn()); return poll(false); },
  onRefresh: (fn) => refreshHooks.push(fn),
};
const views = createViews(ctx);

// ---- 탭과 나눠 보기 ----
const wide = matchMedia("(min-width: 1000px)");
const panes = [...document.querySelectorAll(".pane")];
let layout = store.get("ritual-layout", null);
if (!layout || !Array.isArray(layout.tabs) || layout.tabs.some((t) => !views[t])) {
  layout = { split: innerWidth >= 1200, tabs: ["office", "vault"], active: 0 };
}
const isSplit = () => layout.split && wide.matches;
const visibleTabs = () => (isSplit() ? layout.tabs : layout.tabs.slice(0, 1));

function renderLayout() {
  const split = isSplit();
  if (split && layout.tabs[0] === layout.tabs[1]) layout.tabs[1] = TABS.find(([id]) => id !== layout.tabs[0])[0];
  document.body.classList.toggle("split", split);
  panes[1].hidden = !split;
  $("#split").setAttribute("aria-pressed", String(layout.split));
  $("#split").hidden = !wide.matches;
  panes.forEach((pane, i) => {
    if (i === 1 && !split) return;
    const current = layout.tabs[i];
    pane.classList.toggle("active", split && layout.active === i);
    pane.querySelector(".tabs").replaceChildren(...TABS.map(([id, label], n) => h("button", {
      type: "button", role: "tab", class: "tab" + (id === current ? " on" : ""), "aria-selected": String(id === current),
      title: `Alt + ${n + 1}`, onclick: () => openTab(id, i),
    }, label, id === "ceo" ? h("span", { class: "tab-badge", hidden: true }) : null)));
    const body = pane.querySelector(".pane-body");
    if (body.firstChild !== views[current].el) {
      body.replaceChildren(views[current].el);
      views[current].show?.();
    }
  });
  store.set("ritual-layout", layout);
  if (state) render(state);
}

function openTab(id, i = layout.active) {
  if (!isSplit()) i = 0;
  const other = 1 - i;
  if (isSplit() && layout.tabs[other] === id) layout.tabs[other] = layout.tabs[i]; // 옆 창에 있던 탭이면 서로 바꾼다
  layout.tabs[i] = id;
  layout.active = i;
  renderLayout();
}

panes.forEach((pane, i) => pane.addEventListener("pointerdown", () => {
  if (isSplit() && layout.active !== i) {
    layout.active = i;
    panes.forEach((p, n) => p.classList.toggle("active", n === i));
    store.set("ritual-layout", layout);
  }
}));
$("#split").addEventListener("click", () => {
  layout.split = !layout.split;
  renderLayout();
  toast(layout.split ? "화면을 둘로 나눴어. 창마다 탭을 골라봐" : "한 화면으로 합쳤어");
});
wide.addEventListener("change", renderLayout);

// ---- 그리기 ----
function render(s) {
  const status = $("#status");
  status.className = `status ${s.ollama ? "on" : "off"}`;
  status.textContent = s.ollama ? "AI 연결됨" : "Ollama 꺼짐";
  $("#model").textContent = `${s.ai === "careful" ? "꼼꼼" : "빠름"} · ${s.model}`;
  const p = s.planner;
  $("#dday").hidden = !p.dday;
  if (p.dday) $("#dday").textContent = `${p.dday.title} ${ddayText(p.dday.days)}`;
  $("#studied").textContent = `오늘 공부 ${minutesText(p.stats.today)}`;
  const pending = s.jobs.filter((j) => j.status === "review").length;
  for (const badge of document.querySelectorAll(".tab-badge")) {
    badge.hidden = !pending;
    badge.textContent = pending;
  }
  for (const tab of visibleTabs()) views[tab].update(s);
  if (teamRole && !$("#team").hidden) put($("#teamBody"), teamPanel(teamRole, ctx));
  tickFocus();
}

// ---- 4인 1조 팀 팝업 ----
function openTeam(role) {
  teamRole = role;
  put($("#teamBody"), teamPanel(role, ctx));
  openOverlay($("#team"));
}

function mention(role) {
  closeOverlays();
  const box = $("#text");
  const rest = box.value.replace(/^\s*@\S+\s*/, "");
  box.value = role === "manager" ? rest : `@${NAMES[role]} ${rest}`;
  box.focus();
  box.setSelectionRange(box.value.length, box.value.length);
  toast(role === "manager" ? "rab에게 시킬 일을 적어 주세요" : `${NAMES[role]} 팀에 시킬 일을 적어 주세요`);
}

function editAgain(job) {
  const box = $("#text");
  box.value = job.text;
  if (job.results?.text) ref = { id: job.id, title: jobTitle(job) };
  renderChips();
  box.focus();
  toast("지시를 고쳐서 다시 보내세요" + (ref ? " (그 자료를 쓸게요)" : ""));
}

function rerender() {
  if (state) for (const tab of visibleTabs()) views[tab].update(state);
}

setInterval(() => {
  if (visibleTabs().includes("office")) animateOffice(views.office);
}, 100);

// ---- 폴링 ----
let quitting = false;
let busy = false;
async function poll(loop = true) {
  let s = null;
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (r.ok) s = await r.json();
  } catch {
    s = null;
  }
  $("#downMsg").textContent = quitting ? "퇴근 완료! 이 창은 닫아도 돼" : "사무실 서버가 꺼졌어";
  $("#down").hidden = Boolean(s);
  if (s) {
    state = s;
    busy = s.jobs.some((j) => ["queued", "running", "revising"].includes(j.status));
    render(s);
  }
  if (loop) setTimeout(poll, 1000);
}

// ---- 공부모드 ----
const focusBox = $("#focus");
function openOverlay(el) {
  el.hidden = false;
  el.querySelector("[data-first]")?.focus();
}
function closeOverlays() {
  for (const el of document.querySelectorAll(".overlay")) el.hidden = true;
}
for (const btn of document.querySelectorAll("[data-close]")) btn.addEventListener("click", closeOverlays);

function openFocus() {
  const todos = state?.planner.todos.filter((t) => !t.done) ?? [];
  $("#focusPick").replaceChildren(h("option", { value: "" }, "할 일 안 고름"), ...todos.map((t) => h("option", { value: t.text }, t.text)));
  openOverlay(focusBox);
}
async function startFocus(minutes, kind) {
  const task = kind === "focus" ? $("#focusPick").value : "";
  const res = await act("/api/focus", { minutes, task, kind }, kind === "focus" ? `${minutes}분 집중 시작! 화이팅` : `${minutes}분 쉬자`);
  if (res) poll(false);
}
for (const btn of document.querySelectorAll("[data-focus]")) {
  btn.addEventListener("click", () => startFocus(Number(btn.dataset.focus), btn.dataset.kind ?? "focus"));
}
$("#focusStop").addEventListener("click", async () => {
  const res = await act("/api/focus/stop");
  if (res) {
    toast(res.minutes ? `${res.minutes}분 공부했어. 수고했어!` : "공부모드 껐어", "ok");
    poll(false);
  }
});
$("#focusBtn").addEventListener("click", openFocus);
$("#focusChip").addEventListener("click", openFocus);

function tickFocus() {
  const f = state?.planner.focus;
  const chip = $("#focusChip");
  $("#focusRun").hidden = !f;
  $("#focusSetup").hidden = Boolean(f);
  if (!f) {
    chip.hidden = true;
    $("#focusClock").textContent = "25:00";
    $("#focusTask").textContent = "할 일을 고르고 시작해. 창을 닫아도 시간은 계속 가";
    return;
  }
  const left = Math.max(0, Math.round((new Date(f.end) - Date.now()) / 1000));
  const clock = `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
  chip.hidden = false;
  chip.textContent = `${f.kind === "focus" ? "집중" : "쉬는 중"} ${clock}`;
  $("#focusClock").textContent = clock;
  $("#focusTask").textContent = f.kind === "focus" ? (f.task || "집중!") : "쉬는 시간. 물 한 잔 마셔";
}
setInterval(tickFocus, 250);

// ---- 처음 온 사람 안내 ----
if (!store.get("ritual-welcomed", false)) openOverlay($("#welcome"));
$("#welcomeGo").addEventListener("click", () => {
  store.set("ritual-welcomed", true);
  closeOverlays();
  $("#text").focus();
});

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

// ---- 지시 칸 ----
const files = [];
const showError = (msg) => ($("#barError").textContent = msg);

function setRef(job) {
  ref = { id: job.id, title: jobTitle(job) };
  renderChips();
  $("#text").focus();
  toast(`'${ref.title}' 자료로 뭘 할지 적어 주세요 (예: 문제 10개, 암기카드, 번역)`);
}

function addFiles(list) {
  const big = [];
  for (const f of list) {
    if (f.size > MAX_UPLOAD) big.push(f.name);
    else files.push(f);
  }
  showError(big.length ? `50MB 넘는 파일은 못 올려: ${big.join(", ")}` : "");
  renderChips();
}

function renderChips() {
  put($("#chips"),
    ref && h("span", { class: "chip ref" }, h("span", { title: ref.title }, `자료: ${ref.title}`),
      h("button", { type: "button", "aria-label": "고른 자료 빼기", onclick: () => { ref = null; renderChips(); } }, "✕")),
    ...files.map((f, i) => h("span", { class: "chip" },
      h("span", { title: f.name }, f.name),
      h("button", { type: "button", "aria-label": `${f.name} 빼기`, onclick: () => { files.splice(i, 1); renderChips(); } }, "✕"))));
}

$("#attach").addEventListener("click", () => $("#pick").click());
$("#pick").addEventListener("change", (e) => {
  addFiles(e.target.files);
  e.target.value = "";
});

// ---- 빠른 지시 · 지시 기록 ----
const QUICK = [["PDF로", "PDF 노트로 만들어줘"], ["문제 10개", "문제 10개 만들어줘"], ["암기카드", "암기카드 만들어줘"],
               ["마인드맵", "마인드맵 그려줘"], ["분석", "분석해줘"], ["번역", "영어로 번역해줘"],
               ["파일 찾기", "바탕화면에서 ○○ 찾아서 가져와"], ["오늘 뭐 해?", "오늘 뭐 해야 돼?"], ["폰으로 보내기", "내 폰으로 ○○라고 보내"],
               ["나중에 알려줘", "30분 뒤에 ○○ 알려줘"]];
$("#quick").replaceChildren(...QUICK.map(([label, phrase]) => h("button", { class: "chip-btn", type: "button", onclick: () => {
  const box = $("#text");
  box.value = (box.value.trim() ? box.value.trim() + " " : "") + phrase;
  box.focus();
  const at = box.value.lastIndexOf("○○");
  if (at >= 0) box.setSelectionRange(at, at + 2); // ○○ 자리를 바로 고쳐 쓰게
} }, label)));

let recall = -1;
const pastCommands = () => store.get("ritual-history", []) ?? [];
function remember(text) {
  if (!text.trim()) return;
  store.set("ritual-history", [text, ...pastCommands().filter((t) => t !== text)].slice(0, 50));
  recall = -1;
}

$("#text").addEventListener("keydown", (e) => {
  // 한글 조합 중 Enter는 글자 확정이라 보내지 않는다
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
    e.preventDefault();
    $("#bar").requestSubmit();
    return;
  }
  const box = e.currentTarget;
  const past = pastCommands();
  if ((e.key === "ArrowUp" && (box.value === "" || recall >= 0) && recall < past.length - 1)
      || (e.key === "ArrowDown" && recall >= 0)) {
    e.preventDefault();
    recall += e.key === "ArrowUp" ? 1 : -1;
    box.value = recall >= 0 ? past[recall] : "";
  }
});

$("#bar").addEventListener("submit", async (e) => {
  e.preventDefault();
  const send = $("#send");
  if (send.disabled) return;
  const form = new FormData();
  form.append("text", $("#text").value);
  if (ref) form.append("ref", ref.id);
  for (const f of files) form.append("files", f);
  send.disabled = true;
  try {
    const res = await fetch("/api/command", { method: "POST", body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `오류가 났어 (${res.status})`);
    remember($("#text").value);
    $("#text").value = "";
    files.length = 0;
    ref = null;
    renderChips();
    showError("");
    toast("rab에게 맡겼어요!", "ok");
    poll(false);
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

// ---- 단축키 ----
addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName ?? "");
  if (e.key === "Escape") {
    closeOverlays();
    return;
  }
  if (e.altKey && !e.ctrlKey && /^[1-6]$/.test(e.key)) {
    e.preventDefault();
    openTab(TABS[Number(e.key) - 1][0]);
  } else if (e.altKey && e.code === "KeyS") {
    e.preventDefault();
    $("#split").click();
  } else if (e.altKey && e.code === "KeyG") {
    e.preventDefault();
    openFocus();
  } else if (e.key === "/" && !typing) {
    e.preventDefault();
    $("#text").focus();
  }
});

renderLayout();
poll();
