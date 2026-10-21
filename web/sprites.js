// 직원 픽셀 캐릭터: 16×16, '.'은 투명. 두 프레임 = 타자 치는 손 위치.
// 0~11줄은 두 프레임이 같고, 12~13줄(손)만 다르다. 14~15줄은 키보드.
const BASE = { S: "#f5c9a6", E: "#1b1428", M: "#c0587a", K: "#d8d0ea", k: "#7d6fa8" };
const KEYS = [".KKKKKKKKKKKKKK.", ".kkkkkkkkkkkkkk."];
const sprite = (colors, top, a, b) => ({
  colors: { ...BASE, ...colors },
  frames: [[...top, ...a, ...KEYS], [...top, ...b, ...KEYS]],
});

export const SPRITES = {
  // 실장: 남색 정장 + 빨간 넥타이
  manager: sprite({ H: "#2b2440", C: "#2e3a6e", W: "#f3eefe", T: "#ff4d6d" }, [
    "................",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "...HSSSSSSSSH...",
    "...SSESSSSESS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCWTTWCC....",
    "...CCCCTTCCCC...",
    "..CCCCCTTCCCCC..",
  ], ["..CC.CCTTCC.SS..", "..SS.CCCCCC....."],
     ["..SS.CCTTCC.CC..", ".....CCCCCC.SS.."]),

  // 스캐너: 갈색 삐침 머리 + 파란 안경 + 청록 후드
  scanner: sprite({ H: "#7a4a2a", G: "#3a86ff", C: "#1f9e8f", D: "#f3eefe" }, [
    "......H..H......",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "...HHSSSSSSHH...",
    "...SGEGGGGEGS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCDDCCC....",
    "...CCCCDDCCCC...",
    "..CCCCCCCCCCCC..",
  ], ["..CC.CCCCCC.SS..", "..SS.CCCCCC....."],
     ["..SS.CCCCCC.CC..", ".....CCCCCC.SS.."]),

  // 사서: 주황 긴 머리 + 초록 가디건 + 펼친 책
  librarian: sprite({ H: "#c9774a", C: "#4f8a3c", B: "#6b3fa0", b: "#f3eefe" }, [
    "................",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "..HHSSSSSSSSHH..",
    "..HSSESSSSESSH..",
    "..HSSSSSSSSSSH..",
    "..HHSSSMMSSSHH..",
    "..HH.SSSSSS.HH..",
    "..HHCCCCCCCCHH..",
    "..HCCCCCCCCCCH..",
    "..CCCCCCCCCCCC..",
  ], ["..CC.BBBBBB.SS..", "..SS.BbbbbB....."],
     ["..SS.BBBBBB.CC..", ".....BbbbbB.SS.."]),

  // 디자이너: 검은 베레모 + 금발 + 분홍 줄무늬 티
  designer: sprite({ R: "#2b2440", H: "#e8b04a", C: "#FC34CA", D: "#f3eefe" }, [
    ".......RR.......",
    "....RRRRRRRR....",
    "...RRRRRRRRRRR..",
    "...HHHHHHHHHH...",
    "...HSSSSSSSSH...",
    "...SSESSSSESS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCCCCCC....",
    "...DDDDDDDDDD...",
    "..CCCCCCCCCCCC..",
  ], ["..DD.DDDDDD.SS..", "..SS.CCCCCC....."],
     ["..SS.DDDDDD.DD..", ".....CCCCCC.SS.."]),

  // 출제위원: 회색 머리 + 귀에 꽂은 연필 + 보라 가디건
  examiner: sprite({ H: "#b8b2c8", e: "#ff8fb1", P: "#ffd23f", p: "#3b2f5c", C: "#6b3fa0", W: "#f3eefe" }, [
    "................",
    ".....HHHHHH.....",
    "....HHHHHHHH.e..",
    "...HHHHHHHHHHP..",
    "...HSSSSSSSSHP..",
    "...SSESSSSESSp..",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCWWCCC....",
    "...CCCCWWCCCC...",
    "..CCCCCCCCCCCC..",
  ], ["..CC.CCCCCC.SS..", "..SS.CCCCCC....."],
     ["..SS.CCCCCC.CC..", ".....CCCCCC.SS.."]),

  // 배포담당: 주황 모자 + 파란 점퍼 + 가방끈
  deployer: sprite({ A: "#FD633E", a: "#c94a2a", H: "#2b2440", C: "#3a86ff", D: "#8a5a3a" }, [
    "................",
    ".....AAAAAA.....",
    "....AAAAAAAA....",
    "..aaaaaaaaaaaa..",
    "...HSSSSSSSSH...",
    "...SSESSSSESS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CDCCCCCC....",
    "...CCCDCCCCCC...",
    "..CCCCCDCCCCCC..",
  ], ["..CC.CCCDCC.SS..", "..SS.CCCCDC....."],
     ["..SS.CCCDCC.CC..", ".....CCCCDC.SS.."]),

  // 비서: 단발머리 + 헤드셋 마이크 + 남색 조끼
  secretary: sprite({ H: "#3a2b4f", G: "#9aa0b4", m: "#ff4d6d", C: "#2e3a6e", W: "#f3eefe" }, [
    "................",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "..GHSSSSSSSSHG..",
    "..GHSESSSSESHG..",
    "..GHSSSSSSSSHm..",
    "...HHSSMMSSHm...",
    "...HH.SSSS.HH...",
    "....CCWWWWCC....",
    "...CCCWWWWCCC...",
    "..CCCCWWWWCCCC..",
  ], ["..CC.CWWWWC.SS..", "..SS.CCCCCC....."],
     ["..SS.CWWWWC.CC..", ".....CCCCCC.SS.."]),

  // 조사원: 탐험 모자 + 카키 셔츠 + 돋보기
  researcher: sprite({ A: "#c2a878", a: "#8f7a4f", H: "#5a3a22", C: "#9c8a5a", P: "#7d6c42", L: "#bfe9ff", l: "#8a5a3a" }, [
    "................",
    ".....AAAAAA.....",
    "....AAAAAAAA....",
    "..aaaaaaaaaaaa..",
    "...HSSSSSSSSH...",
    "...SSESSSSESS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCCCCCC....",
    "...CPPCCCCPPC...",
    "..CCCCCCCCCCCC..",
  ], ["..CC.CCCCCC.SSL.", "..SS.CCCCCC...l."],
     ["..SS.CCCCCC.CCL.", ".....CCCCCC.SSl."]),

  // 분석가: 각진 안경 + 회색 정장 + 그래프 태블릿
  analyst: sprite({ H: "#231c33", G: "#0d0b14", C: "#5b5f73", W: "#cfe3ff", B: "#3a86ff", T: "#2b2440", g: "#4ade80" }, [
    "................",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "...HHSSSSSSSH...",
    "...SGEGSSGEGS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCWBBWCC....",
    "...CCCWBBWCCC...",
    "..CCCCCBBCCCCC..",
  ], ["..CC.TTTTTT.SS..", "..SS.TgTgTT....."],
     ["..SS.TTTTTT.CC..", ".....TgTggT.SS.."]),

  // 암기담당: 높은 포니테일 + 노란 후드 + 암기카드
  cards: sprite({ H: "#b5546f", C: "#ffd23f", D: "#c99a1a", F: "#f3eefe", f: "#3a86ff" }, [
    "..........HH....",
    ".....HHHHHHH....",
    "....HHHHHHHHH...",
    "...HHHHHHHHHH...",
    "...HSSSSSSSSH...",
    "...SSESSSSESS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCDDCCC....",
    "...CCCCDDCCCC...",
    "..CCCCCCCCCCCC..",
  ], ["..CC.CCCCCC.FFF.", "..SS.CCCCCC.FfF."],
     ["..FFF.CCCCC.CC..", "..FfF.CCCCC.SS.."]),

  // 정리왕: 작은 왕관 + 초록 셔츠
  mapper: sprite({ Y: "#ffd23f", r: "#ff4d6d", H: "#4a3a6b", C: "#2f9e5b", W: "#f3eefe" }, [
    ".....Y.YY.Y.....",
    ".....YYrYYY.....",
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "...HSSSSSSSSH...",
    "...SSESSSSESS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCWWCCC....",
    "...CCCCWWCCCC...",
    "..CCCCCCCCCCCC..",
  ], ["..CC.CCCCCC.SS..", "..SS.CCCCCC....."],
     ["..SS.CCCCCC.CC..", ".....CCCCCC.SS.."]),

  // 선생님: 올림머리 + 동그란 안경 + 갈색 가디건 + 분필
  tutor: sprite({ H: "#e6e1f0", G: "#8a5a3a", C: "#a0522d", W: "#f3eefe", P: "#ffd23f" }, [
    "......HHHH......",
    ".....HHHHHH.....",
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "...HSSSSSSSSH...",
    "...SGEGSSGEGS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCWWCCC....",
    "...CCCCWWCCCC...",
    "..CCCCCCCCCCCC..",
  ], ["..CC.CCCCCC.SSP.", "..SS.CCCCCC...P."],
     ["..SS.CCCCCC.CC.P", ".....CCCCCC.SS.P"]),

  // 번역가: 헤드폰 + 파란 머리 + 주황 목도리
  translator: sprite({ B: "#2b2440", A: "#22d3ee", H: "#3a5fcd", C: "#6b7bd6", R: "#FD633E" }, [
    "................",
    ".....BBBBBB.....",
    "....BHHHHHHB....",
    "...BHHHHHHHHB...",
    "..AAHSSSSSSHAA..",
    "..AASESSSSESAA..",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCRRRRCC....",
    "...CCCCRRCCCC...",
    "..CCCCCCCCCCCC..",
  ], ["..CC.CCCCCC.SS..", "..SS.CCCCCC....."],
     ["..SS.CCCCCC.CC..", ".....CCCCCC.SS.."]),

  // 코치: 빨간 모자 + 호루라기 + 줄무늬 운동복
  coach: sprite({ R: "#ff4d6d", r: "#c0263f", H: "#2b2440", C: "#d62839", W: "#f3eefe", Y: "#c0c0c0" }, [
    "................",
    ".....RRRRRR.....",
    "....RRRRRRRR....",
    "...RRRRRRRRRrr..",
    "...HSSSSSSSSH...",
    "...SSESSSSESS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CWCCCCWC....",
    "...CCWCYCCWCC...",
    "..CCCWCCCCWCCC..",
  ], ["..CC.CCCCCC.SS..", "..SS.CCCCCC....."],
     ["..SS.CCCCCC.CC..", ".....CCCCCC.SS.."]),

  // 화가: 빨간 베레모 + 물감 묻은 하얀 앞치마 + 팔레트
  painter: sprite({ R: "#d62839", r: "#9c1d2b", H: "#7a4a2a", C: "#f3eefe", p: "#3a86ff", y: "#ffd23f", b: "#2f9e5b", P: "#c99a1a" }, [
    "................",
    "....RRRRRRR.....",
    "...RRRRRRRRRr...",
    "...HHHHHHHHHH...",
    "...HSSSSSSSSH...",
    "...SSESSSSESS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCCCCCC....",
    "...CCpCCCCyCC...",
    "..CCCCCbCCCCCC..",
  ], ["..CC.CCCCCC.PPP.", "..SS.CCCCCC.PyP."],
     ["..PPP.CCCCC.CC..", "..PbP.CCCCC.SS.."]),

  // 영상감독: 검은 모자 + 선글라스 + 슬레이트(딱딱이)
  director: sprite({ A: "#2b2440", a: "#111018", H: "#3a2b4f", G: "#111018", C: "#3b2f5c", W: "#f3eefe", B: "#111018" }, [
    "................",
    ".....AAAAAA.....",
    "....AAAAAAAA....",
    "..aaAAAAAAAA....",
    "...HSSSSSSSSH...",
    "...SGGGSSGGGS...",
    "...SSSSSSSSSS...",
    "....SSSMMSSS....",
    ".....SSSSSS.....",
    "....CCCCCCCC....",
    "...CCCCWWCCCC...",
    "..CCCCCWWCCCCC..",
  ], ["..CC.CCCCCC.BWB.", "..SS.CCCCCC.WBW."],
     ["..BWB.CCCCC.CC..", "..WBW.CCCCC.SS.."]),
};

