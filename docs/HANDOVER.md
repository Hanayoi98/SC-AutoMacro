# SC AutoMacro — AI 인수인계 문서

## 프로젝트 개요

- **프로젝트명**: SC AutoMacro
- **GitHub**: https://github.com/Hanayoi98/SC-AutoMacro
- **메인 파일**: `scan/SC_AutoMacro/macro.py`
- **설정 파일**: `scan/SC_AutoMacro/config/config.json`
- **루프 메모**: `scan/SC_AutoMacro/docs/LOOP_MEMO.md`
- **현재 버전**: v1.4 (진행 중)

스타크래프트 리마스터 게임 자동화 매크로. Python + tkinter UI.

---

## 필수 규칙 (반드시 준수)

### 1. 수정 전 확인
코드/파일 수정(Edit/Write) 전 반드시 변경 내용을 먼저 사용자에게 보여주고 확인받을 것.
- "이렇게 수정하겠습니다 — 진행할까요?" 형태로 먼저 제시
- 사용자가 "진행" 또는 "응" 으로 확인 후 실행

### 2. 수정 후 처리 (순서 준수)
파일 수정 완료 후 아래 3가지를 반드시 순서대로 실행:
1. **syntax 확인** — `python -m py_compile macro.py`
2. **LOOP_MEMO.md 업데이트** — 루프 관련 변경사항 반영
3. **GitHub push** — `git add → git commit → git push origin master`

### 3. 응답 스타일
- 항상 compact하게 응답 (불필요한 설명 생략)
- 루프 구조 확인 요청 시 코드를 읽고 다이어그램 형태로 제시

---

## 파일 구조

```
scan/SC_AutoMacro/
  macro.py              ← 메인 코드 (모든 루프/UI)
  config/config.json    ← 사용자 설정값
  images/               ← 템플릿 이미지 (PNG)
  docs/
    LOOP_MEMO.md        ← 루프 구조 메모 (수정 시마다 갱신)
    HANDOVER.md         ← 이 파일
```

---

## 키 구조

| 키 | 기능 |
|---|---|
| F6 | AutoStart_2 이미지 감지 대기 → 채팅/id_code 입력 |
| F7 | key 이미지 대기 → F2·2·업그레이드·3·마무리 → 마우스 루틴 |
| F8 | @태초 채팅 입력 |
| F9 | 메인 루프 (seal/target 변환) 시작/정지 |
| F11 | 방장모드 또는 따라가기모드 시작/정지 |

---

## 주요 루프 구조 요약

### F6F7 루프 (`_f6f7_loop`)
- F6/F7 키 → 공유 스레드 `_f6f7_thr` + `_f6f7_stop` 토글
- 실행 중 재입력 → 정지 / 정지 후 재입력 → 처음부터 재시작
- F11 입력 시 F6F7 대기 자동 정지
- F7 완료 시 Discord 알림 전송 (`discord_notify_on=True` 시)

### F11 방장모드 (`_host_loop`)
- Step1: Host_1 대기 → 클릭 → Step2
- Step2: Host_2 대기 → 클릭 → Step3
- Step3: Host_3 OCR → 전원 확인 → Host_4 클릭
- `auto_drive_on=True` 시 완료 후 F6 자동 실행

### F11 따라가기 (`_follow_loop`)
- Step1: AutoFollow_3 탐색 → 클릭
- Step2: OCR 닉네임 탐색 (최대 10회 실패 시 종료)
- Step3: AutoFollow_2 클릭 (최대 20회 실패 시 종료)
- `auto_drive_on=True` 시 완료 후 sleep(2.0s) → F6 자동 실행

### F9 메인 루프 (`_f9_loop`)
- 자세한 내용은 `docs/LOOP_MEMO.md` 참조

---

## 스레드 구조

| 변수 | 용도 |
|---|---|
| `_f9thr` + `_stop` | F9 메인 루프 |
| `_f11thr` + `_host_stop` | 방장모드 |
| `_follow_thr` + `_follow_stop` | 따라가기 |
| `_f6f7_thr` + `_f6f7_stop` | F6F7 공통 |

---

## 설정 탭 구성

| 탭 | 내용 |
|---|---|
| 창 크기 | SC 창 해상도 |
| 좌표 설정 | A/B/C/M/ON 좌표 |
| 키 설정 | F6/F9 설정 |
| 게임모드1 | F11 모드 선택 · 방장모드 · 따라가기 설정 |
| 게임모드2 | 게임종료 루프 ON/OFF |
| 고급1 | F9/F7 딜레이 |
| 고급2 | 이미지 매칭 정확도 · 자동운행모드 · Discord 알림 |

---

## 버전 히스토리 요약

| 버전 | 주요 내용 |
|---|---|
| v1.0 | 기본 완성 (F9 루프, F6/F7/F8) |
| v1.1 | count 처리 개선, speed_confidence, F7 딜레이 분리 |
| v1.2 | F11 방장모드 완성 |
| v1.3 | 게임종료 루프, 자동보스선택 OCR, 따라가기 모드, 템플릿 스케일링 |
| v1.4 | F6F7 스레드 통합, OCR 파싱 개선, 자동운행모드, Discord 알림 (진행 중) |

---

## 작업 시 참고

- 루프 구조 확인: `docs/LOOP_MEMO.md` 먼저 읽을 것
- 이미지 매칭: `images/` 폴더의 PNG 파일명과 코드 내 `finder.find("이름")` 일치
- 설정값 타입: `_NUM_KEYS` dict에 등록된 키는 자동 형변환됨 (str/bool/int/float)
- 쿨다운/타임아웃: 하드코딩 상수는 코드 내 주석으로 명시됨
