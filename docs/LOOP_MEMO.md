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

① target_circle / target_circle2 탐색 (region_game, conf=search_confidence)
     없음 → loop_delay → Loop Start
     있음 → tcx, tcy 저장

② key_skip 플래그 확인 (28box ON 모드)
     True →
       loop_delay
       seal_idle 폴링 (최대 5회 × 0.5s) → 클릭
         미감지 → 사이클 스킵 → Loop Start
       loop_delay 후 재캡처
       speed3 감지 → _key_routine()
       speed2 감지 → _bou_conversion()
       speed 없음 → Loop Start
     False → 계속

③ 28box 확인 (b28_conf=box28_confidence_set, region_ui)
     26box 감지 → 오인식 방지, ④로 패스
     28box 감지 + on 있음 → key_skip=True → loop_delay → Loop Start
     28box 감지 + on 없음 → _handle_28box() → key_skip=True → loop_delay → Loop Start
     미감지 → ④

④ seal_idle 확인 (region_game, conf=search_confidence)
     없음 → loop_delay → Loop Start
     있음 → 클릭
     loop_delay 대기 후 화면 재캡처 (grab_screen)
     speed3 감지 (conf=speed_confidence) → _key_routine() → Loop Start
     speed2 감지 (conf=speed_confidence) → _bou_conversion() → Loop Start
     speed 없음 → Loop Start
```

---

## 서브루틴

### _key_routine
```
key 탐색 (region_game)
  없음 → Loop Start 복귀
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

### _bou_conversion
```
myth_text_coord 클릭 (+step_delay)
화면 재캡처
bou 탐색 (conf=search_confidence, region_ui):
  없음 (파편 0개) → rclick(target) 일반변환
  있음 → bou 우측 (bx+5, by-20, 130×50) 영역에서 count_1/2/3 탐색 (conf=count_confidence)
    count 1~3 → rclick(target) 일반변환
    count 4+  → press 'a' 특수변환
```

### _normal_conversion  (내부 사용 용도로만 유지)
```
seal_idle 클릭 → target 우클릭 → Loop Start
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
- True 상태: ② 에서 seal 폴링 → speed2/3 확인 → 변환루트 진행

---

## 설정창 탭 구성
| 탭 | 내용 |
|---|---|
| 창 크기 | SC 창 해상도 |
| 좌표 설정 | A/B/C/M/ON 좌표 |
| F6 설정 | 채팅·식별코드·분기 |
| F9 설정 | 펫·28box 감시 |
| 고급1 | F9/F7 딜레이 |
| 고급2 | 이미지 매칭 정확도 (나머지/box/count/speed) |

### 이미지 매칭 정확도 키
| 키 | 기본값 | 적용 대상 |
|---|---|---|
| `search_confidence` | 0.85 | target_circle, seal_idle, key, bou 등 나머지 |
| `box28_confidence_set` | 0.97 | 26box / 28box |
| `count_confidence` | 0.85 | count_1 / count_2 / count_3 |
| `speed_confidence` | 0.85 | speed2 / speed3 |

_최종 업데이트: 2026-06-26 — _bou_conversion에 myth_text_coord 클릭 복원_
