#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StarCraft Auto Macro v1.0
이미지 인식 기반 스타크래프트 자동화 매크로

단축키
  F6  : 채팅 매크로 + 식별코드 입력 (→ f9_early_branch_on 시 F7 자동 실행)
  F7  : autosetting 대기 후 업그레이드/마우스 루틴
  F8  : @태초 채팅 전송
  F9  : 메인 루프 시작/정지 (토글)
  Ctrl+F12 : 매크로 종료
"""

import os
import sys
import json
import time
import logging
import threading
import subprocess
import queue
from typing import List, Optional, Tuple

# ──────────────────────────────────────────────────────────
# 패키지 자동 설치 (외부 라이브러리 import 전에 실행)
# ──────────────────────────────────────────────────────────
#
# ※ win32gui(pywin32)는 이 목록에서 제외
#   - pip install 후에도 추가 설정이 필요한 경우가 있어
#     import 실패 → 재시작 → 또 실패 → 무한 루프 유발
#   - 창 확인 기능은 선택 사항이므로 아래 try/except 로만 처리
#
_REQUIRED_PACKAGES = [
    # (import 이름,  pip 패키지 이름)
    ("cv2",          "opencv-python"),
    ("numpy",        "numpy"),
    ("keyboard",     "keyboard"),
    ("pyautogui",    "pyautogui"),
    ("pyperclip",    "pyperclip"),
    ("mss",          "mss"),
]


def _check_and_install() -> None:
    """미설치 패키지를 자동으로 pip install. 설치 후 재시작 없이 그대로 진행."""
    missing = []
    for mod_name, pkg_name in _REQUIRED_PACKAGES:
        try:
            __import__(mod_name)
        except ImportError:
            missing.append((mod_name, pkg_name))

    if not missing:
        return  # 모두 설치됨 → 바로 통과

    print("┌─────────────────────────────────────────────┐")
    print("│  필요 패키지 자동 설치를 시작합니다          │")
    print("└─────────────────────────────────────────────┘")
    print(f"  대상: {', '.join(p for _, p in missing)}\n")

    failed = []
    for mod_name, pkg_name in missing:
        print(f"  ▶ Installing {pkg_name} ...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pkg_name],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✓ 완료")
        else:
            print("✗ 실패")
            failed.append(pkg_name)
            if result.stderr:
                print(f"    오류: {result.stderr.strip()}")

    if failed:
        print(f"\n[오류] 다음 패키지 설치에 실패했습니다: {', '.join(failed)}")
        print("       수동으로 설치해주세요:")
        print(f"       pip install {' '.join(failed)}")
        input("\nEnter를 눌러 종료...")
        sys.exit(1)

    # ── 재시작 없이 그대로 진행 ──────────────────────────
    # _check_and_install()은 외부 import 이전에 실행되므로
    # pip 설치 직후 아래의 import cv2 등이 정상 동작함
    print("\n모든 패키지 설치 완료! 계속 진행합니다...\n")


_check_and_install()

# ──────────────────────────────────────────────────────────
# 외부 패키지 import (설치 보장 후)
# ──────────────────────────────────────────────────────────
import cv2
import numpy as np
import keyboard
import pyautogui
import pyperclip
from mss import mss

try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("[경고] pywin32 미설치 - 창 확인 기능 비활성화")

import tkinter as tk
from tkinter import messagebox
import tkinter.ttk as ttk

# ──────────────────────────────────────────────────────────
# 작업 디렉터리 고정
# ──────────────────────────────────────────────────────────
# 관리자 권한 실행 시 CWD 가 C:\Windows\System32 로 바뀌는 문제 방지.
# macro.py 가 있는 폴더를 기준 경로로 항상 고정한다.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(_BASE_DIR)

# ──────────────────────────────────────────────────────────
# 초기화
# ──────────────────────────────────────────────────────────
pyautogui.FAILSAFE = False
pyautogui.PAUSE    = 0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(_BASE_DIR, "macro.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("SC-Macro")

# ── UI 로그 큐 (스레드 → UI 안전 전달) ────────────────────
_log_queue: queue.Queue = queue.Queue(maxsize=500)

class _QueueHandler(logging.Handler):
    """로그를 큐에만 넣고 즉시 반환 (UI 업데이트는 0.5s 배치)"""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass  # 큐 가득 차도 루프에 영향 없음

_qh = _QueueHandler()
_qh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                   datefmt="%H:%M:%S"))
log.addHandler(_qh)

# ──────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(_BASE_DIR, "config", "config.json")
IMAGES_DIR  = os.path.join(_BASE_DIR, "images")
SC_TITLES = [
    "starcraft",      # StarCraft, StarCraft: Remastered, StarCraft: Brood War
    "brood war",      # Brood War (단독 창 제목)
    "스타크래프트",   # 한글 제목
]

DEFAULT_CONFIG: dict = {
    # ── 스펙 원본 설정값 ──
    "f6_chat_macro_on":    False,
    "id_code":             "985545",
    "f6_pet_upgrade":      "c, q10, w6, a10, s2, c, s5, c",
    "f6_final_action":     "w, s, r",
    "f9_pet_interval":     200,
    "f9_pet_upgrade":      "e3",
    "box28_confidence_set": 0.97,
    "f9_box28_monitor_on": True,
    "f9_early_branch_on":  True,
    "check_on_offset_x":   1324,
    "check_on_offset_y":   1056,
    "check_on_offset":     [1324, 1056],
    # ── 미확인 좌표 (직접 측정 후 입력) ──
    "coord_a":         [0, 0],
    "coord_b":         [0, 0],
    "coord_c":         [0, 0],
    "myth_text_coord": [0, 0],
    # ── 탐색 · 입력 튜닝 (F9 루프) ──
    "search_confidence": 0.85,
    "count_confidence":  0.85,
    "input_delay":       0.5,
    "loop_delay":        0.5,
    "mouse_move_dur":    0.5,
    "step_delay":        0.2,
    "key_speed_delay":   1.0,
    "window_size":       [0, 0],
    # ── F7 전용 딜레이 ──
    "f7_input_delay":    0.15,
    "f7_step_delay":     0.2,
    "f7_mouse_move_dur": 0.05,
}


# 문자열로 저장될 수 있는 숫자 키 목록
_NUM_KEYS = {
    "f9_pet_interval":     int,
    "box28_confidence_set": float,
    "check_on_offset_x":   int,
    "check_on_offset_y":   int,
    "search_confidence":   float,
    "count_confidence":    float,
    "input_delay":         float,
    "loop_delay":          float,
    "mouse_move_dur":      float,
    "step_delay":          float,
    "key_speed_delay":     float,
    "f7_input_delay":      float,
    "f7_step_delay":       float,
    "f7_mouse_move_dur":   float,
}

def _coerce_types(cfg: dict) -> dict:
    """config 값 중 문자열로 저장된 숫자를 실제 숫자로 변환"""
    for key, typ in _NUM_KEYS.items():
        if key in cfg and isinstance(cfg[key], str):
            try:
                cfg[key] = typ(cfg[key])
            except (ValueError, TypeError):
                pass
    return cfg

def load_config() -> dict:
    """config.json 로드, 없으면 기본값으로 생성"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        _coerce_types(cfg)          # 문자열 숫자 → 실제 숫자
        log.info("설정 로드: %s", CONFIG_PATH)
        return cfg
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    log.info("기본 config.json 생성 완료 - 좌표 등을 직접 입력하세요")
    return DEFAULT_CONFIG.copy()



# ──────────────────────────────────────────────────────────
# Windows 창 유틸 (ctypes 기반 - pywin32 불필요)
# ──────────────────────────────────────────────────────────
import ctypes
import ctypes.wintypes as _wt

_u32 = ctypes.windll.user32

def _sc_find_hwnd() -> Optional[int]:
    """SC_TITLES 에 해당하는 보이는 창의 hwnd 반환. 없으면 None."""
    found: list = []
    _CB = ctypes.WINFUNCTYPE(ctypes.c_bool, _wt.HWND, _wt.LPARAM)

    def _cb(hwnd, _):
        if _u32.IsWindowVisible(hwnd):
            n = _u32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                _u32.GetWindowTextW(hwnd, buf, n + 1)
                if any(s in buf.value.lower() for s in SC_TITLES):
                    found.append(hwnd)
        return True

    _u32.EnumWindows(_CB(_cb), 0)
    return found[0] if found else None

