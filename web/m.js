// 폰 화면: 일 시키기 · 진행 보기 · 결과 받기 · 결재 · 오늘 할 일
import { $, h, keyed, put, rich, toast } from "./ui.js";

const BADGE = { queued: "접수", running: "진행 중", review: "결재 대기", revising: "수정 중", done: "완료", error: "에러",
                needs_input: "되물음" };
const LINKS = [["analysis", "분석"], ["pdf", "PDF"], ["quiz", "문제"], ["cards", "암기카드"], ["mindmap", "마인드맵"],
               ["translation", "번역"], ["answer", "답변 파일"], ["csv", "CSV"], ["text", "원문"]];
let state = null;
let ref = null;
let tab = "jobs";
const files = [];
const drafts = new Map();

async function post(url, body) {
  const opts = { method: "POST", headers: { "X-Ritual": "1" } };
  if (body instanceof FormData) opts.body = body;
  else {
    opts.body = JSON.stringify(body ?? {});
    opts.headers["Content-Type"] = "application/json";
  }
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || (r.status === 401 ? "연결이 끊겼어. PC의 QR로 다시 들어와줘." : `오류 (${r.status})`));
  return data;
}

async function act(url, body, okMsg) {
  try {
    const data = await post(url, body);
    if (okMsg) toast(okMsg, "ok");
    poll(false);
    return data;
  } catch (e) {
    toast(e instanceof TypeError ? "PC 사무실에 못 보냈어. PC가 켜져 있는지 봐줘." : e.message, "err");
    return null;
  }
}

const title = (j) => j.title || j.text.slice(0, 30) || "첨부 파일 작업";
const no = (j) => (j.no ? `No.${String(j.no).padStart(4, "0")}` : "");
const links = (j) => LINKS.filter(([k]) => j.results[k]).map(([k, label]) =>
  h("a", { class: "btn" + (k === "text" || k === "csv" ? " alt" : ""), href: j.results[k], target: "_blank", rel: "noopener" }, label));

function card(j) {
  const actions = links(j);
  for (const f of j.results.files ?? []) actions.push(h("a", { class: "btn alt", href: f.url, download: f.name }, f.name));
  if (["queued", "running", "revising"].includes(j.status)) {
    actions.push(h("button", { class: "btn no", type: "button", onclick: () => act(`/api/m/jobs/${encodeURIComponent(j.id)}/cancel`, {}, "멈출게요") }, "중단"));
  }
  if (Object.keys(j.results).length) actions.push(h("a", { class: "btn alt", href: `/api/m/jobs/${encodeURIComponent(j.id)}/zip`, download: "" }, "zip"));
  if (j.results.text) {
    actions.push(h("button", { class: "btn alt", type: "button", onclick: () => { ref = j; chips(); $("#text").focus(); } }, "이 자료로 더"));
  }
  return h("article", { class: `card ${j.status}` },
    h("header", {}, h("span", { class: "no" }, no(j)), h("b", {}, title(j)), h("span", { class: `badge ${j.status}` }, BADGE[j.status] ?? j.status)),
    h("p", { class: "muted" }, [j.created, j.seconds ? `${j.seconds}초` : "", (j.names ?? []).join(", ")].filter(Boolean).join(" · ")),
    j.reply && h("p", {}, h("b", { class: "boss" }, "실장님 "), j.reply),
    j.error && h("p", { class: "err" }, j.error),
    j.answer && h("details", { class: "answer", open: j.answer.length < 300 }, h("summary", {}, "선생님 답변"), h("p", {}, rich(j.answer))),
    j.status === "done" && j.last && h("p", { class: "stamp" }, j.last.action === "auto" ? "자동 승인" : "대표 승인"),
    actions.length && h("div", { class: "actions" }, actions),
    j.results.deploy_url && h("p", {}, h("a", { href: j.results.deploy_url, target: "_blank", rel: "noopener" }, j.results.deploy_url)));
}

function reviewCard(j) {
  const comment = h("textarea", { rows: 2, maxlength: 500, "aria-label": "결재 의견", placeholder: "의견 (반려면 뭘 고칠지)",
    oninput: (e) => drafts.set(j.id, e.target.value) });
  comment.value = drafts.get(j.id) ?? "";
  const decide = async (what) => {
    if (await act(`/api/m/jobs/${encodeURIComponent(j.id)}/${what}`, { comment: comment.value }, what === "approve" ? "승인했어" : "반려했어. 다시 고칠게")) {
      drafts.delete(j.id);
    }
  };
  return h("article", { class: "card review" },
    h("header", {}, h("span", { class: "no" }, no(j)), h("b", {}, title(j)), h("span", { class: "badge review" }, j.revision ? `수정본 ${j.revision}` : "결재 대기")),
    j.error && h("p", { class: "err" }, j.error),
    j.answer && h("details", { class: "answer" }, h("summary", {}, "선생님 답변"), h("p", {}, rich(j.answer))),
    h("div", { class: "actions" }, links(j)),
    comment,
    h("div", { class: "actions" },
      h("button", { class: "btn ok", type: "button", onclick: () => decide("approve") }, "승인"),
      h("button", { class: "btn no", type: "button", onclick: () => decide("reject") }, "반려")));
}

