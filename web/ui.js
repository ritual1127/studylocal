// 화면 공용 도우미: DOM 만들기, 서버 부르기, 토스트, 목록 다시 그리기, 브라우저 저장

export const $ = (sel, root = document) => root.querySelector(sel);

const PROPS = new Set(["value", "checked", "disabled", "selected"]);

// 글자는 전부 텍스트 노드로 넣는다 (innerHTML 안 씀)
export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (PROPS.has(key)) el[key] = value;
    else el.setAttribute(key, value);
  }
  el.append(...kids.flat().filter(Boolean));
  return el;
}

// 답변 속 **굵게**만 살린다 (나머지 마크다운은 글자 그대로)
export const rich = (text) => text.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? h("b", {}, part) : part));

// replaceChildren인데 조건부로 빠진 자식(false·null·0)은 건너뛴다
export const put = (el, ...kids) => el.replaceChildren(...kids.flat().filter(Boolean));

export async function api(url, body) {
  const opts = { method: "POST" };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.body = JSON.stringify(body);
    opts.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `오류가 났어 (${r.status})`);
  return data;
}

export async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`오류가 났어 (${r.status})`);
  return r.json();
}

export function toast(msg, kind = "") {
  const el = h("p", { class: `toast ${kind}`, role: kind === "err" ? "alert" : "status" }, msg);
  $("#toasts").append(el);
  setTimeout(() => el.remove(), kind === "err" ? 6000 : 3500);
}

// 서버 부르고 결과를 토스트로 (실패해도 화면은 그대로)
export async function act(url, body, okMsg) {
  try {
    const data = await api(url, body);
    if (okMsg) toast(okMsg, "ok");
    return data;
  } catch (e) {
    toast(e instanceof TypeError ? "사무실 서버에 못 보냈어." : e.message, "err");
    return null;
  }
}

// 목록을 다시 그릴 때 바뀐 항목만 새로 만든다 (입력 중인 칸·포커스가 안 날아가게)
export function keyed(list, items, key, sig, render, empty) {
  const old = list._keyed ?? new Map();
  const next = new Map();
  const els = items.map((item) => {
    const k = key(item);
    const s = sig(item);
    const prev = old.get(k);
    const el = prev && prev.s === s ? prev.el : render(item);
    next.set(k, { s, el });
    return el;
  });
  list._keyed = next;
  if (!els.length) {
    if (list._empty !== empty || list.children.length !== 1) list.replaceChildren(h("p", { class: "empty" }, empty));
    list._empty = empty;
    return;
  }
  list._empty = null;
  els.forEach((el, i) => {
    if (list.children[i] !== el) list.insertBefore(el, list.children[i] ?? null);
  });
  while (list.children.length > els.length) list.lastElementChild.remove();
}

export const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // 저장이 막힌 브라우저면 기억만 못 할 뿐
    }
  },
};

// ---- 회사 조직 ----
export const TEAMS = [
  { id: "ops", name: "경영지원팀", color: "var(--c1)", roles: ["manager", "secretary", "deployer"], extra: "door" },
  { id: "intake", name: "자료조사팀", color: "var(--c3)", roles: ["scanner", "librarian", "researcher", "analyst"] },
  { id: "make", name: "콘텐츠제작팀", color: "var(--c5)", roles: ["designer", "examiner", "cards", "mapper"] },
  { id: "learn", name: "학습지원팀", color: "var(--sky)", roles: ["tutor", "translator", "coach"], extra: "plant" },
];
export const NAMES = {
  manager: "실장", secretary: "비서", deployer: "배포담당", scanner: "스캐너", librarian: "사서",
  researcher: "조사원", analyst: "분석가", designer: "디자이너", examiner: "출제위원", cards: "암기담당",
  mapper: "정리왕", tutor: "선생님", translator: "번역가", coach: "코치",
};
export const DUTY = {
  manager: "업무 배분·보고", secretary: "일정·할 일·알림", deployer: "문제 웹 배포", scanner: "모든 파일·사진 판독",
  librarian: "문학 원문·해설", researcher: "주제 조사", analyst: "자료 분석 보고서", designer: "PDF 공부 노트",
  examiner: "문제 출제", cards: "암기카드", mapper: "마인드맵", tutor: "질문 답변", translator: "번역",
  coach: "공부 계획·공부모드",
};
export const ROLE_OF = Object.fromEntries(Object.entries(NAMES).map(([role, name]) => [name, role]));
export const teamOf = (role) => TEAMS.find((t) => t.roles.includes(role)) ?? TEAMS[0];

// 결과물 종류 (자동 승인 규칙·버튼 이름)
export const OUTPUT_NAMES = {
  analysis: "분석 보고서", pdf: "PDF 노트", quiz: "문제", cards: "암기카드", mindmap: "마인드맵",
  translate: "번역", answer: "답변",
};

export const minutesText = (m) => (m >= 60 ? `${Math.floor(m / 60)}시간 ${m % 60}분` : `${m}분`);
export const ddayText = (days) => (days === 0 ? "D-DAY" : days > 0 ? `D-${days}` : `D+${-days}`);
