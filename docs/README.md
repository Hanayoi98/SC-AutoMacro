# StarCraft Auto Macro v1.0

스타크래프트 Brood War 이미지 인식 기반 자동화 매크로

---

## 파일 구조

```
sc_macro/
├── macro.py          ← 메인 스크립트
├── requirements.txt  ← 의존성
├── config.json       ← 설정값
└── images/           ← 이미지 파일 보관 디렉터리
    ├── autosetting.png
    ├── target_circle.png
    ├── target_circle2.png
    ├── seal_idle.png
    ├── speed2.png
    ├── speed3.png
    ├── key.png
    ├── 28box.png
    ├── on.png
    ├── myth_text.png
    ├── bou.png
    ├── count_1.png
    ├── count_2.png
    └── count_3.png
```

---

## 설치

```bash
pip install -r requirements.txt
```

---

## 이미지 준비

`images/` 폴더에 각 UI 요소의 스크린샷을 저장합니다.

| 파일명 | 용도 |
|---|---|
| `autosetting.png` | F7 대기 트리거 |
| `target_circle.png` / `target_circle2.png` | F9 루프 기준 오브젝트 |
| `seal_idle.png` | seal 확인 클릭 대상 |
| `speed2.png` / `speed3.png` | 속도 상태 판별 |
| `key.png` | 열쇠 아이템 인식 |
| `28box.png` | 상자 28번 상태 |
| `on.png` | ON/OFF 상태 확인 |
| `myth_text.png` | 신화 텍스트 판별 |
| `bou.png` | bou 위젯 인식 |
| `count_1.png` / `count_2.png` / `count_3.png` | count 수치 판별 |

캡처 방법: 게임 실행 후 해당 UI 요소를 화면에 띄운 뒤, 
PNG 스크린샷으로 정확하게 잘라서 저장합니다. (배경 포함 최소 영역)

---

## 미확인 좌표 설정

`config.json`의 다음 값을 게임 화면에서 직접 측정 후 입력합니다.

```json
"coord_a":         [X, Y],   // F7 마우스 루틴 - 더블클릭 지점 A
"coord_b":         [X, Y],   // F7 마우스 루틴 - 더블클릭 지점 B
"coord_c":         [X, Y],   // F7 마우스 루틴 - 싱글클릭 × 4 지점 C
"myth_text_coord": [X, Y],   // 변환 루트 - myth_text 확인용 클릭 좌표
```

좌표 측정 팁: Python에서 `import pyautogui; print(pyautogui.position())` 실행 후 
마우스를 원하는 위치에 올리면 좌표가 출력됩니다.

---

## 설정값 설명

| 키 | 기본값 | 설명 |
|---|---|---|
| `id_code` | `"985545"` | F6에서 입력할 식별코드 |
| `f6_pet_upgrade` | `"c, q10, w6..."` | F7 초반 펫 업그레이드 시퀀스 |
| `f6_final_action` | `"w, s, r"` | F7 마무리 동작 시퀀스 |
| `f9_pet_interval` | `200` | F9 중 펫 업그레이드 주기 (초) |
| `f9_pet_upgrade` | `"e3"` | F9 중 펫 업그레이드 시퀀스 |
| `f9_early_branch_on` | `true` | F6 완료 후 F7 자동 실행 여부 |
| `f9_box28_monitor_on` | `true` | 28box 감시 기능 활성화 |
| `box28_confidence_set` | `0.97` | 28box 이미지 매칭 임계값 (높을수록 정확) |
| `check_on_offset_x/y` | `1324, 1056` | ON/OFF 확인 좌표 |
| `search_confidence` | `0.85` | 기본 이미지 매칭 임계값 |
| `input_delay` | `0.05` | 키 입력 간 딜레이 (초) |
| `loop_delay` | `0.1` | F9 루프 반복 딜레이 (초) |

---

## 입력 문자열 규칙

```
a3   → aaa
q10  → qqqqqqqqqq
w6   → wwwwww
c    → c
```

쉼표로 구분. 예: `"c, q10, w6, a10"` → `c` + `qqqqqqqqqq` + `wwwwww` + `aaaaaaaaaa`

---

## 단축키

| 키 | 기능 |
|---|---|
| `F6` | 채팅 매크로(@자동1) + 식별코드 입력 |
| `F7` | autosetting 대기 후 업그레이드 + 마우스 루틴 |
| `F8` | @태초 채팅 전송 |
| `F9` | 메인 루프 시작 / 다시 누르면 정지 |
| `Ctrl+F12` | 매크로 완전 종료 |

> 모든 단축키는 **스타크래프트 창이 활성화된 상태**에서만 동작합니다.

---

## 실행

```bash
python macro.py
```

관리자 권한 실행을 권장합니다 (키 후킹이 더 안정적으로 동작).

---

## 로그

실행 디렉터리에 `macro.log`가 생성됩니다.  
문제 발생 시 이 파일을 확인하세요.

---

## 미확인 항목 (스펙 원본 기준)

다음 항목은 게임 실행 환경에서 직접 확인/측정이 필요합니다.

- 좌표 A, B, C 실제 위치
- myth_text 확인 좌표
- 각 단계별 세부 딜레이 (ms 단위 조정)
- 이미지 탐색 영역 (region 파라미터)
- 예외 처리 로직 (이미지 탐색 실패 시 복구 방법)