function today(p) {
  const todo = (t) => h("li", { class: t.done ? "done" : "" }, h("label", {},
    h("input", { type: "checkbox", checked: t.done, onchange: (e) => act(`/api/m/todos/${t.id}`, { done: e.target.checked }, e.target.checked ? "잘했어!" : null) }),
    h("span", {}, t.text), t.time && h("small", {}, t.time)));
  const f = p.focus;
  put($("#today"),
    h("h2", {}, `${+p.today.slice(5, 7)}월 ${+p.today.slice(8)}일 (${p.weekday})`),
    p.dday && h("p", { class: "dday" }, `${p.dday.title} ${p.dday.days === 0 ? "D-DAY" : `D-${p.dday.days}`}`),
    h("p", {}, `오늘 공부 ${p.stats.today}분 · 연속 ${p.stats.streak}일`),
    f && h("p", { class: "focus" }, `${f.kind === "focus" ? "집중" : "쉬는 중"} · ${Math.ceil(f.remaining / 60)}분 남음 ${f.task ? "· " + f.task : ""}`),
    h("h3", {}, "일정"),
    h("ul", {}, p.today_events.length ? p.today_events.map((e) => h("li", {}, h("small", {}, e.time || "종일"), " ", e.title)) : [h("li", { class: "muted" }, "오늘은 일정이 없어")]),
    h("h3", {}, "할 일"),
    h("ul", { class: "todos" }, p.todos.length ? p.todos.map(todo) : [h("li", { class: "muted" }, "할 일이 없어")]));
}

function render() {
  if (!state) return;
  const pending = state.jobs.filter((j) => j.status === "review");
  $("#pending").hidden = !pending.length;
  $("#pending").textContent = pending.length;
  $("#working").hidden = !state.working.length;
  $("#working").textContent = `${state.working.join("·")} 일하는 중…`;
  keyed($("#jobs"), state.jobs, (j) => j.id, (j) => JSON.stringify(j), card, "아직 작업이 없어. 아래에 일을 시켜줘!");
  keyed($("#review"), pending, (j) => j.id, (j) => JSON.stringify(j), reviewCard, "결재할 게 없어");
  if (tab === "today") today(state.planner);
}

async function poll(loop = true) {
  try {
    const r = await fetch("/api/m/state", { cache: "no-store" });
    if (r.status === 401) {
      $("#status").className = "status off";
      $("#status").textContent = "잠김: PC의 QR로 다시";
    } else if (r.ok) {
      state = await r.json();
      $("#status").className = `status ${state.ollama ? "on" : "off"}`;
      $("#status").textContent = state.ollama ? "PC 연결됨" : "PC AI 꺼짐";
      render();
    }
  } catch {
    $("#status").className = "status off";
    $("#status").textContent = "PC 연결 끊김";
  }
  if (loop) setTimeout(poll, 3000);
}

for (const btn of document.querySelectorAll(".tab")) {
  btn.addEventListener("click", () => {
    tab = btn.dataset.tab;
    for (const b of document.querySelectorAll(".tab")) {
      b.classList.toggle("on", b === btn);
      b.setAttribute("aria-selected", String(b === btn));
    }
    for (const id of ["jobs", "review", "today"]) $("#" + id).hidden = id !== tab;
    render();
  });
}

// ---- 지시 ----
function chips() {
  put($("#chips"),
    ref && h("span", { class: "chip ref" }, `자료: ${title(ref)}`, h("button", { type: "button", "aria-label": "고른 자료 빼기", onclick: () => { ref = null; chips(); } }, "✕")),
    ...files.map((f, i) => h("span", { class: "chip" }, f.name, h("button", { type: "button", "aria-label": `${f.name} 빼기`, onclick: () => { files.splice(i, 1); chips(); } }, "✕"))));
}
for (const id of ["#camera", "#pick"]) {
  $(id).addEventListener("change", (e) => {
    files.push(...e.target.files);
    e.target.value = "";
    chips();
  });
}
$("#bar").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData();
  form.append("text", $("#text").value);
  if (ref) form.append("ref", ref.id);
  for (const f of files) form.append("files", f);
  $("#send").disabled = true;
  try {
    await post("/api/m/command", form);
    $("#text").value = "";
    files.length = 0;
    ref = null;
    chips();
    $("#err").textContent = "";
    toast("실장님께 맡겼어요! 다 되면 알림 갈게요", "ok");
    poll(false);
  } catch (err) {
    $("#err").textContent = err instanceof TypeError ? "PC 사무실에 못 보냈어." : err.message;
  } finally {
    $("#send").disabled = false;
  }
});

poll();
