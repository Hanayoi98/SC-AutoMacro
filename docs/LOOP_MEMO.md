# SC AutoMacro — 루프 메모

> 코드 수정 시마다 이 파일을 업데이트할 것.

---

## F9 메인 루프 (`_f9_loop`)

```
[Loop Start]
  F2 입력 (+step_delay)
  펫 업그레이드 주기 확인 (_pet_upgrade_check)
  region_game / region_ui 갱신
  화면 1회 캡처 (grab_screen)

① target_circle / target_circle2 탐색 (region_game)
     없음 → loop_delay → Loop Start
     있음 → tcx, tcy 저장

② key_skip 플래그 확인
     True  → loop_delay → ⑤ 변환루트
     False → 계속

③ 28box 확인 (b28_conf=0.97, region_ui)
     감지 + on 있음 → key_skip=True → loop_delay → Loop Start
     감지 + on 없음 → _handle_28box() → key_skip=True → loop_delay → Loop Start
     미감지 → ④

④ seal_idle 확인 (region_game)
     없음 → loop_delay → Loop Start
     있음 → 클릭
     loop_delay 대기 후 화면 재캡처 (grab_screen)
     speed2/3 확인:
       있음 → _key_routine() → Loop Start
       없음 → ⑤ 변환루트

⑤ 변환루트 (_conversion_route)
     speed 없으면 seal_idle 클릭
     myth_text_coord 클릭 (+step_delay)
     myth_text 탐색:
       없음 → _normal_conversion()   → Loop Start
       있음 → _special_conversion_check()
```

---

## 서브루틴

### _key_routine
```
key 탐색 (region_game)
  없음 → _conversion_route()
  있음 → key 클릭 → target 우클릭
         28box 감시 → 있으면 _handle_28box() → return
         key_speed_delay 대기 → Loop Start
```

### _handle_28box
```
3키 입력 → check_on_offset 이동
on 탐색:
  있음 → 아무것도 안 함
  없음 → 클릭 (OFF→ON 전환)
```

### _normal_conversion
```
seal_idle 클릭 → target 우클릭 → Loop Start
```

### _special_conversion_check
```
bou 탐색
  없음 → _normal_conversion()
  있음 → bou 우측 130px 영역에서 count_1/2/3 탐색
    count 있음(1~3) → _normal_conversion()
    count 없음(4+)  → _do_special_conversion()
```

### _do_special_conversion
```
8초 동안 A키 0.5s 간격 입력
2초마다 (key_skip=False 시):
  seal_idle 클릭 → speed 확인
    speed 감지 → _key_routine() → return
8초 완료 → Loop Start
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

## key_skip 플래그
- F9 시작 시 False 초기화
- 28box ON 확인 시 True
- True 상태: ② 에서 변환루트만 진행

---

## 설정창 탭 구성
| 탭 | 내용 |
|---|---|
| 창 크기 | SC 창 해상도 |
| 좌표 설정 | A/B/C/M/ON 좌표 |
| F6 설정 | 채팅·식별코드·분기 |
| F9 설정 | 펫·28box 감시 |
| 고급1 | F9/F7 딜레이 |
| 고급2 | 이미지 매칭 정확도 (나머지/box/count) |

### 이미지 매칭 정확도 키
| 키 | 적용 대상 |
|---|---|
| `search_confidence` | target_circle, seal_idle, speed2/3, key, myth_text, bou 등 나머지 |
| `box28_confidence_set` | 28box |
| `count_confidence` | count_1 / count_2 / count_3 |

_최종 업데이트: 2026-06-26 — 고급창 고급1/고급2 분리, count_confidence 추가_
