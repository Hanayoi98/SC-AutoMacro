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

③ [초반 분기] (f9_early_branch_on=True, is_auto_sell_set 무관)
     seal 좌클릭 (sx, sy) → sleep(0.2)

     speed3 감지 (SPEED3_CONF=0.78, info_reg):
       key 있음 (KEY_CONF=0.78, field_reg) →
         key 좌클릭 + target 우클릭 (inp.click / inp.rclick) → sleep(1.0) → continue
       key 없음 → sleep(0.5) → continue

     speed2 감지 (SPEED2_CONF=0.93, info_reg):
       25box / 26box / 27box 중 하나라도 있으면 → continue (변환 스킵)
       박스 없음 + key 있음 →
         key 좌클릭 + target 우클릭 → sleep(1.0) → continue
       박스 없음 + key 없음 → sleep(0.5) → continue

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

## F6 루틴
```
f6_chat_macro_on=True → ENTER → @자동1 → ENTER (+step_delay)
0키 (+step_delay)
id_code 입력 (SendInput)
f9_early_branch_on=True → f7() 자동 실행
```

## F7 루틴
```
key 이미지 대기 (무한, region_game)
F2 → 2 → f6_pet_upgrade → 3 → f6_final_action  (딜레이: f7_step_delay)
_f7_mouse_routine():  (마우스 이동: f7_mouse_move_dur / 클릭·키 딜레이: 고정 0.45s)
  coord_a 이동 → 더블클릭(0.45s) → Q(0.45s)
  coord_b 이동 → 더블클릭(0.45s) → Q(0.45s)
  coord_c 이동 → (싱글클릭(0.45s) → Q(0.45s)) × 4
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
| F6 설정 | 채팅·식별코드·분기 |
| F9 설정 | 펫·28box 감시 |
| 고급1 | F9/F7 딜레이 |
| 고급2 | 이미지 매칭 정확도 (나머지/box/count/speed) |

---

_최종 업데이트: 2026-06-26 — F9 루프 전면 재작성 (macro.exe 바이트코드 추출 기반) / 28box 자동판매: '3'키 입력 방식 / speed2/3 감지 시 열쇠 삽입 (is_auto_sell_set 무관) / COUNT_CONF 0.94로 상향_
