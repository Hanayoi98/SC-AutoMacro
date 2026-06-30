# SC AutoMacro — 루프 메모

> 코드 수정 시마다 이 파일을 업데이트할 것.

---

## F9 메인 루프 (`_f9_loop`)

```
[Loop Start]
  게임 창(hwnd) 탐색 → 없으면 sleep(1) → continue
  gx, gy, gw, gh 갱신
  _pet_upgrade_check()

  탐색 영역 계산:
    box_reg   = gx+gw*0.10, gy+gh*0.60, gw*0.40, gh*0.20
    info_reg  = gx+gw*0.25, gy+gh*0.75, gw*0.45, gh*0.23
    cmd_reg   = gx+gw*0.65, gy+gh*0.65, gw*0.35, gh*0.35
    field_reg = gx+50, gy+50, gw-100, gh-250
    full_reg  = gx, gy, gw, gh

① [28box 자동판매 설정] (f9_box28_monitor_on=True, is_auto_sell_set=False 일 때만)
     28box 미감지 → 패스
     28box 감지 →
       '3' 키 입력 → sleep(0.5)
       check_on_offset 위치로 마우스 이동 → sleep(0.4)
       ON 감지 시: 설정 완료 로그
       ON 미감지 시: A키 입력
       is_auto_sell_set = True → sleep(0.5) → continue

② seal_idle (SEAL_CONF=0.75, field_reg) + target_circle (TARGET_CONF=0.65, full_reg) 탐색
     target_circle 없으면 target_circle2 탐색
     둘 중 하나라도 없으면 → sleep(0.12) → continue
     sx, sy = seal 중심 / tx, ty = target 중심

③ [초반 분기] (f9_early_branch_on=True)
     seal 좌클릭 (sx, sy) → sleep(0.05)

     speed3 감지 (SPEED3_CONF=0.78, info_reg):
       is_auto_sell_set=False →
         key 탐색 (KEY_CONF=0.78, field_reg)
         key 있음 → key 좌클릭 + target 우클릭 → sleep(1.0) → continue
         key 없음 → 변환루트 fall-through (④ 로 계속)
       is_auto_sell_set=True → 변환루트 fall-through (④ 로 계속)

     speed2 감지 (SPEED2_CONF=0.93, info_reg):
       is_auto_sell_set=False →
         key 탐색 (KEY_CONF=0.78, field_reg)
         key 있음 → key 좌클릭 + target 우클릭 → sleep(1.0) → continue
         key 없음 → 변환루트 fall-through (④ 로 계속)
       is_auto_sell_set=True → 변환루트 fall-through (④ 로 계속)

     speed2/3 모두 없음 → ④ 로 계속

④ 변환 초기 클릭 (gx+gw*0.6, gy+gh*0.5-30) → sleep(0.2)

⑤ [bou(파편) 판정] (bou, conf=0.6, info_reg)
     bou 없음 → 초월인장 일반변환:
       seal 좌클릭 + target 우클릭
     bou 있음 →
       스크린샷 캡처
       count_1/2/3 탐색 (COUNT_CONF=0.94, info_reg)

       count 매칭됨 (found_num=1~3):
         _check_double_digit → True (우측 12×14px 밝은 픽셀, 10개+) → A키 (종말인장)
         _check_double_digit → False → seal 좌클릭 + target 우클릭 (초월인장)

       count 미매칭 (4개+, 인식 초과) → A키 (종말인장)

     sleep(1.0) → Loop Start
```

---

## 서브루틴

### _check_double_digit
```
count 이미지 우측(+2px) 12×14px 영역 픽셀 스캔
  밝기 > 80인 픽셀 발견 → True (10개 이상)
  없음 → False
  matched_num이 2 or 3이면 좌측 16px에서 count_1 추가 탐색 → 있으면 True
```

### _pet_upgrade_check
```
경과시간 >= f9_pet_interval → f9_pet_upgrade 시퀀스 입력
```

---

## F6F7 루틴 (`_f6f7_loop`)

