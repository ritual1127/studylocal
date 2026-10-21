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
};
