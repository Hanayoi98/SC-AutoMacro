#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
좌표 측정 도우미
마우스를 원하는 위치에 올리면 좌표가 실시간 출력됩니다.
F12 누르면 현재 좌표를 config.json에 저장할 수 있습니다.
Ctrl+C 로 종료.
"""
import json, time, sys
import pyautogui
import keyboard

CONFIG_PATH = "config.json"
COORD_KEYS  = ["coord_a", "coord_b", "coord_c", "myth_text_coord"]
DESCRIPTIONS = {
    "coord_a":         "F7 마우스 루틴 - 더블클릭 지점 A",
    "coord_b":         "F7 마우스 루틴 - 더블클릭 지점 B",
    "coord_c":         "F7 마우스 루틴 - 싱글클릭 ×4 지점 C",
    "myth_text_coord": "변환 루트 - myth_text 확인용 클릭 좌표",
}

def load_cfg():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cfg(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def main():
    print("=" * 50)
    print("  좌표 측정 도우미")
    print("=" * 50)
    print("마우스를 원하는 위치에 올리세요.")
    print("F12 : 현재 좌표를 저장할 키에 할당")
    print("Ctrl+C : 종료\n")

    for i, key in enumerate(COORD_KEYS, 1):
        print(f"  [{i}] {key}  →  {DESCRIPTIONS[key]}")
    print()

    cfg = load_cfg()

    def save_coord():
        x, y = pyautogui.position()
        print(f"\n현재 좌표: ({x}, {y})")
        for i, k in enumerate(COORD_KEYS, 1):
            print(f"  [{i}] {k}")
        choice = input("저장할 번호 (1~4, 취소: Enter): ").strip()
        if choice in [str(i) for i in range(1, 5)]:
            k = COORD_KEYS[int(choice) - 1]
            cfg[k] = [x, y]
            save_cfg(cfg)
            print(f"  저장 완료: {k} = [{x}, {y}]")
        print()

    keyboard.add_hotkey("f12", save_coord)

    print("실시간 마우스 좌표:")
    try:
        while True:
            x, y = pyautogui.position()
            print(f"\r  X={x:4d}  Y={y:4d}  ", end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n종료")

if __name__ == "__main__":
    main()