F6/F7 키 공통 토글 스레드 (`_f6f7_thr` + `_f6f7_stop`)
실행 중 재입력 → 정지 / 정지 후 재입력 → 처음부터 시작

```
F6 키 입력
  _f6f7_thr 실행 중 → 정지
  미실행 → start_at_f7=False 로 _f6f7_loop 시작

F7 키 입력
  _f6f7_thr 실행 중 → 정지
  미실행 → start_at_f7=True 로 _f6f7_loop 시작

_f6f7_loop(start_at_f7=False):
  ── F6 구간 ──
  SC 창 hwnd 획득 실패 → 종료
  boss_loop 영역(rx/ry/rw/rh)에서 AutoStart_2 대기 (_f6f7_stop 체크)
  감지 → sleep(1.0)
  f6_chat_macro_on=True → ENTER → @자동1 → ENTER (+step_delay)
  0키 (+step_delay) → id_code 입력 (SendInput)
  f9_early_branch_on=False → 종료

  ── F7 구간 ──
  F2 (화면 재고정)  ← 재시작 시 F2-locked 상태 해제/재설정
  key 이미지 대기 (region_game, _f6f7_stop 체크)
  key 발견 → F2 → 2 → f6_pet_upgrade → 3 → f6_final_action (f7_step_delay)
  _f7_mouse_routine():
    coord_a → 더블클릭(0.45s) → Q(0.45s)
    coord_b → 더블클릭(0.45s) → Q(0.45s)
    coord_c → (싱글클릭(0.45s) → Q(0.45s)) × 4

_f6f7_loop(start_at_f7=True):
  F6 구간 생략 → F7 구간만 실행 (F2 재고정부터)
```

### F7 전용 딜레이 설정키
| 키 | 기본값 | 적용 대상 |
|---|---|---|
| `f7_input_delay` | 0.15s | 키/클릭 후 대기 |
| `f7_step_delay` | 0.2s | 동작 간 대기 |
| `f7_mouse_move_dur` | 0.05s | 마우스 이동 시간 |

## F8 루틴
```
ENTER → @태초 → ENTER
```

---

## 이미지 매칭 정확도 상수 (코드 내 하드코딩)
| 상수 | 값 | 적용 대상 |
|---|---|---|
| SEAL_CONF | 0.75 | seal_idle |
| TARGET_CONF | 0.65 | target_circle / target_circle2 |
| SPEED2_CONF | 0.93 | speed2 |
| SPEED3_CONF | 0.78 | speed3 |
| COUNT_CONF | 0.94 | count_1 / count_2 / count_3 |
| BOX25_CONF | 0.91 | 25box |
| BOX26_CONF | 0.91 | 26box |
| BOX27_CONF | 0.91 | 27box |
| ON_CONF | 0.70 | on |
| KEY_CONF | 0.78 | key |

## 설정창 탭 구성
| 탭 | 내용 |
|---|---|
| 창 크기 | SC 창 해상도 |
| 좌표 설정 | A/B/C/M/ON 좌표 |
| 키 설정 | F6 설정 + F9 설정 통합 |
| 게임모드1 | F11 모드 선택(방장/따라가기) · 방장모드 · 따라가기 설정 |
| 게임모드2 | 게임종료 루프 ON/OFF · (추가 예정) |
| 고급1 | F9/F7 딜레이 |
| 고급2 | 이미지 매칭 정확도 (나머지/box/count/speed) |

---

## F11 방장모드 루프 (`_host_loop`)

