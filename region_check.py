"""
탐색 구역 시각화 도구
실행하면 현재 region_game / region_ui 구역을 화면에 3초간 표시합니다.
"""
import json, time, ctypes, ctypes.wintypes as wt, os

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
    cfg = json.load(f)

u32 = ctypes.windll.user32

SC_TITLES = ["starcraft", "brood war"]

def find_sc():
    found = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n+1)
            u32.GetWindowTextW(hwnd, buf, n+1)
            if any(s in buf.value.lower() for s in SC_TITLES):
                found.append(hwnd)
        return True
    u32.EnumWindows(CB(cb), 0)
    return found[0] if found else None

def get_rect(hwnd):
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right-r.left, r.bottom-r.top

hwnd = find_sc()
if not hwnd:
    print("[오류] 스타크래프트 창을 찾을 수 없습니다.")
    input("Enter로 종료...")
    exit()

wx, wy, ww, wh = get_rect(hwnd)
print(f"SC 창 위치: ({wx}, {wy})  크기: {ww}×{wh}")

gr = cfg.get("region_game", [0,0,0,0])
ur = cfg.get("region_ui",   [0,0,0,0])

abs_gr = (wx+gr[0], wy+gr[1], gr[2], gr[3])
abs_ur = (wx+ur[0], wy+ur[1], ur[2], ur[3])

print(f"region_game 절대좌표: {abs_gr}")
print(f"region_ui  절대좌표: {abs_ur}")

# 투명 오버레이 창으로 구역 표시
import tkinter as tk

root = tk.Tk()
root.overrideredirect(True)          # 타이틀바 없음
root.attributes("-topmost", True)
root.attributes("-transparentcolor", "black")
root.configure(bg="black")

sw = u32.GetSystemMetrics(0)
sh = u32.GetSystemMetrics(1)
root.geometry(f"{sw}x{sh}+0+0")

canvas = tk.Canvas(root, bg="black", highlightthickness=0)
canvas.pack(fill="both", expand=True)

# 노란 박스 (region_game)
x,y,w,h = abs_gr
canvas.create_rectangle(x,y,x+w,y+h, outline="#f9e2af", width=3)
canvas.create_text(x+5, y+5, anchor="nw",
    text=f"region_game  (target_circle, seal, key)",
    fill="#f9e2af", font=("Consolas",11,"bold"))

# 빨간 박스 (region_ui)
x,y,w,h = abs_ur
canvas.create_rectangle(x,y,x+w,y+h, outline="#f38ba8", width=3)
canvas.create_text(x+5, y+5, anchor="nw",
    text=f"region_ui  (speed, box, bou, myth, on)",
    fill="#f38ba8", font=("Consolas",11,"bold"))

# 3초 후 자동 닫힘
root.after(3000, root.destroy)
print("\n화면에 3초간 탐색 구역이 표시됩니다...")
root.mainloop()
print("완료. 구역이 맞지 않으면 config.json의 region_game / region_ui 값을 수정하세요.")
input("Enter로 종료...")