def _sc_get_rect(hwnd: int):
    """(x, y, w, h) 반환."""
    r = _wt.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top

def _sc_move(hwnd: int, w: int, h: int) -> None:
    """창 크기만 변경 (위치 유지)."""
    x, y, _, _ = _sc_get_rect(hwnd)
    _u32.MoveWindow(hwnd, x, y, w, h, True)

def _sc_foreground_hwnd() -> Optional[int]:
    """현재 포그라운드 창 hwnd."""
    return _u32.GetForegroundWindow() or None

def _get_window_title(hwnd: int) -> str:
    n = _u32.GetWindowTextLengthW(hwnd)
    if n == 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    _u32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


# ──────────────────────────────────────────────────────────
# SendInput 기반 유니코드 직접 입력 (한글 포함 모든 문자)
# 클립보드/Ctrl+V 대신 OS 레벨에서 직접 문자 주입
# ──────────────────────────────────────────────────────────
class _KbdInput(ctypes.Structure):
    _fields_ = [
        ("wVk",         ctypes.c_ushort),
        ("wScan",       ctypes.c_ushort),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),   # ULONG_PTR (32/64bit 대응)
    ]

class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg",    ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]

class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KbdInput), ("mi", _MouseInput), ("hi", _HardwareInput)]

class _Input(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_    = [("type", ctypes.c_ulong), ("_u", _InputUnion)]

_KINPUT = 1          # INPUT_KEYBOARD
_UNIC   = 0x0004     # KEYEVENTF_UNICODE
_KEYUP  = 0x0002     # KEYEVENTF_KEYUP

def _type_unicode(text: str, delay: float = 0.04) -> None:
    """
    SendInput + KEYEVENTF_UNICODE 로 한글 포함 모든 문자 직접 입력.
    클립보드/IME/Ctrl+V 불필요 — 게임 채팅창에서도 동작.
    """
    for ch in text:
        code = ord(ch)
        down = _Input(type=_KINPUT, ki=_KbdInput(wVk=0, wScan=code, dwFlags=_UNIC))
        up   = _Input(type=_KINPUT, ki=_KbdInput(wVk=0, wScan=code, dwFlags=_UNIC | _KEYUP))
        arr  = (_Input * 2)(down, up)
        ctypes.windll.user32.SendInput(2, arr, ctypes.sizeof(_Input))
        time.sleep(delay)

# ──────────────────────────────────────────────────────────
# 창 확인
# ──────────────────────────────────────────────────────────
def is_sc_active() -> bool:
    """스타크래프트가 포그라운드 창인지 확인 (ctypes 사용)"""
    try:
        hwnd = _sc_foreground_hwnd()
        if not hwnd:
            return True
        title = _get_window_title(hwnd).lower()
        return any(t in title for t in SC_TITLES)
    except Exception:
        return True


# ──────────────────────────────────────────────────────────
# 이미지 탐색기
# ──────────────────────────────────────────────────────────
class Finder:
    """
    mss(스크린샷) + OpenCV(템플릿 매칭) 기반 이미지 탐색기.
    images/ 디렉터리의 PNG/BMP/JPG 파일을 이름으로 조회.
    """

    def __init__(self, default_conf: float = 0.85) -> None:
        self._sct   = mss()
        self._cache: dict[str, np.ndarray] = {}
        self._conf  = default_conf

    # ── 내부 ──────────────────────────────
    def _load(self, name: str) -> Optional[np.ndarray]:
        if name in self._cache:
            return self._cache[name]
        for ext in (".png", ".bmp", ".jpg"):
            path = os.path.join(IMAGES_DIR, name + ext)
            if os.path.exists(path):
                img = cv2.imread(path)
                if img is not None:
                    self._cache[name] = img
                    return img
        log.warning("이미지 없음: images/%s.[png|bmp|jpg]", name)
        return None

    def _grab(self, region: Optional[Tuple] = None) -> np.ndarray:
        """region=(left, top, width, height) 또는 None(전체 화면)"""
        mon = (
            {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
            if region else self._sct.monitors[1]
        )
        raw = self._sct.grab(mon)
        return cv2.cvtColor(np.array(raw), cv2.COLOR_BGRA2BGR)

    # ── 화면 캡처 (루프당 1회 호출용) ────────
    def grab_screen(self, region: Optional[Tuple] = None) -> np.ndarray:
        """화면을 한 번 캡처해서 반환. 루프에서 이걸 공유하면 CPU 절약."""
        return self._grab(region)

    # ── 캡처된 화면에서 탐색 ───────────────
    def find_in(
        self,
        screen: np.ndarray,
        name: str,
        conf: Optional[float] = None,
        region: Optional[Tuple] = None,
    ) -> Optional[Tuple[int, int]]:
        """미리 캡처된 화면(screen)에서 탐색. 추가 캡처 없음."""
        tmpl = self._load(name)
        if tmpl is None:
            return None
        src = screen
        if region:
            x, y, w, h = region
            src = screen[y:y+h, x:x+w]
        th, tw = tmpl.shape[:2]
        res = cv2.matchTemplate(src, tmpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        c = conf if conf is not None else self._conf
        if maxv >= c:
            ox = region[0] if region else 0
            oy = region[1] if region else 0
            return (maxloc[0] + tw // 2 + ox, maxloc[1] + th // 2 + oy)
        return None

    def find_any_in(
        self,
        screen: np.ndarray,
        names: List[str],
        conf: Optional[float] = None,
        region: Optional[Tuple] = None,
    ) -> Optional[Tuple[str, int, int]]:
        """캡처된 화면에서 여러 이름 중 하나라도 발견 시 반환."""
        for n in names:
            p = self.find_in(screen, n, conf, region)
            if p:
                return (n, p[0], p[1])
        return None

    # ── 공개 메서드 ────────────────────────
    def find(
        self,
        name: str,
        conf: Optional[float] = None,
        region: Optional[Tuple] = None,
    ) -> Optional[Tuple[int, int]]:
        """이미지 탐색. 발견 시 중심 좌표 (x, y) 반환, 없으면 None."""
        tmpl = self._load(name)
        if tmpl is None:
            return None
        scr    = self._grab(region)
        h, w   = tmpl.shape[:2]
        result = cv2.matchTemplate(scr, tmpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(result)
        c  = float(conf if conf is not None else self._conf)
        if maxv >= c:
            ox = region[0] if region else 0
            oy = region[1] if region else 0
            return (maxloc[0] + w // 2 + ox, maxloc[1] + h // 2 + oy)
        return None

    def find_any(
        self,
        names: List[str],
        conf: Optional[float] = None,
        region: Optional[Tuple] = None,
    ) -> Optional[Tuple[str, int, int]]:
        """여러 이름 중 하나라도 발견 시 (이름, x, y) 반환"""
        for n in names:
            p = self.find(n, conf, region)
            if p:
                return (n, p[0], p[1])
        return None

    def wait(
        self,
        name: str,
        conf: Optional[float] = None,
        timeout: Optional[float] = None,
        interval: float = 0.3,
        stop_event: Optional[threading.Event] = None,
        region: Optional[Tuple] = None,
    ) -> Optional[Tuple[int, int]]:
        """이미지가 나타날 때까지 대기. 발견 시 좌표, 타임아웃/중단 시 None."""
        t0 = time.time()
        while True:
            p = self.find(name, conf, region)
            if p:
                return p
            if stop_event and stop_event.is_set():
                return None
            if timeout and time.time() - t0 > timeout:
                return None
            time.sleep(interval)

    def wait_any(
        self,
        names: List[str],
        conf: Optional[float] = None,
        timeout: Optional[float] = None,
        interval: float = 0.3,
        stop_event: Optional[threading.Event] = None,
        region: Optional[Tuple] = None,
    ) -> Optional[Tuple[str, int, int]]:
        """여러 이미지 중 하나가 나타날 때까지 대기"""
        t0 = time.time()
        while True:
            r = self.find_any(names, conf, region)
            if r:
                return r
            if stop_event and stop_event.is_set():
                return None
            if timeout and time.time() - t0 > timeout:
                return None
            time.sleep(interval)


# ──────────────────────────────────────────────────────────
# 입력 핸들러
# ──────────────────────────────────────────────────────────
class Input:
    """키보드 · 마우스 입력 래퍼"""

    def __init__(self, delay: float = 0.05, mouse_dur: float = 0.08) -> None:
        self.delay     = delay
        self.mouse_dur = mouse_dur

    # ── 문자열 파싱 ──────────────────────
    @staticmethod
    def parse(s: str) -> List[str]:
        """
        'a3, c, q10' → ['a','a','a','c','q','q','q','q','q','q','q','q','q','q']
        규칙: 문자(들)+숫자 → 해당 문자를 숫자만큼 반복
        """
        out: List[str] = []
        for token in s.split(","):
            token = token.strip()
            if not token:
                continue
            i = 0
            while i < len(token) and not token[i].isdigit():
                i += 1
            ch  = token[:i]
            cnt = int(token[i:]) if i < len(token) else 1
            out.extend([ch] * cnt)
        return out

    def type_seq(self, s: str) -> None:
        """입력 문자열 실행 (게임 단축키 시퀀스)"""
        if not s:
            return
        for ch in self.parse(s):
            keyboard.press_and_release(ch)
            time.sleep(self.delay)

    def press(self, key: str, d: Optional[float] = None) -> None:
        keyboard.press_and_release(key)
        time.sleep(d if d is not None else self.delay)

    def paste_text(self, text: str) -> None:
        """
        SendInput + KEYEVENTF_UNICODE 로 한글 포함 모든 문자 직접 입력.
        StarCraft 채팅창에서 Ctrl+V 가 동작하지 않는 문제 해결.
        """
        _type_unicode(text, delay=self.delay)

    # ── 마우스 ───────────────────────────
    def move(self, x: int, y: int, dur: Optional[float] = None) -> None:
        pyautogui.moveTo(x, y, duration=dur if dur is not None else self.mouse_dur)

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              d: Optional[float] = None) -> None:
        if x is not None:
            pyautogui.click(x, y)
        else:
            pyautogui.click()
        time.sleep(d if d is not None else self.delay)

    def rclick(self, x: Optional[int] = None, y: Optional[int] = None,
               d: Optional[float] = None) -> None:
        if x is not None:
            pyautogui.rightClick(x, y)
        else:
            pyautogui.rightClick()
        time.sleep(d if d is not None else self.delay)

    def dclick(self, x: Optional[int] = None, y: Optional[int] = None,
               d: Optional[float] = None) -> None:
        if x is not None:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.doubleClick()
        time.sleep(d if d is not None else self.delay)



# ──────────────────────────────────────────────────────────
# UI  (메인창 + 설정창)
# ──────────────────────────────────────────────────────────
class SettingsWindow:
    """설정 창 (Toplevel) - 모든 설정값 편집"""

    C_BG = "#1e1e2e"; C_BG2 = "#313244"; C_BG3 = "#45475a"
    C_FG = "#cdd6f4"; C_FG2 = "#a6adc8"
    C_ACC = "#89b4fa"; C_GREEN = "#a6e3a1"; C_RED = "#f38ba8"
    FONT  = ("Malgun Gothic", 9)
    FONTB = ("Malgun Gothic", 9, "bold")

    COORD_KEYS = [
        ("A",   "coord_a",          "F7 마우스 A  (더블클릭)"),
        ("B",   "coord_b",          "F7 마우스 B  (더블클릭)"),
        ("C",   "coord_c",          "F7 마우스 C  (싱글클릭 ×4)"),
        ("M",   "myth_text_coord",  "변환 루트  myth_text 클릭"),
        ("ON",  "check_on_offset",  "28box  ON/OFF 확인 좌표"),
    ]
    SC_PRESETS = [("640×480",640,480),("800×600",800,600),("1024×768",1024,768)]

    def __init__(self, macro: "Macro", parent: tk.Tk) -> None:
        self.macro = macro
        self.cfg   = macro.cfg
        self._capturing = False
        self._coord_sv: dict[str, tk.StringVar] = {}
        self._status_sv = tk.StringVar(value="")

        self.win = tk.Toplevel(parent)
        self.win.title("SC Auto Macro — 설정")
        self.win.configure(bg=self.C_BG)
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.win.withdraw)

        nb = tk.ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._tab_window(nb)
        self._tab_coords(nb)
        self._tab_f6(nb)
        self._tab_f9(nb)
        self._tab_advanced1(nb)
        self._tab_advanced2(nb)

        # 저장 버튼
        self._btn(self.win, "  저장  ", self._save,
                  bg=self.C_GREEN, fg="#1e1e2e").pack(pady=(0,8))
        self._schedule_sc_refresh()

    # ── 탭 1: 창 크기 ────────────────────────────
    def _tab_window(self, nb):
        f = self._frame(nb); nb.add(f, text=" 창 크기 ")
        self._lbl(f, "[ 게임 창 크기  (4:3 비율) ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(8,2), padx=10)
        self._sc_size_sv = tk.StringVar(value="탐색 중...")
        self._lbl(f, "", sv=self._sc_size_sv, fg=self.C_FG2).pack(anchor="w", padx=10)

        row = tk.Frame(f, bg=self.C_BG); row.pack(anchor="w", padx=10, pady=6)
        self._lbl(row, "너비:").pack(side="left")
        self._w_var = tk.StringVar(value="800")
        tk.Entry(row, textvariable=self._w_var, width=5, **self._entry_kw()).pack(side="left", padx=(4,10))
        self._lbl(row, "높이:").pack(side="left")
        self._h_var = tk.StringVar(value="600")
        tk.Entry(row, textvariable=self._h_var, width=5, **self._entry_kw()).pack(side="left", padx=(4,12))
        self._btn(row, "적용", self._apply_size).pack(side="left")

        def _ow(*_):
            try: self._h_var.set(str(round(int(self._w_var.get())*3//4)))
            except: pass
        self._w_var.trace_add("write", _ow)

        pr = tk.Frame(f, bg=self.C_BG); pr.pack(anchor="w", padx=10, pady=(0,8))
        self._lbl(pr, "프리셋: ").pack(side="left")
        for lbl,w,h in self.SC_PRESETS:
            self._btn(pr, lbl, (lambda ww=w,hh=h: (self._w_var.set(str(ww)), self._h_var.set(str(hh)), self._apply_size()))).pack(side="left", padx=2)

    # ── 탭 2: 좌표 ───────────────────────────────
    def _tab_coords(self, nb):
        f = self._frame(nb); nb.add(f, text=" 좌표 설정 ")
        self._lbl(f, "[ 좌표 설정 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(8,2), padx=10)
        self._lbl(f, "버튼 클릭 → 창 최소화 → 2초 후 마우스 위치 자동 저장", fg=self.C_FG2).pack(anchor="w", padx=10)
        self._lbl(f, "", sv=self._status_sv, fg=self.C_RED).pack(anchor="w", padx=10, pady=(2,6))

        for btn_name, cfg_key, desc in self.COORD_KEYS:
            val = self.cfg.get(cfg_key, [0,0])
            sv  = tk.StringVar(value=f"({val[0]}, {val[1]})")
            self._coord_sv[cfg_key] = sv
            row = tk.Frame(f, bg=self.C_BG); row.pack(fill="x", padx=10, pady=2)
            self._btn(row, f"  {btn_name}  ", lambda k=cfg_key: self._start_capture(k), width=4).pack(side="left")
            tk.Label(row, textvariable=sv, font=self.FONT, bg=self.C_BG, fg=self.C_ACC, width=14, anchor="w").pack(side="left", padx=6)
            self._lbl(row, desc, fg=self.C_FG2).pack(side="left")

    # ── 탭 3: F6 설정 ────────────────────────────
    def _tab_f6(self, nb):
        f = self._frame(nb); nb.add(f, text=" F6 설정 ")
        rows = [
            ("식별코드",        "id_code",          "str"),
            ("F6 펫 업그레이드","f6_pet_upgrade",    "str"),
            ("F6 마무리 동작",  "f6_final_action",   "str"),
            ("채팅 매크로 사용","f6_chat_macro_on",  "bool"),
            ("F7 자동 실행",    "f9_early_branch_on","bool"),
        ]
        self._cfg_rows(f, rows)

    # ── 탭 4: F9 설정 ────────────────────────────
    def _tab_f9(self, nb):
        f = self._frame(nb); nb.add(f, text=" F9 설정 ")
        rows = [
            ("펫 업그레이드 키",    "f9_pet_upgrade",      "str"),
            ("펫 업그레이드 주기(초)","f9_pet_interval",   "num"),
            ("28box 감시",          "f9_box28_monitor_on", "bool"),
        ]
        self._cfg_rows(f, rows)

    # ── 탭 5: 고급1 (딜레이) ─────────────────────
    def _tab_advanced1(self, nb):
        f = self._frame(nb); nb.add(f, text=" 고급1 ")
        self._lbl(f, "[ F9 루프 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(8,2), padx=10)
        rows_f9 = [
            ("키 입력 딜레이(초)",  "input_delay",    "num"),
            ("동작 간 딜레이(초)",  "step_delay",     "num"),
            ("루프 딜레이(초)",     "loop_delay",     "num"),
            ("마우스 이동 시간(초)","mouse_move_dur", "num"),
            ("열쇠 반영 대기(초)",  "key_speed_delay","num"),
        ]
        self._cfg_rows(f, rows_f9)
        self._lbl(f, "[ F7 autosetting ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(10,2), padx=10)
        rows_f7 = [
            ("키 입력 딜레이(초)",  "f7_input_delay",   "num"),
            ("동작 간 딜레이(초)",  "f7_step_delay",    "num"),
            ("마우스 이동 시간(초)","f7_mouse_move_dur","num"),
        ]
        self._cfg_rows(f, rows_f7)

    # ── 탭 6: 고급2 (이미지 매칭 정확도) ─────────
    def _tab_advanced2(self, nb):
        f = self._frame(nb); nb.add(f, text=" 고급2 ")
        self._lbl(f, "[ 이미지 매칭 정확도 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(8,2), padx=10)
        rows = [
            ("그 외 나머지 (0~1)", "search_confidence",   "num"),
            ("box 정확도 (0~1)",   "box28_confidence_set","num"),
            ("count 정확도 (0~1)", "count_confidence",    "num"),
        ]
        self._cfg_rows(f, rows)

    # ── 공통: config 행 생성 ─────────────────────
    def _cfg_rows(self, parent, rows):
        self._sv_map = getattr(self, "_sv_map", {})
        for label, key, kind in rows:
            row = tk.Frame(parent, bg=self.C_BG); row.pack(fill="x", padx=10, pady=4)
            self._lbl(row, label, width=20, anchor="w").pack(side="left")
            if kind == "bool":
                val = self.cfg.get(key, False)
                sv  = tk.BooleanVar(value=bool(val))
                self._sv_map[key] = ("bool", sv)
                tk.Checkbutton(row, variable=sv, bg=self.C_BG, fg=self.C_FG,
                               selectcolor=self.C_BG2, activebackground=self.C_BG,
                               font=self.FONT).pack(side="left")
            else:
                val = self.cfg.get(key, "")
                sv  = tk.StringVar(value=str(val))
                self._sv_map[key] = ("str", sv)
                w = 8 if kind == "num" else 28
                tk.Entry(row, textvariable=sv, width=w, **self._entry_kw()).pack(side="left")

    # ── 저장 ─────────────────────────────────────
    def _save(self):
        sv_map = getattr(self, "_sv_map", {})
        for key, (kind, sv) in sv_map.items():
            try:
                if kind == "bool":
                    self.cfg[key] = sv.get()
                elif kind == "str":
                    self.cfg[key] = sv.get()
                else:
                    self.cfg[key] = float(sv.get()) if "." in sv.get() else int(sv.get())
            except Exception:
                pass
        self.macro.save_config()
        self.win.withdraw()   # 저장 후 설정창 자동 닫기

    # ── SC 창 탐색 ────────────────────────────────
    def _find_sc_hwnd(self): return _sc_find_hwnd()

    def _schedule_sc_refresh(self):
        hwnd = self._find_sc_hwnd()
        if hwnd:
            try:
                _, _, w, h = _sc_get_rect(hwnd)
                t = _get_window_title(hwnd)
                self._sc_size_sv.set(f"[{t}]  {w} × {h}")
            except: self._sc_size_sv.set("창 크기 읽기 실패")
        else:
            self._sc_size_sv.set("스타크래프트 창을 찾을 수 없음")
        self.win.after(2000, self._schedule_sc_refresh)

    def _apply_size(self):
        hwnd = self._find_sc_hwnd()
        if not hwnd:
            messagebox.showwarning("경고", "스타크래프트 창을 찾을 수 없습니다.\n게임을 먼저 실행하세요.", parent=self.win)
            return
        try:
            w = int(self._w_var.get()); h = int(self._h_var.get())
            _sc_move(hwnd, w, h)
            t = _get_window_title(hwnd)
            self._sc_size_sv.set(f"[{t}]  {w} × {h}")
            log.info("SC 창 크기 변경: %d × %d", w, h)
            # 적용된 크기를 config에 저장
            self.cfg["window_size"] = [w, h]
            self.macro.save_config()
            log.info("window_size 저장: %d × %d", w, h)
        except Exception as e:
            messagebox.showerror("오류", str(e), parent=self.win)

    # ── 좌표 캡처 ────────────────────────────────
    def _start_capture(self, cfg_key):
        if self._capturing: return
        self._capturing = True
        names = {"coord_a":"A","coord_b":"B","coord_c":"C","myth_text_coord":"M"}
        name = names.get(cfg_key, cfg_key)
        self._status_sv.set(f"[{name}] 창 최소화 후 2초 뒤 마우스 위치 저장...")
        self.win.update()
        self.win.iconify()
        def _wait():
            time.sleep(2.0)
            x, y = pyautogui.position()
            self.win.after(0, lambda: self._finish_capture(cfg_key, name, x, y))
        threading.Thread(target=_wait, daemon=True).start()

    def _finish_capture(self, cfg_key, name, x, y):
        self.cfg[cfg_key] = [x, y]
        if cfg_key in self._coord_sv:
            self._coord_sv[cfg_key].set(f"({x}, {y})")
        self._status_sv.set(f"✓ [{name}] 저장: ({x}, {y})")
        self.macro.save_config()
        self.win.deiconify()
        self._capturing = False

    # ── 위젯 헬퍼 ────────────────────────────────
    def _frame(self, parent):
        return tk.Frame(parent, bg=self.C_BG, padx=4, pady=4)

    def _lbl(self, parent, text="", sv=None, fg=None, bold=False, **kw):
        font = self.FONTB if bold else self.FONT
        if sv:
            return tk.Label(parent, textvariable=sv, font=font, bg=self.C_BG, fg=fg or self.C_FG, **kw)
        return tk.Label(parent, text=text, font=font, bg=self.C_BG, fg=fg or self.C_FG, **kw)

    def _btn(self, parent, text, cmd, width=None, bg=None, fg=None):
        return tk.Button(parent, text=text, command=cmd, font=self.FONT,
                         bg=bg or self.C_BG2, fg=fg or self.C_FG,
                         relief="flat", padx=8, pady=3,
                         activebackground=self.C_BG3,
                         width=width or 0)

    def _entry_kw(self):
        return dict(bg=self.C_BG2, fg=self.C_FG, insertbackground=self.C_FG,
                    font=self.FONT, relief="flat", bd=3)

    def show(self):
        self.win.deiconify()
        self.win.lift()


# ──────────────────────────────────────────────────────────
class ConfigUI:
    """메인 창 — 간결한 상태 표시 + F9 제어 + 설정 버튼"""

    C_BG = "#1e1e2e"; C_BG2 = "#313244"; C_BG3 = "#45475a"
    C_FG = "#cdd6f4"; C_FG2 = "#a6adc8"
    C_ACC = "#89b4fa"; C_GREEN = "#a6e3a1"; C_RED = "#f38ba8"
    FONT  = ("Malgun Gothic", 9)
    FONTB = ("Malgun Gothic", 10, "bold")

    F_DESC = [
        ("F6", "채팅 (@자동1) + 식별코드 입력"),
        ("F7", "autosetting 대기 → 펫 업그레이드 → 마우스 루틴"),
        ("F8", "@태초 채팅 전송"),
        ("F9", "메인 루프  시작 / 정지  (토글)"),
    ]

    def __init__(self, macro: "Macro") -> None:
        self.macro = macro
        self.root  = tk.Tk()
        self._settings: Optional[SettingsWindow] = None
        self._build()
        self._poll()

    def _build(self):
        r = self.root
        r.title("SC Auto Macro")
        r.configure(bg=self.C_BG)
        r.attributes("-topmost", True)
        r.resizable(False, False)
        r.protocol("WM_DELETE_WINDOW", self._quit)

        # ── 헤더 ─────────────────────────
        tk.Label(r, text="SC Auto Macro  v1.0", font=("Malgun Gothic",12,"bold"),
                 bg=self.C_BG, fg=self.C_ACC).pack(pady=(12,4))

        # ── 상태 표시 ─────────────────────
        self._status_sv = tk.StringVar(value="○  정지")
        tk.Label(r, textvariable=self._status_sv, font=self.FONTB,
                 bg=self.C_BG, fg=self.C_FG2, width=20).pack(pady=2)

        tk.Frame(r, height=1, bg=self.C_BG3).pack(fill="x", padx=12, pady=6)

        # ── 단축키 설명 ───────────────────
        for key, desc in self.F_DESC:
            row = tk.Frame(r, bg=self.C_BG); row.pack(fill="x", padx=16, pady=1)
            tk.Label(row, text=key, font=self.FONTB, bg=self.C_BG,
                     fg=self.C_ACC, width=4, anchor="w").pack(side="left")
            tk.Label(row, text=desc, font=self.FONT, bg=self.C_BG,
                     fg=self.C_FG2, anchor="w").pack(side="left")

        tk.Frame(r, height=1, bg=self.C_BG3).pack(fill="x", padx=12, pady=8)

        # ── 버튼 영역 ─────────────────────
        bot = tk.Frame(r, bg=self.C_BG); bot.pack(pady=(0,12), padx=16)

        self._f9_btn = tk.Button(bot, text="▶  F9 시작", font=self.FONTB,
                                  bg=self.C_GREEN, fg="#1e1e2e",
                                  relief="flat", padx=14, pady=6,
                                  activebackground="#94e2a1",
                                  command=self._toggle_f9)
        self._f9_btn.pack(side="left", padx=(0,8))

        tk.Button(bot, text="⚙  설정", font=self.FONT,
                  bg=self.C_BG2, fg=self.C_FG,
                  relief="flat", padx=12, pady=6,
                  activebackground=self.C_BG3,
                  command=self._open_settings).pack(side="left", padx=(0,8))

        tk.Button(bot, text="🖥  해상도 적용", font=self.FONT,
                  bg=self.C_BG2, fg=self.C_ACC,
                  relief="flat", padx=12, pady=6,
                  activebackground=self.C_BG3,
                  command=self._apply_resolution).pack(side="left", padx=(0,8))

        tk.Button(bot, text="✕  종료", font=self.FONT,
                  bg=self.C_BG2, fg=self.C_RED,
                  relief="flat", padx=12, pady=6,
                  activebackground=self.C_BG3,
                  command=self._quit).pack(side="left")

        # ── 로그 패널 (토글) ───────────────
        tk.Frame(r, height=1, bg=self.C_BG3).pack(fill="x", padx=12, pady=(4,0))

        log_hdr = tk.Frame(r, bg=self.C_BG); log_hdr.pack(fill="x", padx=12, pady=(4,0))
        tk.Label(log_hdr, text="이벤트 로그", font=self.FONT,
                 bg=self.C_BG, fg=self.C_FG2).pack(side="left")
        self._log_toggle_sv = tk.StringVar(value="▼ 펼치기")
        tk.Button(log_hdr, textvariable=self._log_toggle_sv, font=self.FONT,
                  bg=self.C_BG, fg=self.C_ACC, relief="flat",
                  command=self._toggle_log).pack(side="right")

        # 로그 텍스트 영역 (기본 숨김)
        self._log_frame = tk.Frame(r, bg=self.C_BG)
        self._log_text = tk.Text(
            self._log_frame,
            height=10, width=62,
            bg="#11111b", fg="#a6adc8",
            font=("Consolas", 8),
            relief="flat", state="disabled",
            wrap="none",
        )
        sb_y = tk.Scrollbar(self._log_frame, command=self._log_text.yview)
        sb_x = tk.Scrollbar(self._log_frame, orient="horizontal",
                             command=self._log_text.xview)
        self._log_text.configure(yscrollcommand=sb_y.set,
                                  xscrollcommand=sb_x.set)
        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        self._log_text.pack(fill="both", expand=True)
        # 처음엔 숨김
        self._log_visible = False
        tk.Button(r, text="로그 지우기", font=("Malgun Gothic",8),
                  bg=self.C_BG, fg=self.C_FG2, relief="flat",
                  command=self._clear_log).pack(pady=(0,8))

    def _toggle_f9(self):
        threading.Thread(target=self.macro.f9, daemon=True).start()

    def _open_settings(self):
        if self._settings is None:
            self._settings = SettingsWindow(self.macro, self.root)
        else:
            self._settings.show()

    def _poll(self):
        """500ms 마다 F9 상태 + 로그 큐 일괄 갱신"""
        # F9 상태
        if self.macro._f9thr and self.macro._f9thr.is_alive():
            self._status_sv.set("●  실행 중")
            self._f9_btn.configure(text="■  F9 정지", bg=self.C_RED, fg="#1e1e2e",
                                   activebackground="#f5a0b0")
        else:
            self._status_sv.set("○  정지")
            self._f9_btn.configure(text="▶  F9 시작", bg=self.C_GREEN, fg="#1e1e2e",
                                   activebackground="#94e2a1")

        # 로그 큐 → 텍스트 위젯 (로그 패널이 열려 있을 때만)
        if self._log_visible:
            lines = []
            try:
                while True:
                    lines.append(_log_queue.get_nowait())
            except queue.Empty:
                pass
            if lines:
                self._log_text.configure(state="normal")
                self._log_text.insert("end", chr(10).join(lines) + chr(10))
                # 최대 300줄 유지 (메모리 절약)
                total = int(self._log_text.index("end-1c").split(".")[0])
                if total > 300:
                    self._log_text.delete("1.0", f"{total-300}.0")
                self._log_text.see("end")
                self._log_text.configure(state="disabled")

        self.root.after(500, self._poll)

    def _toggle_log(self):
        if self._log_visible:
            self._log_frame.pack_forget()
            self._log_toggle_sv.set("▼ 펼치기")
            self._log_visible = False
            self.root.resizable(False, False)
        else:
            self._log_frame.pack(fill="x", padx=8, pady=(0,4))
            self._log_toggle_sv.set("▲ 접기")
            self._log_visible = True
            self.root.resizable(True, True)
            # 패널 열릴 때 쌓인 로그 즉시 표시
            lines = []
            try:
                while True:
                    lines.append(_log_queue.get_nowait())
            except queue.Empty:
                pass
            if lines:
                self._log_text.configure(state="normal")
                self._log_text.insert("end", chr(10).join(lines) + chr(10))
                self._log_text.see("end")
                self._log_text.configure(state="disabled")

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        # 큐도 비움
        try:
            while True: _log_queue.get_nowait()
        except queue.Empty: pass

    def _apply_resolution(self):
        """저장된 window_size로 SC 창 크기 즉시 적용"""
        self.macro._auto_resize_window()
        # 상태 표시 업데이트
        target = self.macro.cfg.get("window_size", [0, 0])
        if target and target[0] != 0:
            self._status_sv.set(f"해상도 적용: {target[0]}×{target[1]}")
            self.root.after(2000, lambda: self._status_sv.set(
                "●  실행 중" if (self.macro._f9thr and self.macro._f9thr.is_alive())
                else "○  정지"))
        else:
            self._status_sv.set("저장된 해상도 없음 (설정에서 적용 필요)")
            self.root.after(2000, lambda: self._status_sv.set("○  정지"))

    def _quit(self):
        log.info("매크로 종료")
        import os
        os._exit(0)

    def toggle(self):
        try:
            if self.root.state() == "withdrawn":
                self.root.deiconify(); self.root.lift()
            else:
                self.root.withdraw()
        except Exception: pass

    def run(self): self.root.mainloop()

# ──────────────────────────────────────────────────────────
# 메인 매크로
# ──────────────────────────────────────────────────────────
class Macro:
    def __init__(self) -> None:
        self.cfg    = load_config()
        self.finder = Finder(self.cfg.get("search_confidence", 0.85))
        self.inp    = Input(
            delay     = self.cfg.get("input_delay", 0.5),
            mouse_dur = self.cfg.get("mouse_move_dur", 0.5),
        )
        self.inp_f7 = Input(
            delay     = self.cfg.get("f7_input_delay", 0.15),
            mouse_dur = self.cfg.get("f7_mouse_move_dur", 0.05),
        )
        self._stop    = threading.Event()
        self._f9thr:  Optional[threading.Thread] = None
        self._pet_t   = 0.0
        self.ui: Optional[ConfigUI] = None   # 설정 UI (start() 에서 생성)

    def save_config(self) -> None:
        """현재 cfg 를 config.json 에 저장 + 딜레이 즉시 반영"""
        _coerce_types(self.cfg)     # 설정창 Entry값이 str일 수 있음
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, indent=2, ensure_ascii=False)
        # 저장 즉시 Input 객체에도 반영 (재시작 불필요)
        self.inp.delay        = float(self.cfg.get("input_delay",      0.5))
        self.inp.mouse_dur    = float(self.cfg.get("mouse_move_dur",   0.5))
        self.inp_f7.delay     = float(self.cfg.get("f7_input_delay",   0.15))
        self.inp_f7.mouse_dur = float(self.cfg.get("f7_mouse_move_dur",0.05))
        log.info("config.json 저장 완료 (input_delay=%.2f, f7_input_delay=%.2f)",
                 self.inp.delay, self.inp_f7.delay)

    # ── 창 크기 자동 조정 ────────────────
    def _auto_resize_window(self) -> None:
        """저장된 window_size 와 현재 SC 창 크기 비교, 다르면 자동 조정"""
        target = self.cfg.get("window_size", [0, 0])
        if not target or target[0] == 0 or target[1] == 0:
            return  # 저장된 크기 없음 → 스킵
        tw, th = int(target[0]), int(target[1])
        hwnd = _sc_find_hwnd()
        if not hwnd:
            log.warning("창 크기 자동 조정: SC 창을 찾을 수 없음")
            return
        _, _, cw, ch = _sc_get_rect(hwnd)
        if cw != tw or ch != th:
            log.info("창 크기 불일치 (%d×%d) → (%d×%d) 자동 조정", cw, ch, tw, th)
            _sc_move(hwnd, tw, th)
            time.sleep(0.3)  # 창 조정 후 안정화 대기
        else:
            log.info("창 크기 일치: %d×%d", cw, ch)

    # ── 좌표 변환 헬퍼 ───────────────────
    def _abs_region(self, cfg_key: str) -> Optional[Tuple]:
        """window-relative [x,y,w,h] → 절대 화면 좌표 (탐색 구간용).
        설정 안 됐거나 창 못 찾으면 None → 전체 화면 탐색 fallback."""
        rel = self.cfg.get(cfg_key)
        if not rel or len(rel) < 4 or rel[2] == 0 or rel[3] == 0:
            return None
        hwnd = _sc_find_hwnd()
        if not hwnd:
            return None
        try:
            wx, wy, _, _ = _sc_get_rect(hwnd)
            return (wx + rel[0], wy + rel[1], rel[2], rel[3])
        except Exception:
            return None

    def _abs_coord(self, cfg_key: str, default=None) -> List[int]:
        """window-relative [x,y] → 절대 화면 좌표 (마우스 클릭용)."""
        rel = self.cfg.get(cfg_key, default or [0, 0])
        hwnd = _sc_find_hwnd()
        if hwnd:
            try:
                wx, wy, _, _ = _sc_get_rect(hwnd)
                return [rel[0] + wx, rel[1] + wy]
            except Exception:
                pass
        return list(rel)

    def _abs_xy(self, x_key: str, y_key: str) -> Tuple[int, int]:
        """check_on_offset_x/y 같은 별도 키 → 절대 화면 좌표."""
        rx = self.cfg.get(x_key, 0)
        ry = self.cfg.get(y_key, 0)
        hwnd = _sc_find_hwnd()
        if hwnd:
            try:
                wx, wy, _, _ = _sc_get_rect(hwnd)
                return wx + int(rx), wy + int(ry)
            except Exception:
                pass
        return int(rx), int(ry)

    # ─────────────────────────────────────
    # F6: 채팅 + 식별코드 입력
    # ─────────────────────────────────────
    def f6(self) -> None:
        if not is_sc_active():
            log.warning("F6: 스타크래프트 비활성 - 무시")
            return
        log.info("═══ F6 시작 ═══")
        try:
            chat_on = self.cfg.get("f6_chat_macro_on", True)

            if chat_on:
                # ① 채팅창 열기
                self.inp.press("enter")              # input_delay 후

                # ② @자동1 입력 (SendInput 유니코드 직접 주입)
                self.inp.paste_text("@자동1")        # 글자당 input_delay

                # ③ 전송
                self.inp.press("enter")              # input_delay 후
                time.sleep(self.cfg.get("step_delay", 0.2))                     # 전송 후 고정 대기

            # ④ 0: 부대지정 호출 (게임 단축키)
            self.inp.press("0")                     # input_delay 후
            time.sleep(self.cfg.get("step_delay", 0.2))                         # UI 열릴 때까지 고정 대기

            # ⑤ 식별코드 입력 (ENTER 없음 / SendInput 유니코드 직접 주입)
            _type_unicode(str(self.cfg["id_code"]), delay=self.inp.delay)

            log.info("F6 완료 (채팅매크로=%s)", chat_on)

            # ⑥ 자동 분기 → F7 실행
            if self.cfg.get("f9_early_branch_on", False):
                log.info("→ 자동 분기: F7 실행")
                self.f7()

        except Exception as e:
            log.error("F6 오류: %s", e, exc_info=True)

    # ─────────────────────────────────────
    # F7: autosetting 대기 → 업그레이드 → 마우스 루틴
    # ─────────────────────────────────────
    def f7(self) -> None:
        if not is_sc_active():
            log.warning("F7: 스타크래프트 비활성 - 무시")
            return
        log.info("═══ F7 시작 ═══")
        try:
            # key 이미지가 화면에 나타날 때까지 대기 (F9 stop 이벤트와 무관)
            log.info("key 이미지 대기 중...")
            gr = self._abs_region("region_game")
            pos = self.finder.wait("key", region=gr)   # stop_event 없음 → 발견까지 무한 대기
            if not pos:
                log.warning("key 발견 실패")
                return
            log.info("key 발견: %s", pos)

            sd = self.cfg.get("f7_step_delay", 0.2)
            self.inp_f7.press("f2");  time.sleep(sd)
            self.inp_f7.press("2");   time.sleep(sd)

            # 초반 펫 업그레이드 문자열
            self.inp_f7.type_seq(self.cfg.get("f6_pet_upgrade", ""))
            time.sleep(sd)

            self.inp_f7.press("3");   time.sleep(sd)

            # 마무리 동작 문자열
            self.inp_f7.type_seq(self.cfg.get("f6_final_action", ""))
            time.sleep(sd)

            # 마우스 루틴
            self._f7_mouse_routine()
            log.info("F7 완료")

        except Exception as e:
            log.error("F7 오류: %s", e, exc_info=True)

    def _f7_mouse_routine(self) -> None:
        """
        좌표 A: 더블클릭 → Q
        좌표 B: 더블클릭 → Q
        좌표 C: 싱글클릭 + Q  ×4
        (좌표는 config.json의 coord_a/b/c 에 설정)
        """
        ca = self.cfg.get("coord_a", [0, 0])
        cb = self.cfg.get("coord_b", [0, 0])
        cc = self.cfg.get("coord_c", [0, 0])

        if ca == [0, 0] or cb == [0, 0] or cc == [0, 0]:
            log.warning("F7 마우스 루틴: 좌표 A/B/C 미설정 (config.json 확인)")

        _D = 0.45  # 클릭 간 고정 딜레이 (설정값과 무관)

        # 좌표 A
        self.inp_f7.move(*ca)
        self.inp_f7.dclick(d=_D)
        self.inp_f7.press("q", d=_D)

        # 좌표 B
        self.inp_f7.move(*cb)
        self.inp_f7.dclick(d=_D)
        self.inp_f7.press("q", d=_D)

        # 좌표 C (싱글클릭 × 4)
        self.inp_f7.move(*cc)
        for _ in range(4):
            self.inp_f7.click(d=_D)
            self.inp_f7.press("q", d=_D)

    # ─────────────────────────────────────
    # F8: @태초 전송
    # ─────────────────────────────────────
    def f8(self) -> None:
        if not is_sc_active():
            log.warning("F8: 스타크래프트 비활성 - 무시")
            return
        log.info("═══ F8 ═══")
        try:
            self.inp.press("enter", d=0.01)
            _type_unicode("@태초", delay=0.01)
            self.inp.press("enter", d=0.01)
        except Exception as e:
            log.error("F8 오류: %s", e, exc_info=True)

    # ─────────────────────────────────────
    # F9: 메인 루프 시작/정지
    # ─────────────────────────────────────
    def f9(self) -> None:
        if not is_sc_active():
            log.warning("F9: 스타크래프트 비활성 - 무시")
            return

        if self._f9thr and self._f9thr.is_alive():
            log.info("═══ F9 정지 요청 ═══")
            self._stop.set()
            return

        log.info("═══ F9 시작 ═══")
        self._stop.clear()
        self._pet_t  = time.time()
        self._f9thr  = threading.Thread(target=self._f9_loop, daemon=True)
        self._f9thr.start()

    def _f9_loop(self) -> None:
        conf      = self.cfg.get("search_confidence", 0.85)
        b28_conf  = self.cfg.get("box28_confidence_set", 0.97)
        key_skip  = False   # 28box ON 확인 후 열쇠루틴 스킵 플래그

        while not self._stop.is_set():
            try:
                # ── Loop Start ──────────────────────────
                self.inp.press("f2")
                time.sleep(self.cfg.get("step_delay", 0.1))

                self._pet_upgrade_check()
                if self._stop.is_set():
                    break

                gr     = self._abs_region("region_game")
                ur     = self._abs_region("region_ui")
                screen = self.finder.grab_screen()

                # ① target_circle / target_circle2 탐색
                tc = self.finder.find_any_in(screen, ["target_circle", "target_circle2"], conf, gr)
                if not tc:
                    if not hasattr(self, "_last_tc_log") or time.time() - self._last_tc_log > 10:
                        log.info("  [F9] target_circle 탐색 중...")
                        self._last_tc_log = time.time()
                    time.sleep(self.cfg.get("loop_delay", 0.5))
                    continue
                _, tcx, tcy = tc

                # ② 스킵 모드 확인 → ⑤ 변환루트
                # key_skip 은 F9 ON 동안만 유지 (재시작 시 False 초기화)
                if key_skip:
                    log.info("  [②스킵] 변환루트 진행")
                    time.sleep(self.cfg.get("loop_delay", 0.5))
                    self._conversion_route(tcx, tcy, conf, gr, ur, b28_conf, key_skip=True)
                    continue

                # ③ 28box 확인 (26box 감지 시 오인식 방지 → 열쇠루틴으로 패스)
                p26 = self.finder.find_in(screen, "26box", b28_conf, ur)
                if p26:
                    log.info("  [③] 26box 감지 → 28box 제외, 열쇠루틴 진행")
                else:
                    p28 = self.finder.find_in(screen, "28box", b28_conf, ur)
                    if p28:
                        on_p = self.finder.find_in(screen, "on", 0.85, ur)
                        if on_p:
                            log.info("  [③] 28box + ON 확인 → key_skip = True")
                            key_skip = True
                            time.sleep(self.cfg.get("loop_delay", 0.5))
                            continue
                        else:
                            log.info("  [③] 28box + OFF → ON 전환 처리")
                            self._handle_28box(ur)
                            key_skip = True
                            log.info("  [스킵 모드 ON] F9 재시작 전까지 유지")
                            time.sleep(self.cfg.get("loop_delay", 0.5))
                            continue

                # ④ seal_idle 확인 (region_game)
                seal = self.finder.find_in(screen, "seal_idle", conf, gr)
                if not seal:
                    log.info("  [④] seal_idle 미감지 → Loop Start")
                    time.sleep(self.cfg.get("loop_delay", 0.5))
                    continue
                log.info("  [④] seal_idle 감지 → 클릭")
                self.inp.click(*seal)
                if self._stop.is_set():
                    break

                # loop_delay 후 재캡처
                time.sleep(self.cfg.get("loop_delay", 0.5))
                screen = self.finder.grab_screen()

                # speed2/3 확인
                speed = self.finder.find_any_in(screen, ["speed2", "speed3"], conf, ur)
                if speed:
                    log.info("  speed %s 감지 → 열쇠루틴", speed[0])
                    self._key_routine(tcx, tcy, conf, b28_conf, gr, ur)
                else:
                    log.info("  speed 미감지 → ⑤ 변환루트")
                    self._conversion_route(tcx, tcy, conf, gr, ur, b28_conf)

            except Exception as e:
                log.error("F9 루프 오류: %s", e, exc_info=True)
                time.sleep(0.5)

        log.info("F9 루프 종료")
    # ── 주기적 펫 업그레이드 ──────────────
    def _pet_upgrade_check(self) -> None:
        interval = self.cfg.get("f9_pet_interval", 200)
        if time.time() - self._pet_t >= interval:
            log.info("[펫 업그레이드] 실행")
            self.inp.type_seq(self.cfg.get("f9_pet_upgrade", ""))
            self._pet_t = time.time()

    # ── seal 확인 ─────────────────────────
    def _seal_check(self, conf: float) -> None:
        p = self.finder.find("seal_idle", conf)
        if p:
            log.debug("seal_idle 클릭: %s", p)
            self.inp.click(*p)

    def _seal_check_in(self, screen: np.ndarray, conf: float,
                       region: Optional[Tuple] = None) -> None:
        """캡처된 화면에서 seal_idle 확인 (추가 캡처 없음)"""
        p = self.finder.find_in(screen, "seal_idle", conf, region)
        if p:
            log.debug("seal_idle 클릭: %s", p)
            self.inp.click(*p)

    # ─────────────────────────────────────
    # 열쇠 루틴
    # ─────────────────────────────────────
    def _key_routine(self, tcx: int, tcy: int, conf: float, b28_conf: float,
                     gr: Optional[Tuple] = None, ur: Optional[Tuple] = None) -> None:
        """
        key 클릭 → target 우클릭 → key_speed_delay 대기 → Loop Start 복귀.
        Loop Start에서 F2 + speed 확인이 자동으로 이루어짐.
        key 없으면 변환 루트 / 28box 감지 시 처리 후 종료.
        """
        log.info("  [열쇠 루틴]")
        self._pet_upgrade_check()

        key_p = self.finder.find("key", conf, gr)
        if not key_p:
            log.info("  [열쇠루틴] key 이미지 미감지 → 변환루트")
            self._conversion_route(tcx, tcy, conf, gr, ur, b28_conf)
            return

        log.info("  [열쇠루틴] key 감지 @ %s → 삽입", key_p)
        # 열쇠 1회 삽입
        self.inp.click(*key_p)
        self.inp.rclick(tcx, tcy)

        # 28box 감시
        if self.cfg.get("f9_box28_monitor_on", True):
            time.sleep(self.cfg.get("step_delay", 0.1))
            scr = self.finder.grab_screen()
            p28 = self.finder.find_in(scr, "28box", b28_conf, ur)
            if p28:
                log.info("  28box 감지!")
                self._handle_28box(ur)
                return

        # speed 반영 대기 → return → Loop Start (F2 + speed 자동 확인)
        time.sleep(self.cfg.get("key_speed_delay", 1.0))
        log.info("  열쇠 삽입 완료 → Loop Start 복귀")

    def _handle_28box(self, ur: Optional[Tuple] = None) -> None:
        """28box 처리: 3 입력 → ON/OFF 확인 및 전환"""
        self.inp.press("3")
        time.sleep(self.cfg.get("step_delay", 0.2))

        # check_on_offset [x,y] 우선 / 없으면 x,y 개별키 fallback
        _off = self.cfg.get("check_on_offset", [0, 0])
        if _off and (_off[0] != 0 or _off[1] != 0):
            cx, cy = self._abs_coord("check_on_offset")
        else:
            cx, cy = self._abs_xy("check_on_offset_x", "check_on_offset_y")
        self.inp.move(cx, cy)
        time.sleep(self.cfg.get("step_delay", 0.2))

        on_p = self.finder.find("on", 0.85, ur)
        if on_p:
            log.info("  ON 상태 확인 → 열쇠 루틴 종료")
        else:
            log.info("  OFF 상태 → ON 전환 후 종료")
            self.inp.click(cx, cy)

    # ─────────────────────────────────────
    # 변환 루트
    # ─────────────────────────────────────
    def _conversion_route(self, tcx: int, tcy: int, conf: float,
                          gr: Optional[Tuple] = None, ur: Optional[Tuple] = None,
                          b28_conf: float = 0.97, key_skip: bool = False) -> None:
        """
        myth_text_coord 클릭 → myth_text 유무로 분기:
          없음 → 일반 변환
          있음 → 특수 변환 판별 (bou + count)
        """
        log.info("  [변환 루트]")
        mc = self._abs_coord("myth_text_coord")

        if mc == [0, 0]:
            log.warning("  myth_text_coord 미설정 (config.json 확인)")

        step = self.cfg.get("step_delay", 0.2)

        # seal_idle 폴링 (최대 3회) — ④에서 클릭 직후 active 상태일 수 있으므로 대기 후 재시도
        seal_clicked = False
        for attempt in range(3):
            scr = self.finder.grab_screen()
            speed_now = self.finder.find_any_in(scr, ["speed2", "speed3"], conf, ur)
            if speed_now:
                log.info("  [변환루트] speed 감지 → seal 클릭 생략")
                break
            seal = self.finder.find_in(scr, "seal_idle", conf, gr)
            if seal:
                log.info("  [변환루트] seal_idle 클릭 (시도 %d)", attempt + 1)
                self.inp.click(*seal)
                time.sleep(step)
                seal_clicked = True
                break
            log.info("  [변환루트] seal_idle 대기 중... (%d/3)", attempt + 1)
            time.sleep(0.5)

        self.inp.move(*mc)
        self.inp.click()
        time.sleep(step)

        myth = self.finder.find("myth_text", conf, ur)
        if not myth:
            self._normal_conversion(tcx, tcy, conf, gr)
        else:
            self._special_conversion_check(tcx, tcy, conf, ur, gr, b28_conf, key_skip)

    def _normal_conversion(self, tcx: int, tcy: int, conf: float,
                           gr: Optional[Tuple] = None) -> None:
        """일반 변환: seal_idle 클릭 → target 우클릭 → step_delay 대기 → Loop Start"""
        log.info("  → 일반 변환 → Loop Start 복귀")
        sp = self.finder.find("seal_idle", conf, gr)
        if sp:
            self.inp.click(*sp)
        self.inp.rclick(tcx, tcy)
        time.sleep(self.cfg.get("step_delay", 0.1))
        # return → _conversion_route → _f9_loop 상단(Loop Start)으로 복귀

    def _special_conversion_check(self, tcx: int, tcy: int, conf: float,
                                   ur: Optional[Tuple] = None,
                                   gr: Optional[Tuple] = None,
                                   b28_conf: float = 0.97,
                                   key_skip: bool = False) -> None:
        """
        특수 변환 판별:
          bou 탐색 → bou 우측 영역에서 count_1/2/3 탐색
            count 있음(1~3) → 특수 불가 → 일반 변환
            count 없음(4+)  → 특수 변환 수행
        """
        log.info("  → 특수 변환 판별")
        bp = self.finder.find("bou", conf, ur)
        if not bp:
            log.warning("  bou 없음 → 일반 변환 fallback")
            self._normal_conversion(tcx, tcy, conf, gr)
            return

        bx, by = bp
        count_region = (bx + 5, by - 20, 130, 50)

        cnt_conf = self.cfg.get("count_confidence", conf)
        count_found = any(
            self.finder.find(f"count_{i}", cnt_conf, count_region)
            for i in range(1, 4)   # count_1, count_2, count_3
        )

        if count_found:
            log.info("  count 1~3 확인 → 특수 변환 불가 → 일반 변환")
            self._normal_conversion(tcx, tcy, conf)
        else:
            log.info("  count 4+ 확인 → 특수 변환 수행")
            self._do_special_conversion(tcx, tcy, conf, b28_conf, gr, ur, key_skip)

    def _do_special_conversion(self, tcx: int = 0, tcy: int = 0,
                               conf: float = 0.85, b28_conf: float = 0.97,
                               gr: Optional[Tuple] = None,
                               ur: Optional[Tuple] = None,
                               key_skip: bool = False) -> None:
        """
        특수 변환 루프:
          A키 입력 → 0.5s 대기
          → seal_idle 클릭 → myth_text_coord 클릭
          → bou 탐색:
              없음          → _normal_conversion() → return
              있음 + count 1~3 → _normal_conversion() → return
              있음 + count 없음(4+) → 루프 반복
        """
        log.info("  [특수 변환] 루프 시작")
        mc   = self._abs_coord("myth_text_coord")
        step = self.cfg.get("step_delay", 0.1)

        while not self._stop.is_set():
            # seal_idle 폴링 (최대 5회) — A키 후 애니메이션 종료 대기
            for attempt in range(5):
                scr  = self.finder.grab_screen()
                seal = self.finder.find_in(scr, "seal_idle", conf, gr)
                if seal:
                    self.inp.click(*seal)
                    log.info("    seal_idle 클릭 (시도 %d)", attempt + 1)
                    time.sleep(step)
                    break
                log.info("    seal_idle 대기... (%d/5)", attempt + 1)
                time.sleep(0.5)
            else:
                log.warning("  [특수 변환] seal_idle 미감지 → 루프 종료")
                return

            # myth_text_coord 클릭
            self.inp.move(*mc)
            self.inp.click()
            time.sleep(step)

            # bou 탐색
            scr = self.finder.grab_screen()
            bp  = self.finder.find_in(scr, "bou", conf, ur)
            if not bp:
                log.info("  [특수 변환] bou 없음 → 일반 변환")
                self._normal_conversion(tcx, tcy, conf, gr)
                return

            bx, by = bp
            cnt_conf    = self.cfg.get("count_confidence", conf)
            count_found = any(
                self.finder.find_in(scr, f"count_{i}", cnt_conf, (bx + 5, by - 20, 130, 50))
                for i in range(1, 4)
            )
            if count_found:
                log.info("  [특수 변환] count 1~3 감지 → 일반 변환")
                self._normal_conversion(tcx, tcy, conf, gr)
                return

            log.info("  [특수 변환] count 4+ 유지 → A키 입력")
            # A 키
            self.inp.press("a")
            time.sleep(self.cfg.get("loop_delay", 0.5))

        log.info("  [특수 변환] 중단 → Loop Start")

    # ─────────────────────────────────────
    # 시작
    # ─────────────────────────────────────
    def start(self) -> None:
        log.info("╔══════════════════════════════════╗")
        log.info("║  StarCraft Auto Macro  v1.0      ║")
        log.info("╚══════════════════════════════════╝")
        log.info("F6/F7/F8/F9 : 각 기능 | Ctrl+F11 : 설정 창 | Ctrl+F12 : 종료")

        def spawn(fn):
            return lambda: threading.Thread(target=fn, daemon=True).start()

        keyboard.add_hotkey("f6",        spawn(self.f6))
        keyboard.add_hotkey("f7",        spawn(self.f7))
        keyboard.add_hotkey("f8",        spawn(self.f8))
        keyboard.add_hotkey("f9",        spawn(self.f9))
        keyboard.add_hotkey("ctrl+f12",  self._quit)
        keyboard.add_hotkey("ctrl+f11",
                            lambda: self.root.after(0, self.ui.toggle)
                            if self.ui else None)

        log.info("단축키 등록 완료.")

        # 설정 UI 생성 (메인 스레드에서 tk.mainloop 실행)
        self.ui   = ConfigUI(self)
        self.root = self.ui.root        # Ctrl+F11 콜백에서 after() 사용
        self.ui.run()                   # ← 여기서 블록 (keyboard 핫키는 계속 동작)

    def _quit(self) -> None:
        log.info("매크로 종료 중...")
        self._stop.set()
        import os; os._exit(0)


# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        Macro().start()
    except Exception as e:
        import traceback
        print()
        print("="*50)
        print("[CRASH] Error:")
        print("="*50)
        traceback.print_exc()
        print("="*50)
        input("Press Enter to close...")