```
[F11 시작]
  │
  ├─ Step 1: Host_1 대기 (0.1s 폴링)
  │   Host_1 감지 → 클릭 → sleep(3.0s) → Step 2
  │   Host_1 없음 + Host_3 감지 → sleep(1.0s) → Step 3 이동
  │   Host_1/3 없음 + Host_2 감지 → sleep(1.0s) → Step 2 이동
  │   정지 요청 → 종료
  │
  ├─ Step 2: Host_2 대기 (0.1s 폴링)
  │   Host_3 감지 → sleep(1.0s) → Step 3 이동
  │   Host_2 감지 → 클릭 → sleep(2.5s) → Step 3
  │   정지 요청 → 종료
  │
  └─ Step 3: Host_3 OCR 루프 (0.1s 폴링)
      Host_3 미감지 → continue (재탐색)
      Host_3 감지 → OCR 실행
        전원 확인 → sleep(3.0s) → Host_4 클릭 → 종료
        미확인 있음 → sleep(0.5s) → 재탐색
```

### 상수 및 설정
| 항목 | 값 | 설명 |
|---|---|---|
| HOST_CONF | 0.65 | 이미지 매칭 임계값 |
| OCR 오프셋 | x-720, y-518 | Host_3 중심 기준 닉네임 슬롯 좌상단 |
| OCR 크기 | 290×340 px | 닉네임 슬롯 전체 영역 |
| OCR PSM | 6 | 블록 텍스트 |
| 유사도 임계 | 0.70 | difflib OCR 오인식 보정 |
| sleep Step1 클릭 후 | 3.0s | |
| sleep Step2 클릭 후 | 2.5s | |
| sleep 전원확인 후 | 3.0s | Host_4 클릭 전 대기 |

### 이미지 파일
| 파일 | 설명 |
|---|---|
| Host_1.png | Step1 감지 대상 |
| Host_2.png | Step2 감지 대상 |
| Host_3.png | Step3 로비 감지 (닉네임 슬롯 블랙아웃) |
| Host_4.png | 전원 확인 후 클릭 대상 |

---

---

## 게임종료 루프 (`_game_end_check`)

F9 루프 내에서 동작. `game_end_on=True` 일 때 활성화.

```
[비활성 상태 (_game_end_mode=False)]
  SelectBoss_0 탐색 (conf=0.80, sb1_reg)
    sb1_reg: rx=0.2739, ry=0.1682, rw=0.4522, rh=0.4267
  감지 → _game_end_mode=True → F9 루프 이후 로직 스킵, 게임종료 모드 전환

[게임종료 모드 (_game_end_mode=True)]
  BossClear_2 탐색 (conf=0.80, bc2_reg)
    bc2_reg: rx=0.2677, ry=0.2494, rw=0.4553, rh=0.3024
  미감지 → sleep(0.12) → continue
  감지 → 종료 시퀀스:
    PrtSc → 스크린샷 파일 감지 (1.5s 대기)
    파일 없음 → 활성 상태 유지 (재시도)
    파일 있음 →
      sleep(0.5)
      F10 → E → S → Q → sleep(3.0) → Enter → sleep(0.5)
      gamemode_host_on=True → F11 입력 (방장모드 시작)
      _stop.set() → F9 루프 종료
```

### 이미지 파일
| 파일 | 설명 |
|---|---|
| SelectBoss_0.png | 보스선택창 "예상 파티 총 딜량" 텍스트 크롭 (320×30) |
| BossClear_1.png | 게임 클리어 전체 화면 (참조용) |
| BossClear_1T.png | bc2_reg 영역 추출용 노란박스 이미지 |
| BossClear_2.png | 클리어 텍스트 템플릿 (125×30) |

### 내부 변수명 규칙
| 변수 | 설명 |
|---|---|
| `_game_end_mode` | 게임종료 모드 플래그 (F9 루프 내) |
| `_host_stop` | 방장모드 stop Event |
| `_f11thr` | 방장모드 스레드 |
| `gamemode_host_on` | 방장모드 사용 여부 (config 키) |

---

_최종 업데이트: 2026-06-27 — v1.3: F11 방장모드 추가 (OCR 닉네임 전원 확인 / Host_3 슬롯 블랙아웃 / difflib 유사도 매칭) / 게임종료 루프 추가 (SelectBoss_0→BossClear_2→종료 시퀀스) / 👑 방장설정 버튼 메인창 추가_

