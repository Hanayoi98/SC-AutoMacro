#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StarCraft Auto Macro v1.4
이미지 인식 기반 스타크래프트 자동화 매크로

단축키
  F6  : 채팅 매크로 + 식별코드 입력 (→ f9_early_branch_on 시 F7 자동 실행)
  F7  : autosetting 대기 후 업그레이드/마우스 루틴
  F8  : @태초 채팅 전송
  F9  : 메인 루프 시작/정지 (토글)
  F11 : 방장모드 시작/정지 (토글)
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
import difflib
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
    ("pytesseract",  "pytesseract"),
    ("PIL",          "Pillow"),
    ("requests",     "requests"),
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
import pytesseract
from PIL import Image as _PILImage
import requests

# tesseract.exe subprocess CMD 창 숨김 (Windows)
if sys.platform == "win32":
    import subprocess as _sub
    _OrigPopenInit = _sub.Popen.__init__
    def _PatchedPopenInit(self, args, **kwargs):
        kwargs.setdefault("creationflags", 0)
        kwargs["creationflags"] |= _sub.CREATE_NO_WINDOW
        _OrigPopenInit(self, args, **kwargs)
    _sub.Popen.__init__ = _PatchedPopenInit

for _tp in [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
             r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]:
    if os.path.exists(_tp):
        pytesseract.pytesseract.tesseract_cmd = _tp
        break

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
# exe 패키징(PyInstaller) 시 리소스는 _MEIPASS, 유저 데이터는 exe 옆 폴더 사용.
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)   # config, log → exe 옆
    _RES_DIR  = sys._MEIPASS                       # images → 번들 내부
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _RES_DIR  = _BASE_DIR
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
IMAGES_DIR  = os.path.join(_RES_DIR,  "images")
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
    "auto_drive_on":        False,
    "f9_box28_monitor_on": True,
    "max_box":              28,
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
    "speed_confidence":  0.85,
    "input_delay":       0.5,
    "loop_delay":        0.5,
    "mouse_move_dur":    0.5,
    "step_delay":        0.2,
    "key_speed_delay":   1.0,
    "window_size":       [0, 0],
    # ── 게임모드 ──
    "f11_on":                 False,
    "host_username":          "Hanayoi",
    "host_confidence":        0.65,
    "game_end_on":            False,
    "auto_boss_select_on":    False,
    "boss_loop_rx":           0.2677,
    "boss_loop_ry":           0.2494,
    "boss_loop_rw":           0.4553,
    "boss_loop_rh":           0.3024,
    # ── F7 전용 딜레이 ──
    "f7_input_delay":    0.15,
    "f7_step_delay":     0.2,
    "f7_mouse_move_dur": 0.05,
    # ── Discord 알림 ──
    "discord_notify_on":  False,
    "discord_webhook_url": "",
    "discord_user_id":    "",
    # ── Slack 알림 ──
    "slack_notify_on":   False,
    "slack_webhook_url": "",
}


