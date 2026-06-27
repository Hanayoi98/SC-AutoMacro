"""
SC AutoMacro — 환경 설치 프로그램
Python + pip requirements + Tesseract 를 자동으로 설치한다.
stdlib + tkinter 만 사용 → PyInstaller 결과물이 작아진다.
"""
import os, sys, subprocess, urllib.request, threading, ctypes, winreg
import tkinter as tk
from tkinter import ttk, messagebox

BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                            else os.path.abspath(__file__))

PYTHON_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"

def _get_tesseract_url() -> str:
    """GitHub API로 UB-Mannheim Tesseract 최신 w64 설치파일 URL 조회."""
    import json
    api = "https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest"
    req = urllib.request.Request(api, headers={"User-Agent": "SC-AutoMacro-Installer"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    for asset in data["assets"]:
        name = asset["name"]
        if "w64-setup" in name and name.endswith(".exe"):
            return asset["browser_download_url"]
    raise RuntimeError("Tesseract 설치 파일을 찾을 수 없습니다.")


# ── 헬퍼 ──────────────────────────────────────────────────
def _find_python() -> str | None:
    """레지스트리에서 설치된 Python 3 경로 탐색."""
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for sub in (r"SOFTWARE\Python\PythonCore",
                    r"SOFTWARE\WOW6432Node\Python\PythonCore"):
            try:
                key = winreg.OpenKey(hive, sub)
                i = 0
                while True:
                    try:
                        ver = winreg.EnumKey(key, i)
                        ikey = winreg.OpenKey(key, ver + r"\InstallPath")
                        d = winreg.QueryValue(ikey, "").strip()
                        exe = os.path.join(d, "python.exe")
                        if os.path.exists(exe):
                            return exe
                        i += 1
                    except OSError:
                        break
            except OSError:
                pass
    return None


def _tesseract_ok() -> bool:
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if os.path.exists(p):
            return True
    return False


def _tesseract_dir() -> str | None:
    for p in (r"C:\Program Files\Tesseract-OCR",
              r"C:\Program Files (x86)\Tesseract-OCR"):
        if os.path.isdir(p):
            return p
    return None


def _kor_ok() -> bool:
    d = _tesseract_dir()
    if not d:
        return False
    return os.path.exists(os.path.join(d, "tessdata", "kor.traineddata"))


def _download(url: str, dest: str, on_progress) -> None:
    def _cb(count, block, total):
        if total > 0:
            pct = min(100, count * block * 100 // total)
            on_progress(pct)
    urllib.request.urlretrieve(url, dest, _cb)


# ── GUI ───────────────────────────────────────────────────
class App:
    C_BG  = "#1e1e2e"
    C_FG  = "#cdd6f4"
    C_ACC = "#89b4fa"
    C_OK  = "#a6e3a1"
    C_ERR = "#f38ba8"
    FONT  = ("맑은 고딕", 10)

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SC AutoMacro 설치")
        self.root.geometry("500x340")
        self.root.resizable(False, False)
        self.root.configure(bg=self.C_BG)
        self._build()

    def _build(self):
        tk.Label(self.root, text="SC AutoMacro — 환경 설치",
                 font=("맑은 고딕", 14, "bold"),
                 bg=self.C_BG, fg=self.C_ACC).pack(pady=(18, 4))

        self._status = tk.StringVar(value="시작 버튼을 눌러 설치를 진행하세요.")
        tk.Label(self.root, textvariable=self._status,
                 font=self.FONT, bg=self.C_BG, fg=self.C_FG).pack()

        self._pbar = ttk.Progressbar(self.root, length=440, mode="determinate")
        self._pbar.pack(pady=8)

        frame = tk.Frame(self.root, bg=self.C_BG)
        frame.pack(fill="x", padx=28)

        self._log = tk.Text(frame, height=7, font=("Consolas", 9),
                            bg="#313244", fg=self.C_FG,
                            state="disabled", relief="flat", bd=0)
        self._log.pack(fill="x")

        self._btn = tk.Button(self.root, text="  설치 시작  ",
                              font=("맑은 고딕", 11, "bold"),
                              bg=self.C_ACC, fg=self.C_BG,
                              relief="flat", cursor="hand2",
                              command=self._start)
        self._btn.pack(pady=12)

    def _log_line(self, msg: str, color: str = None):
        self._log.config(state="normal")
        tag = f"c{id(color)}"
        if color:
            self._log.tag_configure(tag, foreground=color)
        self._log.insert("end", msg + "\n", tag if color else "")
        self._log.see("end")
        self._log.config(state="disabled")

    def _set(self, msg: str):
        self._status.set(msg)

    def _start(self):
        self._btn.config(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self._install()
            self.root.after(0, lambda: self._set("✅ 설치 완료!"))
            self.root.after(0, lambda: self._log_line("모든 설치가 완료됐습니다.", self.C_OK))
            self.root.after(0, lambda: messagebox.showinfo(
                "완료", "설치 완료!\n실행.bat 으로 매크로를 시작하세요."))
        except Exception as e:
            self.root.after(0, lambda: self._log_line(f"오류: {e}", self.C_ERR))
            self.root.after(0, lambda: messagebox.showerror("오류", str(e)))
        finally:
            self.root.after(0, lambda: self._btn.config(state="normal"))

    # ── 설치 로직 ─────────────────────────────
    def _install(self):
        # 1. Python
        self.root.after(0, lambda: self._set("Python 확인 중..."))
        python_exe = _find_python()

        if not python_exe:
            self.root.after(0, lambda: self._log_line("Python 없음 → 다운로드 중..."))
            dest = os.path.join(BASE_DIR, "_py_setup.exe")
            self._download_with_bar(PYTHON_URL, dest, "Python 다운로드")
            self.root.after(0, lambda: self._set("Python 설치 중..."))
            self.root.after(0, lambda: self._log_line("Python 설치 중... (잠시 대기)"))
            subprocess.run([dest, "/quiet", "InstallAllUsers=0",
                            "PrependPath=1", "Include_test=0"], check=True)
            os.remove(dest)
            python_exe = _find_python()
            if not python_exe:
                raise RuntimeError("Python 설치 후 경로를 찾을 수 없습니다. PC를 재시작 후 다시 시도해 주세요.")
            self.root.after(0, lambda: self._log_line(f"Python 설치 완료: {python_exe}", self.C_OK))
        else:
            self.root.after(0, lambda: self._log_line(f"Python 확인: {python_exe}", self.C_OK))

        # 2. pip install — 진행 바 indeterminate로 전환 후 실시간 스트리밍
        PACKAGES = [
            "opencv-python", "numpy", "keyboard",
            "pyautogui", "pyperclip", "mss", "pytesseract", "Pillow",
        ]
        self.root.after(0, lambda: self._pbar.config(mode="indeterminate", value=0))
        self.root.after(0, self._pbar.start)
        self.root.after(0, lambda: self._set("패키지 설치 중... (시간이 걸릴 수 있습니다)"))
        self.root.after(0, lambda: self._log_line(f"pip install {' '.join(PACKAGES)} ..."))
        proc = subprocess.Popen(
            [python_exe, "-m", "pip", "install"] + PACKAGES,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self.root.after(0, lambda l=line: self._log_line(l))
        proc.wait()
        self.root.after(0, self._pbar.stop)
        self.root.after(0, lambda: self._pbar.config(mode="determinate"))
        if proc.returncode != 0:
            raise RuntimeError("패키지 설치 실패. 로그를 확인하세요.")
        self.root.after(0, lambda: self._log_line("패키지 설치 완료", self.C_OK))

        # 3. Tesseract
        self.root.after(0, lambda: self._set("Tesseract 확인 중..."))
        if not _tesseract_ok():
            self.root.after(0, lambda: self._log_line("Tesseract 없음 → 최신 버전 URL 조회 중..."))
            tess_url = _get_tesseract_url()
            self.root.after(0, lambda u=tess_url: self._log_line(f"다운로드: {u.split('/')[-1]}"))
            dest = os.path.join(BASE_DIR, "_tess_setup.exe")
            self._download_with_bar(tess_url, dest, "Tesseract 다운로드")
            self.root.after(0, lambda: self._set("Tesseract 설치 중..."))
            self.root.after(0, lambda: self._log_line("Tesseract 설치 중..."))
            subprocess.run([dest, "/S"], check=True)
            os.remove(dest)
            self.root.after(0, lambda: self._log_line("Tesseract 설치 완료", self.C_OK))
        else:
            self.root.after(0, lambda: self._log_line("Tesseract: 이미 설치됨", self.C_OK))

        # 4. 한글 언어팩 (kor.traineddata)
        self.root.after(0, lambda: self._set("한글 언어팩 확인 중..."))
        if not _kor_ok():
            self.root.after(0, lambda: self._log_line("kor.traineddata 없음 → 다운로드 중..."))
            KOR_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/kor.traineddata"
            tess_dir = _tesseract_dir()
            dest_kor = os.path.join(BASE_DIR, "kor.traineddata")
            self._download_with_bar(KOR_URL, dest_kor, "한글 언어팩 다운로드")
            kor_target = os.path.join(tess_dir, "tessdata", "kor.traineddata")
            ctypes.windll.shell32.SHFileOperationW  # 관리자 권한 이미 보유
            import shutil
            shutil.move(dest_kor, kor_target)
            self.root.after(0, lambda: self._log_line("한글 언어팩 설치 완료", self.C_OK))
        else:
            self.root.after(0, lambda: self._log_line("한글 언어팩: 이미 설치됨", self.C_OK))

        self.root.after(0, lambda: self._pbar.config(value=100))

    def _download_with_bar(self, url: str, dest: str, label: str):
        self.root.after(0, lambda: self._pbar.config(value=0, mode="determinate"))

        def _cb(count, block, total):
            if total > 0:
                pct = min(100, count * block * 100 // total)
                self.root.after(0, lambda p=pct: self._pbar.config(value=p))
                self.root.after(0, lambda p=pct: self._set(f"{label}... {p}%"))

        urllib.request.urlretrieve(url, dest, _cb)

    def run(self):
        self.root.mainloop()


# ── 진입점 ────────────────────────────────────────────────
if __name__ == "__main__":
    # 관리자 권한 요청
    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable,
            f'"{os.path.abspath(__file__)}"', None, 1)
        sys.exit()
    App().run()