_최종 업데이트: 2026-06-28 — v1.3: 초반분기 is_auto_sell_set 분기 / 딜량 OCR 개선 (3배 확대·LSTM·psm8 재시도) / 따라가기 모드 추가 (F11 host/follow 분기 / AutoFollow_3→OCR→AutoFollow_2) / OCR 전처리 흰색 마스크(HSV V>140,S<80) 클랜태그 제거 / F11 UI 모드별 색상(방장=핑크·따라가기=초록) / 설정탭 개편(키 설정 통합·게임모드1·2 분리)_

---

**v1.3 최종 확정 — 이후 수정은 v1.4부터 진행**

---

_최종 업데이트: 2026-06-28 — v1.4: 따라가기 루프 재시도 구조 추가 (Step2 닉네임 미발견 시 Step1 재시도 최대 5회 / Step3 AutoFollow_2 미발견 시 Step1 재시도 최대 10회 / _follow_stop 체크 추가)_

_최종 업데이트: 2026-06-28 — v1.4: F11 설정 구조 개편 — gamemode_host_on 제거 / f11_on(F11 사용 bool) 신규 추가 / _f11_host·_f11_follow 모두 f11_on 게이트 통일 / _game_end_check 보스선택 분기 f11_mode=="host" 조건으로 변경 / tesseract CMD 창 숨김(CREATE_NO_WINDOW)_

_최종 업데이트: 2026-06-28 — v1.4: 자동보스선택 OCR 파싱 개선 — FIX1 억 앞 선행 0 감지(psm8 재시도) / FIX2 만 앞 >9999 숫자 감지(억 오인식 → psm8 재시도) / 1.5차 trim 4자리+ 조건 추가 및 1·2자리 순차 trim(SelectBoss_1~8 전체 8/8 통과)_

_최종 업데이트: 2026-06-28 — v1.4: 방장모드·따라가기모드 자동운행모드 추가 — Host_4 클릭+0.5s / AutoFollow_2 클릭+2.0s 후 auto_drive_on=True 시 F6 자동 입력 / 고급2 탭에 자동운행모드 체크박스 추가_

_최종 업데이트: 2026-06-28 — v1.4: F11 입력 시 F6F7 대기 자동 정지 — f11() 진입 시 _f6f7_thr 실행 중이면 _f6f7_stop.set() 으로 F6 이미지 대기 즉시 종료_

_최종 업데이트: 2026-06-28 — v1.4: Discord + Slack 알림 추가 — F7 완료 시 각각 독립 ON/OFF / 고급2 탭에 Discord·Slack 섹션 추가_

_최종 업데이트: 2026-06-30 — v1.4: requests 패키지 _REQUIRED_PACKAGES 추가 — 미설치 환경 시작 시 crash 방지_

_최종 업데이트: 2026-06-30 — v1.4: 따라가기 닉네임 OCR 개선 — HSV V 임계값 140→80(숫자 포함 닉네임 인식률 개선) / 동일 line_num 토큰만 합산(잘못된 Y좌표 반환 버그 수정)_

_최종 업데이트: 2026-06-30 — v1.4: 보스선택 딜량 OCR 개선 — SelectBoss_0(딜량 레이블) · SelectBoss_1(억) · SelectBoss_2(만) 템플릿 매칭으로 억값/만값 분리 인식 / 억값: 4자리 이상 or 1000 초과 시 fallback / 만값: SB1~SB2 사이 4자리 이하 숫자만 인식_

_최종 업데이트: 2026-06-30 — v1.4: 자동 보스 실행(auto_boss_run_on) 추가 — 보스선택 완료 후 3.0s 대기 → L키 KEYDOWN → 5.0s 홀드 → KEYUP / 자동 보스 선택 OFF 시 UI 체크박스 비활성화 / 빨간 경고문구 "충분한 딜량 측정 확인없이 사용주의" 표시_

_최종 업데이트: 2026-06-30 — v1.4: config.json UTF-8 BOM 처리 — load_config encoding utf-8 → utf-8-sig (메모장 저장 환경 호환)_