// 꾸밈: 대표실 문, 화분 (한 프레임)
const still = (colors, rows) => ({ colors, frames: [rows, rows] });
export const DECOR = {
  door: still({ D: "#8a5a3a", d: "#5c3a22", Y: "#ffd23f" }, [
    "................",
    "...DDDDDDDDDD...",
    "...DddddddddD...",
    "...DdDDDDDDdD...",
    "...DdDDDDDDdD...",
    "...DdDDDDDDdD...",
    "...DddddddddD...",
    "...DdDDDDDDdD...",
    "...DdDDDDDDYD...",
    "...DdDDDDDDdD...",
    "...DdDDDDDDdD...",
    "...DddddddddD...",
    "...DdDDDDDDdD...",
    "...DdDDDDDDdD...",
    "...DDDDDDDDDD...",
    "................",
  ]),
  plant: still({ G: "#2f9e5b", g: "#1f6e3f", P: "#a0522d", p: "#7a3b1d" }, [
    "................",
    "......G..G......",
    ".....GGGGGG.....",
    "....GGgGGgGG....",
    "...GGGGgGGGGG...",
    "....GGGGGGGG....",
    ".....GGgGGG.....",
    "......GGGG......",
    ".......gg.......",
    ".......gg.......",
    ".....PPPPPP.....",
    ".....PppppP.....",
    "......PPPP......",
    "......PPPP......",
    "......PPPP......",
    "................",
  ]),
};

// 하위 직원: 팀장 그림에서 머리·옷 색만 바꾼다 (4인 1조가 한 팀처럼 보이게)
const HAIR = ["#2b2440", "#7a4a2a", "#c9774a", "#e8b04a", "#3a5fcd", "#b5546f", "#e6e1f0", "#1b1428"];
const CLOTH = ["#2e3a6e", "#1f9e8f", "#4f8a3c", "#6b3fa0", "#d62839", "#c99a1a", "#5b5f73", "#22d3ee"];
export function variant(sprite, i) {
  const colors = { ...sprite.colors };
  if (colors.H) colors.H = HAIR[(i * 3 + 1) % HAIR.length];
  if (colors.C) colors.C = CLOTH[(i * 5 + 2) % CLOTH.length];
  return { colors, frames: sprite.frames };
}