# 문자열로 저장될 수 있는 숫자 키 목록
_NUM_KEYS = {
    "f9_pet_interval":     int,
    "max_box":             int,
    "box28_confidence_set": float,
    "auto_drive_on":        bool,
    "check_on_offset_x":   int,
    "check_on_offset_y":   int,
    "search_confidence":   float,
    "count_confidence":    float,
    "speed_confidence":    float,
    "input_delay":         float,
    "loop_delay":          float,
    "mouse_move_dur":      float,
    "step_delay":          float,
    "key_speed_delay":     float,
    "f7_input_delay":      float,
    "f7_step_delay":       float,
    "f7_mouse_move_dur":   float,
    "boss_loop_rx":        float,
    "boss_loop_ry":        float,
    "boss_loop_rw":        float,
    "boss_loop_rh":        float,
    "host_confidence":     float,
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
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
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

    # 템플릿 이미지를 캡처한 기준 창 크기
    _BASE_W = 1630
    _BASE_H = 1250

    def __init__(self, default_conf: float = 0.85) -> None:
        self._sct   = mss()
        self._cache: dict[str, np.ndarray] = {}         # 원본 템플릿 캐시
        self._scaled_cache: dict[str, np.ndarray] = {}  # 스케일 적용 캐시
        self._conf  = default_conf
        self._sx = 1.0
        self._sy = 1.0

    # ── 스케일 ──────────────────────────────
    def set_scale(self, current_w: int, current_h: int) -> None:
        """현재 SC 창 크기 기준 스케일 계산. 창 크기 바뀔 때마다 호출."""
        sx = current_w / self._BASE_W
        sy = current_h / self._BASE_H
        if abs(sx - self._sx) > 0.001 or abs(sy - self._sy) > 0.001:
            self._sx = sx
            self._sy = sy
            self._scaled_cache.clear()
            log.info("🔍 템플릿 스케일 갱신: %.3f×%.3f (%d×%d → %d×%d)",
                     sx, sy, self._BASE_W, self._BASE_H, current_w, current_h)

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

    def _get_tmpl(self, name: str) -> Optional[np.ndarray]:
        """스케일 적용된 템플릿 반환 (1:1이면 원본 그대로)."""
        if abs(self._sx - 1.0) < 0.001 and abs(self._sy - 1.0) < 0.001:
            return self._load(name)
        if name in self._scaled_cache:
            return self._scaled_cache[name]
        orig = self._load(name)
        if orig is None:
            return None
        h, w = orig.shape[:2]
        new_w = max(1, round(w * self._sx))
        new_h = max(1, round(h * self._sy))
        scaled = cv2.resize(orig, (new_w, new_h), interpolation=cv2.INTER_AREA)
        self._scaled_cache[name] = scaled
        return scaled

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
        tmpl = self._get_tmpl(name)
        if tmpl is None:
            return None
        src = screen
        if region:
            x, y, w, h = region
            src = screen[y:y+h, x:x+w]
        th, tw = tmpl.shape[:2]
        sh, sw = src.shape[:2]
        if sh < th or sw < tw:
            return None
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
        tmpl = self._get_tmpl(name)
        if tmpl is None:
            return None
        scr    = self._grab(region)
        h, w   = tmpl.shape[:2]
        sh, sw = scr.shape[:2]
        if sh < h or sw < w:
            return None
        result = cv2.matchTemplate(scr, tmpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(result)
        c  = float(conf if conf is not None else self._conf)
        if maxv >= c:
            ox = region[0] if region else 0
            oy = region[1] if region else 0
            return (maxloc[0] + w // 2 + ox, maxloc[1] + h // 2 + oy)
        return None

    def find_box(
        self,
        name: str,
        conf: Optional[float] = None,
        region: Optional[Tuple] = None,
    ) -> Optional[Tuple[int, int, int, int]]:
        """이미지 탐색. 발견 시 (left, top, w, h) 반환, 없으면 None."""
        tmpl = self._get_tmpl(name)
        if tmpl is None:
            return None
        scr = self._grab(region)
        th, tw = tmpl.shape[:2]
        sh, sw = scr.shape[:2]
        if sh < th or sw < tw:
            return None
        res = cv2.matchTemplate(scr, tmpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        c = float(conf if conf is not None else self._conf)
        if maxv >= c:
            ox = region[0] if region else 0
            oy = region[1] if region else 0
            return (maxloc[0] + ox, maxloc[1] + oy, tw, th)
        return None

    def find_score(
        self,
        name: str,
        region: Optional[Tuple] = None,
    ) -> float:
        """이미지 최대 매칭 스코어만 반환 (임계값 무관)."""
        tmpl = self._get_tmpl(name)
        if tmpl is None:
            return 0.0
        scr    = self._grab(region)
        result = cv2.matchTemplate(scr, tmpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, _ = cv2.minMaxLoc(result)
        return float(maxv)

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
    C_ACC = "#89b4fa"; C_GREEN = "#a6e3a1"; C_RED = "#f38ba8"; C_PINK = "#f5c2e7"
    FONT  = ("Malgun Gothic", 9)
    FONTB = ("Malgun Gothic", 9, "bold")

    COORD_KEYS = [
        ("A",   "coord_a",          "F7 마우스 A  (더블클릭)"),
        ("B",   "coord_b",          "F7 마우스 B  (더블클릭)"),
        ("C",   "coord_c",          "F7 마우스 C  (싱글클릭 ×4)"),
        ("M",   "myth_text_coord",  "변환 루트  myth_text 클릭"),
        ("ON",  "check_on_offset",  "Max Box  ON/OFF 확인 좌표"),
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
        self._nb = nb

        self._tab_window(nb)
        self._tab_coords(nb)
        self._tab_keys(nb)
        self._tab_gamemode1(nb)
        self._tab_gamemode2(nb)
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

        tk.Frame(f, height=1, bg=self.C_BG3).pack(fill="x", padx=10, pady=(10,4))
        self._lbl(f, "[ 보스 루프 영역 (비율 0.0~1.0) ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(4,2), padx=10)
        rows_bloop = [
            ("영역 X 비율",  "boss_loop_rx", "num"),
            ("영역 Y 비율",  "boss_loop_ry", "num"),
            ("영역 W 비율",  "boss_loop_rw", "num"),
            ("영역 H 비율",  "boss_loop_rh", "num"),
        ]
        self._cfg_rows(f, rows_bloop)
        self._btn(f, "  드래그로 영역 선택  ", self._start_region_drag).pack(anchor="w", padx=10, pady=(6,2))

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

    # ── 탭 3: 키 설정 (F6 + F9) ─────────────────
    def _tab_keys(self, nb):
        f = self._frame(nb); nb.add(f, text=" 키 설정 ")
        self._lbl(f, "[ F6 설정 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(8,2), padx=10)
        rows_f6 = [
            ("식별코드",        "id_code",           "str"),
            ("F6 펫 업그레이드","f6_pet_upgrade",     "str"),
            ("F6 마무리 동작",  "f6_final_action",    "str"),
            ("채팅 매크로 사용","f6_chat_macro_on",   "bool"),
            ("F7 자동 실행",    "f9_early_branch_on", "bool"),
        ]
        self._cfg_rows(f, rows_f6)
        tk.Frame(f, height=1, bg=self.C_BG3).pack(fill="x", padx=10, pady=(10,4))
        self._lbl(f, "[ F9 설정 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(4,2), padx=10)
        rows_f9 = [
            ("펫 업그레이드 키",      "f9_pet_upgrade",      "str"),
            ("펫 업그레이드 주기(초)", "f9_pet_interval",     "num"),
            ("Max Box 감시",          "f9_box28_monitor_on", "bool"),
            ("Max Box 번호",          "max_box",             "num"),
        ]
        self._cfg_rows(f, rows_f9)

    # ── 탭 4: 게임모드1 (F11 방장/따라가기) ─────────
    def _tab_gamemode1(self, nb):
        f = self._frame(nb); nb.add(f, text=" 게임모드1 ")

        # ── F11 모드 선택 ──────────────────────────
        self._lbl(f, "[ F11 실행모드 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(8,2), padx=10)
        self._sv_map = getattr(self, "_sv_map", {})
        self._cfg_rows(f, [("F11 사용", "f11_on", "bool")])
        mode_row = tk.Frame(f, bg=self.C_BG); mode_row.pack(anchor="w", padx=10, pady=4)
        self._lbl(mode_row, "실행 모드", width=20, anchor="w").pack(side="left")
        _mode_sv = tk.StringVar(value=str(self.cfg.get("f11_mode", "host")))
        self._sv_map["f11_mode"] = ("str", _mode_sv)
        tk.Radiobutton(mode_row, text="방장모드", variable=_mode_sv, value="host",
                       bg=self.C_BG, fg=self.C_PINK, selectcolor=self.C_BG2,
                       activebackground=self.C_BG, font=self.FONT).pack(side="left", padx=(0,8))
        tk.Radiobutton(mode_row, text="따라가기", variable=_mode_sv, value="follow",
                       bg=self.C_BG, fg=self.C_GREEN, selectcolor=self.C_BG2,
                       activebackground=self.C_BG, font=self.FONT).pack(side="left")

        # ── 방장모드 ───────────────────────────────
        tk.Frame(f, height=1, bg=self.C_BG3).pack(fill="x", padx=10, pady=(10,4))
        self._lbl(f, "[ 방장모드 ]", bold=True, fg=self.C_PINK).pack(anchor="w", pady=(4,2), padx=10)
        rows_host = [
            ("유저 닉네임",    "host_username",       "str"),
            ("닉네임 인식률",  "host_confidence",     "num"),
            ("자동 보스 선택", "auto_boss_select_on", "bool"),
        ]
        self._cfg_rows(f, rows_host)

        # ── 따라가기 ───────────────────────────────
        tk.Frame(f, height=1, bg=self.C_BG3).pack(fill="x", padx=10, pady=(10,4))
        self._lbl(f, "[ 따라가기 ]", bold=True, fg=self.C_GREEN).pack(anchor="w", pady=(4,2), padx=10)
        rows_follow = [
            ("따라갈 닉네임",      "follow_nickname",   "str"),
            ("이미지 매칭 정확도", "follow_confidence", "num"),
        ]
        self._cfg_rows(f, rows_follow)

        # 닉네임 탐색 영역 드래그 선택
        reg_row = tk.Frame(f, bg=self.C_BG); reg_row.pack(anchor="w", padx=10, pady=4)
        self._lbl(reg_row, "닉네임 탐색 영역", width=20, anchor="w").pack(side="left")
        _cur_reg = self.cfg.get("follow_search_region", [0, 0, 0, 0])
        self._follow_region_sv = tk.StringVar(
            value=f"({_cur_reg[0]}, {_cur_reg[1]}, {_cur_reg[2]}, {_cur_reg[3]})"
        )
        self._lbl(reg_row, sv=self._follow_region_sv, fg=self.C_FG2).pack(side="left", padx=(4,8))
        self._btn(reg_row, "드래그 선택", self._start_follow_region_drag).pack(side="left")

    # ── 탭 5: 게임모드2 (게임종료·추가 예정) ────────
    def _tab_gamemode2(self, nb):
        f = self._frame(nb); nb.add(f, text=" 게임모드2 ")
        self._lbl(f, "[ 게임종료 루프 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(8,2), padx=10)
        rows_end = [
            ("게임종료 루프 사용", "game_end_on", "bool"),
        ]
        self._cfg_rows(f, rows_end)


    # ── 탭 6: 고급1 (딜레이) ─────────────────────
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
            ("speed 정확도 (0~1)", "speed_confidence",    "num"),
        ]
        self._cfg_rows(f, rows)
        self._lbl(f, "[ 방장모드 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(12,2), padx=10)
        self._cfg_rows(f, [("자동운행모드", "auto_drive_on", "bool")])
        self._lbl(f, "[ Discord 알림 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(12,2), padx=10)
        self._cfg_rows(f, [
            ("알림기능",    "discord_notify_on",  "bool"),
            ("웹훅 URL",   "discord_webhook_url", "str"),
            ("사용자 ID",  "discord_user_id",     "str"),
        ])
        self._lbl(f, "[ Slack 알림 ]", bold=True, fg=self.C_ACC).pack(anchor="w", pady=(12,2), padx=10)
        self._cfg_rows(f, [
            ("알림기능",   "slack_notify_on",   "bool"),
            ("웹훅 URL",  "slack_webhook_url",  "str"),
        ])

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
        # 절대 좌표 → SC 창 기준 상대 좌표로 변환
        hwnd = self._find_sc_hwnd()
        if hwnd:
            try:
                wx, wy, _, _ = _sc_get_rect(hwnd)
                rx, ry = x - wx, y - wy
            except Exception:
                rx, ry = x, y
        else:
            rx, ry = x, y
        self.cfg[cfg_key] = [rx, ry]
        if cfg_key in self._coord_sv:
            self._coord_sv[cfg_key].set(f"({rx}, {ry})")
        self._status_sv.set(f"✓ [{name}] 저장: ({rx}, {ry})  [SC창 기준 상대좌표]")
        self.macro.save_config()
        self.win.deiconify()
        self._capturing = False

    # ── 보스 루프 영역 드래그 선택 ───────────────
    def _start_region_drag(self):
        self.win.iconify()
        self.win.after(300, self._open_drag_overlay)

    def _open_drag_overlay(self):
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()

        ov = tk.Toplevel()
        ov.attributes("-fullscreen", True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.25)
        ov.configure(bg="black")
        ov.config(cursor="crosshair")

        canvas = tk.Canvas(ov, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        hint = canvas.create_text(
            sw // 2, 40,
            text="드래그하여 보스 루프 영역을 선택하세요  |  ESC: 취소",
            fill="white", font=("Malgun Gothic", 14, "bold")
        )

        state = {"x0": 0, "y0": 0, "rect": None}

        def on_press(e):
            state["x0"], state["y0"] = e.x, e.y
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(
                e.x, e.y, e.x, e.y,
                outline="#89b4fa", width=2, fill="#89b4fa", stipple="gray25"
            )

        def on_drag(e):
            if state["rect"]:
                canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

        def on_release(e):
            x0, y0 = min(state["x0"], e.x), min(state["y0"], e.y)
            x1, y1 = max(state["x0"], e.x), max(state["y0"], e.y)
            ov.destroy()
            self.win.after(100, lambda: self._finish_region_drag(x0, y0, x1, y1))

        def on_esc(e):
            ov.destroy()
            self.win.deiconify()

        canvas.bind("<ButtonPress-1>",   on_press)
        canvas.bind("<B1-Motion>",       on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        ov.bind("<Escape>", on_esc)
        ov.focus_force()

    def _finish_region_drag(self, x0, y0, x1, y1):
        hwnd = self._find_sc_hwnd()
        if hwnd:
            try:
                gx, gy, gw, gh = _sc_get_rect(hwnd)
            except Exception:
                gx, gy = 0, 0
                gw = self.win.winfo_screenwidth()
                gh = self.win.winfo_screenheight()
        else:
            gx, gy = 0, 0
            gw = self.win.winfo_screenwidth()
            gh = self.win.winfo_screenheight()

        rx = round((x0 - gx) / gw, 4)
        ry = round((y0 - gy) / gh, 4)
        rw = round((x1 - x0)  / gw, 4)
        rh = round((y1 - y0)  / gh, 4)

        for key, val in [("boss_loop_rx", rx), ("boss_loop_ry", ry),
                         ("boss_loop_rw", rw), ("boss_loop_rh", rh)]:
            self.cfg[key] = val
            sv_entry = self._sv_map.get(key)
            if sv_entry:
                sv_entry[1].set(str(val))

        self.macro.save_config()
        self.win.deiconify()
        messagebox.showinfo("영역 저장",
            f"보스 루프 영역 저장 완료\n"
            f"X: {rx}  Y: {ry}\nW: {rw}  H: {rh}", parent=self.win)

    # ── 닉네임 탐색 영역 드래그 선택 ─────────────
    def _start_follow_region_drag(self):
        self.win.iconify()
        self.win.after(300, self._open_follow_drag_overlay)

    def _open_follow_drag_overlay(self):
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()

        ov = tk.Toplevel()
        ov.attributes("-fullscreen", True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.25)
        ov.configure(bg="black")
        ov.config(cursor="crosshair")

        canvas = tk.Canvas(ov, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        canvas.create_text(
            sw // 2, 40,
            text="드래그하여 닉네임 탐색 영역을 선택하세요  |  ESC: 취소",
            fill="white", font=("Malgun Gothic", 14, "bold")
        )

        state = {"x0": 0, "y0": 0, "rect": None}

        def on_press(e):
            state["x0"], state["y0"] = e.x, e.y
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(
                e.x, e.y, e.x, e.y,
                outline="#a6e3a1", width=2, fill="#a6e3a1", stipple="gray25"
            )

        def on_drag(e):
            if state["rect"]:
                canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

        def on_release(e):
            x0, y0 = min(state["x0"], e.x), min(state["y0"], e.y)
            x1, y1 = max(state["x0"], e.x), max(state["y0"], e.y)
            ov.destroy()
            self.win.after(100, lambda: self._finish_follow_region_drag(x0, y0, x1, y1))

        def on_esc(e):
            ov.destroy()
            self.win.deiconify()

        canvas.bind("<ButtonPress-1>",   on_press)
        canvas.bind("<B1-Motion>",       on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        ov.bind("<Escape>", on_esc)
        ov.focus_force()

    def _finish_follow_region_drag(self, x0, y0, x1, y1):
        hwnd = self._find_sc_hwnd()
        if hwnd:
            try:
                gx, gy, _, _ = _sc_get_rect(hwnd)
            except Exception:
                gx, gy = 0, 0
        else:
            gx, gy = 0, 0

        rx = x0 - gx
        ry = y0 - gy
        rw = x1 - x0
        rh = y1 - y0

        self.cfg["follow_search_region"] = [rx, ry, rw, rh]
        if hasattr(self, "_follow_region_sv"):
            self._follow_region_sv.set(f"({rx}, {ry}, {rw}, {rh})")

        self.macro.save_config()
        self.win.deiconify()
        messagebox.showinfo("영역 저장",
            f"닉네임 탐색 영역 저장 완료\n"
            f"X: {rx}  Y: {ry}  W: {rw}  H: {rh}", parent=self.win)

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

    def show_tab(self, index: int):
        self.show()
        self._nb.select(index)


# ──────────────────────────────────────────────────────────
class ConfigUI:
    """메인 창 — 간결한 상태 표시 + F9 제어 + 설정 버튼"""

    # ── 색상 팔레트 (Catppuccin Mocha 기반) ──
    C_BG   = "#1e1e2e"; C_BG2  = "#181825"; C_BG3  = "#313244"; C_BG4 = "#45475a"
    C_FG   = "#cdd6f4"; C_FG2  = "#a6adc8"; C_FG3  = "#6c7086"
    C_ACC  = "#89b4fa"; C_MAUVE= "#cba6f7"; C_TEAL = "#94e2d5"
    C_GREEN= "#a6e3a1"; C_RED  = "#f38ba8"; C_YELL = "#f9e2af"
    C_PINK = "#f5c2e7"
    FONT   = ("Malgun Gothic", 9)
    FONTB  = ("Malgun Gothic", 9, "bold")
    FONTS  = ("Malgun Gothic", 8)
    FONTM  = ("Consolas", 9)

    F_DESC = [
        ("F6",  "#f9e2af", "채팅 + 식별코드 입력"),
        ("F7",  "#cba6f7", "펫 업그레이드 · 마우스 루틴"),
        ("F8",  "#94e2d5", "@태초 채팅 전송"),
        ("F9",  "#a6e3a1", "메인 루프  시작 / 정지"),
        ("F11", "#f5c2e7", "방장모드 / 따라가기  시작 / 정지"),
    ]

    def __init__(self, macro: "Macro") -> None:
        self.macro = macro
        self.root  = tk.Tk()
        self._settings: Optional[SettingsWindow] = None
        self._build()
        self._poll()

    def _build(self):
        r = self.root
        r.title("SC Auto Macro  v1.4")
        r.configure(bg=self.C_BG)
        r.attributes("-topmost", True)
        r.resizable(False, False)
        r.protocol("WM_DELETE_WINDOW", self._quit)

        # ── 상단 액센트 바 ────────────────
        tk.Frame(r, height=3, bg=self.C_ACC).pack(fill="x")

        # ── 헤더 카드 ────────────────────
        hdr = tk.Frame(r, bg=self.C_BG2)
        hdr.pack(fill="x", padx=0, pady=0)

        left_hdr = tk.Frame(hdr, bg=self.C_BG2)
        left_hdr.pack(side="left", padx=16, pady=10)
        tk.Label(left_hdr, text="SC AUTO MACRO", font=("Malgun Gothic",13,"bold"),
                 bg=self.C_BG2, fg=self.C_FG).pack(anchor="w")
        tk.Label(left_hdr, text="StarCraft Automation Suite",
                 font=self.FONTS, bg=self.C_BG2, fg=self.C_FG3).pack(anchor="w")

        ver_frame = tk.Frame(hdr, bg=self.C_BG3, padx=8, pady=4)
        ver_frame.pack(side="right", padx=16, pady=10)
        tk.Label(ver_frame, text="v1.4", font=("Malgun Gothic",10,"bold"),
                 bg=self.C_BG3, fg=self.C_ACC).pack()

        # ── 상태 표시 카드 ───────────────
        status_card = tk.Frame(r, bg=self.C_BG3, pady=8)
        status_card.pack(fill="x", padx=12, pady=(10,4))

        self._status_dot = tk.Label(status_card, text="●", font=("Malgun Gothic",11),
                                     bg=self.C_BG3, fg=self.C_RED)
        self._status_dot.pack(side="left", padx=(14,4))
        self._status_sv = tk.StringVar(value="정지 중")
        tk.Label(status_card, textvariable=self._status_sv, font=self.FONTB,
                 bg=self.C_BG3, fg=self.C_FG).pack(side="left")

        self._host_dot = tk.Label(status_card, text="●", font=("Malgun Gothic",11),
                                   bg=self.C_BG3, fg=self.C_BG4)
        self._host_dot.pack(side="right", padx=(4,4))
        tk.Label(status_card, text="방장", font=self.FONTS,
                 bg=self.C_BG3, fg=self.C_FG3).pack(side="right", padx=(14,0))

        # ── 단축키 패널 ──────────────────
        keys_frame = tk.Frame(r, bg=self.C_BG2)
        keys_frame.pack(fill="x", padx=12, pady=(6,4))

        for key, color, desc in self.F_DESC:
            row = tk.Frame(keys_frame, bg=self.C_BG2)
            row.pack(fill="x", padx=8, pady=2)
            badge = tk.Frame(row, bg=color, padx=5, pady=1)
            badge.pack(side="left")
            blbl = tk.Label(badge, text=key, font=("Malgun Gothic",8,"bold"),
                            bg=color, fg="#1e1e2e")
            blbl.pack()
            if key == "F11":
                self._f11_badge_frame = badge
                self._f11_badge_lbl   = blbl
            tk.Label(row, text=desc, font=self.FONT,
                     bg=self.C_BG2, fg=self.C_FG2).pack(side="left", padx=8)

        # ── 구분선 ───────────────────────
        tk.Frame(r, height=1, bg=self.C_BG4).pack(fill="x", padx=12, pady=8)

        # ── 버튼 행 1: 메인 컨트롤 ───────
        row1 = tk.Frame(r, bg=self.C_BG); row1.pack(padx=12, pady=(0,4), fill="x")

        self._f9_btn = tk.Button(row1, text="▶  F9 시작", font=self.FONTB,
                                  bg=self.C_GREEN, fg="#1e1e2e",
                                  relief="flat", padx=14, pady=7,
                                  activebackground="#b9f0c6",
                                  cursor="hand2",
                                  command=self._toggle_f9)
        self._f9_btn.pack(side="left", padx=(0,6), fill="x", expand=True)

        _init_mode = self.macro.cfg.get("f11_mode", "host")
        _f11_bg, _f11_txt = (self.C_GREEN, "→  F11 따라가기") if _init_mode == "follow" \
                       else (self.C_PINK,  "♟  F11 방장")
        self._f11_btn = tk.Button(row1, text=_f11_txt, font=self.FONTB,
                                   bg=_f11_bg, fg="#1e1e2e",
                                   relief="flat", padx=14, pady=7,
                                   activebackground=self.C_BG4,
                                   cursor="hand2",
                                   command=self._toggle_f11)
        self._f11_btn.pack(side="left", fill="x", expand=True)

        # ── 버튼 행 2: 서브 컨트롤 ───────
        row2 = tk.Frame(r, bg=self.C_BG); row2.pack(padx=12, pady=(0,10), fill="x")

        tk.Button(row2, text="👑  방장설정", font=self.FONTS,
                  bg=self.C_BG3, fg="#f9e2af",
                  relief="flat", padx=10, pady=5,
                  activebackground=self.C_BG4, cursor="hand2",
                  command=self._open_gamemode_settings).pack(side="left", padx=(0,4), fill="x", expand=True)

        tk.Button(row2, text="⚙  설정", font=self.FONTS,
                  bg=self.C_BG3, fg=self.C_FG,
                  relief="flat", padx=10, pady=5,
                  activebackground=self.C_BG4, cursor="hand2",
                  command=self._open_settings).pack(side="left", padx=(0,4), fill="x", expand=True)

        tk.Button(row2, text="🖥  해상도", font=self.FONTS,
                  bg=self.C_BG3, fg=self.C_ACC,
                  relief="flat", padx=10, pady=5,
                  activebackground=self.C_BG4, cursor="hand2",
                  command=self._apply_resolution).pack(side="left", padx=(0,4), fill="x", expand=True)

        tk.Button(row2, text="✕  종료", font=self.FONTS,
                  bg=self.C_BG3, fg=self.C_RED,
                  relief="flat", padx=10, pady=5,
                  activebackground=self.C_BG4, cursor="hand2",
                  command=self._quit).pack(side="left", fill="x", expand=True)

        # ── 로그 패널 ────────────────────
        tk.Frame(r, height=1, bg=self.C_BG4).pack(fill="x", padx=12)

        log_hdr = tk.Frame(r, bg=self.C_BG); log_hdr.pack(fill="x", padx=12, pady=(4,0))
        tk.Label(log_hdr, text="LOG", font=("Consolas",8,"bold"),
                 bg=self.C_BG, fg=self.C_FG3).pack(side="left")
        self._log_toggle_sv = tk.StringVar(value="▼ 펼치기")
        tk.Button(log_hdr, textvariable=self._log_toggle_sv, font=self.FONTS,
                  bg=self.C_BG, fg=self.C_ACC, relief="flat", cursor="hand2",
                  command=self._toggle_log).pack(side="right")
        tk.Button(log_hdr, text="지우기", font=self.FONTS,
                  bg=self.C_BG, fg=self.C_FG3, relief="flat", cursor="hand2",
                  command=self._clear_log).pack(side="right", padx=4)

        self._log_frame = tk.Frame(r, bg=self.C_BG)
        self._log_text = tk.Text(
            self._log_frame, height=10, width=58,
            bg=self.C_BG2, fg="#a6adc8",
            font=("Consolas", 8),
            relief="flat", state="disabled",
            wrap="none", insertbackground=self.C_FG,
        )
        sb_y = tk.Scrollbar(self._log_frame, command=self._log_text.yview, width=10)
        sb_x = tk.Scrollbar(self._log_frame, orient="horizontal",
                             command=self._log_text.xview, width=10)
        self._log_text.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        self._log_text.pack(fill="both", expand=True, padx=(12,0))
        self._log_visible = False

        # ── 하단 액센트 바 ────────────────
        tk.Frame(r, height=2, bg=self.C_BG3).pack(fill="x", pady=(6,0))

    def _toggle_f9(self):
        threading.Thread(target=self.macro.f9, daemon=True).start()

    def _toggle_f11(self):
        threading.Thread(target=self.macro.f11, daemon=True).start()

    def _open_settings(self):
        if self._settings is None:
            self._settings = SettingsWindow(self.macro, self.root)
        else:
            self._settings.show()

    def _open_gamemode_settings(self):
        if self._settings is None:
            self._settings = SettingsWindow(self.macro, self.root)
        self._settings.show_tab(3)

    def _poll(self):
        """500ms 마다 F9 상태 + 로그 큐 일괄 갱신"""
        # F9 상태
        if self.macro._f9thr and self.macro._f9thr.is_alive():
            if self.macro._game_end_mode and self.macro._f9_held:
                elapsed = min(4.0, time.time() - self.macro._f9_press_time)
                if self.macro._boss_select_active:
                    self._status_sv.set("보스선택 모드")
                    self._status_dot.configure(fg="#cba6f7")
                else:
                    self._status_sv.set("게임 종료 대기")
                    self._status_dot.configure(fg="#f9e2af")
                self._f9_btn.configure(
                    text=f"■  종료 감지 중  |  F9 {elapsed:.1f}s / 4s",
                    bg=self.C_RED, fg="#1e1e2e", activebackground="#f5a0b0")
            elif self.macro._game_end_mode and self.macro._boss_select_active:
                self._status_sv.set("보스선택 모드")
                self._status_dot.configure(fg="#cba6f7")
                self._f9_btn.configure(text="■  보스선택 중", bg=self.C_RED, fg="#1e1e2e",
                                       activebackground="#f5a0b0")
            elif self.macro._game_end_mode:
                self._status_sv.set("게임 종료 대기")
                self._status_dot.configure(fg="#f9e2af")
                self._f9_btn.configure(text="■  종료 감지 중", bg=self.C_RED, fg="#1e1e2e",
                                       activebackground="#f5a0b0")
            else:
                self._status_sv.set("실행 중")
                self._status_dot.configure(fg=self.C_GREEN)
                self._f9_btn.configure(text="■  F9 정지", bg=self.C_RED, fg="#1e1e2e",
                                       activebackground="#f5a0b0")
        else:
            self._status_sv.set("정지 중")
            self._status_dot.configure(fg=self.C_RED)
            self._f9_btn.configure(text="▶  F9 시작", bg=self.C_GREEN, fg="#1e1e2e",
                                   activebackground="#b9f0c6")

        # F11 모드 + 실행 상태
        _mode         = self.macro.cfg.get("f11_mode", "host")
        _host_run     = bool(self.macro._f11thr   and self.macro._f11thr.is_alive())
        _follow_run   = bool(self.macro._follow_thr and self.macro._follow_thr.is_alive())
        _f11_color    = self.C_GREEN if _mode == "follow" else self.C_PINK
        # 배지 색상 동기화
        self._f11_badge_frame.configure(bg=_f11_color)
        self._f11_badge_lbl.configure(bg=_f11_color)
        if _host_run or _follow_run:
            _stop_txt = "■  F11 방장 정지" if _mode == "host" else "■  F11 따라가기 정지"
            self._f11_btn.configure(text=_stop_txt, bg=self.C_BG3,
                                    fg=self.C_RED, activebackground=self.C_BG4)
            self._host_dot.configure(fg=_f11_color)
        elif _mode == "follow":
            self._f11_btn.configure(text="→  F11 따라가기", bg=self.C_GREEN,
                                    fg="#1e1e2e", activebackground="#b9f0c6")
            self._host_dot.configure(fg=self.C_BG4)
        else:
            self._f11_btn.configure(text="♟  F11 방장", bg=self.C_PINK,
                                    fg="#1e1e2e", activebackground="#f7d0ee")
            self._host_dot.configure(fg=self.C_BG4)

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
        self._host_stop = threading.Event()
        self._f11thr: Optional[threading.Thread] = None
        self._follow_stop = threading.Event()
        self._follow_thr: Optional[threading.Thread] = None
        self._f6f7_stop = threading.Event()
        self._f6f7_thr: Optional[threading.Thread] = None
        self._game_end_mode = False
        self._boss_select_active = False
        self._f9_press_time = 0.0
        self._f9_held = False
        self._SC_SHOT_DIR   = self._find_sc_shot_dir()
        log.info("📁 스크린샷 폴더: %s", self._SC_SHOT_DIR)
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
        self.finder.set_scale(tw, th)

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
        if self._f6f7_thr and self._f6f7_thr.is_alive():
            log.info("═══ F6F7 정지 ═══")
            self._f6f7_stop.set()
            return
        if not is_sc_active():
            log.warning("F6: 스타크래프트 비활성 - 무시")
            return
        self._f6f7_stop.clear()
        self._f6f7_thr = threading.Thread(
            target=self._f6f7_loop, kwargs={"start_at_f7": False}, daemon=True)
        self._f6f7_thr.start()

    def f7(self) -> None:
        if self._f6f7_thr and self._f6f7_thr.is_alive():
            log.info("═══ F6F7 정지 ═══")
            self._f6f7_stop.set()
            return
        if not is_sc_active():
            log.warning("F7: 스타크래프트 비활성 - 무시")
            return
        self._f6f7_stop.clear()
        self._f6f7_thr = threading.Thread(
            target=self._f6f7_loop, kwargs={"start_at_f7": True}, daemon=True)
        self._f6f7_thr.start()

    def _f6f7_loop(self, start_at_f7: bool = False) -> None:
        log.info("═══ F6F7 루프 시작 (start_at_f7=%s) ═══", start_at_f7)
        try:
            if not start_at_f7:
                # ── F6 구간 ──────────────────────────────
                # AutoStart_2 감지 대기 (boss_loop 영역)
                _hwnd = _sc_find_hwnd()
                if not _hwnd:
                    log.warning("[F6] SC 창을 찾을 수 없음")
                    return
                gx, gy, gw, gh = _sc_get_rect(_hwnd)
                rx = float(self.cfg.get("boss_loop_rx", 0.2677))
                ry = float(self.cfg.get("boss_loop_ry", 0.2494))
                rw = float(self.cfg.get("boss_loop_rw", 0.4553))
                rh = float(self.cfg.get("boss_loop_rh", 0.3024))
                detect_reg = (int(gx+gw*rx), int(gy+gh*ry), int(gw*rw), int(gh*rh))

                log.info("🔍 [F6] AutoStart_2 대기 중...")
                pos = self.finder.wait("AutoStart_2", region=detect_reg,
                                       stop_event=self._f6f7_stop)
                if not pos or self._f6f7_stop.is_set():
                    log.info("[F6] 정지 또는 미감지")
                    return
                log.info("✅ [F6] AutoStart_2 감지 @ %s → sleep(1.0)", pos)
                time.sleep(1.0)
                if self._f6f7_stop.is_set():
                    return

                chat_on = self.cfg.get("f6_chat_macro_on", True)
                if chat_on:
                    self.inp.press("enter")
                    self.inp.paste_text("@자동1")
                    self.inp.press("enter")
                    time.sleep(self.cfg.get("step_delay", 0.2))

                self.inp.press("0")
                time.sleep(self.cfg.get("step_delay", 0.2))
                _type_unicode(str(self.cfg["id_code"]), delay=self.inp.delay)
                log.info("✅ [F6] 완료 (채팅매크로=%s)", chat_on)

                if not self.cfg.get("f9_early_branch_on", False):
                    log.info("═══ F6F7 종료 (F7 미사용) ═══")
                    return

                if self._f6f7_stop.is_set():
                    return

            # ── F7 구간 ──────────────────────────────
            log.info("═══ [F7] 시작 ═══")
            sd = self.cfg.get("f7_step_delay", 0.2)
            gr = self._abs_region("region_game")

            # 재시작 시 화면 F2 재고정
            self.inp_f7.press("f2")
            time.sleep(sd)

            log.info("🔍 [F7] key 이미지 대기 중...")
            pos = self.finder.wait("key", region=gr, stop_event=self._f6f7_stop)
            if not pos or self._f6f7_stop.is_set():
                log.info("[F7] 정지 또는 key 미발견")
                return
            log.info("✅ [F7] key 발견 @ %s", pos)

            self.inp_f7.press("f2");  time.sleep(sd)
            self.inp_f7.press("2");   time.sleep(sd)
            self.inp_f7.type_seq(self.cfg.get("f6_pet_upgrade", ""))
            time.sleep(sd)
            self.inp_f7.press("3");   time.sleep(sd)
            self.inp_f7.type_seq(self.cfg.get("f6_final_action", ""))
            time.sleep(sd)

            if self._f6f7_stop.is_set():
                return

            self._f7_mouse_routine()
            log.info("✅ [F7] 완료")
            if self.cfg.get("discord_notify_on", False):
                _url = self.cfg.get("discord_webhook_url", "").strip()
                _uid = self.cfg.get("discord_user_id", "").strip()
                if _url:
                    _mention = f"<@{_uid}> " if _uid else ""
                    try:
                        requests.post(_url, json={"content": f"{_mention}✅ F7 루프 완료"}, timeout=5)
                    except Exception as _e:
                        log.warning("Discord 알림 실패: %s", _e)
            if self.cfg.get("slack_notify_on", False):
                _surl = self.cfg.get("slack_webhook_url", "").strip()
                if _surl:
                    try:
                        requests.post(_surl, json={"text": "✅ F7 루프 완료"}, timeout=5)
                    except Exception as _e:
                        log.warning("Slack 알림 실패: %s", _e)

        except Exception as e:
            log.error("F6F7 오류: %s", e, exc_info=True)

        log.info("═══ F6F7 루프 종료 ═══")

    def _f7_mouse_routine(self) -> None:
        """
        좌표 A: 더블클릭 → Q
        좌표 B: 더블클릭 → Q
        좌표 C: 싱글클릭 + Q  ×4
        (좌표는 config.json의 coord_a/b/c 에 설정)
        """
        ca = self._abs_coord("coord_a")
        cb = self._abs_coord("coord_b")
        cc = self._abs_coord("coord_c")

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
        if self._f9thr and self._f9thr.is_alive():
            log.info("═══ F9 정지 요청 ═══")
            self._stop.set()
            return

        log.info("═══ F9 시작 ═══")
        self._stop.clear()
        self._pet_t  = time.time()
        self._f9thr  = threading.Thread(target=self._f9_loop, daemon=True)
        self._f9thr.start()

    # ─────────────────────────────────────
    # F11: 방장모드 / 따라가기 시작/정지
    # ─────────────────────────────────────
    def f11(self) -> None:
        if self._f6f7_thr and self._f6f7_thr.is_alive():
            log.info("[F11] F6F7 대기 중 → 자동 정지")
            self._f6f7_stop.set()
        mode = self.cfg.get("f11_mode", "host")
        if mode == "follow":
            self._f11_follow()
        else:
            self._f11_host()

    def _f11_host(self) -> None:
        if not self.cfg.get("f11_on", False):
            log.warning("F11: 비활성 (설정에서 F11 사용 활성화 필요)")
            return

        if self._f11thr and self._f11thr.is_alive():
            log.info("═══ F11 방장모드 정지 ═══")
            self._host_stop.set()
            return

        if not is_sc_active():
            log.warning("F11: 스타크래프트 비활성 - 무시")
            return

        log.info("═══ F11 방장모드 시작 ═══")
        self._host_stop.clear()
        self._f11thr = threading.Thread(target=self._host_loop, daemon=True)
        self._f11thr.start()

    def _f11_follow(self) -> None:
        if not self.cfg.get("f11_on", False):
            log.warning("F11: 비활성 (설정에서 F11 사용 활성화 필요)")
            return

        if self._follow_thr and self._follow_thr.is_alive():
            log.info("═══ F11 따라가기 정지 ═══")
            self._follow_stop.set()
            return

        if not is_sc_active():
            log.warning("F11(follow): 스타크래프트 비활성 - 무시")
            return

        follow_nickname = self.cfg.get("follow_nickname", "").strip()
        if not follow_nickname:
            log.warning("F11(follow): follow_nickname 미설정 (설정창에서 입력 필요)")
            return

        log.info("═══ F11 따라가기 시작 (닉네임: %s) ═══", follow_nickname)
        self._follow_stop.clear()
        self._follow_thr = threading.Thread(target=self._follow_loop, daemon=True)
        self._follow_thr.start()

    # ─────────────────────────────────────
    # 따라가기 루프
    # ─────────────────────────────────────
    def _follow_loop(self) -> None:
        FOLLOW_CONF = float(self.cfg.get("follow_confidence", 0.75))
        nickname    = self.cfg.get("follow_nickname", "").strip()
        MAX_RETRY   = 20

        def _full():
            hwnd = _sc_find_hwnd()
            if not hwnd:
                return None
            gx, gy, gw, gh = _sc_get_rect(hwnd)
            return (gx, gy, gw, gh) if gw > 0 else None

        log.info("═══ [따라가기] 루프 시작 ═══")
        try:
            reg = _full()
            if not reg:
                log.warning("[따라가기] SC 창을 찾을 수 없음")
                return

            search_reg = self._abs_region("follow_search_region")
            if not search_reg:
                log.warning("[따라가기] follow_search_region 미설정 → 전체 창으로 fallback")
                search_reg = reg

            step2_fails = 0
            for attempt in range(1, MAX_RETRY + 1):
                if self._follow_stop.is_set():
                    log.info("[따라가기] 정지 요청")
                    break

                log.info("─── [따라가기] 시도 %d/%d ───", attempt, MAX_RETRY)

                # Step 1: AutoFollow_3 ("친구 [") 탐색 → 클릭
                log.info("🔍 Step1: AutoFollow_3 탐색")
                pos3 = self.finder.find("AutoFollow_3", FOLLOW_CONF, reg)
                if pos3:
                    self.inp.click(int(pos3[0]), int(pos3[1]))
                    log.info("✅ AutoFollow_3 클릭 @ %s", pos3)
                    time.sleep(0.5)
                else:
                    log.warning("AutoFollow_3 미발견 → 계속 진행")

                # Step 2: 닉네임 Y좌표 OCR 탐색
                log.info("🔍 Step2: 닉네임 '%s' OCR 탐색", nickname)
                found_y = self._follow_find_nickname_y(search_reg, nickname)
                if found_y is None:
                    step2_fails += 1
                    log.warning("닉네임 '%s' 미발견 → Step1 재시도 (%d/10)", nickname, step2_fails)
                    if step2_fails >= 10:
                        log.warning("[따라가기] 닉네임 10회 미발견 → 루프 자동 종료")
                        return
                    time.sleep(0.5)
                    continue
                step2_fails = 0
                log.info("✅ 닉네임 발견 Y=%d", found_y)

                # Step 3: 그 Y의 X축에서 AutoFollow_2 탐색 → 클릭
                log.info("🔍 Step3: AutoFollow_2 탐색 (Y=%d)", found_y)
                if self._follow_click_arrow(reg, found_y, FOLLOW_CONF):
                    time.sleep(2.0)
                    if self.cfg.get("auto_drive_on", False):
                        log.info("🚗 [따라가기] 자동운행모드 → F6 입력")
                        self.f6()
                    log.info("✅ [따라가기] 완료")
                    break
                log.warning("AutoFollow_2 미발견 → Step1 재시도 (%d/20)", attempt)
                time.sleep(0.5)
            else:
                log.warning("[따라가기] AutoFollow_2 20회 미발견 → 루프 자동 종료")

        except Exception as e:
            log.error("[따라가기] 오류: %s", e, exc_info=True)

        log.info("═══ [따라가기] 종료 ═══")

    def _follow_find_nickname_y(self, region: tuple, nickname: str) -> Optional[int]:
        """follow_search_region 내 OCR로 닉네임 행의 절대 Y 좌표 반환."""
        px, py, pw, ph = region
        shot = pyautogui.screenshot(region=(px, py, pw, ph))
        bgr  = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
        # 밝은 텍스트 마스크: 닉네임(흰색/밝은회색) 유지, 클랜태그(어두운회색) 제거
        hsv  = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        mask = (hsv[:, :, 2] > 80) & (hsv[:, :, 1] < 80)
        img  = np.where(mask, np.uint8(255), np.uint8(0))
        scale   = 2
        img_big = cv2.resize(img, (pw * scale, ph * scale), interpolation=cv2.INTER_CUBIC)

        data = pytesseract.image_to_data(
            _PILImage.fromarray(img_big),
            output_type=pytesseract.Output.DICT,
            config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'",
        )

        nick_lower = nickname.lower()
        nlen = len(nick_lower)

        def _fuzzy_match(t: str) -> bool:
            # 1. 정확한 substring 포함
            if nick_lower in t:
                return True
            # 2. 전체 문자열 유사도 0.70 이상
            if difflib.SequenceMatcher(None, nick_lower, t).ratio() >= 0.70:
                return True
            # 3. 복합 OCR 문자열 내 슬라이딩 윈도우 (게임 폰트 오인식 보정)
            if len(t) >= nlen:
                for k in range(len(t) - nlen + 1):
                    sub = t[k:k + nlen]
                    if difflib.SequenceMatcher(None, nick_lower, sub).ratio() >= 0.70:
                        return True
            return False

        tokens = [(i, text.strip().lower()) for i, text in enumerate(data["text"]) if text.strip()]
        for idx, (i, t) in enumerate(tokens):
            candidates = [t]
            if idx + 1 < len(tokens):
                candidates.append(t + tokens[idx + 1][1])
            if idx + 2 < len(tokens):
                candidates.append(t + tokens[idx + 1][1] + tokens[idx + 2][1])
            for c in candidates:
                if _fuzzy_match(c):
                    y_in_region = int(data["top"][i] / scale) + int(data["height"][i] / scale) // 2
                    return py + y_in_region
        return None

    def _follow_click_arrow(self, full_reg: tuple, target_y: int, conf: float) -> bool:
        """target_y 행의 X축에서 AutoFollow_2(→ 버튼)를 탐색해 클릭."""
        rx, ry, rw, rh = full_reg
        strip_y = max(ry, target_y - 40)
        strip_reg = (rx, strip_y, rw, 80)
        pos = self.finder.find("AutoFollow_2", conf, strip_reg)
        if pos:
            self.inp.click(int(pos[0]), int(pos[1]))
            log.info("✅ [따라가기] AutoFollow_2 클릭 @ (%d, %d)", pos[0], pos[1])
            return True
        return False

    def _host_loop(self) -> None:
        HOST_CONF = float(self.cfg.get("host_confidence", 0.65))

        def _full():
            hwnd = _sc_find_hwnd()
            if not hwnd:
                return None
            gx, gy, gw, gh = _sc_get_rect(hwnd)
            return (gx, gy, gw, gh) if gw > 0 else None

        def _find(name):
            reg = _full()
            if reg is None:
                return None
            return self.finder.find(name, HOST_CONF, reg)

        def _click_and_wait(name: str, delay: float) -> None:
            res = _find(name)
            if res:
                self.inp.click(int(res[0]), int(res[1]))
                log.info("✅ [방장] %s 클릭", name)
                time.sleep(delay)

        def _ocr_username(h3_pos) -> str:
            # Host_3 중심 기준 닉네임 슬롯 전체 영역 (x-720, y-518, 290×340)
            px = max(0, int(h3_pos[0]) - 720)
            py = max(0, int(h3_pos[1]) - 518)
            pw, ph = 290, 340
            shot = pyautogui.screenshot(region=(px, py, pw, ph))
            img  = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2GRAY)
            _, img = cv2.threshold(img, 80, 255, cv2.THRESH_BINARY)
            img = cv2.resize(img, (pw * 2, ph * 2), interpolation=cv2.INTER_CUBIC)
            return pytesseract.image_to_string(_PILImage.fromarray(img), config="--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'").strip()

        usernames = [u.strip() for u in self.cfg.get("host_username", "Hanayoi").split(",") if u.strip()]

        try:
            # ── Step 1 ─────────────────────────────────────────
            log.info("🔍 [방장] Step1: Host_1 대기")
            goto_step = 2  # 기본값: Host_1 클릭 후 Step2
            step1_done = False
            while not self._host_stop.is_set():
                time.sleep(0.1)
                h1 = _find("Host_1")
                if h1:
                    log.info("✅ [방장] Host_1 감지 → 클릭")
                    self.inp.click(int(h1[0]), int(h1[1]))
                    time.sleep(3.0)
                    step1_done = True
                    break

                # Host_1 없음: Host_3 확인
                h3 = _find("Host_3")
                if h3:
                    log.info("⏭️ [방장] Host_1 없음 / Host_3 감지 → Step3 이동")
                    time.sleep(1.0)
                    goto_step = 3
                    step1_done = True
                    break

                # Host_3 없음: Host_2 확인
                h2 = _find("Host_2")
                if h2:
                    log.info("⏭️ [방장] Host_1 없음 / Host_2 감지 → Step2 이동")
                    time.sleep(1.0)
                    goto_step = 2
                    step1_done = True
                    break

            if not step1_done:
                return  # 정지 요청

            # ── Step 2 ─────────────────────────────────────────
            if goto_step <= 2:
                log.info("🔍 [방장] Step2: Host_2 대기")
                while not self._host_stop.is_set():
                    time.sleep(0.1)
                    # Host_3(OCR 영역) 먼저 확인 → 바로 Step3
                    h3 = _find("Host_3")
                    if h3:
                        log.info("⏭️ [방장] Step2 중 Host_3 감지 → Step3 이동")
                        time.sleep(1.0)
                        break

                    h2 = _find("Host_2")
                    if h2:
                        log.info("✅ [방장] Host_2 감지 → 클릭")
                        self.inp.click(int(h2[0]), int(h2[1]))
                        time.sleep(2.5)
                        break
                else:
                    return

            # ── Step 3 ─────────────────────────────────────────
            def _ocr_match(username: str, ocr_lines: list) -> bool:
                """OCR 각 행과 유사도 비교 (0.70 이상이면 매칭)."""
                u = username.lower()
                for line in ocr_lines:
                    l = line.strip().lower()
                    if not l:
                        continue
                    # 직접 포함 체크
                    if u in l:
                        return True
                    # 유사도 체크 (OCR 오인식 보정)
                    ratio = difflib.SequenceMatcher(None, u, l).ratio()
                    if ratio >= 0.70:
                        return True
                return False

            reg0 = _full()
            if reg0:
                log.info("🖥️ [방장] 게임 창 크기: %dx%d", reg0[2], reg0[3])
            log.info("🔍 [방장] Step3: Host_3 OCR 루프 시작 (닉네임: %s)", ", ".join(usernames))
            while not self._host_stop.is_set():
                time.sleep(0.1)
                h3 = _find("Host_3")
                if not h3:
                    continue

                log.info("🟡 [방장] Host_3 감지 → OCR")
                ocr_text = _ocr_username(h3)
                log.info("📋 [방장] OCR: %r", ocr_text)
                ocr_lines = ocr_text.splitlines()

                found   = [u for u in usernames if _ocr_match(u, ocr_lines)]
                missing = [u for u in usernames if not _ocr_match(u, ocr_lines)]
                log.info("✅ 확인: %s | ❌ 미확인: %s", found, missing)
                if not missing:
                    log.info("🎯 [방장] 전원 확인 (%s) → 3.0s 후 Host_4 클릭", ", ".join(found))
                    time.sleep(3.0)
                    _click_and_wait("Host_4", 0.5)
                    if self.cfg.get("auto_drive_on", False):
                        log.info("🚗 [방장] 자동운행모드 → F6 입력")
                        self.f6()
                    break
                else:
                    log.info("⏳ [방장] 미확인 인원 있음 → 재탐색")
                    time.sleep(0.5)

        except Exception as e:
            log.error("[방장] 루프 오류: %s", e, exc_info=True)

        log.info("═══ F11 방장모드 종료 ═══")

    # ─────────────────────────────────────
    # 게임 종료 루프
    # ─────────────────────────────────────
    @staticmethod
    def _find_sc_shot_dir() -> str:
        """StarCraft 스크린샷 폴더를 자동 탐색 (OneDrive 리디렉션 포함)."""
        import ctypes, ctypes.wintypes
        # SHGetFolderPathW로 실제 내 문서 경로 획득 (OneDrive 리디렉션 자동 반영)
        try:
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
            docs = buf.value
        except Exception:
            docs = os.path.expanduser("~\\Documents")

        home = os.path.expanduser("~")
        candidates = [
            os.path.join(docs, "StarCraft", "Screenshots"),
            os.path.join(home, "Documents", "StarCraft", "Screenshots"),
            os.path.join(home, "OneDrive", "문서", "StarCraft", "Screenshots"),
            os.path.join(home, "OneDrive", "Documents", "StarCraft", "Screenshots"),
        ]
        for path in candidates:
            if os.path.isdir(path):
                return path
        # 폴더가 없으면 내 문서 기준 경로 반환 (게임 최초 실행 전)
        return os.path.join(docs, "StarCraft", "Screenshots")

    _SC_SHOT_DIR: str = ""   # 런타임에 _find_sc_shot_dir()로 초기화

    # ─────────────────────────────────────
    # 자동 보스 선택
    # ─────────────────────────────────────
    @staticmethod
    def _parse_dps_억(text: str) -> float:
        import re
        # 1차: 정상 파싱 (한글 OCR 성공 시)
        m억 = re.search(r'([\d,]+)\s*억', text)
        m만 = re.search(r'([\d,]+)\s*만', text)
        if m억:
            억_val = float(m억.group(1).replace(',', ''))
            만_val = float(m만.group(1).replace(',', '')) / 10000.0 if m만 else 0.0
            return 억_val + 만_val

        # 1.5차: 억 미인식 + 만 인식 시 — 억 오인식 digit 제거 후 재조합
        # 예: "119억 6984만" → OCR "1194 6984 만" / "193억 3723만" → "19398 3723 만"
        # 3자리 이하(raw≤999)는 정상값으로 처리, 4자리+ 일 때만 trim 적용
        if m만:
            만_val = float(m만.group(1).replace(',', '')) / 10000.0
            before_만 = text[:m만.start()]
            n1_list = [int(n.replace(',', '')) for n in re.findall(r'[\d,]+', before_만) if n.replace(',', '')]
            if n1_list:
                raw = n1_list[-1]
                raw_str = str(raw)
                if len(raw_str) >= 4:
                    for trim in range(1, min(len(raw_str) - 1, 3)):
                        trimmed = int(raw_str[:-trim])
                        if 1 <= trimmed <= 999:
                            log.info("📋 [보스선택] 억 오인식 보정: %d → %d억 (trim=%d)", raw, trimmed, trim)
                            return float(trimmed) + 만_val
                    trimmed = int(raw_str[:-1])
                    if 1 <= trimmed <= 9999:
                        log.info("📋 [보스선택] 억 오인식 보정(fallback): %d → %d억", raw, trimmed)
                        return float(trimmed) + 만_val
                if 1 <= raw <= 9999:
                    return float(raw) + 만_val

        # 2차: 한글 OCR 실패 시 — 콜론 뒤 숫자만 추출
        after_colon = re.split(r':', text)[-1]
        nums = [int(n.replace(',', '')) for n in re.findall(r'[\d,]+', after_colon) if n.replace(',', '')]
        if not nums:
            nums = [int(n.replace(',', '')) for n in re.findall(r'[\d,]+', text) if n.replace(',', '')]

        if len(nums) >= 2:
            n1, n2 = nums[0], nums[1]
            if 1 <= n1 <= 99999 and 0 <= n2 <= 9999:
                return n1 + n2 / 10000.0
        if len(nums) >= 1:
            n = nums[0]
            if 1 <= n <= 99999:
                return float(n)
            if 10000 < n <= 999999999:
                return n / 10000.0

        return 0.0

    def _auto_boss_select(self, reg) -> None:
        """
        보스 선택 화면 진입 시 파티 딜량 OCR → 최적 보스+난이도로 자동 이동.
        L(도전)은 누르지 않음 — 수동 입력 대기.
        비활성 상태(auto_boss_select_on=False)에서는 호출되지 않음.
        """
        import re
        BOSS_HP = {
            # (boss_idx, diff_idx): {인원수: HP(억)}
            # 헬 (W×4)
            (0, 4): {6: 100.0,   5: 83.4,   4: 66.8,   3: 50.2,   2: 33.6},
            (1, 4): {6: 115.0,   5: 95.91,  4: 76.82,  3: 57.73,  2: 38.64},
            (2, 4): {6: 130.0,   5: 108.42, 4: 86.84,  3: 65.26,  2: 43.68},
            (3, 4): {6: 145.0,   5: 120.93, 4: 96.86,  3: 72.79,  2: 48.72},
            (4, 4): {6: 165.0,   5: 137.61, 4: 110.22, 3: 82.83,  2: 55.44},
            # 카오스 (W×5)
            (0, 5): {6: 200.0,   5: 166.8,  4: 133.6,  3: 100.4},
            (1, 5): {6: 240.0,   5: 200.16, 4: 160.32, 3: 120.48},
            (2, 5): {6: 285.0,   5: 237.69, 4: 190.38, 3: 143.07},
            (3, 5): {6: 335.0,   5: 279.39, 4: 223.78, 3: 168.17},
            (4, 5): {6: 400.0,   5: 333.6,  4: 267.2,  3: 200.8},
        }
        BOSS_NAMES = ["알카", "이터", "크라", "노바", "엔드"]
        DIFF_NAMES = ["이지", "노말", "하드", "익스", "헬", "카오스"]

        # 1. 인원 수 (host_username 쉼표 split)
        usernames = [u.strip() for u in self.cfg.get("host_username", "").split(",") if u.strip()]
        player_count = max(1, len(usernames))
        log.info("🎯 [보스선택] 인원 수: %d인", player_count)

        # 2. SelectBoss_0 위치 확인 (find_box → 우측 끝 좌표 획득)
        sb0_box = self.finder.find_box("SelectBoss_0", 0.75, reg)
        if sb0_box is None:
            log.warning("⚠️ [보스선택] SelectBoss_0 미감지 → 중단")
            return

        # 3. 파티 딜량 OCR (템플릿 우측 끝에서 시작 → 딜량 숫자 영역만 크롭)
        gx, gy, gw, gh = reg
        sb0_left, sb0_top, sb0_w, sb0_h = sb0_box
        ocr_x = max(0, sb0_left + sb0_w)        # 템플릿 우측 끝
        ocr_y = max(0, sb0_top - 5)
        ocr_w = min(500, int(gx + gw) - ocr_x)  # 숫자 영역 최대 500px
        ocr_h = sb0_h + 10
        shot = pyautogui.screenshot(region=(ocr_x, ocr_y, ocr_w, ocr_h))
        img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2GRAY)
        _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        img = cv2.resize(img, (ocr_w * 3, ocr_h * 3), interpolation=cv2.INTER_CUBIC)
        # psm7 먼저, 아래 조건 중 하나라도 해당되면 psm8 재시도
        #   ① 만 값 > 9999 (노이즈로 자릿수 증가)
        #   ② 억이 OCR에 있으나 digit 직전 매칭 실패 (예: "11 디 억" → "9"→"디" 오인식)
        pil_img = _PILImage.fromarray(img)
        ocr_text = ""
        for _cfg in ["--oem 3 --psm 7", "--oem 3 --psm 8"]:
            try:
                _t = pytesseract.image_to_string(pil_img, lang="kor+eng", config=_cfg).strip()
            except Exception:
                _t = ""
            log.info("📋 [보스선택] OCR [%s]: %r", _cfg.split()[-1], _t)
            if not _t:
                continue
            _m만 = re.search(r'([\d,]+)\s*만', _t)
            _만_val = int(_m만.group(1).replace(',', '')) if _m만 else -1
            _m억_direct = re.search(r'([\d,]+)\s*억', _t)
            _억_exists = '억' in _t
            # 채택 조건: (억 직접 매칭 성공 + 만 유효/없음) OR (억 없음 + 만 유효)
            _valid = (_m억_direct is not None and (not _m만 or 0 <= _만_val <= 9999)) or \
                     (_m억_direct is None and not _억_exists and 0 <= _만_val <= 9999)
            # 억 없고 만도 없지만 억 직접 매칭 성공 (만 없는 단일 억 케이스)
            if not _m만 and _m억_direct:
                _valid = True
            # [FIX1] 억 앞 숫자 선행 0 → 앞 digit 누락 오인식 → psm8 재시도
            if _m억_direct and _m억_direct.group(1).startswith('0'):
                _valid = False
            # [FIX2] 억 미인식인데 만 앞 숫자 >9999 → 억 오인식 의심 → psm8 재시도
            if _m억_direct is None and not _억_exists and _m만:
                _before_만 = _t[:_m만.start()]
                if any(int(n) > 9999 for n in re.findall(r'\d+', _before_만)):
                    _valid = False
            if _valid:
                ocr_text = _t
                break
            if not ocr_text:
                ocr_text = _t
        if not ocr_text:
            try:
                ocr_text = pytesseract.image_to_string(
                    pil_img, config="--psm 7 -c tessedit_char_whitelist=0123456789,.: "
                ).strip()
                log.info("📋 [보스선택] 한글 OCR 불가 → 숫자 전용 fallback: %r", ocr_text)
                if not any(c.isdigit() for c in ocr_text):
                    ocr_text = pytesseract.image_to_string(pil_img, config="--psm 7").strip()
            except Exception:
                pass
        log.info("📋 [보스선택] 딜량 OCR: %r", ocr_text)

        party_dps = self._parse_dps_억(ocr_text)
        if party_dps <= 0:
            log.warning("⚠️ [보스선택] 딜량 파싱 실패 (%r) → 중단", ocr_text)
            return
        log.info("💥 [보스선택] 파티 딜량: %.4f억", party_dps)

        # 4. 조건 만족(딜량 > HP) 중 HP 최대값 탐색
        # 2인은 카오스 클리어 조건 미충족(게임 제한) → 헬(diff_idx=4)까지만 허용
        max_diff = 4 if player_count <= 2 else 5
        if player_count <= 2:
            log.info("👥 [보스선택] 2인 파티 → 카오스 제외, 헬 최대 적용")

        best = None  # (hp, boss_idx, diff_idx)
        for (b, d), hp_map in BOSS_HP.items():
            if d > max_diff:
                continue
            hp = hp_map.get(player_count)
            if hp is None:
                continue
            if party_dps > hp:
                if best is None or hp > best[0]:
                    best = (hp, b, d)

        if best is None:
            log.warning("⚠️ [보스선택] 조건 만족 보스 없음 (딜량: %.2f억) → 중단", party_dps)
            return

        hp_val, boss_idx, diff_idx = best
        log.info("🏆 [보스선택] 선택: %s %s (HP %.2f억)",
                 DIFF_NAMES[diff_idx], BOSS_NAMES[boss_idx], hp_val)

        # 5. SC 창 감지 + PostMessage 키입력 헬퍼
        _WM_KEYDOWN = 0x0100
        _WM_KEYUP   = 0x0101
        _VK = {
            'w': 0x57, 's': 0x53, 'a': 0x41, 'd': 0x44,
            'l': 0x4C, 'e': 0x45, 'q': 0x51,
        }

        hwnd = _sc_find_hwnd()
        log.info("🖥️ [보스선택] SC hwnd: %s", hwnd)

        def _post_key(key: str, delay: float = 0.5):
            vk = _VK.get(key.lower())
            if vk and hwnd:
                _u32.PostMessageW(hwnd, _WM_KEYDOWN, vk, 0)
                time.sleep(0.05)
                _u32.PostMessageW(hwnd, _WM_KEYUP, vk, 0)
                time.sleep(delay)
            else:
                self.inp.press(key, delay)

        # 6. 보스 이동 (S × boss_idx)
        for i in range(boss_idx):
            log.info("➡️ [보스선택] S (%d/%d)", i + 1, boss_idx)
            _post_key("s", 0.5)

        # 7. 난이도 설정 (W × diff_idx)
        for i in range(diff_idx):
            log.info("⬆️ [보스선택] W (%d/%d)", i + 1, diff_idx)
            _post_key("w", 0.5)

        log.info("✅ [보스선택] 완료 → %s %s 대기 (L은 수동 입력)",
                 DIFF_NAMES[diff_idx], BOSS_NAMES[boss_idx])

    def _game_end_check(self, reg, is_active: bool) -> tuple:
        """
        게임종료 루프.
        - is_active=False : SelectBoss_0 감지 시 True 반환 (활성화)
        - is_active=True  : BossClear_2 감지 시 종료 시퀀스 실행
        반환: (새로운 is_active 값, 시퀀스 실행 여부)
        """
        import glob as _glob

        if not is_active:
            gx, gy, gw, gh = reg
            rx = float(self.cfg.get("boss_loop_rx", 0.2677))
            ry = float(self.cfg.get("boss_loop_ry", 0.2494))
            rw = float(self.cfg.get("boss_loop_rw", 0.4553))
            rh = float(self.cfg.get("boss_loop_rh", 0.3024))
            boss_reg = (
                int(gx + gw * rx),
                int(gy + gh * ry),
                int(gw * rw),
                int(gh * rh),
            )
            if self.finder.find("SelectBoss_0", 0.80, boss_reg):
                log.info("🎮 [종료] SelectBoss_0 감지")
                if self.cfg.get("f11_mode", "host") == "host":
                    self._boss_select_active = True
                    if self.cfg.get("auto_boss_select_on", False):
                        log.info("🎯 [보스선택] 방장모드 + 자동보스선택 ON → 보스선택 시작")
                        self._auto_boss_select(reg)
                        log.info("🔄 [보스선택] 완료 → 게임종료 모드 전환")
                    else:
                        log.info("🎮 [보스선택] 방장모드 ON → 보스선택 모드 전환")
                else:
                    log.info("🎮 [종료] 게임종료 모드 전환")
                return True, False
            return False, False

        gx, gy, gw, gh = reg
        rx = float(self.cfg.get("boss_loop_rx", 0.2677))
        ry = float(self.cfg.get("boss_loop_ry", 0.2494))
        rw = float(self.cfg.get("boss_loop_rw", 0.4553))
        rh = float(self.cfg.get("boss_loop_rh", 0.3024))
        boss_reg = (
            int(gx + gw * rx),
            int(gy + gh * ry),
            int(gw * rw),
            int(gh * rh),
        )
        if not self.finder.find("BossClear_2", 0.80, boss_reg):
            return True, False

        log.info("🏆 [종료] BossClear_2 감지 → 종료 시퀀스 시작")

        # 스크린샷 폴더 감시 시작 (PrtSc 전)
        before = set(_glob.glob(self._SC_SHOT_DIR + r"\*.png") +
                     _glob.glob(self._SC_SHOT_DIR + r"\*.bmp"))
        log.info("📁 [종료] 폴더 감시 시작")

        self.inp.press("print screen")
        log.info("📸 [종료] PrtSc 입력")
        time.sleep(1.5)

        # 신규 파일 확인 → 없으면 루프 중단
        after = set(_glob.glob(self._SC_SHOT_DIR + r"\*.png") +
                    _glob.glob(self._SC_SHOT_DIR + r"\*.bmp"))
        new_files = after - before
        if not new_files:
            log.warning("⚠️ [종료] 스크린샷 파일 미확인 → 루프 중단")
            return True, False   # 활성 상태 유지, 시퀀스 미실행
        log.info("✅ [종료] 스크린샷 확인: %s", os.path.basename(new_files.pop()))
        time.sleep(0.5)
        self.inp.press("f10");   time.sleep(0.3)
        self.inp.press("e");     time.sleep(0.3)
        self.inp.press("s");     time.sleep(0.3)
        self.inp.press("q");     time.sleep(3.0)
        self.inp.press("enter"); time.sleep(0.5)

        if self.cfg.get("f11_on", False):
            log.info("♟️ [종료] f11_on → F11 직접 호출")
            threading.Thread(target=self.f11, daemon=True).start()

        log.info("✅ [종료] 게임 종료 시퀀스 완료")
        return False, True   # 시퀀스 완료 후 비활성화

    def _f9_loop(self) -> None:
        # macro.exe 추출 정확도 상수
        SEAL_CONF   = 0.75
        TARGET_CONF = 0.65
        SPEED2_CONF = 0.93
        SPEED3_CONF = 0.78
        COUNT_CONF  = 0.94
        BOX25_CONF  = 0.91
        BOX26_CONF  = 0.91
        BOX27_CONF  = 0.91
        ON_CONF     = 0.70
        KEY_CONF    = 0.78

        is_auto_sell_set = False
        self._game_end_mode = False
        self._boss_select_active = False

        while not self._stop.is_set():
            try:
                # ── 게임 창 위치/크기 ────────────────────
                hwnd = _sc_find_hwnd()
                if not hwnd:
                    time.sleep(1)
                    continue
                gx, gy, gw, gh = _sc_get_rect(hwnd)
                if gw <= 0 or gh <= 0:
                    time.sleep(1)
                    continue

                full_reg = (gx, gy, gw, gh)

                # ── 게임종료 모드: BossClear_2 전담 탐색 ──
                if self._game_end_mode:
                    try:
                        _, did_end = self._game_end_check(full_reg, True)
                    except Exception as e:
                        log.error("[종료] 게임종료 루프 오류: %s", e, exc_info=True)
                        time.sleep(1.0)
                        continue
                    if did_end:
                        log.info("🔴 [종료] 게임종료 완료 → F9 루프 종료")
                        self._stop.set()
                        break
                    time.sleep(0.12)
                    continue

                self._pet_upgrade_check()
                if self._stop.is_set():
                    break

                # ── 탐색 영역 (게임 창 상대 비율) ─────────
                box_reg   = (int(gx + gw*0.10), int(gy + gh*0.60), int(gw*0.40), int(gh*0.20))
                info_reg  = (int(gx + gw*0.25), int(gy + gh*0.75), int(gw*0.45), int(gh*0.23))
                cmd_reg   = (int(gx + gw*0.65), int(gy + gh*0.65), int(gw*0.35), int(gh*0.35))
                field_reg = (gx + 50, gy + 50, gw - 100, gh - 250)
                b28_conf  = self.cfg.get("box28_confidence_set", 0.93)
                max_box   = int(self.cfg.get("max_box", 28))

                # ── 게임종료 루프 (SelectBoss_0 감지) ─────
                if self.cfg.get("game_end_on", False):
                    active, _ = self._game_end_check(full_reg, False)
                    if active:
                        log.info("🟡 [종료] SelectBoss_0 감지 → 게임종료 모드 전환")
                        self._game_end_mode = True
                        continue

                # ── Max Box 자동 판매 설정 ───────────────
                if self.cfg.get("f9_box28_monitor_on", True) and not is_auto_sell_set:
                    if self.finder.find(f"{max_box}box", b28_conf, box_reg):
                        log.info("📦 [%d상자 발견] 자동 판매 설정 시작", max_box)
                        log.info("⌨️ [자동판매] '3' 키 입력")
                        self.inp.press("3")
                        time.sleep(0.5)
                        _off = self.cfg.get("check_on_offset", [0, 0])
                        if _off and (_off[0] != 0 or _off[1] != 0):
                            cx, cy = self._abs_coord("check_on_offset")
                        else:
                            cx, cy = self._abs_xy("check_on_offset_x", "check_on_offset_y")
                        pyautogui.moveTo(cx, cy)
                        time.sleep(0.4)
                        if self.finder.find("on", ON_CONF, cmd_reg):
                            log.info("✅ [자동판매] ON 확인 → 설정 완료")
                        else:
                            log.info("⌨️ [자동판매] ON 미감지 → A키 입력")
                            self.inp.press("a")
                        is_auto_sell_set = True
                        time.sleep(0.5)
                        continue

                # ── seal_idle + target_circle 탐색 ────────
                seal = self.finder.find("seal_idle", SEAL_CONF, field_reg)
                target = self.finder.find("target_circle", TARGET_CONF, full_reg)
                if not target:
                    target = self.finder.find("target_circle2", TARGET_CONF, full_reg)

                if not (seal and target):
                    time.sleep(0.12)
                    continue

                sx, sy = seal
                tx, ty = target

                # ── 초반 분기 ────────────────────────────
                if self.cfg.get("f9_early_branch_on", True):
                    log.info("⚙️ [초반 분기] 대기 인장 선택")
                    pyautogui.click(int(sx), int(sy))
                    time.sleep(0.05)

                    if self.finder.find("speed3", SPEED3_CONF, info_reg):
                        if not is_auto_sell_set:
                            log.info("⏩ speed3(3배속) 감지 → 열쇠 탐색")
                            key_res = self.finder.find("key", KEY_CONF, field_reg)
                            if key_res:
                                log.info("🔑 열쇠 발견 → 클릭 후 타겟 우클릭")
                                self.inp.click(int(key_res[0]), int(key_res[1]))
                                self.inp.rclick(int(tx), int(ty))
                                time.sleep(1.0)
                                continue
                            else:
                                log.info("🔍 speed3 감지 / 열쇠 없음 → 변환루트")
                        else:
                            log.info("⏩ speed3 감지 / MaxBox 도달 → 변환루트")

                    elif self.finder.find("speed2", SPEED2_CONF, info_reg):
                        if not is_auto_sell_set:
                            log.info("▶️ speed2(2배속) 감지 → 열쇠 탐색")
                            key_res = self.finder.find("key", KEY_CONF, field_reg)
                            if key_res:
                                log.info("🔑 열쇠 발견 → 클릭 후 타겟 우클릭")
                                self.inp.click(int(key_res[0]), int(key_res[1]))
                                self.inp.rclick(int(tx), int(ty))
                                time.sleep(1.0)
                                continue
                            else:
                                log.info("🔍 speed2 감지 / 열쇠 없음 → 변환루트")
                        else:
                            log.info("▶️ speed2 감지 / MaxBox 도달 → 변환루트")

                # ── 변환 초기 클릭 ────────────────────────
                pyautogui.click(int(gx + gw * 0.6), int(gy + gh * 0.5) - 30)
                time.sleep(0.1)

                # ── bou(파편) 판정 ────────────────────────
                bou_found = self.finder.find("bou", 0.6, info_reg)

                if not bou_found:
                    log.info("🔮 [초월인장] 파편 0개 → 일반 변환")
                    pyautogui.click(int(sx), int(sy))
                    time.sleep(0.1)
                    pyautogui.rightClick(int(tx), int(ty))
                else:
                    snapshot    = pyautogui.screenshot()
                    found_num   = None
                    matched_box = None
                    for i in range(1, 4):
                        c_box = self.finder.find_box(f"count_{i}", COUNT_CONF, info_reg)
                        if c_box:
                            found_num   = i
                            matched_box = c_box
                            break

                    if found_num and matched_box:
                        if self._check_double_digit(matched_box, found_num, snapshot):
                            log.info("💀 [종말인장] 숫자 %d 주변 다른 숫자(10개+) → A키", found_num)
                            self.inp.press("a")
                        else:
                            log.info("🔮 [초월인장] 파편 %d개 부족 → 일반 변환", 4 - found_num)
                            pyautogui.click(int(sx), int(sy))
                            time.sleep(0.1)
                            pyautogui.rightClick(int(tx), int(ty))
                    else:
                        log.info("💀 [종말인장] 파편 4개+ (인식 초과) → A키")
                        self.inp.press("a")

                time.sleep(0.5)

            except Exception as e:
                log.error("F9 루프 오류: %s", e, exc_info=True)
                time.sleep(1.0)

        log.info("F9 루프 종료")

    def _check_double_digit(self, box: Tuple, matched_num: int, snapshot) -> bool:
        """count 이미지 우측 12×14픽셀 스캔 → 밝은 픽셀(>80) 있으면 True (10개 이상 판정)"""
        if snapshot is None:
            return False
        left, top, width, height = box
        gsx = int(left + width + 2)
        gsy = int(top)
        for dx in range(12):
            for dy in range(14):
                try:
                    pv = snapshot.getpixel((gsx + dx, gsy + dy))
                    v  = pv[0] if isinstance(pv, tuple) else pv
                    if v > 80:
                        return True
                except Exception:
                    pass
        if matched_num in (2, 3):
            lr = (int(left - 16), int(top - 2), 20, int(height + 4))
            if self.finder.find_box("count_1", 0.88, lr):
                return True
        return False

    # ── 주기적 펫 업그레이드 ──────────────
    def _pet_upgrade_check(self) -> None:
        interval = self.cfg.get("f9_pet_interval", 200)
        if time.time() - self._pet_t >= interval:
            log.info("[펫 업그레이드] 실행")
            self.inp.press("2")
            self.inp.type_seq(self.cfg.get("f9_pet_upgrade", ""))
            self._pet_t = time.time()

    # ─────────────────────────────────────
    # 시작
    # ─────────────────────────────────────
    def start(self) -> None:
        log.info("╔══════════════════════════════════╗")
        log.info("║  StarCraft Auto Macro  v1.4      ║")
        log.info("╚══════════════════════════════════╝")
        log.info("F6/F7/F8/F9 : 각 기능 | Ctrl+F11 : 설정 창 | Ctrl+F12 : 종료")

        def spawn(fn):
            return lambda: threading.Thread(target=fn, daemon=True).start()

        keyboard.add_hotkey("f6",        spawn(self.f6))
        keyboard.add_hotkey("f7",        spawn(self.f7))
        keyboard.add_hotkey("f8",        spawn(self.f8))
        keyboard.add_hotkey("f11",       spawn(self.f11))
        keyboard.add_hotkey("ctrl+f12",  self._quit)
        keyboard.add_hotkey("ctrl+f11",
                            lambda: self.root.after(0, self.ui.toggle)
                            if self.ui else None)

        # F9: 단순 누름 → 루프 토글 / 4초 장누름 → 모드 전환
        _f9_timer = [None]
        _f9_long_fired = [False]

        def _f9_hook(e):
            if e.name != "f9":
                return
            if e.event_type == "down" and not self._f9_held:
                self._f9_held = True
                self._f9_press_time = time.time()
                _f9_long_fired[0] = False

                def _long_press():
                    if not self._f9_held:
                        return
                    _f9_long_fired[0] = True
                    if self._f9thr and self._f9thr.is_alive():
                        if self._game_end_mode:
                            log.info("🔄 [F9 장누름] 게임종료 대기 → 일반 모드")
                            self._game_end_mode = False
                            self._boss_select_active = False
                        else:
                            log.info("🔄 [F9 장누름] 일반 → 게임종료 대기 모드")
                            self._game_end_mode = True

                _f9_timer[0] = threading.Timer(4.0, _long_press)
                _f9_timer[0].start()

            elif e.event_type == "up" and self._f9_held:
                self._f9_held = False
                if _f9_timer[0]:
                    _f9_timer[0].cancel()
                    _f9_timer[0] = None
                if not _f9_long_fired[0]:
                    threading.Thread(target=self.f9, daemon=True).start()

        keyboard.hook(_f9_hook)

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
