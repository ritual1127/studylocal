# ritual의 공부 사무실 (studylocal)

내 PC의 로컬 AI(qwen3.5) 직원들이 학교 프린트를 예쁜 노트 PDF와 문제 풀이 웹페이지로 바꿔 주는 픽셀 아트 사무실.

인터넷 AI 서비스에 프린트를 올리지 않는다. 글자 읽기·정리·문제 내기는 전부 내 PC의 Ollama에서 돈다.
인터넷을 쓰는 건 두 가지뿐이다: 문학 작품 원문 가져오기(위키문헌·위키백과), 그리고 내가 [배포]를 눌렀을 때 Vercel에 문제 페이지 올리기.

## 설치

필요한 것: [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com/), [Node.js](https://nodejs.org/)(npm), Microsoft Edge 또는 Chrome.

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
vercel login   # 배포 기능을 쓸 때만, 한 번
```

`install.ps1`이 하는 일: qwen3.5 모델 받기(없을 때만) → 파이썬 환경(`%LOCALAPPDATA%\ritual-office\venv`) → 픽셀 로고·아이콘 만들기 → Vercel CLI 설치(없을 때만) → 바탕화면에 **ritual의 공부 사무실** 아이콘 만들기.

## 쓰는 법

바탕화면 아이콘을 누르면 사무실 창이 뜬다. 아래 명령 바에 적고 Enter (줄바꿈은 Shift+Enter). 프린트 사진·PDF는 [첨부]를 누르거나 창에 끌어다 놓는다.

- `이 프린트 예쁘게 PDF로 만들어줘` (사진이나 PDF 첨부)
- `이 프린트로 문제 10개 만들어줘` (첨부)
- `운수 좋은 날 가져와서 문제 10개 만들어줘`

결과는 오른쪽 **결과 보관함**에 쌓인다: [PDF 열기] · [문제 미리보기] · [텍스트] · [폴더] · [배포].
[배포]는 한 번 더 눌러야 올라가고, 받은 공개 링크는 [복사]로 복사한다.
다 쓰면 [퇴근] (일하는 중이면 한 번 더 눌러야 꺼진다).

## 직원 소개

| 직원 | 하는 일 |
|---|---|
| 실장 | 명령을 읽고 누가 무슨 일을 할지 정한다. 애매하면 되묻는다 |
| 스캐너 | 사진·PDF 프린트의 글자를 읽는다 (최대 20쪽) |
| 사서 | 문학 작품을 찾는다. 저작권이 끝난 작품만 위키문헌 원문을 가져오고, 아니면 해설만 정리한다 |
| 디자이너 | 요약·핵심 개념을 정리해 픽셀 로고가 들어간 노트 PDF를 만든다 |
| 출제위원 | 객관식·OX·단답형 문제와 해설을 만들어 한 장짜리 문제 풀이 페이지로 만든다 |
| 배포담당 | 문제 페이지를 Vercel에 올려 공개 링크를 만든다 |

## 내 PC 실측

2026-10-21, OMEN 16 (RTX 5060 Laptop 8GB, RAM 32GB), 전원 연결, `qwen3.5:latest`, `NUM_CTX = 16384`, `MAX_IMAGE_SIDE = 1600`.
시험 프린트: A4 한 장 "세포의 구조" (약 800자, 표 1개, `tests/fixtures/handout.html`).

| 작업 | 걸린 시간 |
|---|---|
| 프린트 사진 글자 읽기 (OCR) | 15초 |
| 노트 PDF 만들기 | 25초 |
| 문제 5개 만들기 | 16초 |
| 작품 가져오기 (운수 좋은 날) | 18초 |
| 사무실 화면에서 "PDF + 문제 5개" 한 번에 | 58초 |
| GPU 메모리(VRAM) 최대 사용 | 6.5GB / 8GB |

OCR이 한 장에 3분을 넘지 않아서 기본값(`NUM_CTX 16384`, `MAX_IMAGE_SIDE 1600`)을 그대로 쓴다.
다시 재려면: `$env:RITUAL_LIVE="1"; uv run pytest tests/test_live.py -v -s`

## 고급 모드

더 큰 모델(qwen3.6 36B MoE)로 바꾸기:

```powershell
setx RITUAL_MODEL qwen3.6:latest
```

사무실을 껐다 다시 켜면 적용된다. 훨씬 느리고 RAM을 23GB쯤 쓴다. 되돌리려면 `setx RITUAL_MODEL qwen3.5:latest`.

## 결과물 위치

`output/jobs/<작업 번호>/`에 작업마다 원본(`inputs/`), 읽은 글(`source.txt`), 노트(`note.pdf`), 문제 페이지(`quiz/`)가 남는다.
배포용 사이트는 `output/ritual-quiz/`에 모인다.

## 배포한 문제 내리기

`output/ritual-quiz/q/<작업 번호>` 폴더를 지운 뒤 아무 문제나 [배포]를 누르면, 그 문제가 빠진 사이트로 다시 올라간다.

## 문제 해결

- **상태등이 "Ollama 꺼짐"**: 작업 표시줄에서 Ollama를 켜거나 터미널에서 `ollama serve`. 사무실 아이콘을 누를 때도 자동으로 켜 본다.
- **느릴 때**: 전원을 연결하고, 게임·영상 편집처럼 GPU를 쓰는 앱을 끈다.
- **"사무실 서버가 꺼졌어"**: 바탕화면 아이콘을 다시 누른다.
- **배포가 안 될 때**: 터미널에서 `vercel login`을 한 번 한다.
- **로그**: `%LOCALAPPDATA%\ritual-office\office.log`

## 폰트 라이선스

픽셀 폰트 [Galmuri](https://github.com/quiple/galmuri) (© Lee Minseo, SIL Open Font License 1.1) — `web/fonts/OFL.txt`.
