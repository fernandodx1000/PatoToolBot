import os, sys
import traceback
import datetime

# ── Anchor all relative paths to the app folder ──────────────────────────────
# When relaunched elevated (UAC "runas") Windows starts the process with the
# working directory set to C:\Windows\System32, so logs/configs written with
# relative paths land there. Anchor to the exe/script folder first.
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    os.chdir(APP_DIR)
except Exception:
    pass

def _pick_log_dir():
    """App folder if writable, else %APPDATA%\\PatoToolBot (e.g. Program Files)."""
    try:
        _probe = os.path.join(APP_DIR, '.write_probe')
        with open(_probe, 'w') as _t:
            _t.write('x')
        os.remove(_probe)
        return APP_DIR
    except Exception:
        d = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'PatoToolBot')
        try:
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            return os.path.expanduser('~')

LOG_DIR = _pick_log_dir()
STARTUP_LOG = os.path.join(LOG_DIR, 'startup.log')

def _slog(msg, mode='a'):
    try:
        with open(STARTUP_LOG, mode) as f:
            f.write(f"[{datetime.datetime.now()}] {msg}\n")
    except Exception:
        pass

# Redirect stderr/stdout to files so we can see errors
class Tee:
    def __init__(self, name, mode):
        self.file = open(name, mode)
        self.name = name
    def write(self, data):
        self.file.write(data)
        self.file.flush()
    def flush(self):
        self.file.flush()

try:
    sys.stdout = Tee(os.path.join(LOG_DIR, 'stdout.log'), 'w')
    sys.stderr = Tee(os.path.join(LOG_DIR, 'stderr.log'), 'w')
except Exception:
    pass

# Startup logging
_slog(f"App starting... (logs in {LOG_DIR})", mode='w')
_slog(f"sys.frozen: {getattr(sys, 'frozen', False)}")
_slog(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}")
_slog(f"cwd: {os.getcwd()}")
_slog(f"argv: {sys.argv}")

# Fix TCL/TK BEFORE _tkinter.pyd loads — must be first thing in file
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _tcl = os.path.join(sys._MEIPASS, '_tcl_data')
    _tk  = os.path.join(sys._MEIPASS, '_tk_data')
    _slog(f"Tcl path: {_tcl}")
    _slog(f"Tk path: {_tk}")
    _slog(f"Tcl init.tcl exists: {os.path.isfile(os.path.join(_tcl, 'init.tcl'))}")
    if os.path.isfile(os.path.join(_tcl, 'init.tcl')):
        os.environ['TCL_LIBRARY'] = _tcl
        os.environ['TK_LIBRARY']  = _tk
        os.environ['PATH'] = sys._MEIPASS + os.pathsep + os.environ.get('PATH', '')
        _slog("TCL/TK environment set successfully")

def log_exception(exc_type, exc_value, exc_traceback):
    try:
        with open(os.path.join(LOG_DIR, "error_log.txt"), "a", encoding="utf-8") as f:
            f.write("\n\n===== CRASH =====\n")
            f.write("Time: " + str(datetime.datetime.now()) + "\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except:
        pass

import re
import tkinter as tk
_slog("Tkinter imported successfully")
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
from tkinter import Canvas, Toplevel, Label, Frame
import threading
import time
import io
import base64
_slog("Importing pyautogui/keyboard...")
import pyautogui
import json
import random
import keyboard
import ctypes
import win32con
import win32gui
import win32api
from difflib import SequenceMatcher
import hashlib
import subprocess
import platform
import uuid
import requests
import gc

# Import cv2 with error handling
_slog("Importing cv2...")
try:
    import cv2
except ImportError as e:
    print(f"Warning: cv2 (OpenCV) not available: {e}", file=sys.stderr)
    cv2 = None

# Try importing torch and easyocr
# NOTE: first launch on a new machine can take MINUTES here — the antivirus
# scans every bundled CUDA/torch DLL (several GB). The process sits in the
# task manager with no window until this finishes.
_slog("Importing torch (can take minutes on first launch — AV scanning)...")
try:
    import torch
except ImportError as e:
    print(f"Warning: torch not available: {e}", file=sys.stderr)
    torch = None
_slog("torch imported")

_slog("Importing easyocr...")
try:
    import easyocr
except ImportError as e:
    print(f"Warning: easyocr not available: {e}", file=sys.stderr)
    easyocr = None
_slog("easyocr imported — all heavy imports done")

# Catch all unhandled exceptions
sys.excepthook = log_exception

# PyInstaller hidden import hint — do not remove
try:
    if getattr(__builtins__, '__spec__', None) is None:
        import easyocr as _easyocr_hint  # noqa: F401
except Exception:
    pass
from PIL import Image, ImageTk, ImageEnhance, ImageOps, ImageFilter
import numpy as np
import cv2

# Set DPI Awareness
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# ── Fix torch/cv2 DLL loading when running as PyInstaller onedir ──────────────
# Must happen before ANY torch or cv2 import, otherwise c10.dll fails to load
if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
    _exe_dir = os.path.dirname(sys.executable)
    _internal = os.path.join(_exe_dir, '_internal')
    _torch_lib = os.path.join(_internal, 'torch', 'lib')
    _torch_lib2 = os.path.join(_base, 'torch', 'lib')
    for _p in (_torch_lib, _torch_lib2, _internal, _base, _exe_dir):
        if os.path.isdir(_p) and _p not in os.environ.get('PATH', ''):
            os.environ['PATH'] = _p + os.pathsep + os.environ.get('PATH', '')
    # Also tell Windows DLL loader explicitly
    try:
        import ctypes as _ct2
        for _p in (_torch_lib, _torch_lib2, _internal):
            if os.path.isdir(_p):
                _ct2.windll.kernel32.AddDllDirectory(_p)
    except Exception:
        pass


DEFAULT_REGION = (0, 0, 1920, 1080)
BASE_RES = (1920, 1080)   # resolution configs are built at
_SCALE_X = 1.0            # set at runtime
_SCALE_Y = 1.0

def _detect_screen_res():
    """Return (w, h) of the primary monitor."""
    try:
        import ctypes as _ct
        user32 = _ct.windll.user32
        user32.SetProcessDPIAware()
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        import tkinter as _tk
        r = _tk.Tk(); r.withdraw()
        w, h = r.winfo_screenwidth(), r.winfo_screenheight()
        r.destroy()
        return w, h

def _init_scaling(base_w=1920, base_h=1080):
    global _SCALE_X, _SCALE_Y, BASE_RES
    BASE_RES = (base_w, base_h)
    sw, sh = _detect_screen_res()
    _SCALE_X = sw / base_w
    _SCALE_Y = sh / base_h

def _sx(v): return int(round(v * _SCALE_X))
def _sy(v): return int(round(v * _SCALE_Y))
def _sr(region):
    """Scale a region tuple/list (x, y, w, h)."""
    if not region or len(region) < 4: return region
    return (_sx(region[0]), _sy(region[1]), _sx(region[2]), _sy(region[3]))
_user32 = ctypes.windll.user32
API_BASE_URL = "http://132.145.60.51:5000"
JWT_TOKEN = None

CURRENT_VERSION = "2.21"
APP_NAME = "PatoToolBot.exe"
UPDATE_TEMP_NAME = "update.zip"

# ── Game definitions ──────────────────────────────────────────────────
GAME_CONFIGS = {
    "arena_breakout": {
        "name": "Arena Breakout",
        "emoji": "🎯",
        "exe_names": ["UAGame.exe", "ArenaBreakout.exe", "Arena Breakout.exe"],
        "window_title": "Arena Breakout",
        "color": "#ffd700",
    },
    "arc_raiders": {
        "name": "Arc Raiders",
        "emoji": "⚡",
        "exe_names": ["PioneerGame.exe","PioneerGame-e.exe", "ArcRaiders.exe", "Arc Raiders.exe", "ArcRaiders-Win64-Shipping.exe"],
        # The shipping exe is now randomly named (e.g. "PioneerGame-Win64-Shipping_8f3a.exe"),
        # so match any process whose name contains one of these fragments.
        "exe_contains": ["pioneer"],
        "window_title": "Arc Raiders",
        "color": "#00bcd4",
    },
}


def _exe_matches_game(proc_name: str, cfg: dict) -> bool:
    """True if a process exe name matches this game — by exact name or substring fragment.

    Some games randomize their shipping exe name, so cfg may declare
    'exe_contains' fragments that are matched anywhere within the process name.
    """
    if not proc_name or not cfg:
        return False
    n = proc_name.lower()
    if n in [e.lower() for e in cfg.get("exe_names", [])]:
        return True
    return any(frag.lower() in n for frag in cfg.get("exe_contains", []))

# Initialize EasyOCR reader once
import uuid as _uuid

def _new_action_id():
    """Generate a short unique ID for an action."""
    return _uuid.uuid4().hex[:10]

def _ensure_ids(actions):
    """Recursively ensure every action dict has a unique '_id'.
    Safe to call on old configs — adds IDs where missing, never changes existing ones."""
    for act in actions:
        if not isinstance(act, dict):
            continue
        if "_id" not in act or not act["_id"]:
            act["_id"] = _new_action_id()
        p = act.get("params", {})
        for key in ("body", "true_branch", "false_branch", "cases", "default"):
            if key in p and isinstance(p[key], list):
                _ensure_ids(p[key])
        if "cases" in p and isinstance(p["cases"], list):
            for case in p["cases"]:
                if isinstance(case, dict) and "body" in case:
                    _ensure_ids(case["body"])

def _reassign_ids(actions):
    """Recursively force-generate brand new unique '_id' for every action.
    Use this when loading configs from server or file to prevent duplicate IDs."""
    seen = set()
    def _walk(acts):
        for act in acts:
            if not isinstance(act, dict):
                continue
            new_id = _new_action_id()
            # Guarantee uniqueness even within this batch
            while new_id in seen:
                new_id = _new_action_id()
            seen.add(new_id)
            act["_id"] = new_id
            p = act.get("params", {})
            for key in ("body", "true_branch", "false_branch", "default"):
                if key in p and isinstance(p[key], list):
                    _walk(p[key])
            if "cases" in p and isinstance(p["cases"], list):
                for case in p["cases"]:
                    if isinstance(case, dict) and "body" in case:
                        _walk(case["body"])
    _walk(actions)

def _ocr_clear_cache():
    """Release PyTorch GPU/CPU tensors + trim process RAM after each OCR call."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass
    gc.collect(0)   # gen-0 only — fast, catches short-lived numpy/cv2 arrays

def _trim_ram():
    """Trim Python virtual RAM on Windows — forces OS to reclaim pages."""
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
    except Exception:
        pass
    gc.collect()   # full collect

# ── Execution flow signals ────────────────────────────────────────────
class _BreakLoop(Exception): pass
class _ContinueLoop(Exception): pass
class _ReturnEnd(Exception): pass
class _StopSequence(Exception): pass  # stops bot completely

# Lazy-loaded — only initialised on first OCR call to avoid 2min startup delay
reader = None

# Global GPU preference flag — set by the Settings checkbox before reinit
_ocr_use_gpu = True   # default True — uses GPU when CUDA is available, falls back to CPU

def _cuda_available() -> bool:
    """Return True only when a real CUDA device is present and functional."""
    try:
        import torch as _torch
        return _torch.cuda.is_available() and _torch.cuda.device_count() > 0
    except Exception:
        return False

def _get_ocr_gpu_status() -> dict:
    """Return a dict with GPU availability info for display in Settings."""
    info = {
        "cuda_available": False,
        "device_name": "N/A",
        "vram_total_mb": 0,
        "vram_free_mb": 0,
        "ocr_using_gpu": False,
        "reader_initialized": reader is not None,
    }
    try:
        import torch as _torch
        info["cuda_available"] = _torch.cuda.is_available()
        if info["cuda_available"]:
            idx = _torch.cuda.current_device()
            info["device_name"] = _torch.cuda.get_device_name(idx)
            props = _torch.cuda.get_device_properties(idx)
            info["vram_total_mb"] = props.total_memory // (1024 * 1024)
            mem_reserved = _torch.cuda.memory_reserved(idx)
            info["vram_free_mb"] = (props.total_memory - mem_reserved) // (1024 * 1024)
    except Exception as _e:
        info["cuda_error"] = str(_e)
    info["ocr_using_gpu"] = _ocr_use_gpu and info["cuda_available"]
    return info

def _get_reader(force_reinit=False):
    global reader, _ocr_use_gpu
    if reader is None or force_reinit:
        import io as _io, sys as _sys, easyocr as _easyocr, shutil as _sh
        _model_dir = os.path.join(_appdata_dir(), "models")
        os.makedirs(_model_dir, exist_ok=True)

        # If models are corrupt, delete and let EasyOCR redownload
        _craft = os.path.join(_model_dir, "model", "craft_mlt_25k.pth")
        _eng   = os.path.join(_model_dir, "model", "english_g2.pth")
        for _mf in [_craft, _eng]:
            if os.path.exists(_mf) and os.path.getsize(_mf) < 1024:
                print(f"[OCR] Corrupt model detected, deleting: {_mf}")
                try: os.remove(_mf)
                except: pass

        # Determine whether to use GPU
        _want_gpu = _ocr_use_gpu and _cuda_available()
        if _ocr_use_gpu and not _cuda_available():
            print("[OCR] GPU requested but CUDA not available — falling back to CPU")
        print(f"[OCR] Initializing EasyOCR — gpu={_want_gpu}")

        _stderr_bak = _sys.stderr
        _sys.stderr = _io.StringIO()
        try:
            reader = _easyocr.Reader(['en'], gpu=_want_gpu, verbose=False,
                                     model_storage_directory=_model_dir)
        except Exception as _e:
            _sys.stderr = _stderr_bak
            _err = str(_e)
            # If GPU init fails, retry with CPU
            if _want_gpu and any(x in _err for x in ("DLL", "WinError 1114", "c10.dll", "CUDA", "cuda")):
                print(f"[OCR] GPU init failed ({_err[:80]}), retrying with CPU...")
                _stderr_bak2 = _sys.stderr
                _sys.stderr = _io.StringIO()
                try:
                    reader = _easyocr.Reader(['en'], gpu=False, verbose=False,
                                             model_storage_directory=_model_dir)
                finally:
                    _sys.stderr = _stderr_bak2
            # If model load fails due to corruption, wipe models and retry once
            elif any(x in _err for x in ("zip file", "differ", "decompressing", "corrupt")):
                print(f"[OCR] Model corrupt — clearing and redownloading...")
                _model_path = os.path.join(_model_dir, "model")
                if os.path.exists(_model_path):
                    _sh.rmtree(_model_path, ignore_errors=True)
                _stderr_bak2 = _sys.stderr
                _sys.stderr = _io.StringIO()
                try:
                    reader = _easyocr.Reader(['en'], gpu=_want_gpu, verbose=False,
                                             model_storage_directory=_model_dir)
                finally:
                    _sys.stderr = _stderr_bak2
            else:
                raise
        finally:
            try: _sys.stderr = _stderr_bak
            except: pass
    return reader

def _safe_readtext(img, **kwargs):
    """Call readtext and reinitialize reader on DLL/torch errors."""
    for attempt in range(2):
        try:
            return _get_reader(force_reinit=(attempt > 0)).readtext(img, **kwargs)
        except Exception as e:
            err = str(e)
            if attempt == 0 and any(x in err for x in ("DLL", "WinError 1114", "c10.dll", "torch")):
                global reader
                reader = None  # force reinit on next call
                continue
            raise
    return []

def get_hwid() -> str:
    """
    Stable HWID using only CPU ID + Motherboard serial.
    - CPU ID: never changes (not affected by drivers, VPNs, renames)
    - Motherboard serial: tied to physical hardware
    Falls back gracefully so the hash stays consistent even if one fails.
    """
    parts = []

    # 1. CPU ID — most stable identifier, survives reboots/updates/renames
    try:
        cpu = subprocess.check_output(
            'powershell -Command "(Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1).ProcessorId"',
            shell=True, stderr=subprocess.DEVNULL
        ).decode(errors='ignore').strip()
        parts.append(cpu if cpu and cpu not in ("", "None", "To Be Filled By O.E.M.") else "CPU-ERR")
    except Exception:
        parts.append("CPU-ERR")

    # 2. Motherboard serial — tied to physical board
    try:
        mb = subprocess.check_output(
            'powershell -Command "(Get-CimInstance -ClassName Win32_BaseBoard | Select-Object -First 1).SerialNumber"',
            shell=True, stderr=subprocess.DEVNULL
        ).decode(errors='ignore').strip()
        parts.append(mb if mb and mb not in ("", "None", "To Be Filled By O.E.M.", "Default string") else "MB-ERR")
    except Exception:
        parts.append("MB-ERR")

    # 3. BIOS serial as tiebreaker (stable, not user-changeable)
    try:
        bios = subprocess.check_output(
            'powershell -Command "(Get-CimInstance -ClassName Win32_BIOS | Select-Object -First 1).SerialNumber"',
            shell=True, stderr=subprocess.DEVNULL
        ).decode(errors='ignore').strip()
        parts.append(bios if bios and bios not in ("", "None", "To Be Filled By O.E.M.", "Default string") else "BIOS-ERR")
    except Exception:
        parts.append("BIOS-ERR")

    raw = "_".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest().upper()[:32]


def get_hwid_legacy() -> str:
    """Old HWID method — used as fallback to migrate existing licenses."""
    parts = []
    try:
        disk = subprocess.check_output(
            'powershell -Command "Get-PhysicalDisk | Select-Object -First 1 -ExpandProperty SerialNumber"',
            shell=True, stderr=subprocess.DEVNULL
        ).decode(errors='ignore').strip()
        parts.append(disk or "DISK-ERR")
    except Exception:
        parts.append("DISK-ERR")
    try:
        mb = subprocess.check_output(
            'powershell -Command "Get-CimInstance -ClassName Win32_BaseBoard | Select-Object -ExpandProperty SerialNumber"',
            shell=True, stderr=subprocess.DEVNULL
        ).decode(errors='ignore').strip()
        parts.append(mb or "MB-ERR")
    except Exception:
        parts.append("MB-ERR")
    try:
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> i) & 0xff) for i in range(0,48,8)][::-1])
        parts.append(mac)
    except Exception:
        parts.append("MAC-ERR")
    try:
        parts.append(platform.node() + "_" + os.getlogin())
    except Exception:
        parts.append("NODE-ERR")
    raw = "_".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest().upper()[:32]


def api_request(method: str, endpoint: str, json_data=None, params=None, require_auth=True):
    global JWT_TOKEN
    url = f"{API_BASE_URL}{endpoint}"
    headers = {}
    if require_auth and JWT_TOKEN:
        headers["Authorization"] = f"Bearer {JWT_TOKEN}"
    try:
        if method.upper() == "GET":
            with requests.get(url, headers=headers, params=params or {}, timeout=10) as r:
                try:
                    data = r.json()
                except Exception:
                    data = {"raw_response": r.text[:300], "error": "Not JSON"}
                if r.status_code == 401:
                    code = data.get("code", "") if isinstance(data, dict) else ""
                    if code in ("token_expired", "token_invalid", "token_missing", "token_revoked"):
                        JWT_TOKEN = None  # clear stale token
                        data = {"error": "Session expired — please log in again", "code": code}
                return data, r.status_code
        elif method.upper() == "POST":
            with requests.post(url, headers=headers, json=json_data, timeout=10) as r:
                try:
                    data = r.json()
                except Exception:
                    data = {"raw_response": r.text[:300], "error": "Not JSON"}
                if r.status_code == 401:
                    code = data.get("code", "") if isinstance(data, dict) else ""
                    if code in ("token_expired", "token_invalid", "token_missing", "token_revoked"):
                        JWT_TOKEN = None  # clear stale token
                        data = {"error": "Session expired — please log in again", "code": code}
                return data, r.status_code
        else:
            return {"error": f"Unsupported method {method}"}, 405
    except requests.RequestException as e:
        return {"error": f"Network error: {str(e)}"}, 0

def _center_win(win, w, h):
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")


def check_for_update(force=False):
    try:
        info, code = api_request("GET", "/update/info", require_auth=False)
        if code != 200 or not isinstance(info, dict):
            print("Update check failed - continuing")
            return

        latest_version = info.get("latest_version", "0.0")
        download_url   = info.get("download_url")

        def _ver(v):
            try: return tuple(int(x) for x in str(v).split("."))
            except: return (0,)
        if not force and _ver(latest_version) <= _ver(CURRENT_VERSION):
            print(f"Up to date (v{CURRENT_VERSION})")
            return

        # ── Confirm dialog (skipped when force=True) ─────────────────────
        if not force:
            confirmed = [False]
            confirm_win = tk.Tk()
            confirm_win.title("Update Available")
            confirm_win.configure(bg="#0a0e27")
            confirm_win.resizable(False, False)
            confirm_win.attributes("-topmost", True)
            _center_win(confirm_win, 460, 290)

            tk.Frame(confirm_win, bg="#1a1f3a", height=70).pack(fill="x")
            hdr = tk.Frame(confirm_win, bg="#1a1f3a")
            hdr.place(x=0, y=0, width=460, height=70)
            tk.Label(hdr, text="\U0001f986  Update Available",
                     font=("Segoe UI", 14, "bold"), bg="#1a1f3a", fg="#ffd700").place(relx=0.5, rely=0.5, anchor="center")

            body = tk.Frame(confirm_win, bg="#0a0e27")
            body.pack(fill="both", expand=True, padx=30, pady=(80, 10))

            tk.Label(confirm_win, text=f"New version  {latest_version}  is available",
                     font=("Segoe UI", 12, "bold"), bg="#0a0e27", fg="#ffffff").place(x=30, y=85)
            tk.Label(confirm_win, text=f"You are on version  {CURRENT_VERSION}",
                     font=("Segoe UI", 10), bg="#0a0e27", fg="#8b9dc3").place(x=30, y=115)
            tk.Label(confirm_win, text="Download and install now?",
                     font=("Segoe UI", 10), bg="#0a0e27", fg="#a0a0a0").place(x=30, y=150)

            def do_yes():
                confirmed[0] = True
                confirm_win.destroy()

            tk.Button(confirm_win, text="  Update Now  ", font=("Segoe UI", 10, "bold"),
                      bg="#ffd700", fg="#0a0e27", relief="flat", cursor="hand2",
                      command=do_yes, padx=10, pady=8).place(x=30, y=220)
            tk.Button(confirm_win, text="  Skip  ", font=("Segoe UI", 10),
                      bg="#2a2f4a", fg="#8b9dc3", relief="flat", cursor="hand2",
                      command=confirm_win.destroy, padx=10, pady=8).place(x=155, y=220)

            confirm_win.mainloop()

            if not confirmed[0]:
                print("User skipped update")
                return

        # ── Progress window ───────────────────────────────────────────────
        BAR_W = 420
        prog_win = tk.Tk()
        prog_win.title("Updating PatoToolBot")
        prog_win.configure(bg="#0a0e27")
        prog_win.resizable(False, False)
        prog_win.attributes("-topmost", True)
        _center_win(prog_win, 480, 230)

        # Header
        hdr2 = tk.Frame(prog_win, bg="#1a1f3a", height=60)
        hdr2.pack(fill="x")
        hdr2.pack_propagate(False)
        tk.Label(hdr2, text="\U0001f986  PatoToolBot Updater",
                 font=("Segoe UI", 13, "bold"), bg="#1a1f3a", fg="#ffd700").pack(expand=True)

        body2 = tk.Frame(prog_win, bg="#0a0e27")
        body2.pack(fill="both", expand=True, padx=26, pady=10)

        status_var = tk.StringVar(value="Connecting to server...")
        tk.Label(body2, textvariable=status_var, font=("Consolas", 9),
                 bg="#0a0e27", fg="#8b9dc3").pack(anchor="w", pady=(0, 8))

        # Fixed-width bar container so we always know BAR_W pixels wide
        bar_bg = tk.Frame(body2, bg="#1a1f3a", width=BAR_W, height=20)
        bar_bg.pack(anchor="w")
        bar_bg.pack_propagate(False)
        bar_fill = tk.Frame(bar_bg, bg="#ffd700", height=20, width=0)
        bar_fill.place(x=0, y=0, height=20, width=0)

        info_row = tk.Frame(body2, bg="#0a0e27")
        info_row.pack(fill="x", pady=(6, 0))
        pct_var = tk.StringVar(value="0%")
        tk.Label(info_row, textvariable=pct_var, font=("Consolas", 11, "bold"),
                 bg="#0a0e27", fg="#ffffff").pack(side="left")
        size_var = tk.StringVar(value="")
        tk.Label(info_row, textvariable=size_var, font=("Consolas", 8),
                 bg="#0a0e27", fg="#4a5568").pack(side="right")

        prog_win.update()

        # ── Shared state between download thread and UI ───────────────────
        state = {
            "pct": 0.0, "dl_mb": 0.0, "total_mb": None,
            "status": "Connecting to server...",
            "done": False, "error": None
        }

        def update_ui():
            if not prog_win.winfo_exists():
                return
            # Bar width is always based on fixed BAR_W — never winfo_width()
            w = int(BAR_W * min(state["pct"], 100) / 100)
            bar_fill.place(x=0, y=0, height=20, width=w)
            pct_var.set(f"{state['pct']:.0f}%")
            status_var.set(state["status"])
            if state["total_mb"]:
                size_var.set(f"{state['dl_mb']:.2f} MB  /  {state['total_mb']:.2f} MB")
            elif state["dl_mb"]:
                size_var.set(f"{state['dl_mb']:.2f} MB downloaded")
            if not state["done"]:
                prog_win.after(40, update_ui)

        def on_error_check():
            if not prog_win.winfo_exists():
                return
            if state.get("error"):
                prog_win.destroy()
                tk.messagebox.showerror("Download Failed", state["error"])
                return
            if not state["done"]:
                prog_win.after(200, on_error_check)

        def download_thread():
            # ── Paths ────────────────────────────────────────────────────
            appdata_dir = _appdata_dir()
            vbs_path    = os.path.join(appdata_dir, "pato_update.vbs")
            zip_path    = os.path.join(appdata_dir, "update.zip")

            cur_pid = os.getpid()

            # Current exe and its parent folder (the onedir dist folder)
            if getattr(sys, "frozen", False):
                cur_exe    = os.path.abspath(sys.executable)
            else:
                cur_exe    = os.path.abspath(__file__)
            cur_dir    = os.path.dirname(cur_exe)   # e.g. dist\PatoToolBot
            cur_pid    = os.getpid()

            # ── 1. Download ZIP ───────────────────────────────────────────
            try:
                state["status"] = "Connecting to server..."
                with requests.get(download_url, timeout=300, stream=True) as r:
                    if r.status_code != 200:
                        state["error"] = f"Server returned HTTP {r.status_code}"
                        state["done"]  = True
                        return
                    total = int(r.headers.get("content-length", 0))
                    state["total_mb"] = total / 1024 / 1024 if total else None
                    downloaded = 0
                    state["status"] = "Downloading update..."
                    with open(zip_path, "wb") as fz:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                fz.write(chunk)
                                downloaded += len(chunk)
                                state["dl_mb"] = downloaded / 1024 / 1024
                                if total:
                                    state["pct"] = (downloaded / total) * 85
                                else:
                                    state["pct"] = min(80, state["dl_mb"] * 1.5)
            except Exception as e:
                state["error"] = str(e)
                state["done"]  = True
                return

            state["pct"]    = 90
            state["status"] = "Preparing install..."
            state["done"]   = True
            time.sleep(0.3)

            # ── 2. VBS: kill → extract zip over cur_dir → relaunch ────────
            cur_exe_vbs = cur_exe.replace("\\", "\\\\")
            cur_dir_vbs = cur_dir.replace("\\", "\\\\")
            zip_vbs     = zip_path.replace("\\", "\\\\")

            vbs = (
                "' PatoToolBot OneDir Updater\r\n"
                "Dim fso, shell\r\n"
                "Set fso   = CreateObject(\"Scripting.FileSystemObject\")\r\n"
                "Set shell = CreateObject(\"WScript.Shell\")\r\n"
                f"Dim targetPid : targetPid = {cur_pid}\r\n"
                f"Dim curExe    : curExe    = \"{cur_exe_vbs}\"\r\n"
                f"Dim curDir    : curDir    = \"{cur_dir_vbs}\"\r\n"
                f"Dim zipFile   : zipFile   = \"{zip_vbs}\"\r\n"
                "\r\n"
                "' 1. Kill running process\r\n"
                "shell.Run \"taskkill /F /PID \" & targetPid, 0, True\r\n"
                "WScript.Sleep 1000\r\n"
                "\r\n"
                "'  2. Wait 2s\r\n"
                "WScript.Sleep 2000\r\n"
                "\r\n"
                "' 3. Extract ZIP over install dir using PowerShell\r\n"
                "Dim psCmd\r\n"
                "psCmd = \"powershell -NoProfile -Command \"\"Expand-Archive -Path '\" & zipFile & \"' -DestinationPath '\" & curDir & \"' -Force\"\"\"\r\n"
                "shell.Run psCmd, 0, True\r\n"
                "\r\n"
                "' 4. Delete zip\r\n"
                "If fso.FileExists(zipFile) Then fso.DeleteFile zipFile, True\r\n"
                "\r\n"
                "' 5. Relaunch\r\n"
                "WScript.Sleep 500\r\n"
                "If fso.FileExists(curExe) Then\r\n"
                "    shell.Run \"python \"\"\" & curExe & \"\"\" --updated\", 1, False\r\n"
                "Else\r\n"
                "    shell.Run \"explorer http://132.145.60.51:5000/dl/\", 1, False\r\n"
                "    MsgBox \"Update failed: exe not found after extract.\", 48, \"PatoToolBot Update\"\r\n"
                "End If\r\n"
                "\r\n"
                "' 6. Self-delete\r\n"
                "WScript.Sleep 1000\r\n"
                "fso.DeleteFile WScript.ScriptFullName, True\r\n"
            )
            with open(vbs_path, "w", encoding="utf-8") as _f:
                _f.write(vbs)

            def finish():
                if prog_win.winfo_exists():
                    prog_win.destroy()
                ctypes.windll.shell32.ShellExecuteW(
                    None, "open", "wscript.exe",
                    f'"{vbs_path}"',
                    None, 0
                )
                time.sleep(0.5)
                sys.exit(0)

            prog_win.after(0, finish)





        import threading as _t
        prog_win.after(40, update_ui)
        prog_win.after(200, on_error_check)
        _t.Thread(target=download_thread, daemon=True).start()
        prog_win.mainloop()

    except Exception as e:
        print(f"Update error: {e}")


def check_license_status(hwid: str):
    global JWT_TOKEN
    if not JWT_TOKEN:
        return {"status": "error", "message": "Not authenticated"}, 401
    return api_request("GET", "/license/status", params={"hwid": hwid})


class SplashScreen:
    W, H = 340, 360
    _TRANSPARENT = "#010101"

    def __init__(self, gif_path=None, master=None):
        if master:
            self.root = tk.Toplevel(master)
        else:
            self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", self._TRANSPARENT)
        self.root.configure(bg=self._TRANSPARENT)
        try:
            ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            if os.path.exists(ico):
                self.root.iconbitmap(ico)
        except Exception:
            pass
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{self.W}x{self.H}+{(sw-self.W)//2}+{(sh-self.H)//2}")

        # Duck emoji
        tk.Label(self.root, text="🦆",
                 font=("Segoe UI Emoji", 120),
                 bg=self._TRANSPARENT, fg="#ffd700").place(relx=0.5, rely=0.42, anchor="center")

        # Status label (hidden by default)
        self._status_var = tk.StringVar(value="")
        self._status_lbl = tk.Label(self.root, textvariable=self._status_var,
                                     font=("Segoe UI", 10, "bold"),
                                     bg=self._TRANSPARENT, fg="#ffd700")
        self._status_lbl.place(relx=0.5, rely=0.78, anchor="center")

        # Progress bar canvas
        self._bar_canvas = tk.Canvas(self.root, width=260, height=8,
                                      bg="#1a1f3a", highlightthickness=0, bd=0)
        self._bar_canvas.place(relx=0.5, rely=0.88, anchor="center")
        self._bar_rect = self._bar_canvas.create_rectangle(0, 0, 0, 8, fill="#ffd700", outline="")
        self._bar_canvas.place_forget()  # hidden until set_status called

        self.root.update()

    def set_status(self, text: str, pct: float = None):
        """Update status text and optional progress bar (0-100)."""
        try:
            self._status_var.set(text)
            if pct is not None:
                self._bar_canvas.place(relx=0.5, rely=0.88, anchor="center")
                w = int(260 * max(0, min(100, pct)) / 100)
                self._bar_canvas.coords(self._bar_rect, 0, 0, w, 8)
            self.root.update()
        except Exception:
            pass

    def show_and_wait(self, duration_ms=3000):
        end = time.time() + duration_ms / 1000
        while time.time() < end:
            try:
                self.root.update()
                time.sleep(0.016)
            except Exception:
                return
        self.close()

    def pump(self):
        """Keep splash alive — call from main thread while waiting."""
        try:
            self.root.update()
        except Exception:
            pass

    def close(self):
        try:
            if self.root:
                self.root.destroy()
                self.root = None
                gc.collect()
        except Exception:
            pass


def _appdata_dir() -> str:
    """Return %APPDATA%/PatoToolBot, creating it if needed."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "PatoToolBot")
    # One-time migration from the old folder name (keeps OCR models, login, hwid cache)
    old = os.path.join(base, "PatoArenaBot")
    if not os.path.isdir(folder) and os.path.isdir(old):
        try:
            os.rename(old, folder)
        except Exception:
            pass
    os.makedirs(folder, exist_ok=True)
    return folder

_CRED_FILE  = os.path.join(_appdata_dir(), "last_user.txt")
_RES_FILE   = os.path.join(_appdata_dir(), "base_resolution.txt")

def _save_base_res(res_str: str):
    try:
        open(_RES_FILE, "w", encoding="utf-8").write(res_str.strip())
    except Exception:
        pass

def _load_base_res() -> str:
    try:
        return open(_RES_FILE, "r", encoding="utf-8").read().strip()
    except Exception:
        return "1920x1080"

def _save_last_user(username: str):
    try:
        with open(_CRED_FILE, "w", encoding="utf-8") as f:
            f.write(username.strip())
    except Exception:
        pass

def _load_last_user() -> str:
    try:
        with open(_CRED_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

class AuthWindow:
    def __init__(self, _master=None):
        if _master:
            self.root = tk.Toplevel(_master)
        else:
            self.root = tk.Tk()
        self.root.title("Pato's Tool  Bot - Login")
        self.root.geometry("520x800")
        _set_icon(self.root)
        self.root.configure(bg="#0a0e27")
        self.root.minsize(480, 700)
        self.root.resizable(True, True)
        self.hwid = get_hwid()   # must run on main thread — PowerShell behaves differently in worker threads
        self.authenticated = False
        self.username = ""
        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
    
    def _autosize_dialog(self, dialog, min_w=300, min_h=200, pad=40):
        """Resize dialog to fit its content then center it."""
        dialog.update_idletasks()
        w = max(dialog.winfo_reqwidth() + pad, min_w)
        h = max(dialog.winfo_reqheight() + pad, min_h)
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        dialog.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _center_dialog(self, dialog):
        dialog.update_idletasks()
        w = dialog.winfo_width()
        h = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (w // 2)
        y = (dialog.winfo_screenheight() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        main_container = tk.Frame(self.root, bg="#0a0e27")
        main_container.pack(fill="both", expand=True)
        main_container.grid_rowconfigure(1, weight=1)
        main_container.grid_columnconfigure(0, weight=1)
        
        header = tk.Frame(main_container, bg="#1a1f3a", height=160)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        tk.Label(header, text="🦆", font=("Arial", 60), bg="#1a1f3a", fg="#ffd700").pack(pady=(20,0))
        tk.Label(header, text="PATO'S Tool Bot", font=("Consolas", 22, "bold"), bg="#1a1f3a", fg="#ffd700").pack()
        tk.Label(header, text="Market Bot v2.15 - 2026", font=("Consolas", 12), bg="#1a1f3a", fg="#8b9dc3").pack(pady=4)

        form = tk.Frame(main_container, bg="#0a0e27")
        form.grid(row=1, column=0, sticky="nsew", padx=60, pady=30)
        form.grid_columnconfigure(0, weight=1)

        tk.Label(form, text="Login", font=("Consolas", 16, "bold"), bg="#0a0e27", fg="#ffffff").pack(pady=(0,20))
        tk.Label(form, text="Username", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        self.username_entry = tk.Entry(form, font=("Consolas", 13), bg="#1a1f3a", fg="#fff",
                                       insertbackground="#ffd700", relief="flat", bd=0)
        self.username_entry.pack(fill="x", ipady=10, pady=(4,20))
        _last = _load_last_user()
        self.username_entry.insert(0, _last if _last else "pato")

        tk.Label(form, text="Password", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        self.password_entry = tk.Entry(form, font=("Consolas", 13), show="•", bg="#1a1f3a", fg="#fff",
                                       insertbackground="#ffd700", relief="flat", bd=0)
        self.password_entry.pack(fill="x", ipady=10, pady=(4,20))
        if _last:
            self.root.after(50, self.password_entry.focus)

        self._login_btn = tk.Button(form, text="LOGIN", font=("Consolas", 13, "bold"), bg="#ffd700", fg="#0a0e27",
                  relief="flat", cursor="hand2", command=self._attempt_login)
        self._login_btn.pack(fill="x", ipady=12, pady=(0,15))

        tk.Button(form, text="REGISTER NEW ACCOUNT", font=("Consolas", 11, "bold"), bg="#2ecc71", fg="white",
                  relief="flat", cursor="hand2", command=self._open_register).pack(fill="x", ipady=10)

        tk.Button(form, text="Forgot Password?", font=("Consolas", 10), bg="#0a0e27", fg="#8b9dc3",
                  relief="flat", cursor="hand2", command=self._open_forgot_password).pack(pady=(10,0))

        hwid_f = tk.Frame(form, bg="#0a0e27")
        hwid_f.pack(fill="x", pady=(40,0))
        tk.Label(hwid_f, text="Your HWID:", font=("Consolas", 10, "bold"), bg="#0a0e27", fg="#e74c3c").pack(anchor="w")
        hwid_txt = tk.Text(hwid_f, height=4, font=("Consolas", 10), bg="#1a1f3a", fg="#95a5a6",
                           relief="flat", bd=0, wrap="word")
        hwid_txt.insert("1.0", self.hwid if self.hwid else "Loading...")
        hwid_txt.config(state="disabled")
        hwid_txt.pack(fill="x", pady=6)
        tk.Label(hwid_f, text="(send to admin if needed)", font=("Consolas", 9, "italic"),
                 bg="#0a0e27", fg="#4a5568").pack(anchor="w")

        def _fill_hwid():
            import threading as _t
            def _fetch():
                hwid = get_hwid()
                self.hwid = hwid
                def _update():
                    try:
                        hwid_txt.config(state="normal")
                        hwid_txt.delete("1.0", tk.END)
                        hwid_txt.insert("1.0", hwid)
                        hwid_txt.config(state="disabled")
                    except Exception:
                        pass
                self.root.after(0, _update)
            _t.Thread(target=_fetch, daemon=True).start()
        self.root.after(100, _fill_hwid)

        footer = tk.Frame(main_container, bg="#0a0e27")
        footer.grid(row=2, column=0, sticky="ew")
        tk.Label(footer, text=f"API: {API_BASE_URL}", font=("Consolas", 9), bg="#0a0e27", fg="#4a5568").pack(pady=20)

        self.password_entry.bind("<Return>", lambda e: self._attempt_login())
        self.username_entry.bind("<Return>", lambda e: self.password_entry.focus())
        self.username_entry.focus()

    def _open_register(self):
        win = Toplevel(self.root)
        win.title("Register")
        win.configure(bg="#0a0e27")
        win.transient(self.root)
        win.grab_set()
        self._center_dialog(win)

        main_frame = tk.Frame(win, bg="#0a0e27")
        main_frame.pack(fill="both", expand=True, padx=50, pady=20)
        main_frame.grid_columnconfigure(0, weight=1)

        tk.Label(main_frame, text="Create Account", font=("Consolas", 16, "bold"), bg="#0a0e27", fg="#ffd700").pack(pady=(0,20))

        tk.Label(main_frame, text="Username", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        u_ent = tk.Entry(main_frame, font=("Consolas", 13), bg="#1a1f3a", fg="#fff", insertbackground="#ffd700", relief="flat")
        u_ent.pack(fill="x", ipady=8, pady=(4,16))

        tk.Label(main_frame, text="Email", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        e_ent = tk.Entry(main_frame, font=("Consolas", 13), bg="#1a1f3a", fg="#fff", insertbackground="#ffd700", relief="flat")
        e_ent.pack(fill="x", ipady=8, pady=(4,16))
        tk.Label(main_frame, text="Used for password recovery", font=("Consolas", 9, "italic"), bg="#0a0e27", fg="#4a5568").pack(anchor="w", pady=(0,8))

        tk.Label(main_frame, text="Password", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        p_ent = tk.Entry(main_frame, font=("Consolas", 13), show="•", bg="#1a1f3a", fg="#fff", insertbackground="#ffd700", relief="flat")
        p_ent.pack(fill="x", ipady=8, pady=(4,16))

        tk.Label(main_frame, text="Confirm Password", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        c_ent = tk.Entry(main_frame, font=("Consolas", 13), show="•", bg="#1a1f3a", fg="#fff", insertbackground="#ffd700", relief="flat")
        c_ent.pack(fill="x", ipady=8, pady=(4,30))

        def register():
            u  = u_ent.get().strip()
            em = e_ent.get().strip()
            p1 = p_ent.get()
            p2 = c_ent.get()
            if len(u) < 3:  return messagebox.showerror("Error", "Username ≥ 3 chars", parent=win)
            if "@" not in em or "." not in em:
                return messagebox.showerror("Error", "Enter a valid email", parent=win)
            if p1 != p2:    return messagebox.showerror("Error", "Passwords do not match", parent=win)
            if len(p1) < 4: return messagebox.showerror("Error", "Password ≥ 4 chars", parent=win)

            resp, code = api_request("POST", "/register", json_data={"username": u, "password": p1, "email": em}, require_auth=False)
            if code == 201:
                messagebox.showinfo("Success", f"Account '{u}' created.\nLogin now.", parent=win)
                win.destroy()
                self.username_entry.delete(0, tk.END)
                self.username_entry.insert(0, u)
                self.password_entry.focus()
            else:
                msg = resp.get("error", f"HTTP {code}") if isinstance(resp, dict) else "Server error"
                messagebox.showerror("Failed", msg, parent=win)

        tk.Button(main_frame, text="REGISTER", font=("Consolas", 12, "bold"), bg="#2ecc71", fg="white",
                  relief="flat", command=register).pack(fill="x", ipady=12, pady=(0,8))
        tk.Button(main_frame, text="Cancel", font=("Consolas", 11), bg="#34495e", fg="white",
                  relief="flat", command=win.destroy).pack(fill="x", ipady=10)
        win.update_idletasks()
        self._autosize_dialog(win, min_w=400, min_h=400)

    def _open_forgot_password(self):
        win = Toplevel(self.root)
        win.title("Forgot Password")
        win.configure(bg="#0a0e27")
        win.transient(self.root)
        win.grab_set()

        f = tk.Frame(win, bg="#0a0e27")
        f.pack(fill="both", expand=True, padx=40, pady=30)

        tk.Label(f, text="Reset Password", font=("Consolas", 15, "bold"), bg="#0a0e27", fg="#ffd700").pack(pady=(0,6))
        tk.Label(f, text="Enter your email address.\nWe'll send you a reset link.", font=("Consolas", 10),
                 bg="#0a0e27", fg="#8b9dc3", justify="center").pack(pady=(0,20))

        tk.Label(f, text="Email", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        em_ent = tk.Entry(f, font=("Consolas", 13), bg="#1a1f3a", fg="#fff", insertbackground="#ffd700", relief="flat")
        em_ent.pack(fill="x", ipady=8, pady=(4,20))

        def send_reset():
            em = em_ent.get().strip()
            if "@" not in em:
                return messagebox.showerror("Error", "Enter a valid email", parent=win)
            resp, code = api_request("POST", "/password/forgot", json_data={"email": em}, require_auth=False)
            messagebox.showinfo("Sent", "If that email is registered you will receive a reset link.", parent=win)
            win.destroy()

        tk.Button(f, text="SEND RESET LINK", font=("Consolas", 11, "bold"), bg="#ffd700", fg="#0a0e27",
                  relief="flat", cursor="hand2", command=send_reset).pack(fill="x", ipady=10, pady=(0,8))
        tk.Button(f, text="Cancel", font=("Consolas", 10), bg="#34495e", fg="white",
                  relief="flat", command=win.destroy).pack(fill="x", ipady=8)
        em_ent.bind("<Return>", lambda e: send_reset())
        self._autosize_dialog(win, min_w=380, min_h=240)
        em_ent.focus()

    def _prompt_add_email(self, on_done=None):
        """Show after login for accounts without an email.
        Calls on_done() when the window is closed (saved or skipped)."""
        win = Toplevel(self.root)
        win.title("Add Email")
        win.configure(bg="#0a0e27")
        win.transient(self.root)
        win.grab_set()

        f = tk.Frame(win, bg="#0a0e27")
        f.pack(fill="both", expand=True, padx=40, pady=30)

        tk.Label(f, text="📧 Add Your Email", font=("Consolas", 14, "bold"), bg="#0a0e27", fg="#ffd700").pack(pady=(0,8))
        tk.Label(f, text="Your account doesn't have an email.\nAdd one now to enable password recovery.",
                 font=("Consolas", 10), bg="#0a0e27", fg="#8b9dc3", justify="center").pack(pady=(0,18))

        tk.Label(f, text="Email", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        em_ent = tk.Entry(f, font=("Consolas", 13), bg="#1a1f3a", fg="#fff", insertbackground="#ffd700", relief="flat")
        em_ent.pack(fill="x", ipady=8, pady=(4,18))

        def _close():
            try:
                win.grab_release()
                win.destroy()
            except Exception:
                pass
            if on_done:
                on_done()

        def save():
            em = em_ent.get().strip()
            if "@" not in em or "." not in em:
                return messagebox.showerror("Error", "Enter a valid email", parent=win)
            def _do_save():
                resp, code = api_request("POST", "/account/set_email", json_data={"email": em})
                win.after(0, lambda: _on_save_result(resp, code))
            def _on_save_result(resp, code):
                if code == 200:
                    messagebox.showinfo("Saved", "Email saved!", parent=win)
                    _close()
                else:
                    msg = resp.get("error", f"HTTP {code}") if isinstance(resp, dict) else "Server error"
                    messagebox.showerror("Failed", msg, parent=win)
            threading.Thread(target=_do_save, daemon=True).start()

        win.protocol("WM_DELETE_WINDOW", _close)
        tk.Button(f, text="SAVE EMAIL", font=("Consolas", 11, "bold"), bg="#ffd700", fg="#0a0e27",
                  relief="flat", cursor="hand2", command=save).pack(fill="x", ipady=10, pady=(0,8))
        tk.Button(f, text="Skip (not recommended)", font=("Consolas", 9), bg="#0a0e27", fg="#4a5568",
                  relief="flat", cursor="hand2", command=_close).pack()
        em_ent.bind("<Return>", lambda e: save())
        self._autosize_dialog(win, min_w=380, min_h=260)
        em_ent.focus()

    def _attempt_login(self):
        global JWT_TOKEN
        if not getattr(self, '_hwid_ready', True) or not self.hwid:
            messagebox.showwarning("Please wait", "Still initializing, please try again in a moment.")
            return
        u = self.username_entry.get().strip()
        p = self.password_entry.get()
        if not u or not p:
            messagebox.showerror("Error", "Enter username and password")
            return

        # Disable login button to prevent double-click
        try:
            self._login_btn.config(state="disabled", text="Logging in...")
        except Exception:
            pass

        def _do_login():
            resp, code = api_request("POST", "/login", json_data={"username": u, "password": p}, require_auth=False)
            self.root.after(0, lambda: _on_login(resp, code))

        def _on_login(resp, code):
            global JWT_TOKEN
            try:
                self._login_btn.config(state="normal", text="LOGIN")
            except Exception:
                pass
            if code != 200 or not isinstance(resp, dict) or "access_token" not in resp:
                msg = resp.get("error", f"HTTP {code}") if isinstance(resp, dict) else "Connection failed"
                messagebox.showerror("Login Failed", msg)
                self.password_entry.delete(0, tk.END)
                return

            JWT_TOKEN = resp["access_token"]
            self.username = u
            _save_last_user(u)
            _needs_email_prompt = not resp.get("has_email", True)

            # Now check license in background
            try:
                self._login_btn.config(state="disabled", text="Checking license...")
            except Exception:
                pass
            threading.Thread(target=lambda: _do_license(_needs_email_prompt), daemon=True).start()

        def _do_license(_needs_email_prompt):
            hwid = self.hwid
            lic, lic_code = check_license_status(hwid)
            self.root.after(0, lambda: _on_license(lic, lic_code, _needs_email_prompt))

        def _on_license(lic, lic_code, _needs_email_prompt):
            try:
                self._login_btn.config(state="normal", text="LOGIN")
            except Exception:
                pass

            if lic_code == 200 and isinstance(lic, dict) and lic.get("status") == "active":
                if not lic.get("games"):
                    lic["games"] = [lic.get("game") or "arena_breakout"]
                if not lic.get("game"):
                    lic["game"] = "arena_breakout"
                self.authenticated = True
                self._license_info = lic
                if _needs_email_prompt:
                    self._prompt_add_email(on_done=self.root.quit)
                else:
                    self.root.quit()
                return

            # No active license on current HWID — try legacy in background
            threading.Thread(target=lambda: _do_legacy(_needs_email_prompt), daemon=True).start()

        def _do_legacy(_needs_email_prompt):
            legacy_hwid = get_hwid_legacy()
            if legacy_hwid == self.hwid:
                self.root.after(0, lambda: _show_activation())
                return
            lic_legacy, code_legacy = check_license_status(legacy_hwid)
            if code_legacy == 200 and isinstance(lic_legacy, dict) and lic_legacy.get("status") == "active":
                if not lic_legacy.get("games"):
                    lic_legacy["games"] = [lic_legacy.get("game") or "arena_breakout"]
                if not lic_legacy.get("game"):
                    lic_legacy["game"] = "arena_breakout"
                migrate_r, migrate_c = api_request("POST", "/license/migrate",
                    json_data={"old_hwid": legacy_hwid, "new_hwid": self.hwid})
                if migrate_c == 200:
                    self.root.after(0, lambda: _finish(lic_legacy, _needs_email_prompt))
                    return
                self.hwid = legacy_hwid
                self.root.after(0, lambda: _finish(lic_legacy, _needs_email_prompt))
                return
            self.root.after(0, lambda: _show_activation())

        def _finish(lic, _needs_email_prompt):
            self.authenticated = True
            self._license_info = lic
            if _needs_email_prompt:
                self._prompt_add_email(on_done=self.root.quit)
            else:
                self.root.quit()

        def _show_activation():
            _master = self.root.master if self.root.master else self.root
            self.root.withdraw()

            act_win = Toplevel(_master)
            act_win.title("Activate License")
            act_win.configure(bg="#0a0e27")
            act_win.geometry("520x520")
            act_win.minsize(480, 480)
            act_win.resizable(True, True)
            act_win.lift()
            act_win.focus_force()

            main_frame = tk.Frame(act_win, bg="#0a0e27")
            main_frame.pack(fill="both", expand=True, padx=40, pady=20)
            main_frame.grid_columnconfigure(0, weight=1)

            tk.Label(main_frame, text="Activate License", font=("Consolas", 18, "bold"), bg="#0a0e27", fg="#ffd700").pack(pady=(0,10))
            tk.Label(main_frame, text=f"User: {self.username}", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(pady=(0,20))
            tk.Label(main_frame, text="HWID:", font=("Consolas", 10, "bold"), bg="#0a0e27", fg="#e74c3c").pack(anchor="w")
            txt = tk.Text(main_frame, height=3, font=("Consolas", 10), bg="#1a1f3a", fg="#95a5a6", relief="flat", wrap="word")
            txt.insert("1.0", self.hwid)
            txt.config(state="disabled")
            txt.pack(fill="x", pady=(4,20))

            tk.Label(main_frame, text="Serial Key:", font=("Consolas", 11), bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
            serial_ent = tk.Entry(main_frame, font=("Consolas", 14), bg="#1a1f3a", fg="#fff",
                                  insertbackground="#ffd700", relief="flat", bd=4)
            serial_ent.pack(fill="x", ipady=10, pady=(4,0))

            act_status = tk.StringVar(value="")
            tk.Label(main_frame, textvariable=act_status, font=("Consolas", 9),
                     bg="#0a0e27", fg="#e74c3c").pack(anchor="w", pady=(4,0))

            def activate():
                key = serial_ent.get().strip()
                if not key:
                    act_status.set("Enter a serial key")
                    serial_ent.focus_set()
                    return
                act_status.set("⏳ Activating...")
                act_btn.config(state="disabled")
                def _do():
                    r, c = api_request("POST", "/license/activate", json_data={"serial": key, "hwid": self.hwid})
                    act_win.after(0, lambda: _on_act(r, c))
                def _on_act(r, c):
                    act_btn.config(state="normal")
                    if c == 200 and isinstance(r, dict) and "message" in r:
                        act_status.set("✅ Activated!")
                        act_btn.config(state="disabled")
                        def _fetch_lic():
                            lic_fresh, _ = check_license_status(self.hwid)
                            act_win.after(0, lambda: _on_fresh(lic_fresh))
                        def _on_fresh(lic_fresh):
                            lic_fresh = lic_fresh if isinstance(lic_fresh, dict) else {}
                            if not lic_fresh.get("games"):
                                lic_fresh["games"] = [lic_fresh.get("game") or "arena_breakout"]
                            if not lic_fresh.get("game"):
                                lic_fresh["game"] = "arena_breakout"
                            self.authenticated = True
                            self._license_info = lic_fresh
                            act_win.destroy()
                            self.root.quit()
                        threading.Thread(target=_fetch_lic, daemon=True).start()
                    else:
                        msg = r.get("error", f"HTTP {c}") if isinstance(r, dict) else "Failed"
                        act_status.set(f"❌ {msg}")
                        serial_ent.focus_set()
                threading.Thread(target=_do, daemon=True).start()

            serial_ent.bind("<Return>", lambda e: activate())

            btn_frame = tk.Frame(main_frame, bg="#0a0e27")
            btn_frame.pack(fill="x", pady=(30, 0))
            btn_frame.grid_columnconfigure(0, weight=1)
            act_btn = tk.Button(btn_frame, text="ACTIVATE", font=("Consolas", 13, "bold"), bg="#2ecc71", fg="white",
                      relief="flat", command=activate)
            act_btn.pack(fill="x", ipady=14, pady=(0, 10))
            tk.Button(btn_frame, text="Cancel", font=("Consolas", 11), bg="#e74c3c", fg="white",
                      relief="flat", command=lambda: [act_win.destroy(), self.root.quit()]).pack(fill="x", ipady=10)

            act_win.update_idletasks()
            sw = act_win.winfo_screenwidth()
            sh = act_win.winfo_screenheight()
            w, h = 520, 520
            act_win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
            act_win.lift()
            act_win.grab_set()
            serial_ent.focus_set()

        threading.Thread(target=_do_login, daemon=True).start()

    def show(self):
        self.root.mainloop()
        try:
            self.root.withdraw()  # hide auth window — master root keeps running
        except Exception:
            pass
        return self.authenticated, self.username


# Bot's own Tk root hwnd — set at startup to exclude from game searches
_BOT_HWNDS: set = set()

def _find_notepad_window():
    """Find Notepad window by process name — works on Win10 and Win11."""
    try:
        import psutil
        notepad_pids = set()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if (proc.info["name"] or "").lower() in ("notepad.exe", "notepad"):
                    notepad_pids.add(proc.info["pid"])
            except Exception:
                pass
        if not notepad_pids:
            return []
        # Find windows belonging to those PIDs
        found = []
        def _cb(hwnd, _):
            try:
                if hwnd in _BOT_HWNDS:
                    return True
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                pid = ctypes.c_ulong()
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in notepad_pids:
                    title = win32gui.GetWindowText(hwnd)
                    rect  = win32gui.GetWindowRect(hwnd)
                    w = rect[2] - rect[0]
                    h = rect[3] - rect[1]
                    if w > 50 and h > 50:
                        found.append({"hwnd": hwnd, "title": title or "Notepad",
                                      "class": win32gui.GetClassName(hwnd), "rect": rect})
            except Exception:
                pass
            return True
        win32gui.EnumWindows(_cb, None)
        return found
    except Exception:
        # Fallback: title search
        return find_game_window_enhanced("Notepad")

def find_game_window_enhanced(title_fragment: str):
    windows = []
    def cb(hwnd, _):
        try:
            if hwnd in _BOT_HWNDS:
                return True  # never match the bot's own windows
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title_fragment.lower() in title.lower():
                    # Extra guard: skip any window whose class is Tkinter
                    cls = win32gui.GetClassName(hwnd)
                    if cls in ("TkTopLevel", "TkChild", "Tk"):
                        return True
                    windows.append({
                        'hwnd': hwnd,
                        'title': title,
                        'class': cls,
                        'rect': win32gui.GetWindowRect(hwnd)
                    })
        except:
            pass
        return True
    win32gui.EnumWindows(cb, None)
    return windows


def find_game_by_pid_or_exe(game_key: str):
    """
    Find a running game window by scanning all processes for matching exe names.
    Works even when the window title changes (full-screen mode, loading screens, etc).
    Returns list of window dicts same format as find_game_window_enhanced.
    """
    cfg = GAME_CONFIGS.get(game_key)
    if not cfg:
        return []

    target_pids = set()

    # Scan running processes for matching exe names
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if _exe_matches_game(proc.info['name'], cfg):
                    target_pids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        # psutil not available — fall back to title-based search
        pass

    if not target_pids:
        # Fallback: title fragment search
        return find_game_window_enhanced(cfg["window_title"])

    # Find windows belonging to those PIDs
    import ctypes as _ct
    PROCESS_QUERY_INFORMATION = 0x0400
    found = []

    def enum_cb(hwnd, _):
        try:
            if hwnd in _BOT_HWNDS:
                return True
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True
            lpdw_pid = ctypes.c_ulong()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw_pid))
            if lpdw_pid.value in target_pids:
                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                if w > 100 and h > 100:  # skip tiny helper windows
                    found.append({
                        'hwnd': hwnd,
                        'title': title,
                        'class': win32gui.GetClassName(hwnd),
                        'rect': rect,
                        'pid': lpdw_pid.value,
                    })
        except Exception:
            pass
        return True

    win32gui.EnumWindows(enum_cb, None)

    # Sort: prefer fullscreen/maximised windows first
    def _score(w):
        rect = w['rect']
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        return -area  # largest window first

    found.sort(key=_score)
    return found


def is_game_running(game_key: str) -> bool:
    """Return True if the game process is currently running."""
    cfg = GAME_CONFIGS.get(game_key)
    if not cfg:
        return False
    try:
        import psutil
        for proc in psutil.process_iter(['name']):
            try:
                if _exe_matches_game(proc.info['name'], cfg):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        wins = find_game_window_enhanced(cfg["window_title"])
        return bool(wins)
    return False


def focus_window_advanced(hwnd):
    """Bring hwnd to front using raw win32 API — works cross-process."""
    try:
        u32  = ctypes.windll.user32
        k32  = ctypes.windll.kernel32

        SW_RESTORE = 9
        SW_SHOW    = 5

        # 1. Restore if minimised
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05)

        # 2. Get thread IDs
        cur_tid = k32.GetCurrentThreadId()
        tgt_tid = u32.GetWindowThreadProcessId(hwnd, None)

        # 3. Attach input queues so SetForegroundWindow is never blocked
        if tgt_tid and tgt_tid != cur_tid:
            u32.AttachThreadInput(cur_tid, tgt_tid, True)

        # 4. Raw win32 sequence — each call reinforces the last
        u32.ShowWindow(hwnd, SW_SHOW)
        u32.BringWindowToTop(hwnd)
        u32.SetForegroundWindow(hwnd)
        u32.SetActiveWindow(hwnd)
        u32.SetFocus(hwnd)

        # 5. Detach
        if tgt_tid and tgt_tid != cur_tid:
            u32.AttachThreadInput(cur_tid, tgt_tid, False)

        # 6. Final nudge — post WM_ACTIVATE to the window
        WM_ACTIVATE    = 0x0006
        WA_ACTIVE      = 1
        u32.PostMessageW(hwnd, WM_ACTIVATE, WA_ACTIVE, 0)

        return True
    except Exception as e:
        print(f"[focus] error: {e}")
        return False


# Global app ref so InputMethods can access the overlay
_APP_INSTANCE = [None]

def _screenshot_clean(region=None):
    """Take screenshot with bot window hidden and overlay moved if they overlap the region."""
    import numpy as np
    import time as _time

    app = _APP_INSTANCE[0]

    def _overlaps(wx, wy, ww, wh):
        """Check if a window rect overlaps the capture region."""
        if not region:
            return True  # full screen always overlaps
        rx, ry, rw, rh = region
        return (rx < wx + ww and rx + rw > wx and
                ry < wy + wh and ry + rh > wy)

    def _best_corner(ww, wh, sw, sh):
        """Pick screen corner furthest from region centre."""
        if not region:
            return 20, 20
        cx = region[0] + region[2] / 2
        cy = region[1] + region[3] / 2
        candidates = [
            (20, 20),
            (sw - ww - 20, 20),
            (20, sh - wh - 40),
            (sw - ww - 20, sh - wh - 40),
        ]
        return max(candidates, key=lambda p: abs(p[0] - cx) + abs(p[1] - cy))

    _hidden = False
    _ov_moved = False
    _ov_old_geo = None

    if app:
        # ── 1. Hide main bot window if it overlaps ────────────────
        try:
            bx = app.root.winfo_rootx()
            by = app.root.winfo_rooty()
            bw = app.root.winfo_width()
            bh = app.root.winfo_height()
            if _overlaps(bx, by, bw, bh):
                app.root.withdraw()
                _hidden = True
        except Exception:
            pass

        # ── 2. Move overlay if it overlaps (don't hide — less flicker) ──
        try:
            ov = getattr(app, "_run_overlay", None)
            if ov and ov.winfo_exists():
                ox = ov.winfo_x()
                oy = ov.winfo_y()
                ow = ov.winfo_width()
                oh = ov.winfo_height()
                if _overlaps(ox, oy, ow, oh):
                    _ov_old_geo = f"+{ox}+{oy}"
                    sw = ov.winfo_screenwidth()
                    sh = ov.winfo_screenheight()
                    nx, ny = _best_corner(ow, oh, sw, sh)
                    ov.geometry(f"+{nx}+{ny}")
                    _ov_moved = True
        except Exception:
            pass

        if _hidden or _ov_moved:
            _time.sleep(0.08)  # let Windows redraw

    img = pyautogui.screenshot(region=region)
    img_np = np.array(img)

    # ── Restore ───────────────────────────────────────────────────
    if app:
        if _hidden:
            try: app.root.deiconify()
            except: pass
        if _ov_moved and _ov_old_geo:
            try:
                ov = getattr(app, "_run_overlay", None)
                if ov and ov.winfo_exists():
                    ov.geometry(_ov_old_geo)
            except: pass

    return img, img_np

def _screenshot_to_base64(region):
    img, img_np = _screenshot_clean(region=region)
    try:
        with io.BytesIO() as buf:
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("ascii")
    finally:
        img.close()
        del img_np

def _dodge_overlay_if_needed(cx, cy, padding=30):
    """If the overlay window covers (cx,cy), move it out of the way instantly."""
    app = _APP_INSTANCE[0]
    if not app:
        return
    try:
        ov = getattr(app, "_run_overlay", None)
        if not ov or not ov.winfo_exists():
            return
        ox = ov.winfo_x(); oy = ov.winfo_y()
        ow = ov.winfo_width(); oh = ov.winfo_height()
        if (ox - padding) <= cx <= (ox + ow + padding) and            (oy - padding) <= cy <= (oy + oh + padding):
            sw = ov.winfo_screenwidth(); sh = ov.winfo_screenheight()
            candidates = [(20,20),(sw-ow-20,20),(20,sh-oh-40),(sw-ow-20,sh-oh-40)]
            best = max(candidates, key=lambda p: abs(p[0]-cx)+abs(p[1]-cy))
            ov.geometry(f"+{best[0]}+{best[1]}")
            app.log(f"  ⤡ Overlay moved to avoid click at ({cx},{cy})")
    except Exception:
        pass

class InputMethods:
    @staticmethod
    def send_click(x, y, button="left"):
        _dodge_overlay_if_needed(x, y)
        sw = _user32.GetSystemMetrics(0)
        sh = _user32.GetSystemMetrics(1)
        nx = int(x * 65535 / sw)
        ny = int(y * 65535 / sh)

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]

        def send(flags, dx=0, dy=0):
            mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=None)
            inp = INPUT(type=0, mi=mi)
            _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        send(0x8000 | 0x0001, nx, ny)
        time.sleep(0.04)

        if button == "left":
            send(0x0002)
            time.sleep(0.04)
            send(0x0004)
        elif button == "right":
            send(0x0008)
            time.sleep(0.04)
            send(0x0010)
        elif button == "double":
            send(0x0002)
            time.sleep(0.03)
            send(0x0004)
            time.sleep(0.15)   # 150ms between clicks
            send(0x0002)
            time.sleep(0.03)
            send(0x0004)

    @staticmethod
    def type_text(text: str):
        keyboard.write(text)
        time.sleep(0.06)

    @staticmethod
    def clear_and_type(x: int, y: int, text: str):
        InputMethods.send_click(x, y, "left")
        time.sleep(0.18)
        keyboard.press('ctrl')
        keyboard.press('a')
        keyboard.release('a')
        keyboard.release('ctrl')
        time.sleep(0.12)
        keyboard.press_and_release('delete')
        time.sleep(0.12)
        InputMethods.type_text(text)


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class GameLauncherWindow:
    """
    Post-login window that lets the user choose which licensed game to run the bot for.
    Shows only the games the license covers.
    Polls game process status every 2s and enables/disables launch buttons accordingly.
    """

    def __init__(self, username: str, license_info: dict, master=None):
        self.username = username
        self.license_info = license_info or {}
        self.selected_game = None

        # Determine which games this license covers
        raw_games = self.license_info.get("games") or self.license_info.get("game")
        if isinstance(raw_games, list) and raw_games:
            self.licensed_games = raw_games
        elif isinstance(raw_games, str) and raw_games:
            self.licensed_games = [raw_games]
        else:
            self.licensed_games = ["arena_breakout"]

        self.licensed_games = [g for g in self.licensed_games if g in GAME_CONFIGS]
        if not self.licensed_games:
            self.licensed_games = ["arena_breakout"]

        if master:
            self.root = tk.Toplevel(master)
        else:
            self.root = tk.Tk()
        self.root.title("Pato Tool Bot — Select Game")
        self.root.configure(bg="#0a0e27")
        self.root.resizable(False, False)
        _set_icon(self.root)
        self._build_ui()
        _center_win(self.root, 620, 640)

    def _build_ui(self):
        C = {"bg": "#0a0e27", "bg2": "#1a1f3a", "bg3": "#2a3f5f",
             "gold": "#ffd700", "text": "#ffffff", "dim": "#8b9dc3",
             "green": "#2ecc71", "red": "#e74c3c", "info": "#3498db",
             "orange": "#f39c12", "locked": "#2c2c3e"}

        BUY_URLS = {
            "arena_breakout": "https://patotools.mysellauth.com/product/patos-arena-breakout-market-bot",
            "arc_raiders":    "https://patotools.mysellauth.com/product/pato-arc-raider-bot",
        }

        # ── Header ──
        hdr = tk.Frame(self.root, bg=C["bg2"], height=90)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🦆", font=("Arial", 40), bg=C["bg2"], fg=C["gold"]).place(x=20, rely=0.5, anchor="w")
        tk.Label(hdr, text="SELECT GAME", font=("Consolas", 18, "bold"),
                 bg=C["bg2"], fg=C["gold"]).place(relx=0.5, y=28, anchor="center")
        tk.Label(hdr, text=f"Welcome, {self.username}  •  Choose a game to launch the bot",
                 font=("Consolas", 10), bg=C["bg2"], fg=C["dim"]).place(relx=0.5, y=62, anchor="center")

        # ── License badge ──
        lic_text = self._lic_text()
        lic_color = C["green"] if "⭐" in lic_text or "✅" in lic_text else C["red"]
        tk.Label(self.root, text=lic_text, font=("Segoe UI", 9, "bold"),
                 bg=C["bg"], fg=lic_color).pack(pady=(14, 4))

        # ── Game cards — always show ALL games ──
        self._status_vars = {}
        self._launch_btns = {}

        cards_frame = tk.Frame(self.root, bg=C["bg"])
        cards_frame.pack(fill="both", expand=True, padx=30, pady=10)

        for game_key, cfg in GAME_CONFIGS.items():
            has_license = game_key in self.licensed_games
            card_bg = C["bg2"] if has_license else C["locked"]

            card = tk.Frame(cards_frame, bg=card_bg, bd=1, relief="solid")
            card.pack(fill="x", pady=8, ipady=10)

            # ── Left: emoji ──
            left = tk.Frame(card, bg=card_bg)
            left.pack(side="left", padx=18, pady=6)
            emoji_color = cfg["color"] if has_license else "#555577"
            tk.Label(left, text=cfg["emoji"] if has_license else "🔒",
                     font=("Arial", 36), bg=card_bg, fg=emoji_color).pack()

            # ── Mid: name + status ──
            mid = tk.Frame(card, bg=card_bg)
            mid.pack(side="left", fill="both", expand=True, pady=6)
            name_color = cfg["color"] if has_license else "#666688"
            tk.Label(mid, text=cfg["name"], font=("Consolas", 14, "bold"),
                     bg=card_bg, fg=name_color).pack(anchor="w")

            if has_license:
                status_lbl = tk.Label(mid, text="⏳ Checking...",
                                      font=("Segoe UI", 9), bg=card_bg, fg=C["dim"])
                status_lbl.pack(anchor="w")
                self._status_vars[game_key] = (None, status_lbl)
            else:
                tk.Label(mid, text="No license — purchase to unlock",
                         font=("Segoe UI", 9), bg=card_bg, fg="#888899").pack(anchor="w")

            # ── Right: Launch or Buy button ──
            right = tk.Frame(card, bg=card_bg)
            right.pack(side="right", padx=14, pady=6)

            if has_license:
                def make_launch(gk=game_key):
                    def _launch():
                        self._polling = False
                        self.selected_game = gk
                        self.root.quit()
                    return _launch

                btn = tk.Button(right, text="▶  LAUNCH", font=("Consolas", 11, "bold"),
                                bg=C["green"], fg="white", relief="flat", cursor="hand2",
                                state="disabled", command=make_launch(game_key),
                                padx=12, pady=8)
                btn.pack()
                self._launch_btns[game_key] = btn
            else:
                def make_buy(url=BUY_URLS[game_key]):
                    def _buy():
                        import webbrowser
                        webbrowser.open(url)
                    return _buy

                tk.Button(right, text="🛒  BUY", font=("Consolas", 11, "bold"),
                          bg=C["orange"], fg="white", relief="flat", cursor="hand2",
                          command=make_buy(), padx=12, pady=8).pack()

        # ── Activate Serial Key section ──
        sep = tk.Frame(self.root, bg="#2a3f5f", height=1)
        sep.pack(fill="x", padx=20, pady=(8, 0))

        act_frame = tk.Frame(self.root, bg=C["bg"])
        act_frame.pack(fill="x", padx=30, pady=(10, 0))

        tk.Label(act_frame, text="🔑  Have a serial key? Activate it below:",
                 font=("Consolas", 10, "bold"), bg=C["bg"], fg=C["gold"]).pack(anchor="w", pady=(0, 6))

        input_row = tk.Frame(act_frame, bg=C["bg"])
        input_row.pack(fill="x")

        serial_var = tk.StringVar()
        serial_entry = tk.Entry(input_row, textvariable=serial_var,
                                font=("Consolas", 12), bg="#1a1f3a", fg="#fff",
                                insertbackground=C["gold"], relief="flat", bd=4)
        serial_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        serial_entry.insert(0, "PATO-XXXX-XXXX-XXXX")
        serial_entry.config(fg="#555577")

        def _on_focus_in(e):
            if serial_entry.get() == "PATO-XXXX-XXXX-XXXX":
                serial_entry.delete(0, tk.END)
                serial_entry.config(fg="#ffffff")

        def _on_focus_out(e):
            if not serial_entry.get().strip():
                serial_entry.insert(0, "PATO-XXXX-XXXX-XXXX")
                serial_entry.config(fg="#555577")

        serial_entry.bind("<FocusIn>", _on_focus_in)
        serial_entry.bind("<FocusOut>", _on_focus_out)

        act_status = tk.StringVar(value="")
        act_status_lbl = tk.Label(act_frame, textvariable=act_status,
                                   font=("Segoe UI", 9), bg=C["bg"], fg=C["green"])
        act_status_lbl.pack(anchor="w", pady=(4, 0))

        def do_activate():
            key = serial_var.get().strip().upper()
            if not key or key == "PATO-XXXX-XXXX-XXXX":
                act_status.set("⚠ Enter a serial key first")
                act_status_lbl.config(fg=C["red"])
                return
            act_btn.config(state="disabled", text="Activating...")
            act_status.set("⏳ Contacting server...")
            act_status_lbl.config(fg=C["dim"])

            def _do_in_thread():
                try:
                    hwid = get_hwid()
                except Exception:
                    hwid = ""
                r, c = api_request("POST", "/license/activate",
                                    json_data={"serial": key, "hwid": hwid})
                self.root.after(0, lambda: _on_result(r, c))

            def _on_result(r, c):
                act_btn.config(state="normal", text="ACTIVATE")
                if c == 200 and isinstance(r, dict) and "message" in r:
                    game_val = r.get("game", "arena_breakout")
                    game_name = GAME_CONFIGS.get(game_val, {}).get("name", game_val)
                    act_status.set(f"✅ Activated for {game_name}! Refreshing...")
                    act_status_lbl.config(fg=C["green"])
                    serial_entry.delete(0, tk.END)
                    games_new = r.get("games") or [r.get("game", "arena_breakout")]
                    changed = False
                    for g in games_new:
                        if g not in self.licensed_games:
                            self.licensed_games.append(g)
                            changed = True
                    if changed:
                        self.root.after(800, self._rebuild_ui)
                    else:
                        act_status.set(f"✅ Already active for {game_name}!")
                else:
                    msg = r.get("error", f"HTTP {c}") if isinstance(r, dict) else "Server error"
                    act_status.set(f"❌ {msg}")
                    act_status_lbl.config(fg=C["red"])

            threading.Thread(target=_do_in_thread, daemon=True).start()

        act_btn = tk.Button(input_row, text="ACTIVATE", font=("Consolas", 11, "bold"),
                            bg=C["info"], fg="white", relief="flat", cursor="hand2",
                            command=do_activate, padx=14, pady=8)
        act_btn.pack(side="left")

        serial_entry.bind("<Return>", lambda e: do_activate())

        # ── Footer ──
        foot = tk.Frame(self.root, bg=C["bg"])
        foot.pack(fill="x", padx=30, pady=(10, 14))
        tk.Label(foot, text="💡 Start your game first, then click Launch",
                 font=("Segoe UI", 9, "italic"), bg=C["bg"], fg=C["dim"]).pack(side="left")

        # Start status polling (only for licensed games)
        self._polling = True
        if self._status_vars:
            self.root.after(200, self._poll_game_status)

    def _rebuild_ui(self):
        """Destroy all widgets and rebuild UI with updated licensed_games list."""
        try:
            self._polling = False  # pause poll while rebuilding
            for widget in self.root.winfo_children():
                widget.destroy()
            self._status_vars = {}
            self._launch_btns = {}
            self._build_ui()  # _build_ui sets _polling = True and restarts poll
            # Re-register close handler (destroyed with widgets but protocol persists on root)
            def _on_close():
                self._polling = False
                try:
                    self.root.destroy()
                except Exception:
                    pass
            self.root.protocol("WM_DELETE_WINDOW", _on_close)
        except Exception:
            pass

    def _lic_text(self):
        lic = self.license_info
        lic_type = str(lic.get("type", "")).lower()
        if lic_type in ("forever", "lifetime"):
            return "⭐ Lifetime License"
        days = lic.get("days_remaining")
        if days is not None:
            if days <= 0: return "⚠ License expired"
            if days == 1: return "⏰ 1 day left"
            if days <= 3: return f"⚠ {days} days left"
            return f"✅ {days} days left"
        return "🔑 License active"

    def _poll_game_status(self):
        """Run process scan in background, update UI on main thread."""
        if not getattr(self, '_polling', False):
            return

        def _scan():
            try:
                import psutil
                proc_names = set()
                for proc in psutil.process_iter(["name"]):
                    try:
                        n = (proc.info["name"] or "").lower()
                        proc_names.add(n)
                    except Exception:
                        pass

                notepad_open = "notepad.exe" in proc_names
                game_states = {}
                for game_key, cfg in GAME_CONFIGS.items():
                    game_states[game_key] = any(_exe_matches_game(pn, cfg) for pn in proc_names)

            except Exception as e:
                print(f"[poll] scan error: {e}")
                notepad_open = False
                game_states = {gk: False for gk in GAME_CONFIGS}

            # Push UI update + reschedule to main thread in one shot
            if getattr(self, '_polling', False):
                self.root.after(0, lambda s=game_states, n=notepad_open: self._apply_status(s, n))

        threading.Thread(target=_scan, daemon=True).start()

    def _apply_status(self, game_states: dict, notepad_open: bool):
        """Apply scan results to UI widgets — main thread only."""
        # Reschedule next poll from here — we're guaranteed on main thread
        if getattr(self, '_polling', False):
            self.root.after(2000, self._poll_game_status)
        for game_key, (_, status_lbl) in list(self._status_vars.items()):
            btn = self._launch_btns.get(game_key)
            if btn is None or not status_lbl.winfo_exists():
                continue
            cfg = GAME_CONFIGS[game_key]
            running = game_states.get(game_key, False)
            if running:
                status_lbl.config(text=f"🟢 {cfg['name']} is running", fg="#2ecc71")
                btn.config(state="normal", bg="#2ecc71")
            elif notepad_open:
                status_lbl.config(text="📝 Notepad detected — launch without game", fg="#f39c12")
                btn.config(state="normal", bg="#f39c12")
            else:
                status_lbl.config(text="🔴 Not detected — start the game first", fg="#e74c3c")
                btn.config(state="disabled", bg="#555")

    def show(self):
        """Block until user selects a game. Returns (game_key, game_cfg) or (None, None)."""
        # X button: stop polling and quit mainloop cleanly
        def _on_close():
            self._polling = False
            self.root.quit()
        self.root.protocol("WM_DELETE_WINDOW", _on_close)
        self.root.mainloop()
        self._polling = False
        try:
            self.root.withdraw()
        except Exception:
            pass
        if self.selected_game:
            return self.selected_game, GAME_CONFIGS[self.selected_game]
        return None, None


class AutoClickBot:
    LOGIC_ACTIONS = [
        "Declare Variable (int/float/bool/string)",
        "Loop Start (repeat X times)",
        "Loop While (var condition)",
        "Loop For (var from X to Y)",
        "If Variable > X (branch)",
        "If Variable < X (branch)",
        "If Variable == X (branch)",
        "If Variable != X (branch)",
        "If Bool True (branch)",
        "If Bool False (branch)",
        "If Variable Exists (branch)",
        "If Image Exists (branch)",
        "If OCR number ≥ X (branch)",
        "If OCR text exists (branch)",
        "If OCR any text (branch)",
        "Set Variable",
        "Add To Variable",
        "Subtract From Variable",
        "Multiply Variable",
        "Divide Variable",
        "Modulo Variable",
        "Increment Variable",
        "Decrement Variable",
        "Toggle Bool (True ↔ False)",
        "Set Bool To True",
        "Set Bool To False",
        "Append String",
        "Reset Variable",
        "Delete Variable",
        "Break Loop",
        "Continue Loop",
        "Return / End",
        "Stop Sequence",
        "Else (branch)",
        "Else If (branch)",
        "Switch Case (multiple branches)",
        "If Variable Changed (branch)",
        "Comment",
    ]

    EXECUTION_ACTIONS = [
        "Single Click",
        "Double Click",
        "Right Click",
        "Right Click → Click Menu Item",
        "Find Image & Click",
        "Move Mouse & Scroll",
        "OCR Click (Search Text)",
        "OCR Right Click (Search Text)",
        "Manual Coordinates",
        "Clear & Write Price",
        "Clear & Write Text",
        "Type Text",
        "Press Key",
        "Press & Release",
        "Wait (milliseconds)",
        "Wait Random (min-max ms)",
        "Wait for Text (OCR)",
        "Read OCR Number → Variable",
        "Counter: Reset",
        "Counter: Add 1",
        "Counter: Subtract 1",
        "Screenshot & Save",
        "Increment Loop Counter",
    ]

    CLICK_BUTTON = {
        "Single Click": "left",
        "Double Click": "double",
        "Right Click": "right",
        "Manual Coordinates": "left",
    }

    def __init__(self, root: tk.Tk, username: str, license_info: dict = None, game_key: str = "arena_breakout"):
        self.root = root
        self.username = username
        self.license_info = license_info or {}
        self.game_key = game_key
        self.game_cfg = GAME_CONFIGS.get(game_key, GAME_CONFIGS["arena_breakout"])
        self._notepad_mode = False
        self._target_hwnd = None
        self.root.title(f"Pato's Bot • {self.game_cfg['name']} • {username} • F9 = STOP")
        self.root.geometry("1800x1050")
        _set_icon(self.root)
        self.root.minsize(1200, 700)
        self.root.configure(bg="#0a0e27")
        self.root.resizable(True, True)

        self.running = False
        self._stop_event = threading.Event()
        self.sequence = []
        self.target_list = None
        self.debug_log = []
        self._last_gc_time = time.time()
        self.variables = {}
        self.drag_data = None
        self.frame_map = {}
        self._clipboard_action = None   # for cut/copy/paste
        self._refresh_pending = None    # debounce timer for refresh
        self._drag_scroll_active = False
        self._drag_start_y = 0
        self._last_ocr_stable = None
        self.log_cleanup_counter = 0  # ← ADD THIS
        self.iteration_count = 0 

        self.ACTION_HANDLERS = {
            "Single Click": self._handle_click,
            "Double Click": self._handle_click,
            "Right Click": self._handle_click,
            "Right Click → Click Menu Item": self._handle_right_click_menu_item,
            "Manual Coordinates": self._handle_click,
            "Move Mouse & Scroll": self._handle_move_and_scroll,
            "OCR Click (Search Text)": self._handle_ocr_click,
            "OCR Right Click (Search Text)": self._handle_ocr_click,
            "Find Image & Click": self._handle_image_click,
            "Clear & Write Price": self._handle_clear_write,
            "Clear & Write Text": self._handle_clear_write_text,
            "Type Text": self._handle_type_text,
            "Press Key": self._handle_press_key,
            "Press & Release": self._handle_press_release,
            "Wait (milliseconds)": self._handle_wait,
            "Wait Random (min-max ms)": self._handle_wait_random,
            "Wait for Text (OCR)": self._handle_wait_for_text,
            "Counter: Reset": self._handle_counter_reset,
            "Counter: Add 1": self._handle_counter_add,
            "Counter: Subtract 1": self._handle_counter_sub,
            "Set Variable": self._handle_set_variable,
            "Add To Variable": self._handle_add_to_variable,
            "Subtract From Variable": self._handle_subtract_variable,
            "Multiply Variable": self._handle_multiply_variable,
            "Divide Variable": self._handle_divide_variable,
            "Modulo Variable": self._handle_modulo_variable,
            "Increment Variable": self._handle_increment_variable,
            "Decrement Variable": self._handle_decrement_variable,
            "Toggle Bool (True ↔ False)": self._handle_toggle_bool,
            "Set Bool To True": self._handle_set_bool_true,
            "Set Bool To False": self._handle_set_bool_false,
            "Append String": self._handle_append_string,
            "Reset Variable": self._handle_reset_variable,
            "Delete Variable": self._handle_delete_variable,
            "If Variable Exists (branch)": self._handle_if_variable_exists,
            "If Image Exists (branch)": self._handle_if_image_exists,
            "Loop For (var from X to Y)": self._handle_loop_for,
            "Else (branch)": self._handle_else,
            "Else If (branch)": self._handle_else_if,
            "Switch Case (multiple branches)": self._handle_switch_case,
            "Return / End": self._handle_return,
            "Stop Sequence": self._handle_stop_sequence,
            "Declare Variable (int/float/bool/string)": self._handle_declare_variable,
            "Break Loop": self._handle_break_loop,
            "Continue Loop": self._handle_continue_loop,
            "Comment": self._handle_comment,
            "Loop Start (repeat X times)": self._handle_loop_start,
            "Loop While (var condition)": self._handle_loop_while,
            "If Variable > X (branch)": self._handle_if_variable_gt,
            "If Variable < X (branch)": self._handle_if_variable_lt,
            "If Variable == X (branch)": self._handle_if_variable_eq,
            "If Variable != X (branch)": self._handle_if_variable_ne,
            "If Bool True (branch)": self._handle_if_bool_true,
            "If Bool False (branch)": self._handle_if_bool_false,
            "Screenshot & Save": self._handle_screenshot,
            "Increment Loop Counter": self._handle_increment_loop,
            "If OCR number ≥ X (branch)": self._handle_if_ocr_ge,
            "If OCR text exists (branch)": self._handle_if_ocr_text_exists,
            "If OCR any text (branch)": self._handle_if_ocr_any_text,
            "Read OCR Number → Variable": self._handle_read_ocr_number,
            "If Variable Changed (branch)": self._handle_if_variable_changed,
        }

        _APP_INSTANCE[0] = self
        self._build_ui()
        # Register all bot Tk windows so they're excluded from game window searches
        def _register_bot_hwnds():
            try:
                for w in self.root.winfo_children() + [self.root]:
                    try:
                        _BOT_HWNDS.add(int(w.frame(), 16))
                    except Exception:
                        pass
                _BOT_HWNDS.add(int(self.root.frame(), 16))
            except Exception:
                pass
        self.root.after(200, _register_bot_hwnds)
        self._setup_hotkeys()
        self._setup_drag_scroll()
        _ensure_ids(self.sequence)  # patch any pre-existing actions on startup
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.stop()
        if hasattr(self, '_keyboard_hook'):
            try:
                keyboard.remove_hotkey(self._keyboard_hook)
            except:
                pass
        self.root.quit()
        self.root.destroy()
        # Explicit GC collect on close
        gc.collect()
    
    def _autosize_dialog(self, dialog, min_w=300, min_h=200, pad=40):
        """Resize dialog to fit its content then center it."""
        dialog.update_idletasks()
        w = max(dialog.winfo_reqwidth() + pad, min_w)
        h = max(dialog.winfo_reqheight() + pad, min_h)
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        dialog.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _center_dialog(self, dialog):
        dialog.update_idletasks()
        w = dialog.winfo_width()
        h = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (w // 2)
        y = (dialog.winfo_screenheight() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

    def _setup_hotkeys(self):
        def stop():
            self.stop()
            self.log("[F9] STOP")
            
            # Bring main application window to front and give it focus
            try:
                self.root.lift()                     # Raise window above others
                self.root.focus_force()              # Force keyboard focus
                # Brief topmost trick helps against stubborn fullscreen/games
                self.root.attributes('-topmost', True)
                self.root.after(120, lambda: self.root.attributes('-topmost', False))
            except Exception as focus_error:
                self.log(f"Focus main window after F9 failed: {focus_error}")

        try:
            self._keyboard_hook = keyboard.add_hotkey("f9", stop)
            self.log("F9 registered (stop + focus main window)")
        except Exception as e:
            self.log(f"F9 registration failed: {e}")

    def _setup_drag_scroll(self):
        # Smooth scroll animation using velocity/friction
        self._drag_scroll_active = False

    def _animate_scroll(self):
        pass  # Replaced by instant per-frame scroll in _on_mousewheel

    def _get_license_text(self):
        """Return a short license status string for the header label."""
        lic = self.license_info
        lic_type = str(lic.get("type", "")).lower()
        if lic_type in ("forever", "lifetime"):
            return "⭐ Lifetime License"
        days = lic.get("days_remaining")
        if days is not None:
            if days <= 0:
                return "⚠ License expired"
            elif days == 1:
                return "⏰ 1 day left"
            elif days <= 3:
                return f"⚠ {days} days left"
            else:
                return f"✅ {days} days left"
        expires_at = lic.get("expires_at")
        if expires_at:
            try:
                from datetime import datetime as _dt
                exp = _dt.fromisoformat(expires_at.replace("Z", "+00:00"))
                now = _dt.utcnow().replace(tzinfo=exp.tzinfo) if exp.tzinfo else _dt.utcnow()
                days_left = (exp - now).days
                if days_left <= 0:
                    return "⚠ License expired"
                return f"✅ {days_left} days left"
            except Exception:
                pass
        return "🔑 License active"

    def _start_license_refresh(self):
        """Refresh license label every 60s and fetch fresh info from server."""
        def _refresh():
            try:
                hwid = get_hwid()
                lic, code = check_license_status(hwid)
                if code == 200 and isinstance(lic, dict):
                    self.license_info = lic
                    try:
                        self.license_lbl.config(
                            text=self._get_license_text(),
                            fg="#e74c3c" if "expired" in self._get_license_text() or "⚠" in self._get_license_text() else self.colors['accent']
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                self.root.after(60000, _refresh)
            except Exception:
                pass
        self.root.after(2000, _refresh)

    def _build_ui(self):
        # Color scheme moderno
        self.colors = {
            'bg_dark': '#0a0e27',
            'bg_medium': '#1a1f3a',
            'bg_light': '#2a3f5f',
            'accent': '#ffd700',
            'success': '#2ecc71',
            'danger': '#e74c3c',
            'info': '#3498db',
            'text': '#ffffff',
            'text_dim': '#a0a0a0'
        }
        
        # ============= TOP BAR =============
        top_bar = tk.Frame(self.root, bg=self.colors['bg_medium'], height=80)
        top_bar.pack(fill="x", padx=10, pady=10)
        top_bar.pack_propagate(False)
        
        left_section = tk.Frame(top_bar, bg=self.colors['bg_medium'])
        left_section.pack(side="left", fill="y", padx=20)
        
        tk.Label(left_section, text="🦆", font=("Arial", 36), 
              bg=self.colors['bg_medium'], fg=self.colors['accent']).pack(side="left", padx=(0, 15))
        
        title_frame = tk.Frame(left_section, bg=self.colors['bg_medium'])
        title_frame.pack(side="left", fill="y")
        
        tk.Label(title_frame, text=f"PatoBot  •  {self.game_cfg['name']}", font=("Segoe UI", 20, "bold"),
              bg=self.colors['bg_medium'], fg=self.colors['text']).pack(anchor="w")
        tk.Label(title_frame, text=f"Advanced Automation Suite v{CURRENT_VERSION}", font=("Segoe UI", 9),
              bg=self.colors['bg_medium'], fg=self.colors['text_dim']).pack(anchor="w")
        
        right_section = tk.Frame(top_bar, bg=self.colors['bg_medium'])
        right_section.pack(side="right", fill="y", padx=20)
        
        user_frame = tk.Frame(right_section, bg=self.colors['bg_light'], relief="flat", padx=6, pady=4)
        user_frame.pack(side="right", padx=5, pady=10)
        
        tk.Label(user_frame, text="👤", font=("Arial", 16),
              bg=self.colors['bg_light'], fg=self.colors['accent']).pack(side="left", padx=(10, 5))
        
        user_info = tk.Frame(user_frame, bg=self.colors['bg_light'])
        user_info.pack(side="left", padx=(0, 10))
        
        tk.Label(user_info, text=f"👤 {self.username}", font=("Segoe UI", 10, "bold"),
              bg=self.colors['bg_light'], fg=self.colors['text']).pack(anchor="w")
        self.license_lbl = tk.Label(user_info, text=self._get_license_text(),
              font=("Segoe UI", 8), bg=self.colors['bg_light'], fg=self.colors['accent'],
              wraplength=200, justify="left")
        self.license_lbl.pack(anchor="w", fill="x")
        self.status_lbl = tk.Label(user_info, text="F9 = Stop", font=("Segoe UI", 8),
              bg=self.colors['bg_light'], fg=self.colors['success'])
        self.status_lbl.pack(anchor="w")
        self._start_license_refresh()
        
        # ============= TAB BAR =============
        tab_bar = tk.Frame(self.root, bg=self.colors['bg_dark'], height=44)
        tab_bar.pack(fill="x", padx=10, pady=(0, 0))
        tab_bar.pack_propagate(False)

        self._tab_sequence_btn = tk.Button(
            tab_bar, text="📝  Sequence Builder", font=("Segoe UI", 10, "bold"),
            bg=self.colors['accent'], fg=self.colors['bg_dark'],
            relief="flat", cursor="hand2", padx=20,
            command=lambda: self._switch_tab("sequence")
        )
        self._tab_sequence_btn.pack(side="left", fill="y", padx=(0, 3))

        self._tab_configs_btn = tk.Button(
            tab_bar, text="⚡  Pre-made Configs", font=("Segoe UI", 10, "bold"),
            bg=self.colors['bg_medium'], fg=self.colors['text_dim'],
            relief="flat", cursor="hand2", padx=20,
            command=lambda: self._switch_tab("configs")
        )
        self._tab_configs_btn.pack(side="left", fill="y")

        self._tab_settings_btn = tk.Button(
            tab_bar, text="⚙  Settings", font=("Segoe UI", 10, "bold"),
            bg=self.colors['bg_medium'], fg=self.colors['text_dim'],
            relief="flat", cursor="hand2", padx=20,
            command=lambda: self._switch_tab("settings")
        )
        self._tab_settings_btn.pack(side="right", fill="y")

        # ============= PAGE CONTAINER =============
        self._page_container = tk.Frame(self.root, bg=self.colors['bg_dark'])
        self._page_container.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        # ============= MAIN CONTENT (3 COLUMNS) =============
        main_content = tk.Frame(self._page_container, bg=self.colors['bg_dark'])
        main_content.pack(fill="both", expand=True)
        
        # LEFT PANEL - Actions (25%)
        left_panel = tk.Frame(main_content, bg=self.colors['bg_medium'], width=320)
        left_panel.pack(side="left", fill="both", padx=(0, 5))
        left_panel.pack_propagate(False)
        
        actions_header = tk.Frame(left_panel, bg=self.colors['bg_light'], height=50)
        actions_header.pack(fill="x")
        actions_header.pack_propagate(False)
        tk.Label(actions_header, text="📚 Actions", font=("Segoe UI", 12, "bold"),
              bg=self.colors['bg_light'], fg=self.colors['text']).pack(side="left", padx=15, pady=15)
        
        logic_section = tk.Frame(left_panel, bg=self.colors['bg_medium'])
        logic_section.pack(fill="x", padx=10, pady=10)
        
        tk.Label(logic_section, text="🔧 Logic", font=("Segoe UI", 10, "bold"),
              bg=self.colors['bg_medium'], fg=self.colors['accent']).pack(anchor="w", pady=(0,5))
        self.logic_combo = ttk.Combobox(logic_section, values=self.LOGIC_ACTIONS, state="readonly", font=("Consolas", 9))
        self.logic_combo.current(0)
        self.logic_combo.pack(fill="x", pady=(0,5))
        tk.Button(logic_section, text="➕ Add", font=("Segoe UI", 9, "bold"), 
                  bg=self.colors['info'], fg="white", relief="flat", command=self._add_logic, cursor="hand2").pack(fill="x", ipady=6)
        
        exec_section = tk.Frame(left_panel, bg=self.colors['bg_medium'])
        exec_section.pack(fill="x", padx=10, pady=10)
        
        tk.Label(exec_section, text="⚡ Actions", font=("Segoe UI", 10, "bold"),
              bg=self.colors['bg_medium'], fg=self.colors['accent']).pack(anchor="w", pady=(0,5))
        self.exec_combo = ttk.Combobox(exec_section, values=self.EXECUTION_ACTIONS, state="readonly", font=("Consolas", 9))
        self.exec_combo.current(0)
        self.exec_combo.pack(fill="x", pady=(0,5))
        tk.Button(exec_section, text="➕ Add", font=("Segoe UI", 9, "bold"), 
                  bg=self.colors['success'], fg="white", relief="flat", command=self._add_execution, cursor="hand2").pack(fill="x", ipady=6)
        
        tips_frame = tk.Frame(left_panel, bg=self.colors['bg_dark'])
        tips_frame.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(tips_frame, text="💡 Tips", font=("Segoe UI", 9, "bold"),
              bg=self.colors['bg_dark'], fg=self.colors['accent']).pack(anchor="w", pady=5)
        tips = scrolledtext.ScrolledText(tips_frame, height=8, font=("Segoe UI", 8),
                                        bg=self.colors['bg_dark'], fg=self.colors['text_dim'],
                                        relief="flat", bd=0, wrap="word", state="disabled")
        tips.pack(fill="both", expand=True)
        tips.config(state="normal")
        tips.insert("1.0", "• Drag to reorder\n• F9 = Stop\n• Save often!")
        tips.config(state="disabled")
        
        # CENTER PANEL - Sequence (50%)
        center_panel = tk.Frame(main_content, bg=self.colors['bg_medium'])
        center_panel.pack(side="left", fill="both", expand=True, padx=5)
        
        seq_header = tk.Frame(center_panel, bg=self.colors['bg_light'], height=50)
        seq_header.pack(fill="x")
        seq_header.pack_propagate(False)
        
        tk.Label(seq_header, text="📝 Sequence", font=("Segoe UI", 12, "bold"),
              bg=self.colors['bg_light'], fg=self.colors['text']).pack(side="left", padx=15, pady=15)
        
        toolbar = tk.Frame(seq_header, bg=self.colors['bg_light'])
        toolbar.pack(side="right", padx=15)
        
        tk.Button(toolbar, text="💾", font=("Arial", 14), bg=self.colors['info'], fg="white",
                 relief="flat", cursor="hand2", command=self._save_sequence, padx=8, pady=2).pack(side="left", padx=2)
        tk.Button(toolbar, text="📂", font=("Arial", 14), bg=self.colors['info'], fg="white",
                 relief="flat", cursor="hand2", command=self._load_sequence, padx=8, pady=2).pack(side="left", padx=2)
        tk.Button(toolbar, text="🗑", font=("Arial", 14), bg="#c0392b", fg="white",
                 relief="flat", cursor="hand2", command=self._clear_sequence, padx=8, pady=2).pack(side="left", padx=2)
        
        canvas_frame = tk.Frame(center_panel, bg=self.colors['bg_dark'])
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Canvas + custom slim scrollbar side by side
        canvas_container = tk.Frame(canvas_frame, bg=self.colors['bg_dark'])
        canvas_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_container, bg=self.colors['bg_dark'], highlightthickness=0, bd=0,
                                  confine=True)
        self.canvas.pack(side="left", fill="both", expand=True)

        # Pretty slim scrollbar
        _sb_frame = tk.Frame(canvas_container, bg="#1a1f3a", width=6)
        _sb_frame.pack(side="right", fill="y")
        _sb_frame.pack_propagate(False)
        self._sb_thumb = tk.Frame(_sb_frame, bg="#ffd700", cursor="hand2")

        def _update_scrollbar(*_):
            try:
                top, bot = self.canvas.yview()
                h = _sb_frame.winfo_height()
                thumb_h = max(30, int((bot - top) * h))
                thumb_y = int(top * h)
                self._sb_thumb.place(x=0, y=thumb_y, width=6, height=thumb_h)
                # Hide thumb if content fits
                self._sb_thumb.place_forget() if (top == 0.0 and bot == 1.0) else None
                if top != 0.0 or bot != 1.0:
                    self._sb_thumb.place(x=0, y=thumb_y, width=6, height=thumb_h)
            except Exception:
                pass

        # Drag scrollbar thumb
        _sb_drag = {"start_y": 0, "start_top": 0.0}
        def _sb_press(e):
            _sb_drag["start_y"] = e.y_root
            _sb_drag["start_top"] = self.canvas.yview()[0]
        def _sb_drag_move(e):
            dy = e.y_root - _sb_drag["start_y"]
            h = _sb_frame.winfo_height()
            if h > 0:
                self.canvas.yview_moveto(_sb_drag["start_top"] + dy / h)
                _update_scrollbar()
        self._sb_thumb.bind("<ButtonPress-1>", _sb_press)
        self._sb_thumb.bind("<B1-Motion>", _sb_drag_move)

        self.canvas.configure(yscrollcommand=lambda *a: _update_scrollbar())
        self._update_scrollbar = _update_scrollbar

        self.inner = tk.Frame(self.canvas, bg=self.colors['bg_dark'])
        self.canvas_window_id = self.canvas.create_window((0,0), window=self.inner, anchor="nw")

        def _on_inner_configure(e):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            _update_scrollbar()
        self.inner.bind("<Configure>", _on_inner_configure)

        def update_canvas_width(event=None):
            canvas_width = self.canvas.winfo_width()
            if canvas_width > 1:
                self.canvas.itemconfig(self.canvas_window_id, width=canvas_width)
            _update_scrollbar()
        self.canvas.bind("<Configure>", update_canvas_width)
        self.root.bind("<Configure>", lambda e: self.root.after_idle(update_canvas_width))

        # Smooth mousewheel scroll — bind_all so child widgets don't eat events
        self._scroll_velocity = 0
        self._scroll_animating = False

        def _on_mousewheel(event):
            # Only scroll if mouse is over the canvas area
            cx = self.canvas.winfo_rootx()
            cy = self.canvas.winfo_rooty()
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            mx, my = event.x_root, event.y_root
            if cx <= mx <= cx + cw and cy <= my <= cy + ch:
                direction = -1 * (event.delta // 120) if event.delta else (-1 if event.num == 4 else 1)
                # One tick = exactly one action row height (50px), instant
                try:
                    bbox      = self.canvas.bbox("all")
                    content_h = (bbox[3] - bbox[1]) if bbox else 0
                    canvas_h  = self.canvas.winfo_height()
                    if content_h > canvas_h:
                        step    = direction * 50 / content_h
                        cur     = self.canvas.yview()[0]
                        new_top = max(0.0, min(1.0 - canvas_h / content_h, cur + step))
                        self.canvas.yview_moveto(new_top)
                        self._update_scrollbar()
                except Exception:
                    self.canvas.yview_scroll(direction, "units")

        # Store as instance so settings panel can restore it after leave
        self._on_mousewheel = _on_mousewheel
        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        self.root.bind_all("<Button-4>", _on_mousewheel)
        self.root.bind_all("<Button-5>", _on_mousewheel)

        # Keep no-op for compatibility with existing create_frame calls
        self._bind_mousewheel_to_children = lambda w: None

        # RIGHT PANEL - Controls (25%)
        right_panel = tk.Frame(main_content, bg=self.colors['bg_medium'], width=300)
        right_panel.pack(side="right", fill="both", padx=(5, 0))
        right_panel.pack_propagate(False)
        
        ctrl_header = tk.Frame(right_panel, bg=self.colors['bg_light'], height=50)
        ctrl_header.pack(fill="x")
        ctrl_header.pack_propagate(False)
        tk.Label(ctrl_header, text="🎮 Control", font=("Segoe UI", 12, "bold"),
              bg=self.colors['bg_light'], fg=self.colors['text']).pack(side="left", padx=15, pady=15)
        
        controls_frame = tk.Frame(right_panel, bg=self.colors['bg_medium'])
        controls_frame.pack(fill="x", padx=15, pady=15)
        
        btn_frame = tk.Frame(controls_frame, bg=self.colors['bg_medium'])
        btn_frame.pack(fill="x", pady=(0, 15))
        
        self.start_btn = tk.Button(btn_frame, text="▶️ START", font=("Segoe UI", 11, "bold"),
                                   bg=self.colors['success'], fg="white", relief="flat",
                                   cursor="hand2", command=self.start, pady=10)
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        
        self.stop_btn = tk.Button(btn_frame, text="⏹️ STOP", font=("Segoe UI", 11, "bold"),
                                  bg=self.colors['danger'], fg="white", relief="flat",
                                  cursor="hand2", state="disabled", command=self.stop, pady=10)
        self.stop_btn.pack(side="right", fill="x", expand=True, padx=(3, 0))
        
        status_frame = tk.Frame(controls_frame, bg=self.colors['bg_dark'], relief="flat")
        status_frame.pack(fill="x", pady=10, ipady=8)
        
        tk.Label(status_frame, text="📊 Status", font=("Segoe UI", 9, "bold"),
              bg=self.colors['bg_dark'], fg=self.colors['accent']).pack(pady=5)
        
        self.status_var = tk.StringVar(value="IDLE | Mode: BUY")
        tk.Label(status_frame, textvariable=self.status_var, font=("Consolas", 8),
                bg=self.colors['bg_dark'], fg=self.colors['text']).pack()
        
        log_header = tk.Frame(right_panel, bg=self.colors['bg_light'], height=40)
        log_header.pack(fill="x", pady=(15, 0))
        log_header.pack_propagate(False)
        tk.Label(log_header, text="📝 Log", font=("Segoe UI", 10, "bold"),
              bg=self.colors['bg_light'], fg=self.colors['text']).pack(side="left", padx=15, pady=10)
        
        log_frame = tk.Frame(right_panel, bg=self.colors['bg_dark'])
        log_frame.pack(fill="both", expand=True, padx=15, pady=(10, 15))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 8),
            bg=self.colors['bg_dark'], fg=self.colors['text_dim'],
            insertbackground=self.colors['text'], relief="flat", bd=0, state="disabled"
        )
        self.log_text.pack(fill="both", expand=True)

        self._sequence_page = main_content
        self._build_configs_panel()
        self._build_settings_panel()
        self._schedule_refresh()

    def _switch_tab(self, tab: str):
        # Hide all pages
        for page in (self._sequence_page, self._configs_page, self._settings_page):
            page.pack_forget()
        # Reset all buttons
        for btn in (self._tab_sequence_btn, self._tab_configs_btn, self._tab_settings_btn):
            btn.config(bg=self.colors['bg_medium'], fg=self.colors['text_dim'])
        # Show selected
        if tab == "sequence":
            self._sequence_page.pack(fill="both", expand=True)
            self._tab_sequence_btn.config(bg=self.colors['accent'], fg=self.colors['bg_dark'])
        elif tab == "configs":
            self._configs_page.pack(fill="both", expand=True)
            self._tab_configs_btn.config(bg=self.colors['accent'], fg=self.colors['bg_dark'])
        elif tab == "settings":
            self._settings_page.pack(fill="both", expand=True)
            self._tab_settings_btn.config(bg=self.colors['accent'], fg=self.colors['bg_dark'])

    def _build_settings_panel(self):
        self._settings_page = tk.Frame(self._page_container, bg=self.colors['bg_dark'])

        # ── Header ───────────────────────────────────────────────────────
        hdr = tk.Frame(self._settings_page, bg=self.colors['bg_medium'], height=50)
        hdr.pack(fill="x", pady=(0, 10))
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚙  Settings",
                 font=("Segoe UI", 11, "bold"), bg=self.colors['bg_medium'],
                 fg=self.colors['text']).pack(side="left", padx=20, pady=14)

        # ── Scrollable body ───────────────────────────────────────────────
        _s_outer = tk.Frame(self._settings_page, bg=self.colors['bg_dark'])
        _s_outer.pack(fill="both", expand=True)
        _s_canvas = tk.Canvas(_s_outer, bg=self.colors['bg_dark'], highlightthickness=0, bd=0)
        _s_sb = tk.Scrollbar(_s_outer, orient="vertical", command=_s_canvas.yview,
                              bg=self.colors['bg_medium'], troughcolor=self.colors['bg_dark'],
                              width=6, relief="flat", bd=0)
        _s_canvas.configure(yscrollcommand=_s_sb.set)
        _s_sb.pack(side="right", fill="y")
        _s_canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(_s_canvas, bg=self.colors['bg_dark'])
        _s_win = _s_canvas.create_window((0, 0), window=body, anchor="nw")
        def _s_on_configure(e):
            _s_canvas.configure(scrollregion=_s_canvas.bbox("all"))
        def _s_on_canvas_resize(e):
            _s_canvas.itemconfig(_s_win, width=e.width)
        body.bind("<Configure>", _s_on_configure)
        _s_canvas.bind("<Configure>", _s_on_canvas_resize)
        def _s_scroll(e):
            _s_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
            return "break"  # prevent event propagating to sequence canvas
        # Only bind when mouse is over settings canvas — not bind_all
        def _s_enter(e):
            _s_canvas.bind_all("<MouseWheel>", _s_scroll)
        def _s_leave(e):
            _s_canvas.unbind_all("<MouseWheel>")
            # Restore sequence canvas scroll
            try: self.root.bind_all("<MouseWheel>", self._on_mousewheel)
            except Exception: pass
        _s_canvas.bind("<Enter>", _s_enter)
        _s_canvas.bind("<Leave>", _s_leave)
        # add some padding inside
        body.configure(padx=30, pady=10)

        def section(parent, title):
            tk.Label(parent, text=title, font=("Segoe UI", 10, "bold"),
                     bg=self.colors['bg_dark'], fg=self.colors['accent']).pack(anchor="w", pady=(18, 4))
            sep = tk.Frame(parent, bg=self.colors['bg_medium'], height=1)
            sep.pack(fill="x", pady=(0, 10))

        def row(parent, label, widget_fn):
            f = tk.Frame(parent, bg=self.colors['bg_dark'])
            f.pack(fill="x", pady=4)
            tk.Label(f, text=label, font=("Segoe UI", 9), width=28,
                     bg=self.colors['bg_dark'], fg=self.colors['text'], anchor="w").pack(side="left")
            widget_fn(f)

        # ── Bot Behaviour ────────────────────────────────────────────────
        section(body, "🤖  Bot Behaviour")

        # Loop delay
        self._setting_loop_delay = tk.DoubleVar(value=0.08)
        def make_loop_delay(f):
            tk.Entry(f, textvariable=self._setting_loop_delay, width=8,
                     font=("Consolas", 10), bg=self.colors['bg_medium'],
                     fg=self.colors['text'], insertbackground=self.colors['accent'],
                     relief="flat").pack(side="left")
            tk.Label(f, text="seconds between cycles", font=("Segoe UI", 8),
                     bg=self.colors['bg_dark'], fg=self.colors['text_dim']).pack(side="left", padx=6)
        row(body, "Cycle delay (s)", make_loop_delay)

        # Auto scroll focus interval
        self._setting_focus_every = tk.IntVar(value=5)
        def make_focus(f):
            tk.Entry(f, textvariable=self._setting_focus_every, width=8,
                     font=("Consolas", 10), bg=self.colors['bg_medium'],
                     fg=self.colors['text'], insertbackground=self.colors['accent'],
                     relief="flat").pack(side="left")
            tk.Label(f, text="cycles between window re-focus", font=("Segoe UI", 8),
                     bg=self.colors['bg_dark'], fg=self.colors['text_dim']).pack(side="left", padx=6)
        row(body, "Re-focus every N cycles", make_focus)

        # Auto scroll margin
        self._setting_scroll_margin = tk.IntVar(value=60)
        def make_margin(f):
            tk.Entry(f, textvariable=self._setting_scroll_margin, width=8,
                     font=("Consolas", 10), bg=self.colors['bg_medium'],
                     fg=self.colors['text'], insertbackground=self.colors['accent'],
                     relief="flat").pack(side="left")
            tk.Label(f, text="px from edge to trigger auto-scroll", font=("Segoe UI", 8),
                     bg=self.colors['bg_dark'], fg=self.colors['text_dim']).pack(side="left", padx=6)
        row(body, "Drag auto-scroll margin", make_margin)

        self._setting_auto_gc = tk.BooleanVar(value=True)
        self._setting_gc_threshold = tk.IntVar(value=500)
        def make_auto_gc(f):
            tk.Checkbutton(f, variable=self._setting_auto_gc,
                           text="Free virtual RAM when available drops below",
                           font=("Segoe UI", 9), bg=self.colors['bg_dark'],
                           fg=self.colors['text'], selectcolor=self.colors['bg_medium'],
                           activebackground=self.colors['bg_dark'],
                           activeforeground=self.colors['text']).pack(side="left")
            tk.Entry(f, textvariable=self._setting_gc_threshold, width=5,
                     font=("Consolas", 10), bg=self.colors['bg_medium'],
                     fg=self.colors['text'], insertbackground=self.colors['accent'],
                     relief="flat").pack(side="left", padx=4)
            tk.Label(f, text="MB", font=("Segoe UI", 8),
                     bg=self.colors['bg_dark'], fg=self.colors['text_dim']).pack(side="left")
        row(body, "Virtual RAM cleanup", make_auto_gc)

        # ── OCR ──────────────────────────────────────────────────────────
        section(body, "🔍  OCR")

        self._setting_ocr_confidence = tk.DoubleVar(value=0.6)
        def make_ocr_conf(f):
            s = tk.Scale(f, variable=self._setting_ocr_confidence,
                         from_=0.1, to=1.0, resolution=0.05, orient="horizontal",
                         length=160, bg=self.colors['bg_dark'], fg=self.colors['text'],
                         highlightthickness=0, troughcolor=self.colors['bg_medium'],
                         activebackground=self.colors['accent'])
            s.pack(side="left")
            tk.Label(f, textvariable=tk.StringVar(), font=("Consolas", 9),
                     bg=self.colors['bg_dark'], fg=self.colors['text_dim']).pack(side="left", padx=6)
            def update_label(*_):
                pass
            self._setting_ocr_confidence.trace_add("write", update_label)
        row(body, "Min confidence threshold", make_ocr_conf)

        self._setting_use_gpu = tk.BooleanVar(value=_ocr_use_gpu)
        def make_gpu(f):
            chk = tk.Checkbutton(f, variable=self._setting_use_gpu, text="Use GPU (EasyOCR)",
                           font=("Segoe UI", 9), bg=self.colors['bg_dark'],
                           fg=self.colors['text'], selectcolor=self.colors['bg_medium'],
                           activebackground=self.colors['bg_dark'],
                           activeforeground=self.colors['text'])
            chk.pack(side="left")

            def _check_gpu_status():
                info = _get_ocr_gpu_status()
                if info["cuda_available"]:
                    vram_info = f"\nVRAM Total : {info['vram_total_mb']} MB\nVRAM Free  : {info['vram_free_mb']} MB"
                    gpu_name = f"\nGPU        : {info['device_name']}"
                    status_icon = "YES ✅"
                else:
                    vram_info = ""
                    gpu_name = ""
                    status_icon = "NO ❌"
                ocr_status = "✅ GPU" if info["ocr_using_gpu"] else "⚠️  CPU (GPU disabled or unavailable)"
                reader_status = "✅ Loaded" if info["reader_initialized"] else "⏳ Not yet loaded"
                msg = (
                    f"═══ GPU / CUDA Status ═══\n\n"
                    f"CUDA Available : {status_icon}"
                    f"{gpu_name}{vram_info}\n\n"
                    f"OCR Engine     : {ocr_status}\n"
                    f"Reader Status  : {reader_status}\n"
                )
                if "cuda_error" in info:
                    msg += f"\nError: {info['cuda_error']}"
                messagebox.showinfo("GPU Status", msg)

            def _apply_gpu_setting():
                global _ocr_use_gpu, reader
                new_val = self._setting_use_gpu.get()
                if new_val == _ocr_use_gpu:
                    return
                _ocr_use_gpu = new_val
                reader = None  # force reinit on next OCR call
                if new_val:
                    if _cuda_available():
                        self.log("GPU acceleration ENABLED — OCR will use GPU on next call")
                    else:
                        self.log("⚠️  GPU selected but CUDA not available — will stay on CPU")
                else:
                    self.log("GPU acceleration DISABLED — OCR will use CPU")

            chk.config(command=_apply_gpu_setting)

            tk.Button(f, text="🔍 Check GPU Status",
                      font=("Segoe UI", 8, "bold"),
                      bg=self.colors.get('info', '#1565c0'), fg="white",
                      relief="flat", cursor="hand2",
                      command=_check_gpu_status, padx=10).pack(side="left", padx=(12, 0))

        row(body, "GPU acceleration", make_gpu)

        # ── UI ───────────────────────────────────────────────────────────
        # ── Resolution Scaling ───────────────────────────────────────────
        section(body, "📹  Resolution Scaling")

        detected_w, detected_h = _detect_screen_res()
        self._setting_base_res = tk.StringVar(value=_load_base_res())
        COMMON_RES = ["1280x720", "1366x768", "1600x900", "1920x1080", "2560x1440", "3840x2160"]

        def make_res(f):
            tk.Label(f, text="Config built at:", font=("Segoe UI", 8),
                     bg=self.colors["bg_dark"], fg=self.colors["text_dim"]).pack(side="left", padx=(0,6))
            res_combo = ttk.Combobox(f, textvariable=self._setting_base_res,
                                     values=COMMON_RES, width=12, font=("Consolas", 9))
            res_combo.pack(side="left")
            tk.Label(f, text=f"  →  your screen: {detected_w}x{detected_h}", font=("Segoe UI", 8),
                     bg=self.colors["bg_dark"], fg=self.colors["accent"]).pack(side="left", padx=8)
            def apply_res(*_):
                try:
                    res_str = self._setting_base_res.get().strip()
                    bw, bh = map(int, res_str.lower().split("x"))
                    _init_scaling(bw, bh)
                    _save_base_res(res_str)
                    self.log(f"Scaling: {bw}x{bh} -> {detected_w}x{detected_h} (sx={_SCALE_X:.3f} sy={_SCALE_Y:.3f})")
                except Exception as e:
                    self.log(f"Resolution error: {e}")
            tk.Button(f, text="Apply", font=("Segoe UI", 8, "bold"),
                      bg=self.colors["accent"], fg="#0a0e27", relief="flat",
                      cursor="hand2", command=apply_res, padx=8).pack(side="left", padx=4)
            res_combo.bind("<<ComboboxSelected>>", apply_res)
        row(body, "Base resolution", make_res)

        section(body, "🖥  Interface")

        def make_force_update(f):
            tk.Button(f, text="⬆  Force Update Now", font=("Segoe UI", 9, "bold"),
                      bg="#e74c3c", fg="white", relief="flat", cursor="hand2", padx=10, pady=4,
                      command=lambda: check_for_update(force=True)).pack(side="left")
            tk.Label(f, text="re-downloads even if up to date", font=("Segoe UI", 8),
                     bg=self.colors['bg_dark'], fg=self.colors['text_dim']).pack(side="left", padx=8)
        row(body, "Force update", make_force_update)

        self._setting_log_limit = tk.IntVar(value=300)
        def make_log(f):
            tk.Entry(f, textvariable=self._setting_log_limit, width=8,
                     font=("Consolas", 10), bg=self.colors['bg_medium'],
                     fg=self.colors['text'], insertbackground=self.colors['accent'],
                     relief="flat").pack(side="left")
            tk.Label(f, text="max log lines kept", font=("Segoe UI", 8),
                     bg=self.colors['bg_dark'], fg=self.colors['text_dim']).pack(side="left", padx=6)
        row(body, "Log buffer size", make_log)

        self._setting_topmost = tk.BooleanVar(value=False)
        def make_topmost(f):
            def toggle():
                self.root.attributes("-topmost", self._setting_topmost.get())
            tk.Checkbutton(f, variable=self._setting_topmost, text="Always on top",
                           font=("Segoe UI", 9), bg=self.colors['bg_dark'],
                           fg=self.colors['text'], selectcolor=self.colors['bg_medium'],
                           activebackground=self.colors['bg_dark'],
                           activeforeground=self.colors['text'],
                           command=toggle).pack(side="left")
        row(body, "Window always on top", make_topmost)

        # ── Account ──────────────────────────────────────────────────────
        section(body, "👤  Account")

        def make_hwid_row(f):
            hwid_val = get_hwid()
            e = tk.Entry(f, font=("Consolas", 9), width=36,
                         bg=self.colors['bg_medium'], fg=self.colors['text_dim'],
                         relief="flat", state="readonly")
            e.pack(side="left")
            e.config(state="normal")
            e.insert(0, hwid_val)
            e.config(state="readonly")
            def copy_hwid():
                self.root.clipboard_clear()
                self.root.clipboard_append(hwid_val)
                self.log("HWID copied to clipboard")
            tk.Button(f, text="📋 Copy", font=("Segoe UI", 8),
                      bg=self.colors['info'], fg="white", relief="flat",
                      cursor="hand2", command=copy_hwid, padx=6).pack(side="left", padx=6)
        row(body, "Your HWID", make_hwid_row)

        def make_user_row(f):
            tk.Label(f, text=self.username, font=("Consolas", 10, "bold"),
                     bg=self.colors['bg_dark'], fg=self.colors['accent']).pack(side="left")
        row(body, "Logged in as", make_user_row)

        # ── Memory ───────────────────────────────────────────────────────
        section(body, "🧹  Memory")

        ram_row = tk.Frame(body, bg=self.colors['bg_dark'])
        ram_row.pack(fill="x", pady=4)
        self._ram_label = tk.Label(ram_row, text="RAM: calculating...", font=("Consolas", 9),
                                   bg=self.colors['bg_dark'], fg=self.colors['text_dim'])
        self._ram_label.pack(side="left")

        def do_trim():
            _trim_ram()
            self._update_ram_label()
            self.log("Manual RAM trim done")

        tk.Button(ram_row, text="🧹 Free RAM Now", font=("Segoe UI", 9),
                  bg=self.colors['bg_medium'], fg=self.colors['text'], relief="flat",
                  cursor="hand2", command=do_trim, padx=10, pady=4).pack(side="left", padx=16)

        self._update_ram_label()

        section(body, "🛠  Developer")

        self._setting_dev_mode = tk.BooleanVar(value=getattr(self, '_dev_mode', False))
        dev_row = tk.Frame(body, bg=self.colors['bg_dark'])
        dev_row.pack(fill="x", pady=4)
        tk.Checkbutton(dev_row, text="Enable Dev Mode",
                       variable=self._setting_dev_mode,
                       font=("Segoe UI", 10), bg=self.colors['bg_dark'],
                       fg=self.colors['text'], selectcolor=self.colors['bg_medium'],
                       activebackground=self.colors['bg_dark'],
                       activeforeground=self.colors['accent'],
                       cursor="hand2").pack(side="left")
        tk.Label(dev_row, text="When saving a config, asks for title, description and icon",
                 font=("Segoe UI", 8, "italic"), bg=self.colors['bg_dark'],
                 fg=self.colors['text_dim']).pack(side="left", padx=(12, 0))

        # ── Save button ───────────────────────────────────────────────────
        tk.Frame(body, bg=self.colors['bg_dark'], height=20).pack()
        tk.Button(body, text="  ✓  Save Settings  ", font=("Segoe UI", 10, "bold"),
                  bg=self.colors['success'], fg="white", relief="flat", cursor="hand2",
                  command=self._save_settings, pady=10, padx=20).pack(anchor="w")

    def _update_ram_label(self):
        try:
            import os, psutil
            proc = psutil.Process(os.getpid())
            mb = proc.memory_info().rss / 1024 / 1024
            color = "#ff5555" if mb > 1500 else "#ffdd44" if mb > 800 else "#55ff88"
            self._ram_label.config(text=f"RAM used by bot: {mb:.0f} MB", fg=color)
        except Exception:
            self._ram_label.config(text="RAM: (psutil not installed)")

    def _save_settings(self):
        try:
            global _ocr_use_gpu, reader
            self._dev_mode = self._setting_dev_mode.get() if hasattr(self, '_setting_dev_mode') else False
            mode_txt = "ON" if self._dev_mode else "OFF"
            new_gpu = self._setting_use_gpu.get() if hasattr(self, '_setting_use_gpu') else False
            if new_gpu != _ocr_use_gpu:
                _ocr_use_gpu = new_gpu
                reader = None
            gpu_txt = "GPU" if _ocr_use_gpu and _cuda_available() else ("GPU (no CUDA)" if _ocr_use_gpu else "CPU")
            self.log(f"Settings saved — cycle delay: {self._setting_loop_delay.get()}s  |  log limit: {self._setting_log_limit.get()} lines  |  dev mode: {mode_txt}  |  OCR: {gpu_txt}")
            messagebox.showinfo("Settings", "Settings saved!")
        except Exception as e:
            self.log(f"Settings error: {e}")

    def _build_configs_panel(self):
        import copy as _copy
        self._configs_page = tk.Frame(self._page_container, bg=self.colors['bg_dark'])

        # Header
        hdr = tk.Frame(self._configs_page, bg=self.colors['bg_medium'], height=50)
        hdr.pack(fill="x", pady=(0, 6))
        hdr.pack_propagate(False)
        tk.Label(hdr, text="\u26a1 Pre-made Configs  \u2014  loaded from server",
                 font=("Segoe UI", 11, "bold"), bg=self.colors['bg_medium'],
                 fg=self.colors['text']).pack(side="left", padx=20, pady=14)
        self._cfg_reload_btn = tk.Button(
            hdr, text="\U0001f504 Refresh", font=("Segoe UI", 9, "bold"),
            bg=self.colors['info'], fg="white", relief="flat", cursor="hand2",
            command=self._load_configs_from_server, padx=12
        )
        self._cfg_reload_btn.pack(side="right", padx=15, pady=10)

        # Scrollable card area
        scroll_wrap = tk.Frame(self._configs_page, bg=self.colors['bg_dark'])
        scroll_wrap.pack(fill="both", expand=True)
        self._cfg_canvas = tk.Canvas(scroll_wrap, bg=self.colors['bg_dark'], highlightthickness=0, bd=0)
        cfg_sb = ttk.Scrollbar(scroll_wrap, orient="vertical", command=self._cfg_canvas.yview)
        self._cfg_canvas.configure(yscrollcommand=cfg_sb.set)
        self._cfg_inner = tk.Frame(self._cfg_canvas, bg=self.colors['bg_dark'])
        self._cfg_canvas_win_id = self._cfg_canvas.create_window((0, 0), window=self._cfg_inner, anchor="nw")
        self._cfg_inner.bind("<Configure>", lambda e: self._cfg_canvas.configure(
            scrollregion=self._cfg_canvas.bbox("all")))
        def _cfg_resize(e):
            self._cfg_canvas.itemconfig(self._cfg_canvas_win_id, width=e.width)
        self._cfg_canvas.bind("<Configure>", _cfg_resize)
        # Scroll wheel support on configs panel
        def _cfg_scroll(e):
            self._cfg_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        def _cfg_enter(e): self._cfg_canvas.bind_all("<MouseWheel>", _cfg_scroll)
        def _cfg_leave(e):
            self._cfg_canvas.unbind_all("<MouseWheel>")
            try: self.root.bind_all("<MouseWheel>", self._on_mousewheel)
            except Exception: pass
        self._cfg_canvas.bind("<Enter>", _cfg_enter)
        self._cfg_canvas.bind("<Leave>", _cfg_leave)
        self._cfg_canvas.pack(side="left", fill="both", expand=True)
        cfg_sb.pack(side="right", fill="y")

        # Load on first build
        # Defer load so UI is fully built before hitting the server
        self.root.after(200, self._load_configs_from_server)

    def _load_configs_from_server(self):
        """Fetch configs from /configs endpoint and rebuild cards."""
        for w in self._cfg_inner.winfo_children():
            w.destroy()
        tk.Label(
            self._cfg_inner, text="\u23f3 Loading configs from server...",
            font=("Segoe UI", 11), bg=self.colors['bg_dark'], fg=self.colors['text_dim']
        ).pack(padx=20, pady=30)
        self._configs_page.update_idletasks()

        def fetch():
            try:
                data, code = api_request("GET", "/configs", params={"game": self.game_key})
                if code != 200 or not isinstance(data, list):
                    err = data.get("error", f"HTTP {code}") if isinstance(data, dict) else f"HTTP {code}"
                    self.root.after(0, lambda: self._show_configs_error(f"Server error: {err}"))
                    return
                self.root.after(0, lambda: self._render_config_cards(data))
            except Exception as e:
                self.root.after(0, lambda: self._show_configs_error(str(e)))

        import threading as _threading
        _threading.Thread(target=fetch, daemon=True).start()

    def _show_configs_error(self, msg: str):
        for w in self._cfg_inner.winfo_children():
            w.destroy()
        tk.Label(
            self._cfg_inner, text=f"\u274c {msg}",
            font=("Segoe UI", 11), bg=self.colors['bg_dark'], fg=self.colors['danger']
        ).pack(padx=20, pady=30)

    def _render_config_cards(self, configs: list):
        import copy as _copy
        from collections import OrderedDict
        for w in self._cfg_inner.winfo_children():
            w.destroy()

        if not configs:
            tk.Label(
                self._cfg_inner,
                text="\U0001f4ed No configs found on server.\nDrop .json files into the configs/ folder.",
                font=("Segoe UI", 11), bg=self.colors['bg_dark'], fg=self.colors['text_dim'],
                justify="center"
            ).pack(padx=20, pady=40)
            return

        COLS = 4

        # ── Group configs by category ────────────────────────────────────
        # Each config may have: category (str), category_desc (str)
        # Preserve insertion order; "Uncategorised" always goes last.
        categories = OrderedDict()   # cat_name -> {"desc": str, "configs": list}
        cat_descs   = {}             # collect category descriptions from configs

        for cfg in configs:
            cat  = cfg.get("category", "").strip() or "Uncategorised"
            desc = cfg.get("category_desc", "").strip()
            if cat not in categories:
                categories[cat] = {"desc": "", "configs": []}
            if desc and not categories[cat]["desc"]:
                categories[cat]["desc"] = desc
            categories[cat]["configs"].append(cfg)

        # Move "Uncategorised" to the end
        if "Uncategorised" in categories:
            categories["Uncategorised"] = categories.pop("Uncategorised")

        # ── Accent colours cycling per category ──────────────────────────
        CAT_COLORS = ["#3498db", "#9b59b6", "#e67e22", "#e74c3c",
                      "#1abc9c", "#f39c12", "#2ecc71", "#e91e63"]

        def make_load(snap, cname, cres="1920x1080", cmeta=None):
            def load():
                if self.sequence and not messagebox.askyesno(
                    "Load Config",
                    f"Replace current sequence with '{cname}'?\nContinue?"
                ):
                    return
                self.sequence = _copy.deepcopy(snap)
                _reassign_ids(self.sequence)
                self._loaded_meta = cmeta or {"name": cname, "description": "", "icon": "🎮"}
                self._scroll_to_top_next = True
                self._schedule_refresh()
                self._switch_tab("sequence")
                res_str = cres or "1920x1080"
                try:
                    bw, bh = map(int, res_str.lower().split("x"))
                    _init_scaling(bw, bh)
                    if hasattr(self, "_setting_base_res"):
                        self._setting_base_res.set(res_str)
                except Exception:
                    pass
                self.log(f"Loaded config: {cname}  | base res: {res_str}")
            return load

        # ── Render each category section ─────────────────────────────────
        for cat_idx, (cat_name, cat_data) in enumerate(categories.items()):
            accent = CAT_COLORS[cat_idx % len(CAT_COLORS)]

            # ── Category header bar ──────────────────────────────────────
            hdr_frame = tk.Frame(self._cfg_inner, bg=self.colors['bg_medium'])
            hdr_frame.pack(fill="x", padx=0, pady=(18 if cat_idx > 0 else 4, 0))

            # Coloured left stripe
            tk.Frame(hdr_frame, bg=accent, width=5).pack(side="left", fill="y")

            hdr_text = tk.Frame(hdr_frame, bg=self.colors['bg_medium'])
            hdr_text.pack(side="left", fill="both", expand=True, padx=16, pady=10)

            tk.Label(hdr_text, text=cat_name,
                     font=("Segoe UI", 13, "bold"),
                     bg=self.colors['bg_medium'], fg=accent).pack(anchor="w")

            if cat_data["desc"]:
                tk.Label(hdr_text, text=cat_data["desc"],
                         font=("Segoe UI", 9),
                         bg=self.colors['bg_medium'],
                         fg=self.colors['text_dim']).pack(anchor="w")

            # Count badge
            cnt = len(cat_data["configs"])
            tk.Label(hdr_frame, text=f"  {cnt} config{'s' if cnt != 1 else ''}  ",
                     font=("Consolas", 9), bg=accent,
                     fg="#0a0e27", padx=6, pady=2).pack(side="right", padx=12, pady=10)

            # Thin separator line below header
            tk.Frame(self._cfg_inner, bg=accent, height=1).pack(fill="x", padx=0, pady=(0, 8))

            # ── Cards grid for this category ─────────────────────────────
            grid_frame = tk.Frame(self._cfg_inner, bg=self.colors['bg_dark'])
            grid_frame.pack(fill="x", padx=8, pady=(0, 4))
            for col in range(COLS):
                grid_frame.grid_columnconfigure(col, weight=1)

            for i, cfg in enumerate(cat_data["configs"]):
                row, col = divmod(i, COLS)
                card = tk.Frame(grid_frame, bg=self.colors['bg_medium'], relief="flat", bd=0)
                card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

                # Top accent stripe matching category colour
                tk.Frame(card, bg=accent, height=5).pack(fill="x")

                body = tk.Frame(card, bg=self.colors['bg_medium'])
                body.pack(fill="both", expand=True, padx=16, pady=12)

                tk.Label(body, text=cfg.get("emoji", "\u2699\ufe0f"), font=("Arial", 28),
                         bg=self.colors['bg_medium'], fg=accent).pack(anchor="w")
                tk.Label(body, text=cfg.get("name", "Unnamed"), font=("Segoe UI", 11, "bold"),
                         bg=self.colors['bg_medium'], fg=self.colors['text']).pack(anchor="w", pady=(4, 2))
                tk.Label(body, text=cfg.get("desc", ""), font=("Segoe UI", 9),
                         bg=self.colors['bg_medium'], fg=self.colors['text_dim'],
                         wraplength=210, justify="left").pack(anchor="w")
                steps = len(cfg.get("sequence", []))
                tk.Label(body, text=f"{steps} steps  \u2022  {cfg.get('filename', '')}",
                         font=("Consolas", 8), bg=self.colors['bg_medium'],
                         fg=self.colors['text_dim']).pack(anchor="w", pady=(6, 10))

                cfg_meta = {
                    "name": cfg.get("name", "Config"),
                    "description": cfg.get("description", ""),
                    "icon": cfg.get("icon", "🎮")
                }
                tk.Button(body, text="\u2b07  Load Config", font=("Segoe UI", 10, "bold"),
                          bg=self.colors['success'], fg="white", relief="flat", cursor="hand2",
                          command=make_load(_copy.deepcopy(cfg.get("sequence", [])),
                                            cfg.get("name", "Config"),
                                            cfg.get("base_res", "1920x1080"),
                                            cfg_meta),
                          pady=8).pack(fill="x")


    def log(self, msg: str):
        """Optimized logging to prevent memory leaks."""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        try:
            self.root.after(0, lambda m=msg: self._ov_log_write(m))
        except: pass
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, line)
        
        # Keep only the last 300 lines to save memory
        num_lines = int(self.log_text.index('end-1c').split('.')[0])
        limit = self._setting_log_limit.get() if hasattr(self, "_setting_log_limit") else 300
        if num_lines > limit:
            self.log_text.delete("1.0", f"{num_lines-limit}.0")
            
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        #print(line.strip())

        if self.log_cleanup_counter % 500 == 0:
            self.log_text.delete("1.0", tk.END)
            gc.collect()
    
    def log_image(self, img_np, label="OCR region"):
        """Insert a thumbnail into the log text widget and overlay."""
        try:
            from PIL import Image as _PilImg, ImageTk as _ImageTk

            # Convert numpy to PIL
            pil_img = _PilImg.fromarray(img_np)

            # Scale to max 280px wide for log, 200px for overlay
            def _make_tk_img(pil, max_w):
                w, h = pil.size
                if w == 0 or h == 0:
                    return None
                if w > max_w:
                    scale = max_w / w
                    pil = pil.resize((max_w, max(1, int(h * scale))), _PilImg.LANCZOS)
                # Gold border
                bordered = _PilImg.new("RGB", (pil.width + 4, pil.height + 4), (255, 215, 0))
                bordered.paste(pil, (2, 2))
                return _ImageTk.PhotoImage(bordered)

            tk_img_log = _make_tk_img(pil_img, 280)
            tk_img_ov  = _make_tk_img(pil_img, 200)

            if not hasattr(self, "_log_images"):
                self._log_images = []
            if tk_img_log: self._log_images.append(tk_img_log)
            if tk_img_ov:  self._log_images.append(tk_img_ov)
            if len(self._log_images) > 20:
                self._log_images = self._log_images[-20:]

            ts = time.strftime("%H:%M:%S")

            # ── Main log window ──────────────────────────────────
            if tk_img_log:
                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, f"[{ts}] \U0001f4f7 {label}:\n")
                self.log_text.image_create(tk.END, image=tk_img_log, padx=4, pady=2)
                self.log_text.insert(tk.END, "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")

            # ── Overlay log ──────────────────────────────────────
            if tk_img_ov:
                try:
                    ov_txt = getattr(self, "_ov_log", None)
                    if ov_txt and self._run_overlay and self._run_overlay.winfo_exists():
                        ov_txt.config(state="normal")
                        ov_txt.insert(tk.END, f"[{ts}] \U0001f4f7 {label}:\n", "ts")
                        ov_txt.image_create(tk.END, image=tk_img_ov, padx=2, pady=2)
                        ov_txt.insert(tk.END, "\n")
                        ov_txt.see(tk.END)
                        ov_txt.config(state="disabled")
                        self._ov_log_lines += 2
                except Exception:
                    pass

        except Exception as e:
            self.log(f"  [screenshot display failed: {e}]")

    def update_status(self):
        self.status_var.set(f"{'RUNNING' if self.running else 'STOPPED'}")
        self.status_lbl.config(text=f"User: {self.username} • F9 = Stop")

    def _focus_game_window_for_action(self):
        # In notepad mode, always use the stored hwnd
        if getattr(self, '_notepad_mode', False):
            hwnd = getattr(self, '_target_hwnd', None)
            if hwnd and win32gui.IsWindow(hwnd):
                focus_window_advanced(hwnd)
                time.sleep(0.3)
                return True
            # Notepad was closed — try to find it again
            wins = _find_notepad_window()
            if wins:
                self._target_hwnd = wins[0]['hwnd']
                focus_window_advanced(self._target_hwnd)
                time.sleep(0.3)
                return True
            messagebox.showwarning("Notepad Closed", "Notepad was closed. Reopen it to continue.")
            return False

        cfg = self.game_cfg
        # ── Try game first ────────────────────────────────────────────────
        wins = find_game_by_pid_or_exe(self.game_key)
        if not wins:
            wins = find_game_window_enhanced(cfg["window_title"])

        if wins:
            hwnd = wins[0]['hwnd']
            self.log(f"Focusing: {wins[0]['title']} ({cfg['name']})")
            if focus_window_advanced(hwnd):
                time.sleep(0.5)
                self.log(f"✓ {cfg['name']} window focused")
            else:
                self.log(f"⚠ Could not focus {cfg['name']} window — continuing anyway (run bot as admin if this causes issues)")
            return True

        # ── Game not found — auto-fall back to Notepad if it's open ──────
        notepad_wins = _find_notepad_window()
        if notepad_wins:
            self._notepad_mode = True
            self._target_hwnd = notepad_wins[0]['hwnd']
            focus_window_advanced(self._target_hwnd)
            time.sleep(0.3)
            self.log(f"📝 Notepad detected — switching to Notepad mode ({notepad_wins[0]['title']})")
            return True

        messagebox.showwarning("Game Not Found",
            f"Cannot find {cfg['name']} running.\n"
            "Start the game, or open Notepad to test the bot.")
        return False

    def _handle_click(self, act):
        p = act["params"]
        x = _sx(int(p.get("x", 960)))
        y = _sy(int(p.get("y", 540)))
        btn = self.CLICK_BUTTON[act["type"]]
        self.log(f"{act['type']} → ({x},{y})")
        InputMethods.send_click(x, y, btn)
        time.sleep(random.uniform(0.27, 0.35))

    def _handle_right_click_menu_item(self, act):
        """Right-click a fixed position, then OCR-find the menu item in a small
        box around the click point and left-click it. Using a small region keeps
        OCR fast and accurate."""
        p = act["params"]
        x = _sx(int(p.get("x", 960)))
        y = _sy(int(p.get("y", 540)))
        menu_text = p.get("menu_text", "").strip()
        wait_ms   = float(p.get("wait_ms", 300))
        timeout   = float(p.get("timeout", 3.0))

        self.log(f"Right Click → ({x},{y})  then find menu item '{menu_text}'")
        InputMethods.send_click(x, y, "right")

        # Wait for context menu to render
        time.sleep(max(wait_ms / 1000.0, 0.15) + random.uniform(0.03, 0.07))

        if not menu_text:
            self.log("Right Click Menu: no menu_text set, skipping OCR click")
            return

        # OCR in a small 420x380 box around the click point — menus always open
        # near the cursor so no need to scan the full screen.
        sw, sh = _detect_screen_res()
        BOX_W, BOX_H = 420, 380
        rx = max(0, min(x, sw - BOX_W))
        ry = max(0, min(y, sh - BOX_H))
        menu_region = (rx, ry, BOX_W, BOX_H)

        clean_target = menu_text.replace(" ", "").lower()
        found = False
        start_time = time.time()

        while self.running and (time.time() - start_time) < timeout and not found:
            try:
                img, img_np = _screenshot_clean(region=menu_region)
                img.close()

                results = _safe_readtext(
                    img_np,
                    detail=1,
                    paragraph=False,
                    min_size=8,
                    text_threshold=0.55,
                    low_text=0.3,
                    contrast_ths=0.05,
                )
                del img_np
                _ocr_clear_cache()

                for detection in results:
                    bbox, text, conf = detection
                    clean_text = text.strip().replace(" ", "").lower()
                    sim = similarity(clean_target, clean_text)
                    substring_match = clean_target in clean_text

                    if (sim >= 0.75 or substring_match) and conf >= 0.40:
                        (top_left, top_right, bottom_right, bottom_left) = bbox
                        cx = int((top_left[0] + bottom_right[0]) / 2) + menu_region[0]
                        cy = int((top_left[1] + bottom_right[1]) / 2) + menu_region[1]

                        InputMethods.send_click(cx, cy, "left")
                        self.log(f"Menu item '{text}' (conf {conf:.2f}, sim {sim:.2%}) → left click at ({cx},{cy})")
                        found = True
                        break

                del results

            except Exception as e:
                self.log(f"Right Click Menu OCR error: {e}")

            if not found:
                time.sleep(0.08)

        if not found:
            self.log(f"Right Click Menu: '{menu_text}' not found within {timeout:.1f}s")
        _ocr_clear_cache()

    def _handle_move_and_scroll(self, act):
        p = act.get("params", {})
        
        x = _sx(int(p.get("x", 960)))
        y = _sy(int(p.get("y", 540)))
        direction = p.get("direction", "down").lower()
        steps = int(p.get("steps", 4))              # number of scroll notches
        delay_ms = float(p.get("delay_ms", 35))     # delay between each scroll tick
        
        if direction not in ("up", "down"):
            self.log("Invalid scroll direction - defaulting to down")
            direction = "down"

        scroll_delta = steps if direction == "up" else -steps

        self.log(f"Move to ({x}, {y}) → Scroll {direction.upper()} ×{steps} (delay {delay_ms}ms)")

        try:
            # Move mouse to position (instant move - Windows API)
            win32api.SetCursorPos((x, y))
            time.sleep(0.08 + random.uniform(0, 0.04))  # small realistic pause

            # Scroll step by step
            for _ in range(abs(steps)):
                if not self.running:
                    return
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_WHEEL,
                    0, 0,
                    scroll_delta,  # positive = scroll up, negative = scroll down
                    0
                )
                time.sleep(delay_ms / 1000.0 + random.uniform(-0.008, 0.012))

        except Exception as e:
            self.log(f"Move & Scroll error: {e}")

    def _handle_ocr_click(self, act):
        p = act["params"]
        base = p.get("text", "")
        txt = base
        
        if not txt:
            self.log("OCR: missing text")
            return

        region = tuple(_sr(p.get("region", DEFAULT_REGION)))
        self.log(f"OCR Click: searching for '{txt}'")

        clean_target = txt.strip().replace(" ", "").lower()
        found = False
        start_time = time.time()
        TIMEOUT = 3.0

        attempt = 0

        while self.running and (time.time() - start_time) < TIMEOUT and not found:
            attempt += 1

            try:
                # Use 'with' or explicitly close
                img, img_np = _screenshot_clean(region=region)
                img.close() # Explicit close

                h, w = img_np.shape[:2]
                if max(h, w) > 900:
                    scale = 900 / max(h, w)
                    img_np = cv2.resize(img_np, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                else:
                    scale = 1.0

                results = _safe_readtext(
                    img_np,
                    detail=1,
                    paragraph=False,
                    min_size=10,
                    text_threshold=0.65,
                    low_text=0.3,
                    contrast_ths=0.05,
                )
                
                # Cleanup heavy numpy array immediately
                del img_np
                _ocr_clear_cache()

                for detection in results:  # noqa
                    bbox, text, conf = detection
                    clean_text = text.strip().replace(" ", "").lower()

                    sim = similarity(clean_target, clean_text)
                    substring_match = clean_target in clean_text

                    if (sim >= 0.78 or substring_match) and conf >= 0.45:
                        (top_left, top_right, bottom_right, bottom_left) = bbox
                        cx = int((top_left[0] + bottom_right[0]) / 2)
                        cy = int((top_left[1] + bottom_right[1]) / 2)

                        if scale != 1.0:
                            cx = int(cx / scale)
                            cy = int(cy / scale)

                        cx += region[0]
                        cy += region[1]

                        btn = "right" if "Right" in act["type"] else "left"
                        InputMethods.send_click(cx, cy, btn)

                        self.log(f"Found '{text}' (conf {conf:.2f}, sim {sim:.2%}) → {btn} click")
                        found = True
                        break

                del results  # free tensor refs immediately

            except Exception as e:
                self.log(f"OCR error: {e}")

            if not found:
                time.sleep(0.08)

        if not found:
            self.log(f"OCR Click timeout (1s) - '{txt}' not found")
        _ocr_clear_cache()

    def _handle_image_click(self, act):
        p = act.get("params", {})
        image_data = p.get("image_data")
        image_path = p.get("image_path", "")
        image_name = p.get("image_name") or (os.path.basename(image_path) if image_path else "screenshot")
        
        # Wait for UI to fully render before searching (default 200ms)
        wait_ms = float(p.get("wait_ms", 200))
        if wait_ms > 0:
            time.sleep(wait_ms / 1000.0)
        
        if image_data:
            try:
                img_bytes = base64.b64decode(image_data)
                arr = np.frombuffer(img_bytes, np.uint8)
                template = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if template is None:
                    raise ValueError("Failed to decode template image data")
            except Exception as e:
                self.log(f"Image Click: unable to decode template ({e})")
                return
        elif image_path and os.path.exists(image_path):
            try:
                template = cv2.imread(image_path, cv2.IMREAD_COLOR)
                if template is None:
                    raise ValueError("Failed to load template image")
            except Exception as e:
                self.log(f"Image Click: unable to load image '{image_path}' ({e})")
                return
        else:
            self.log("Image Click: no image template provided")
            return

        if template.shape[2] == 4:
            template = cv2.cvtColor(template, cv2.COLOR_BGRA2BGR)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        region = tuple(_sr(p.get("region", DEFAULT_REGION)))
        self.log(f"Image Click: searching for '{image_name}'")

        found = False
        start_time = time.time()
        TIMEOUT = 5.0
        threshold = 0.72

        while self.running and (time.time() - start_time) < TIMEOUT and not found:
            try:
                img, img_np = _screenshot_clean(region=region)
                img.close()
                target_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                if template_gray.shape[0] > target_gray.shape[0] or template_gray.shape[1] > target_gray.shape[1]:
                    raise ValueError("Template image is larger than the selected search region")
                res = cv2.matchTemplate(target_gray, template_gray, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                if max_val >= threshold:
                    top_left = max_loc
                    h, w = template_gray.shape[:2]
                    cx = int(region[0] + top_left[0] + w / 2)
                    cy = int(region[1] + top_left[1] + h / 2)
                    InputMethods.send_click(cx, cy, "left")
                    self.log(f"Found image '{image_name}' (score {max_val:.2f}) → click")
                    found = True
                del img_np
            except Exception as e:
                self.log(f"Image Click error: {e}")
            if not found:
                time.sleep(0.18)

        if not found:
            self.log(f"Image Click timeout - '{image_name}' not found")

    def _pick_comma_mode(self, current="decimal"):
        """Show dialog to pick comma interpretation mode. Returns 'decimal' or 'thousands'."""
        result = [current]
        win = Toplevel(self.root)
        win.title("Comma Mode  (default: decimal)")
        win.configure(bg="#0a0e27")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        win.geometry("420x200")

        tk.Label(win, text="How should comma ( , ) be read?",
                 font=("Consolas", 11, "bold"), bg="#0a0e27", fg="#ffd700").pack(pady=(18,8), padx=20)

        var = tk.StringVar(value=current if current else "decimal")
        f = tk.Frame(win, bg="#0a0e27")
        f.pack(padx=30, pady=4, fill="x")
        for val, label in [("decimal",   "Decimal point  →  20,540 = 20.540"),
                            ("thousands", "Thousands sep  →  20,540 = 20540")]:
            tk.Radiobutton(f, text=label, variable=var, value=val,
                           font=("Consolas", 10), bg="#0a0e27", fg="#fff",
                           selectcolor="#1a1f3a", activebackground="#0a0e27",
                           activeforeground="#ffd700").pack(anchor="w", pady=3)

        def confirm():
            result[0] = var.get()
            win.destroy()
        tk.Button(win, text="OK", font=("Consolas", 11, "bold"),
                  bg="#2ecc71", fg="white", relief="flat",
                  command=confirm).pack(pady=14, ipadx=20, ipady=4)
        win.update_idletasks()
        self._autosize_dialog(win, min_w=380, min_h=180)
        win.wait_window()
        return result[0]

    def _handle_if_ocr_ge(self, act):
        p = act["params"]
        min_val = float(p.get("min_value", 0))
        region = tuple(_sr(p.get("region", DEFAULT_REGION)))
        comma_mode = p.get("comma_mode", "decimal")  # "decimal" or "thousands"

        self.log(f"━━━ [OCR-IF ≥] ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log(f"  Region     : {region}")
        self.log(f"  Target     : number ≥ {min_val:,.3f}")
        self.log(f"  Comma mode : {'decimal  (20,540 = 20.540)' if comma_mode == 'decimal' else 'thousands (20,540 = 20540)'}") 

        candidates = []
        attempt = 0
        start_time = time.time()
        MAX_DURATION = 12.0
        self._last_ocr_stable = None

        # --- IMPROVED EXTRACTION LOGIC ---
        def extract_number_from_text(text):
            """Extract number respecting comma_mode:
              decimal   → comma is decimal point: 20,540 = 20.540
              thousands → comma is thousands sep:  20,540 = 20540
            """
            raw = text.strip()
            if not raw:
                return None, None

            # Fix common OCR char confusions
            clean = raw.replace("O", "0").replace("o", "0")
            clean = clean.replace("l", "1").replace("I", "1").replace("|", "1")
            clean = clean.replace("S", "5").replace("s", "5")
            clean = clean.replace("Z", "2").replace("z", "2")
            clean = clean.replace("B", "8").replace(" ", "")

            # Strip non-numeric prefix/suffix
            clean = re.sub(r"^[^\d,\.]+|[^\d,\.]+$", "", clean)
            if not clean:
                return None, None

            if comma_mode == "decimal":
                # Comma = decimal, dot = thousands separator
                # 20,540  -> 20.540   |  1.000,50 -> 1000.50
                normalized = clean.replace(".", "").replace(",", ".")
            else:
                # Comma = thousands, dot = decimal
                # 20,540  -> 20540    |  20,540.75 -> 20540.75
                normalized = clean.replace(",", "")

            try:
                num = float(normalized)
                return num, f"parsed-{comma_mode}"
            except ValueError:
                pass

            digits_only = re.sub(r"\D", "", clean)
            if digits_only:
                try:
                    return float(digits_only), "digits-only"
                except ValueError:
                    pass

            return None, None

        # -----------------------------------------

        while self.running and (time.time() - start_time) < MAX_DURATION:
            attempt += 1
            elapsed = time.time() - start_time
            self.log(f"  [Attempt #{attempt}] elapsed={elapsed:.1f}s")

            try:
                # 1. Capture (window is hidden during this call if overlapping)
                img, img_np = _screenshot_clean(region=region)
                img.close()
                try:
                    _thumb = img_np.copy()
                    self.root.after(0, lambda arr=_thumb: self.log_image(arr, f"OCR≥ region {region}"))
                except Exception:
                    pass

                # 2. Preprocessing
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                del img_np

                _, thresh1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                thresh2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                                cv2.THRESH_BINARY, 11, 2)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                enhanced = clahe.apply(gray)

                # 3. OCR — 2 passes
                all_results = []
                for img_source, src_name in [(gray, "original"), (enhanced, "enhanced")]:
                    res = _safe_readtext(img_source, detail=1, paragraph=False, min_size=8,
                                         text_threshold=0.6, low_text=0.3)
                    self.log(f"    [{src_name}] raw detections: {[r[1] for r in res]}")
                    all_results.extend([(r, src_name) for r in res])
                    del res
                    _ocr_clear_cache()

                del gray, thresh1, thresh2, enhanced

                # 4. Process
                for (detection, preprocess_type) in all_results:
                    bbox, text, conf = detection
                    num, source = extract_number_from_text(text)
                    if num is None:
                        self.log(f"    ✘ '{text}' (conf={conf:.2f}) → could not parse")
                        continue
                    if not (0.001 <= num <= 999_999_999):
                        self.log(f"    ✘ '{text}' → {num} out of range")
                        continue
                    self.log(f"    ✔ '{text}' → {num:,.3f}  conf={conf*100:.0f}%  src={source}  pre={preprocess_type}")
                    candidates.append((num, conf*100, text.strip(), source, preprocess_type))

            except Exception as e:
                self.log(f"  ✘ EasyOCR error: {str(e)}")

            # 5. Early exit
            if candidates:
                best_conf = max(c[1] for c in candidates)
                self.log(f"  Candidates so far: {len(candidates)} | best conf={best_conf:.0f}%")
                if best_conf >= 65:
                    self.log(f"  Confidence threshold met — stopping early")
                    break

                current_best = max(candidates, key=lambda x: (-x[1], -len(x[2])))
                curr_num = current_best[0]
                if self._last_ocr_stable is not None:
                    last_num, last_raw = self._last_ocr_stable
                    if abs(last_num - curr_num) < 0.001:
                        self.log(f"  Stable value {curr_num:,.3f} confirmed — stopping")
                        break
                self._last_ocr_stable = (curr_num, current_best[2])
            else:
                self.log(f"  No candidates yet — retrying...")

            time.sleep(0.05)

            if attempt % 2 == 0:
                _ocr_clear_cache()

        if not candidates:
            self.log(f"  ✘ No valid number found after {attempt} attempts → running FALSE branch")
            for sub in p.get("false_branch", []):
                self._execute_action(sub)
            return

        # Sort: confidence → proximity to min_val → length
        candidates.sort(key=lambda x: (-x[1], abs(x[0] - min_val), -len(x[2])))
        best_num, best_conf, best_raw, best_source, best_preprocess = candidates[0]

        self.log(f"  ── Result ──────────────────────────────────")
        self.log(f"  Raw text : '{best_raw}'")
        self.log(f"  Parsed   : {best_num:,.3f}")
        self.log(f"  Conf     : {best_conf:.0f}%  |  src={best_source}  pre={best_preprocess}")
        self.log(f"  Threshold: {best_num:,.3f} {'≥' if best_num >= min_val else '<'} {min_val:,.3f}")

        if best_num >= min_val:
            self.log(f"  ✔ TRUE  → running true branch ({len(p.get('true_branch',[]))} actions)")
            for sub in p.get("true_branch", []):
                self._execute_action(sub)
        else:
            self.log(f"  ✘ FALSE → running false branch ({len(p.get('false_branch',[]))} actions)")
            for sub in p.get("false_branch", []):
                self._execute_action(sub)

        self.log(f"━━━ [OCR-IF ≥ done] ━━━━━━━━━━━━━━━━━━━━━━━━")
        _ocr_clear_cache()

    def _handle_if_ocr_text_exists(self, act):
        p = act["params"]
        target = str(p.get("text", "")).lower().strip()
        if not target:
            for sub in p.get("false_branch", []):
                self._execute_action(sub)
            return

        region = tuple(_sr(p.get("region", DEFAULT_REGION)))
        found = False
        start_time = time.time()
        
        try:
            img, img_np = _screenshot_clean(region=region)
            img.close()
            try:
                _thumb = img_np.copy()
                self.root.after(0, lambda arr=_thumb: self.log_image(arr, f"OCR text region {region}"))
            except Exception:
                pass

            # Grayscale only — avoids running OCR 4x which leaks vRAM
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            del img_np

            results = _safe_readtext(gray, detail=1, paragraph=False,
                                      text_threshold=0.6, low_text=0.3)
            del gray
            _ocr_clear_cache()

            target_norm = "".join(c for c in target if c.isalnum())
            for _, text, conf in results:
                if conf < 0.35: continue
                normalized = "".join(c for c in text.lower() if c.isalnum())
                if target_norm and target_norm in normalized:
                    found = True
                    break
            del results
        except Exception as e:
            self.log(f"OCR error: {e}")
        finally:
            _ocr_clear_cache()

        self.log(f"━━━ [OCR-TEXT EXISTS] ━━━━━━━━━━━━━━━━━━━━━━")
        self.log(f"  Target : '{target}'  |  Region: {region}")
        self.log(f"  Result : {'✔ FOUND' if found else '✘ NOT FOUND'} → running {'TRUE' if found else 'FALSE'} branch")
        branch = "true_branch" if found else "false_branch"
        for sub in p.get(branch, []):
            self._execute_action(sub)
        self.log(f"━━━ [OCR-TEXT EXISTS done] ━━━━━━━━━━━━━━━━━━")

    def _handle_if_ocr_any_text(self, act):
        """Branch true if ANY real text/numbers are detected in region."""
        p = act["params"]
        region = tuple(_sr(p.get("region", DEFAULT_REGION)))
        # Wait for UI to fully render before screenshotting
        wait_ms = float(p.get("wait_ms", 300))
        if wait_ms > 0:
            time.sleep(wait_ms / 1000.0)

        found = False
        img = None
        img_np = None
        results = None
        try:
            img = pyautogui.screenshot(region=region)
            img_np = np.array(img)
            img.close()
            img = None

            # Show thumbnail in log
            try:
                _thumb = img_np.copy()
                self.root.after(0, lambda arr=_thumb: self.log_image(arr, f"OCR any text {region}"))
            except Exception:
                pass

            # Resize if too large — keep it under 900px max side
            h, w = img_np.shape[:2]
            if max(h, w) > 900:
                scale = 900 / max(h, w)
                img_np = cv2.resize(img_np, None, fx=scale, fy=scale,
                                    interpolation=cv2.INTER_AREA)

            # Pass RGB directly — do NOT binarize, it creates false positives
            results = _safe_readtext(img_np, detail=1, paragraph=False,
                                     min_size=10,
                                     text_threshold=0.75,
                                     low_text=0.5,
                                     contrast_ths=0.1)
            del img_np
            img_np = None

            # Filter: confidence >= 0.7, length >= 2, at least 2 alphanumeric chars
            real_results = []
            for (_, text, conf) in results:
                text = text.strip()
                if conf >= 0.7 and len(text) >= 2:
                    if sum(1 for c in text if c.isalnum()) >= 2:
                        real_results.append(f"{text}({conf:.2f})")

            found = len(real_results) > 0
            del results
            results = None
            gc.collect(0)

            self.log(f"━━━ [OCR ANY TEXT] ━━━━━━━━━━━━━━━━━━━━━━━━")
            self.log(f"  Region : {region}  wait={wait_ms:.0f}ms")
            if found:
                self.log(f"  ✔ Found: {real_results}")
                self.log(f"  → TRUE branch")
            else:
                self.log(f"  ✘ No text detected → FALSE branch")
        except Exception as e:
            self.log(f"  ✘ OCR any text error: {e}")
            found = False
        finally:
            # Always clean up to prevent memory leaks
            if img is not None:
                try: img.close()
                except: pass
            if img_np is not None:
                del img_np
            if results is not None:
                del results
            _ocr_clear_cache()
            gc.collect(0)

        branch = "true_branch" if found else "false_branch"
        for sub in p.get(branch, []):
            self._execute_action(sub)
        self.log(f"━━━ [OCR ANY TEXT done] ━━━━━━━━━━━━━━━━━━━━")

    def _handle_read_ocr_number(self, act):
        """Read a number from screen region and store it in a variable."""
        p = act["params"]
        var_name    = p.get("var", "ocr_value")
        region      = tuple(_sr(p.get("region", DEFAULT_REGION)))
        comma_mode  = p.get("comma_mode", "decimal")

        self.log(f"━━━ [READ OCR NUMBER → '{var_name}'] ━━━━━━━━━━━━━━━━━━")
        self.log(f"  Region     : {region}")
        self.log(f"  Comma mode : {comma_mode}")

        def _extract(text):
            raw = text.strip()
            raw = raw.replace("O","0").replace("o","0").replace("l","1")
            raw = raw.replace("I","1").replace("|","1").replace("S","5")
            raw = raw.replace("Z","2").replace("B","8").replace(" ","")
            raw = re.sub(r"^[^\d,\.]+|[^\d,\.]+$", "", raw)
            if not raw:
                return None
            if comma_mode == "decimal":
                normalized = raw.replace(".", "").replace(",", ".")
            else:
                normalized = raw.replace(",", "")
            try:
                return float(normalized)
            except ValueError:
                digits = re.sub(r"\D", "", raw)
                return float(digits) if digits else None

        candidates = []
        start_time = time.time()
        MAX_DURATION = 8.0
        attempt = 0

        while self.running and (time.time() - start_time) < MAX_DURATION:
            attempt += 1
            try:
                img, img_np = _screenshot_clean(region=region)
                img.close()
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                del img_np
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                enhanced = clahe.apply(gray)
                all_results = []
                for src in [gray, enhanced]:
                    res = _safe_readtext(src, detail=1, paragraph=False,
                                        min_size=8, text_threshold=0.6, low_text=0.3)
                    all_results.extend(res)
                    del res
                del gray, enhanced
                _ocr_clear_cache()
                for (_, text, conf) in all_results:
                    num = _extract(text)
                    if num is not None and 0.001 <= num <= 999_999_999:
                        candidates.append((num, conf, text.strip()))
                        self.log(f"  ✔ '{text}' → {num:,.3f}  conf={conf*100:.0f}%")
                del all_results
            except Exception as e:
                self.log(f"  ✘ OCR error: {e}")

            if candidates:
                best = max(candidates, key=lambda x: x[1])
                if best[1] >= 0.65:
                    break
            time.sleep(0.4)

        if not candidates:
            self.log(f"  ✘ No number found — '{var_name}' unchanged")
            self.log(f"━━━ [READ OCR NUMBER done] ━━━━━━━━━━━━━━━━━━━━━━━━")
            return

        best_num, best_conf, best_raw = max(candidates, key=lambda x: x[1])
        old_val = self.variables.get(var_name, None)
        self.variables[var_name] = best_num
        # Store previous value for "If Variable Changed" check
        self.variables[f"__prev_{var_name}"] = old_val if old_val is not None else best_num
        self.log(f"  Result : '{best_raw}' → {best_num:,.3f}  (conf {best_conf*100:.0f}%)")
        self.log(f"  Stored : {var_name} = {best_num:,.3f}  (prev={old_val})")
        self.log(f"━━━ [READ OCR NUMBER done] ━━━━━━━━━━━━━━━━━━━━━━━━")
        _ocr_clear_cache()

    def _handle_if_variable_changed(self, act):
        """Branch true if a variable's value differs from when it was last read."""
        p = act["params"]
        var_name = p.get("var", "ocr_value")
        tolerance = float(p.get("tolerance", 0.0))

        current  = self.variables.get(var_name, None)
        previous = self.variables.get(f"__prev_{var_name}", None)

        self.log(f"━━━ [IF VARIABLE CHANGED '{var_name}'] ━━━━━━━━━━━━━━━━")
        self.log(f"  Previous : {previous}")
        self.log(f"  Current  : {current}")
        self.log(f"  Tolerance: ±{tolerance}")

        if current is None or previous is None:
            changed = False
            self.log(f"  ✘ No previous value — FALSE")
        else:
            try:
                diff = abs(float(current) - float(previous))
                changed = diff > tolerance
                self.log(f"  Diff     : {diff:.3f}  → {'CHANGED ✔' if changed else 'SAME ✘'}")
            except Exception:
                changed = current != previous
                self.log(f"  String compare → {'CHANGED ✔' if changed else 'SAME ✘'}")

        branch = "true_branch" if changed else "false_branch"
        self.log(f"  → {'TRUE' if changed else 'FALSE'} branch ({len(p.get(branch,[]))} actions)")
        for sub in p.get(branch, []):
            self._execute_action(sub)
        self.log(f"━━━ [IF VARIABLE CHANGED done] ━━━━━━━━━━━━━━━━━━━━━━")

    def _handle_clear_write(self, act):
        p = act["params"]
        x = _sx(int(p.get("x", 960)))
        y = _sy(int(p.get("y", 540)))
        price = p.get("price", "1200")
        self.log(f"Clear & write '{price}' @ ({x},{y})")
        InputMethods.clear_and_type(x, y, str(price))

    def _handle_clear_write_text(self, act):
        p = act["params"]
        x = _sx(int(p.get("x", 960)))
        y = _sy(int(p.get("y", 540)))
        text = p.get("text", "")
        self.log(f"Clear & write text \"{text}\" @ ({x},{y})")
        InputMethods.clear_and_type(x, y, text)

    def _handle_wait(self, act):
        ms = float(act["params"].get("milliseconds", 1200))
        self.log(f"Wait {ms:.0f} ms")
        deadline = time.time() + ms / 1000.0
        while time.time() < deadline:
            if not self.running or self._stop_event.is_set():
                return
            time.sleep(min(0.05, deadline - time.time()))

    def _handle_wait_random(self, act):
        p = act["params"]
        min_ms = p.get("min_ms", 800)
        max_ms = p.get("max_ms", 1600)
        ms = random.uniform(min_ms, max_ms)
        self.log(f"Wait random {ms:.0f} ms")
        deadline = time.time() + ms / 1000.0
        while time.time() < deadline:
            if not self.running or self._stop_event.is_set():
                return
            time.sleep(min(0.05, deadline - time.time()))

    def _handle_wait_for_text(self, act):
        """Block sequence until target text appears in region, or timeout."""
        p = act["params"]
        target = str(p.get("text", "")).strip()
        if not target:
            self.log("Wait for Text: no text set — skipping")
            return

        region   = tuple(_sr(p.get("region", DEFAULT_REGION)))
        timeout  = float(p.get("timeout_ms", 10000)) / 1000.0
        interval = float(p.get("interval_ms", 300))  / 1000.0
        target_norm = "".join(c for c in target.lower() if c.isalnum())

        self.log(f"⏳ Wait for Text: '{target}'  timeout={timeout:.1f}s  rgn {region}")
        start = time.time()
        found = False

        while self.running and (time.time() - start) < timeout:
            try:
                img, img_np = _screenshot_clean(region=region)
                img.close()
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                del img_np
                results = _safe_readtext(gray, detail=1, paragraph=False,
                                         text_threshold=0.6, low_text=0.3)
                del gray
                _ocr_clear_cache()
                for _, text, conf in results:
                    if conf < 0.35:
                        continue
                    norm = "".join(c for c in text.lower() if c.isalnum())
                    if target_norm and target_norm in norm:
                        elapsed = time.time() - start
                        self.log(f"✔ Found '{text}' after {elapsed:.2f}s — continuing")
                        found = True
                        break
                del results
            except Exception as e:
                self.log(f"Wait for Text OCR error: {e}")
            if found:
                break
            time.sleep(interval)

        if not found:
            self.log(f"✘ Wait for Text timeout ({timeout:.1f}s) — '{target}' never appeared")


    def _handle_counter_reset(self, act):
        name = act["params"].get("name", "default")
        self.variables[name] = 0
        self.log(f"Reset '{name}' → 0")

    def _handle_counter_add(self, act):
        name = act["params"].get("name", "default")
        self.variables[name] = self.variables.get(name, 0) + 1
        self.log(f"'{name}' → {self.variables[name]}")

    def _handle_counter_sub(self, act):
        name = act["params"].get("name", "default")
        self.variables[name] = self.variables.get(name, 0) - 1
        self.log(f"'{name}' → {self.variables[name]}")

    def _handle_set_variable(self, act):
        p = act["params"]
        name = p.get("name", "var")
        value = p.get("value", 0)
        self.variables[name] = value
        self.log(f"Set {name} = {value}")

    def _handle_declare_variable(self, act):
        p = act["params"]
        name = p.get("name", "var")
        var_type = p.get("type", "int")
        value = p.get("value", 0)
        try:
            if var_type == "int":
                self.variables[name] = int(value)
            elif var_type == "float":
                self.variables[name] = float(value)
            elif var_type == "bool":
                if isinstance(value, bool):
                    self.variables[name] = value
                elif str(value).lower() in ("true", "1", "yes"):
                    self.variables[name] = True
                else:
                    self.variables[name] = False
            else:
                self.variables[name] = str(value)
            self.log(f"◆ Declare {var_type} {name} = {self.variables[name]}")
        except Exception as e:
            self.log(f"ERROR: Failed to declare {name}: {e}")

    def _handle_add_to_variable(self, act):
        p = act["params"]
        name = p.get("name", "var")
        amount = p.get("amount", 1)
        self.variables[name] = self.variables.get(name, 0) + amount
        self.log(f"Add {amount} to {name} → {self.variables[name]}")

    def _handle_subtract_variable(self, act):
        p = act["params"]
        name = p.get("name", "var")
        amount = p.get("amount", 1)
        self.variables[name] = self.variables.get(name, 0) - amount
        self.log(f"Subtract {amount} from {name} → {self.variables[name]}")

    def _handle_multiply_variable(self, act):
        p = act["params"]
        name = p.get("name", "var")
        amount = p.get("amount", 2)
        self.variables[name] = self.variables.get(name, 0) * amount
        self.log(f"Multiply {name} by {amount} → {self.variables[name]}")

    def _handle_divide_variable(self, act):
        p = act["params"]
        name = p.get("name", "var")
        amount = p.get("amount", 2)
        if amount != 0:
            self.variables[name] = self.variables.get(name, 0) / amount
            self.log(f"Divide {name} by {amount} → {self.variables[name]}")
        else:
            self.log(f"ERROR: Division by zero for {name}")

    def _handle_modulo_variable(self, act):
        p = act["params"]
        name = p.get("name", "var")
        amount = p.get("amount", 2)
        if amount != 0:
            self.variables[name] = self.variables.get(name, 0) % amount
            self.log(f"Modulo {name} by {amount} → {self.variables[name]}")
        else:
            self.log(f"ERROR: Modulo by zero for {name}")

    def _handle_increment_variable(self, act):
        name = act["params"].get("name", "var")
        if name in self.variables and isinstance(self.variables[name], (int, float)):
            self.variables[name] += 1
            self.log(f"Increment '{name}' → {self.variables[name]}")
        else:
            self.log(f"Cannot increment: '{name}' not numeric")

    def _handle_decrement_variable(self, act):
        name = act["params"].get("name", "var")
        if name in self.variables and isinstance(self.variables[name], (int, float)):
            self.variables[name] -= 1
            self.log(f"Decrement '{name}' → {self.variables[name]}")
        else:
            self.log(f"Cannot decrement: '{name}' not numeric")

    def _handle_toggle_bool(self, act):
        name = act["params"].get("name", "var")
        if name in self.variables and isinstance(self.variables[name], bool):
            self.variables[name] = not self.variables[name]
            self.log(f"Toggle '{name}' → {self.variables[name]}")
        else:
            self.log(f"Cannot toggle: '{name}' not boolean")

    def _handle_set_bool_true(self, act):
        name = act["params"].get("name", "var")
        if name in self.variables and isinstance(self.variables[name], bool):
            self.variables[name] = True
            self.log(f"Set '{name}' → True")
        else:
            self.log(f"Cannot set: '{name}' not boolean")

    def _handle_set_bool_false(self, act):
        name = act["params"].get("name", "var")
        if name in self.variables and isinstance(self.variables[name], bool):
            self.variables[name] = False
            self.log(f"Set '{name}' → False")
        else:
            self.log(f"Cannot set: '{name}' not boolean")

    def _handle_append_string(self, act):
        name = act["params"].get("name", "var")
        text = act["params"].get("text", "")
        if name in self.variables and isinstance(self.variables[name], str):
            self.variables[name] += text
            self.log(f"Append '{name}' → {self.variables[name]}")
        else:
            self.log(f"Cannot append: '{name}' not string")

    def _handle_reset_variable(self, act):
        name = act["params"].get("name", "var")
        if name in self.variables:
            val = self.variables[name]
            if isinstance(val, int):
                self.variables[name] = 0
            elif isinstance(val, float):
                self.variables[name] = 0.0
            elif isinstance(val, bool):
                self.variables[name] = False
            elif isinstance(val, str):
                self.variables[name] = ""
            self.log(f"Reset '{name}' → {self.variables[name]}")

    def _handle_delete_variable(self, act):
        name = act["params"].get("name", "var")
        if name in self.variables:
            del self.variables[name]
            self.log(f"Deleted variable '{name}'")

    def _handle_break_loop(self, act):
        self.log("↩ Break Loop")
        raise _BreakLoop()

    def _handle_continue_loop(self, act):
        self.log("↻ Continue Loop")
        raise _ContinueLoop()

    def _handle_comment(self, act):
        comment = act["params"].get("text", "")
        self.log(f"// {comment}")

    def _handle_loop_start(self, act):
        times = max(1, act["params"].get("times", 5))
        body = act["params"].get("body", [])
        self.log(f"LOOP ×{times}")
        for _ in range(times):
            if not self.running or self._stop_event.is_set():
                break
            try:
                for sub in body:
                    if not self.running or self._stop_event.is_set():
                        return
                    self._execute_action(sub)
            except _BreakLoop:
                break
            except _ContinueLoop:
                continue

    def _handle_loop_while(self, act):
        p = act["params"]
        var_name = p.get("var", "var")
        thresh = p.get("threshold", 0)
        operator = p.get("operator", ">")
        body = p.get("body", [])
        self.log(f"LOOP WHILE {var_name} {operator} {thresh}")
        while self.running and not self._stop_event.is_set():
            val = self.variables.get(var_name, 0)
            condition = False
            if operator == ">":
                condition = val > thresh
            elif operator == "<":
                condition = val < thresh
            elif operator == "==":
                condition = val == thresh
            elif operator == "!=":
                condition = val != thresh
            if not condition:
                break
            try:
                for sub in body:
                    if not self.running or self._stop_event.is_set():
                        return
                    self._execute_action(sub)
            except _BreakLoop:
                break
            except _ContinueLoop:
                continue

    def _handle_loop_for(self, act):
        var_name = act["params"].get("var", "i")
        start = act["params"].get("start", 0)
        end = act["params"].get("end", 10)
        body = act["params"].get("body", [])
        self.log(f"FOR {var_name} = {start} TO {end}")
        for i in range(start, end + 1):
            if not self.running or self._stop_event.is_set():
                break
            self.variables[var_name] = i
            try:
                for sub in body:
                    if not self.running or self._stop_event.is_set():
                        return
                    self._execute_action(sub)
            except _BreakLoop:
                break
            except _ContinueLoop:
                continue

    def _handle_if_variable_gt(self, act):
        p = act["params"]
        var_name = p.get("var", "var")
        thresh = p.get("threshold", 0)
        val = self.variables.get(var_name, 0)
        self.log(f"{var_name} = {val} > {thresh} ?")
        if val > thresh:
            for sub in p.get("true_branch", []):
                self._execute_action(sub)
        else:
            for sub in p.get("false_branch", []):
                self._execute_action(sub)

    def _handle_if_variable_lt(self, act):
        p = act["params"]
        var_name = p.get("var", "var")
        thresh = p.get("threshold", 0)
        val = self.variables.get(var_name, 0)
        self.log(f"{var_name} = {val} < {thresh} ?")
        if val < thresh:
            for sub in p.get("true_branch", []):
                self._execute_action(sub)
        else:
            for sub in p.get("false_branch", []):
                self._execute_action(sub)

    def _handle_if_variable_eq(self, act):
        p = act["params"]
        var_name = p.get("var", "var")
        thresh = p.get("threshold", 0)
        val = self.variables.get(var_name, 0)
        self.log(f"{var_name} = {val} == {thresh} ?")
        if val == thresh:
            for sub in p.get("true_branch", []):
                self._execute_action(sub)
        else:
            for sub in p.get("false_branch", []):
                self._execute_action(sub)

    def _handle_if_variable_ne(self, act):
        p = act["params"]
        var_name = p.get("var", "var")
        thresh = p.get("threshold", 0)
        val = self.variables.get(var_name, 0)
        self.log(f"{var_name} = {val} != {thresh} ?")
        if val != thresh:
            for sub in p.get("true_branch", []):
                self._execute_action(sub)
        else:
            for sub in p.get("false_branch", []):
                self._execute_action(sub)

    def _handle_if_bool_true(self, act):
        p = act["params"]
        var_name = p.get("var", "bool_var")
        val = self.variables.get(var_name, False)
        self.log(f"IF {var_name} == true ?")
        if val:
            for sub in p.get("true_branch", []):
                self._execute_action(sub)
        else:
            for sub in p.get("false_branch", []):
                self._execute_action(sub)

    def _handle_if_bool_false(self, act):
        p = act["params"]
        var_name = p.get("var", "bool_var")
        val = self.variables.get(var_name, False)
        self.log(f"IF {var_name} == false ?")
        if not val:
            for sub in p.get("true_branch", []):
                self._execute_action(sub)
        else:
            for sub in p.get("false_branch", []):
                self._execute_action(sub)

    def _handle_if_variable_exists(self, act):
        name = act["params"].get("var", "var")
        true_branch = act["params"].get("true_branch", [])
        false_branch = act["params"].get("false_branch", [])
        if name in self.variables:
            self.log(f"IF EXISTS '{name}' → TRUE")
            for sub in true_branch:
                self._execute_action(sub)
        else:
            self.log(f"IF EXISTS '{name}' → FALSE")
            for sub in false_branch:
                self._execute_action(sub)

    def _handle_if_image_exists(self, act):
        p = act["params"]
        image_data = p.get("image_data")
        image_path = p.get("image_path", "")
        image_name = p.get("image_name") or (os.path.basename(image_path) if image_path else "screenshot")
        region = tuple(_sr(p.get("region", DEFAULT_REGION)))
        self.log(f"━━━ [IF IMAGE EXISTS] ━━━━━━━━━━━━━━━━━━━")
        self.log(f"  Image : {image_name}")
        self.log(f"  Region: {region}")

        found = False
        template = None
        if image_data:
            try:
                img_bytes = base64.b64decode(image_data)
                arr = np.frombuffer(img_bytes, np.uint8)
                template = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if template is None:
                    raise ValueError("Failed to decode template image data")
            except Exception as e:
                self.log(f"  ✘ Image decode error: {e}")
        elif image_path and os.path.exists(image_path):
            try:
                template = cv2.imread(image_path, cv2.IMREAD_COLOR)
                if template is None:
                    raise ValueError("Failed to load template image")
            except Exception as e:
                self.log(f"  ✘ Image load error: {e}")
        else:
            self.log(f"  ✘ Image missing")

        if template is not None:
            try:
                if template.shape[2] == 4:
                    template = cv2.cvtColor(template, cv2.COLOR_BGRA2BGR)
                template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

                img, img_np = _screenshot_clean(region=region)
                img.close()
                target_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                del img_np

                if template_gray.shape[0] <= target_gray.shape[0] and template_gray.shape[1] <= target_gray.shape[1]:
                    res = cv2.matchTemplate(target_gray, template_gray, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    self.log(f"  Match score: {max_val:.3f}")
                    if max_val >= 0.70:
                        found = True
                        self.log(f"  ✔ Image found")
                    else:
                        self.log(f"  ✘ Image not found")
                else:
                    self.log("  ✘ Template larger than search region")
            except Exception as e:
                self.log(f"  ✘ Image match error: {e}")

        branch = "true_branch" if found else "false_branch"
        self.log(f"  → running {'TRUE' if found else 'FALSE'} branch")
        for sub in p.get(branch, []):
            self._execute_action(sub)

    def _handle_else(self, act):
        body = act["params"].get("body", [])
        self.log("ELSE branch")
        for sub in body:
            self._execute_action(sub)

    def _handle_else_if(self, act):
        var_name = act["params"].get("var", "var")
        operator = act["params"].get("operator", "==")
        thresh = act["params"].get("threshold", 0)
        true_branch = act["params"].get("true_branch", [])
        false_branch = act["params"].get("false_branch", [])
        val = self.variables.get(var_name, 0)
        condition = False
        if operator == ">":
            condition = val > thresh
        elif operator == "<":
            condition = val < thresh
        elif operator == "==":
            condition = val == thresh
        elif operator == "!=":
            condition = val != thresh
        if condition:
            self.log(f"ELSE IF {var_name} {operator} {thresh} → TRUE")
            for sub in true_branch:
                self._execute_action(sub)
        else:
            self.log(f"ELSE IF {var_name} {operator} {thresh} → FALSE")
            for sub in false_branch:
                self._execute_action(sub)

    def _handle_switch_case(self, act):
        var_name = act["params"].get("var", "var")
        cases = act["params"].get("cases", [])
        default = act["params"].get("default", [])
        val = self.variables.get(var_name, 0)
        matched = False
        for case in cases:
            case_val = case.get("value", 0)
            if val == case_val:
                self.log(f"SWITCH '{var_name}' = {val} (CASE {case_val})")
                for sub in case.get("body", []):
                    self._execute_action(sub)
                matched = True
                break
        if not matched:
            self.log(f"SWITCH '{var_name}' = {val} (DEFAULT)")
            for sub in default:
                self._execute_action(sub)

    def _handle_return(self, act):
        self.log("⏹ Return / End")
        raise _ReturnEnd()

    def _handle_stop_sequence(self, act):
        self.log("🛑 Stop Sequence")
        raise _StopSequence()

    def _handle_type_text(self, act):
        p = act["params"]
        text = p.get("text", "")
        self.log(f"Type: '{text}'")
        InputMethods.type_text(text)

    def _handle_press_key(self, act):
        p = act["params"]
        key = p.get("key", "enter").lower()
        self.log(f"Press key: {key}")
        keyboard.press(key)
        time.sleep(0.1)

    def _handle_press_release(self, act):
        p = act["params"]
        key = p.get("key", "enter").lower()
        self.log(f"Press & Release: {key}")
        keyboard.press_and_release(key)
        time.sleep(0.1)

    def _handle_screenshot(self, act):
        p = act["params"]
        filename = p.get("filename", "screenshot.png")
        region = tuple(_sr(p.get("region", DEFAULT_REGION)))
        self.log(f"Screenshot → {filename}")
        try:
            img = pyautogui.screenshot(region=region)
            img.save(filename)
            img.close()
        except Exception as e:
            self.log(f"Screenshot error: {e}")

    def _handle_increment_loop(self, act):
        name = act["params"].get("counter", "loop_counter")
        self.variables[name] = self.variables.get(name, 0) + 1
        self.log(f"Loop counter '{name}' → {self.variables[name]}")

    def _execute_action(self, act):
        if not self.running or self._stop_event.is_set():
            return
        handler = self.ACTION_HANDLERS.get(act["type"])
        if handler:
            handler(act)
        else:
            self.log(f"Unknown action: {act['type']}")
    
        # Add cleanup
        self.log_cleanup_counter += 1
        self.iteration_count += 1
    
        if self.log_cleanup_counter >= 500:
            try:
                self.log_text.config(state="normal")
                self.log_text.delete("1.0", tk.END)
                self.log_text.config(state="disabled")
                self.log("═══ LOGS CLEARED ═══")
                self.log_cleanup_counter = 0
            except:
                pass
            gc.collect()
    
        if self.iteration_count % 100 == 0:
            gc.collect()

    def _get_declared_variables(self, var_type=None):
        result = []
        def scan(actions):
            for act in actions:
                act_type = act.get("type", "")
                if act_type == "Declare Variable (int/float/bool/string)":
                    p = act.get("params", {})
                    v_type = p.get("type", "")
                    v_name = p.get("name", "")
                    if v_name and (var_type is None or v_type == var_type):
                        result.append(v_name)
                for key in ["body", "true_branch", "false_branch"]:
                    if key in act.get("params", {}):
                        scan(act["params"][key])
        scan(self.sequence)
        return result

    def _show_var_selection(self, title="Select Variable", var_type=None):
        vars_list = self._get_declared_variables(var_type)
        if not vars_list:
            messagebox.showwarning("No Variables", f"Declare a variable first")
            return None
        sel_win = Toplevel(self.root)
        sel_win.title(title)
        sel_win.transient(self.root)
        sel_win.configure(bg="#0a0e27")
        sel_win.grab_set()
        selected = [None]
        
        main_frame = tk.Frame(sel_win, bg="#0a0e27")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        main_frame.grid_rowconfigure(1, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        tk.Label(main_frame, text="Select variable:", font=("Consolas", 12, "bold"), bg="#0a0e27", fg="#ffd700").grid(row=0, column=0, pady=(0,10))
        listbox = tk.Listbox(main_frame, height=12, font=("Consolas", 11), bg="#1a1f3a", fg="#fff", selectmode="single")
        for v in vars_list:
            listbox.insert(tk.END, v)
        listbox.grid(row=1, column=0, sticky="nsew", pady=(0,15))
        
        btn_frame = tk.Frame(main_frame, bg="#0a0e27")
        btn_frame.grid(row=2, column=0, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)
        
        def ok():
            if listbox.curselection():
                selected[0] = listbox.get(listbox.curselection())
                sel_win.destroy()
        def cancel():
            sel_win.destroy()
        tk.Button(btn_frame, text="Confirm", command=ok, font=("Consolas", 11, "bold"), bg="#2ecc71", fg="white", relief="flat", padx=30, pady=8).grid(row=0, column=0, sticky="ew", padx=(0,5))
        tk.Button(btn_frame, text="Cancel", command=cancel, font=("Consolas", 11, "bold"), bg="#e74c3c", fg="white", relief="flat", padx=30, pady=8).grid(row=0, column=1, sticky="ew", padx=(5,0))
        self._autosize_dialog(sel_win, min_w=360, min_h=280)
        sel_win.wait_window()
        return selected[0]

    def _set_target_and_show_menu(self, target_list, menu_type):
        self.target_list = target_list
        if menu_type == "logic":
            self._add_logic()
        else:
            self._add_execution()

    def _add_logic(self):
        typ = self.logic_combo.get()
        self._add_selected_action(typ)

    def _add_execution(self):
        typ = self.exec_combo.get()
        self._add_selected_action(typ)

    def _add_selected_action(self, typ):
        params = {}
        # ... (Params logic same as original, just condensed for brevity here) ...
        # [Full param logic kept intact]
        if typ == "Loop Start (repeat X times)":
            cnt = simpledialog.askinteger("Loop", "Repeat how many times?", initialvalue=5, minvalue=1)
            if cnt is None: return
            params["times"] = cnt
            params["body"] = []

        elif typ == "Move Mouse & Scroll":
            pos = self._pick_position()
            if pos is None:
                return
            direction = simpledialog.askstring(
                "Scroll Direction",
                "Scroll direction (up / down):",
                initialvalue="down"
            )
            if direction is None:
                return
            direction = direction.strip().lower()
            if direction not in ("up", "down"):
                messagebox.showwarning("Invalid", "Please enter 'up' or 'down'")
                return

            steps = simpledialog.askinteger(
                "Scroll Amount",
                "How many scroll steps/notches?",
                initialvalue=4,
                minvalue=1,
                maxvalue=30
            )
            if steps is None:
                return

            delay_ms = simpledialog.askinteger(
                "Delay between scrolls",
                "Milliseconds between each scroll tick",
                initialvalue=35,
                minvalue=10,
                maxvalue=200
            )
            if delay_ms is None:
                return

            params["x"] = pos[0]
            params["y"] = pos[1]
            params["direction"] = direction
            params["steps"] = steps
            params["delay_ms"] = delay_ms

        elif typ == "If OCR any text (branch)":
            wait_ms = simpledialog.askfloat("UI Wait", "Wait before screenshot (ms):\n0 = instant, 300 = default, 500+ = slow UI",
                                             initialvalue=300, minvalue=0, maxvalue=5000)
            if wait_ms is None: wait_ms = 300
            region = self._pick_region()
            if region is None:
                region = list(DEFAULT_REGION)
            params["region"] = region
            params["wait_ms"] = wait_ms
            params["true_branch"] = []
            params["false_branch"] = []

        elif typ == "If OCR text exists (branch)":
            text = simpledialog.askstring("OCR Text", "Text to search:")
            if not text:
                return
            region = self._pick_region()
            if region is None:
                region = list(DEFAULT_REGION)
            params["text"] = text
            params["region"] = region
            params["true_branch"] = []
            params["false_branch"] = []

        elif typ == "Wait for Text (OCR)":
            text = simpledialog.askstring("Wait for Text", "Text to wait for:")
            if not text:
                return
            timeout_ms = simpledialog.askfloat(
                "Timeout", "Max wait time (ms):\ne.g. 10000 = 10 seconds",
                initialvalue=10000, minvalue=500, maxvalue=9999999)
            if timeout_ms is None:
                timeout_ms = 10000
            interval_ms = simpledialog.askfloat(
                "Check Interval", "How often to check (ms):\ne.g. 300 = every 300ms",
                initialvalue=300, minvalue=50, maxvalue=9999999)
            if interval_ms is None:
                interval_ms = 300
            region = self._pick_region()
            if region is None:
                region = list(DEFAULT_REGION)
            params["text"]        = text
            params["region"]      = region
            params["timeout_ms"]  = timeout_ms
            params["interval_ms"] = interval_ms

        elif typ == "Loop While (var condition)":
            var = self._show_var_selection("Loop While Variable")
            if var is None: return
            op = simpledialog.askstring("Operator", "Operator (> < == !=):", initialvalue=">")
            thresh = simpledialog.askfloat("Threshold", "Compare to:", initialvalue=10)
            if op is None or thresh is None: return
            params["var"] = var
            params["operator"] = op.strip()
            params["threshold"] = thresh
            params["body"] = []
        elif typ == "If OCR number ≥ X (branch)":
            min_value = simpledialog.askfloat("Minimum Value", "If number ≥ this value → true", initialvalue=1500.0)
            if min_value is None: return
            comma_mode = self._pick_comma_mode("decimal")
            region = self._pick_region()
            if region is None: region = list(DEFAULT_REGION)
            params["min_value"] = min_value
            params["comma_mode"] = comma_mode
            params["region"] = region
            params["true_branch"] = []
            params["false_branch"] = []
        elif typ in ("If Variable > X (branch)", "If Variable < X (branch)", "If Variable == X (branch)", "If Variable != X (branch)"):
            var = self._show_var_selection("If Variable")
            if var is None: return
            thresh = simpledialog.askfloat("Threshold", "Value:", initialvalue=5)
            if thresh is None: return
            params["var"] = var
            params["threshold"] = thresh
            params["true_branch"] = []
            params["false_branch"] = []
        elif typ in ("If Bool True (branch)", "If Bool False (branch)"):
            var = self._show_var_selection("Bool Variable", "bool")
            if var is None: return
            params["var"] = var
            params["true_branch"] = []
            params["false_branch"] = []
        elif typ == "Declare Variable (int/float/bool/string)":
            name = simpledialog.askstring("Declare", "Variable name:", initialvalue="myVar")
            if name is None: return
            type_win = Toplevel(self.root)
            type_win.title("Select Type")
            type_win.configure(bg="#0a0e27")
            type_win.transient(self.root)
            type_win.grab_set()
            
            main_frame = tk.Frame(type_win, bg="#0a0e27")
            main_frame.pack(fill="both", expand=True, padx=40, pady=20)
            main_frame.grid_columnconfigure(0, weight=1)
            
            tk.Label(main_frame, text="Select Variable Type:", font=("Consolas", 12, "bold"),
                     bg="#0a0e27", fg="#ffd700").pack(pady=(0,15))
            var_type = tk.StringVar(value="int")
            for t in ["int", "float", "bool", "string"]:
                tk.Radiobutton(main_frame, text=t, variable=var_type, value=t,
                               font=("Consolas", 11), bg="#0a0e27", fg="#fff",
                               selectcolor="#1a1f3a").pack(anchor="w", pady=5)
            def confirm():
                type_win.destroy()
            tk.Button(main_frame, text="OK", font=("Consolas", 11, "bold"),
                      bg="#2ecc71", fg="white", relief="flat", command=confirm).pack(pady=(15,0), ipady=5, fill="x")
            self._autosize_dialog(type_win, min_w=260, min_h=220)
            type_win.wait_window()
            selected_type = var_type.get()
            if selected_type == "bool":
                bool_win = Toplevel(self.root)
                bool_win.title("Set Value")
                bool_win.configure(bg="#0a0e27")
                bool_win.transient(self.root)
                bool_win.grab_set()
                
                main_frame_bool = tk.Frame(bool_win, bg="#0a0e27")
                main_frame_bool.pack(fill="both", expand=True, padx=40, pady=20)
                main_frame_bool.grid_columnconfigure(0, weight=1)
                
                tk.Label(main_frame_bool, text="Initial Value:", font=("Consolas", 12, "bold"),
                         bg="#0a0e27", fg="#ffd700").pack(pady=(0,15))
                bool_val = tk.StringVar(value="true")
                tk.Radiobutton(main_frame_bool, text="True", variable=bool_val, value="true",
                               font=("Consolas", 11), bg="#0a0e27", fg="#fff",
                               selectcolor="#1a1f3a").pack(anchor="w", pady=5)
                tk.Radiobutton(main_frame_bool, text="False", variable=bool_val, value="false",
                               font=("Consolas", 11), bg="#0a0e27", fg="#fff",
                               selectcolor="#1a1f3a").pack(anchor="w", pady=5)
                def confirm_bool():
                    bool_win.destroy()
                tk.Button(main_frame_bool, text="OK", font=("Consolas", 11, "bold"),
                          bg="#2ecc71", fg="white", relief="flat", command=confirm_bool).pack(pady=(10,0), ipady=5, fill="x")
                self._autosize_dialog(bool_win, min_w=240, min_h=180)
                bool_win.wait_window()
                value = bool_val.get() == "true"
            else:
                if selected_type == "int":
                    value = simpledialog.askinteger("Value", f"Initial value ({selected_type}):", initialvalue=0)
                elif selected_type == "float":
                    value = simpledialog.askfloat("Value", f"Initial value ({selected_type}):", initialvalue=0.0)
                else:
                    value = simpledialog.askstring("Value", f"Initial value ({selected_type}):", initialvalue="")
                if value is None: return
            params["name"] = name.strip()
            params["type"] = selected_type
            params["value"] = value
        elif typ == "Set Variable":
            name = self._show_var_selection("Set Variable")
            if name is None: return
            value = simpledialog.askfloat("Value", "Set to:", initialvalue=0)
            if value is None: return
            params["name"] = name
            params["value"] = value
        elif typ in ("Add To Variable", "Subtract From Variable", "Multiply Variable", "Divide Variable", "Modulo Variable"):
            name = self._show_var_selection(typ)
            if name is None: return
            amount = simpledialog.askfloat("Amount", "Value:", initialvalue=1)
            if amount is None: return
            params["name"] = name
            params["amount"] = amount
        elif typ in ("Increment Variable", "Decrement Variable", "Toggle Bool (True ↔ False)", "Set Bool To True", "Set Bool To False", "Reset Variable", "Delete Variable"):
            name = self._show_var_selection(typ.split()[0])
            if name is None: return
            params["name"] = name
        elif typ == "Append String":
            name = self._show_var_selection("Append String", "string")
            if name is None: return
            text = simpledialog.askstring("Text", "Append:", initialvalue="")
            if text is None: return
            params["name"] = name
            params["text"] = text
        elif typ == "Comment":
            text = simpledialog.askstring("Comment", "Comment text:")
            if text is None: return
            params["text"] = text
        elif typ == "Wait Random (min-max ms)":
            min_ms = simpledialog.askinteger("Min", "Min ms:", initialvalue=800)
            max_ms = simpledialog.askinteger("Max", "Max ms:", initialvalue=1600)
            if min_ms is None or max_ms is None: return
            params["min_ms"] = min_ms
            params["max_ms"] = max_ms
        elif typ in ("Counter: Reset", "Counter: Add 1", "Counter: Subtract 1"):
            name = simpledialog.askstring("Counter", "Name:", initialvalue="count")
            if name is None: return
            params["name"] = name.strip() or "default"
        elif typ == "Type Text":
            text = simpledialog.askstring("Text", "Type:", initialvalue="hello")
            if text is None: return
            params["text"] = text
        elif typ in ("Press Key", "Press & Release"):
            key = simpledialog.askstring("Key", "Key name:", initialvalue="enter")
            if key is None: return
            params["key"] = key.strip().lower()
        elif typ == "Screenshot & Save":
            filename = simpledialog.askstring("Save As", "Filename:", initialvalue="screenshot.png")
            if filename is None: return
            region = self._pick_region()
            if region is None: region = list(DEFAULT_REGION)
            params["filename"] = filename.strip()
            params["region"] = region
        elif typ == "If Image Exists (branch)":
            messagebox.showinfo("Capture Template", "Select the region containing the image template to search for.")
            template_region = self._pick_region()
            if template_region is None:
                return
            image_data = _screenshot_to_base64(template_region)
            region = self._pick_region()
            if region is None:
                region = list(DEFAULT_REGION)
            params["image_data"] = image_data
            params["image_name"] = f"screenshot {template_region[2]}x{template_region[3]}"
            params["region"] = region
            params["true_branch"] = []
            params["false_branch"] = []
        elif typ == "Increment Loop Counter":
            name = simpledialog.askstring("Counter", "Counter name:", initialvalue="loop_counter")
            if name is None: return
            params["counter"] = name.strip()
        elif typ == "Read OCR Number → Variable":
            name = simpledialog.askstring("Variable Name",
                "Store the number in variable named:", initialvalue="ocr_value")
            if not name: return
            comma_mode = self._pick_comma_mode("decimal")
            region = self._pick_region()
            if region is None: region = list(DEFAULT_REGION)
            params["var"] = name.strip()
            params["comma_mode"] = comma_mode
            params["region"] = region
        elif typ == "If Variable Changed (branch)":
            var = self._show_var_selection("Select Variable to Check")
            if var is None: return
            tolerance = simpledialog.askfloat("Tolerance",
                "Min change to count as 'changed'\n(0 = any change, 10 = must differ by >10):",
                initialvalue=0.0, minvalue=0.0)
            if tolerance is None: tolerance = 0.0
            params["var"] = var
            params["tolerance"] = tolerance
            params["true_branch"] = []
            params["false_branch"] = []
        elif typ == "Find Image & Click":
            messagebox.showinfo("Capture Template", "Select the region containing the image template to click.")
            template_region = self._pick_region()
            if template_region is None:
                return
            image_data = _screenshot_to_base64(template_region)
            region = self._pick_region()
            if region is None:
                region = list(DEFAULT_REGION)
            params["image_data"] = image_data
            params["image_name"] = f"screenshot {template_region[2]}x{template_region[3]}"
            params["region"] = region
        elif typ in ("OCR Click (Search Text)", "OCR Right Click (Search Text)"):
            txt = simpledialog.askstring("Text", "Find & click:", initialvalue="Buy")
            if not txt: return
            region = self._pick_region()
            if region is None: region = list(DEFAULT_REGION)
            params["text"] = txt.strip()
            params["region"] = region
        elif typ == "Clear & Write Text":
            pos = self._pick_position()
            if pos is None: return
            text = simpledialog.askstring("Text", "Text to type:", initialvalue="")
            if text is None: return
            params["x"], params["y"] = pos
            params["text"] = text
        elif typ == "Clear & Write Price":
            pos = self._pick_position()
            if pos is None: return
            price = simpledialog.askstring("Price", "Value:", initialvalue="1200")
            if price is None: return
            params["x"], params["y"] = pos
            params["price"] = price.strip()
        elif typ in ("Single Click", "Double Click", "Right Click"):
            pos = self._pick_position()
            if pos is None: return
            params["x"], params["y"] = pos
        elif typ == "Right Click → Click Menu Item":
            pos = self._pick_position()
            if pos is None: return
            params["x"], params["y"] = pos
            menu_text = simpledialog.askstring(
                "Menu Item Text",
                "Text of the menu item to click\n(OCR will find it wherever the menu appears):",
                initialvalue="Inspect"
            )
            if not menu_text: return
            params["menu_text"] = menu_text.strip()
            wait_ms = simpledialog.askfloat(
                "Menu Open Delay",
                "Wait (ms) after right-click for menu to appear:",
                initialvalue=300.0, minvalue=50.0, maxvalue=2000.0
            )
            params["wait_ms"] = wait_ms if wait_ms is not None else 300.0
        elif typ == "Manual Coordinates":
            x = simpledialog.askinteger("X", "X:", initialvalue=960)
            y = simpledialog.askinteger("Y", "Y:", initialvalue=540)
            if x is None or y is None: return
            params["x"], params["y"] = x, y
        elif typ == "Wait (milliseconds)":
            ms = simpledialog.askfloat("Delay", "ms", initialvalue=1200.0)
            if ms is None: return
            params["milliseconds"] = ms
        elif typ == "Loop For (var from X to Y)":
            var = self._show_var_selection("Loop For Variable")
            if var is None: return
            start_val = simpledialog.askinteger("Start", "From:", initialvalue=0)
            if start_val is None: return
            end_val = simpledialog.askinteger("End", "To:", initialvalue=10)
            if end_val is None: return
            params["var"] = var
            params["start"] = start_val
            params["end"] = end_val
            params["body"] = []
        elif typ == "Else (branch)":
            params["body"] = []
        elif typ == "Else If (branch)":
            var = self._show_var_selection("Else If Variable")
            if var is None: return
            op = simpledialog.askstring("Operator", "Operator (> < == !=):", initialvalue="==")
            thresh = simpledialog.askfloat("Threshold", "Compare to:", initialvalue=0)
            if op is None or thresh is None: return
            params["var"] = var
            params["operator"] = op.strip()
            params["threshold"] = thresh
            params["true_branch"] = []
            params["false_branch"] = []
        elif typ == "Switch Case (multiple branches)":
            var = self._show_var_selection("Switch Variable")
            if var is None: return
            num_cases = simpledialog.askinteger("Cases", "Number of cases:", initialvalue=3, minvalue=1)
            if num_cases is None: return
            params["var"] = var
            params["cases"] = [{"value": i, "body": []} for i in range(num_cases)]
            params["default"] = []
        elif typ == "Return / End":
            params = {}
        
        new_act = {"type": typ, "params": params, "_id": _new_action_id()}
        target = self.target_list if self.target_list is not None else self.sequence
        target.append(new_act)
        self.target_list = None
        self.log(f"Added: {typ}")
        self._schedule_refresh()

    def _pick_position(self):
        if not self._focus_game_window_for_action():
            return None
        time.sleep(0.3)

        img_raw = pyautogui.screenshot()
        img = img_raw.convert("RGB")
        enhancer = ImageEnhance.Brightness(img)
        dimmed = enhancer.enhance(0.5)
        photo = ImageTk.PhotoImage(dimmed)
        
        # Cleanup intermediate
        img_raw.close()
        
        top = Toplevel()
        top.attributes("-fullscreen", True, "-topmost", True)
        top.overrideredirect(True)
        top.config(cursor="cross")

        c = Canvas(top, highlightthickness=0)
        c.pack(fill="both", expand=True)
        c.create_image(0, 0, anchor="nw", image=photo)
        c.photo = photo

        c.create_text(top.winfo_screenwidth() // 2, 60,
                      text="Click to select position (ESC to cancel)",
                      fill="#00ffaa", font=("Consolas", 16, "bold"))

        pos_text = c.create_text(top.winfo_screenwidth() // 2, 120,
                                 text="(0, 0)", fill="#00ffaa",
                                 font=("Consolas", 14))

        result = [None]

        def motion(e):
            bx = int(round(e.x / _SCALE_X))
            by = int(round(e.y / _SCALE_Y))
            c.itemconfig(pos_text, text=f"({bx}, {by})")

        def click(e):
            # Convert screen pixels → base-resolution space so _sx/_sy in handler
            # scales back to the correct real screen position.
            bx = int(round(e.x / _SCALE_X))
            by = int(round(e.y / _SCALE_Y))
            result[0] = (bx, by)
            top.destroy()

        def cancel(e):
            top.destroy()

        c.bind("<Motion>", motion)
        c.bind("<Button-1>", click)
        top.bind("<Escape>", cancel)
        top.focus_set()
        top.wait_window()
        
        # Cleanup
        del photo
        gc.collect()

        if result[0]:
            self.root.lift()
            self.root.focus_force()

        return result[0]

    def _pick_region(self):
        if not self._focus_game_window_for_action():
            return None
        time.sleep(0.3)

        img_raw = pyautogui.screenshot()
        img = img_raw.convert("RGB")
        enhancer = ImageEnhance.Brightness(img)
        dimmed = enhancer.enhance(0.5)
        photo = ImageTk.PhotoImage(dimmed)
        img_raw.close()

        top = Toplevel()
        top.attributes("-fullscreen", True, "-topmost", True)
        top.overrideredirect(True)
        top.config(cursor="cross")

        c = Canvas(top, highlightthickness=0)
        c.pack(fill="both", expand=True)
        c.create_image(0, 0, anchor="nw", image=photo)
        c.photo = photo

        c.create_text(top.winfo_screenwidth() // 2, 60,
                      text="Drag to select region (ESC to cancel)",
                      fill="#00ffaa", font=("Consolas", 16, "bold"))

        info_text = c.create_text(top.winfo_screenwidth() // 2, 120,
                                  text="(0, 0) → 0×0", fill="#00ffaa",
                                  font=("Consolas", 14))

        state = {"start": None, "rect": None}
        result = [None]

        def press(e):
            state["start"] = (e.x, e.y)
            if state["rect"]:
                c.delete(state["rect"])
            state["rect"] = c.create_rectangle(e.x, e.y, e.x, e.y,
                                               outline="#00ffaa", width=4)

        def motion(e):
            bx = int(round(e.x / _SCALE_X))
            by = int(round(e.y / _SCALE_Y))
            bw = abs(int(round((e.x - (state['start'][0] if state['start'] else e.x)) / _SCALE_X)))
            bh = abs(int(round((e.y - (state['start'][1] if state['start'] else e.y)) / _SCALE_Y)))
            c.itemconfig(info_text, text=f"({bx}, {by}) → {bw}×{bh}")

            if state["start"]:
                x0, y0 = state["start"]
                c.coords(state["rect"], x0, y0, e.x, e.y)

        def release(e):
            if not state["start"]:
                return
            x0, y0 = state["start"]
            rx = min(x0, e.x)
            ry = min(y0, e.y)
            rw = abs(e.x - x0)
            rh = abs(e.y - y0)
            if rw > 15 and rh > 15:
                # Convert screen pixels → base-resolution space
                result[0] = (
                    int(round(rx / _SCALE_X)),
                    int(round(ry / _SCALE_Y)),
                    int(round(rw / _SCALE_X)),
                    int(round(rh / _SCALE_Y)),
                )
            top.destroy()

        def cancel(e):
            top.destroy()

        c.bind("<ButtonPress-1>", press)
        c.bind("<B1-Motion>", motion)
        c.bind("<Motion>", motion)
        c.bind("<ButtonRelease-1>", release)
        top.bind("<Escape>", cancel)
        top.focus_set()
        top.wait_window()
        
        del photo
        gc.collect()

        if result[0]:
            self.root.lift()
            self.root.focus_force()

        return result[0]

    def _save_sequence(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")])
        if not path: return
        res_str = self._setting_base_res.get() if hasattr(self, "_setting_base_res") else "1920x1080"
        export = {"base_res": res_str, "sequence": self.sequence}

        # Dev mode: ask for title, description and icon before saving
        if getattr(self, '_dev_mode', False):
            prefill = getattr(self, '_loaded_meta', {"name": "", "description": "", "icon": "🎮"})
            meta = self._prompt_config_metadata(prefill=prefill)
            if meta is None:
                return  # user cancelled
            if meta["name"]:
                export["name"] = meta["name"]
            if meta["description"]:
                export["description"] = meta["description"]
            if meta["icon"]:
                export["icon"] = meta["icon"]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, ensure_ascii=False)
        self.log(f"Saved: {path}  |  base res: {res_str}" + (f"  |  name: {export.get('name','')}" if export.get('name') else ""))

    def _prompt_config_metadata(self, prefill=None):
        """Show a dialog asking for config title, description and icon. Returns dict or None if cancelled."""
        prefill = prefill or {"name": "", "description": "", "icon": "🎮"}
        result = [None]
        win = Toplevel(self.root)
        win.title("Config Details")
        win.configure(bg="#0a0e27")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        ICONS = ["⚔️","🛡️","💰","🔄","🏆","🎯","🤖","⚡","🔥","🌟","🛒","📦","🗡️","💎","🎮"]

        f = tk.Frame(win, bg="#0a0e27")
        f.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Label(f, text="💾  Save Config", font=("Segoe UI", 13, "bold"),
                 bg="#0a0e27", fg="#ffd700").pack(pady=(0, 16))

        # Title
        tk.Label(f, text="Title", font=("Segoe UI", 10, "bold"),
                 bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        title_var = tk.StringVar(value=prefill.get("name", ""))
        tk.Entry(f, textvariable=title_var, font=("Consolas", 12),
                 bg="#1a1f3a", fg="#fff", insertbackground="#ffd700",
                 relief="flat").pack(fill="x", ipady=8, pady=(4, 14))

        # Description
        tk.Label(f, text="Description", font=("Segoe UI", 10, "bold"),
                 bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        desc_txt = tk.Text(f, height=3, font=("Consolas", 11),
                           bg="#1a1f3a", fg="#fff", insertbackground="#ffd700",
                           relief="flat", wrap="word")
        desc_txt.insert("1.0", prefill.get("description", ""))
        desc_txt.pack(fill="x", pady=(4, 14))

        # Icon picker
        tk.Label(f, text="Icon", font=("Segoe UI", 10, "bold"),
                 bg="#0a0e27", fg="#8b9dc3").pack(anchor="w")
        current_icon = prefill.get("icon", ICONS[0])
        if current_icon not in ICONS:
            current_icon = ICONS[0]
        icon_var = tk.StringVar(value=current_icon)
        icon_grid = tk.Frame(f, bg="#0a0e27")
        icon_grid.pack(fill="x", pady=(4, 16))

        selected_btn = [None]
        def _pick_icon(ic, btn):
            icon_var.set(ic)
            if selected_btn[0]:
                selected_btn[0].config(bg="#1a1f3a", relief="flat")
            btn.config(bg="#ffd700", relief="flat")
            selected_btn[0] = btn

        for i, ic in enumerate(ICONS):
            btn = tk.Button(icon_grid, text=ic, font=("Arial", 16),
                            bg="#1a1f3a", fg="white", relief="flat",
                            cursor="hand2", width=2, pady=2)
            btn.config(command=lambda b=btn, ico=ic: _pick_icon(ico, b))
            btn.grid(row=i//8, column=i%8, padx=2, pady=2)
            if ic == current_icon:
                btn.config(bg="#ffd700")
                selected_btn[0] = btn

        # Buttons
        btn_row = tk.Frame(f, bg="#0a0e27")
        btn_row.pack(fill="x", pady=(4, 0))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        def _save():
            result[0] = {
                "name": title_var.get().strip(),
                "description": desc_txt.get("1.0", tk.END).strip(),
                "icon": icon_var.get()
            }
            win.destroy()

        def _cancel():
            win.destroy()

        tk.Button(btn_row, text="Save", font=("Segoe UI", 10, "bold"),
                  bg="#ffd700", fg="#0a0e27", relief="flat", cursor="hand2",
                  command=_save).grid(row=0, column=0, sticky="ew", padx=(0,4), ipady=8)
        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 10),
                  bg="#2a2f4a", fg="#8b9dc3", relief="flat", cursor="hand2",
                  command=_cancel).grid(row=0, column=1, sticky="ew", padx=(4,0), ipady=8)

        win.update_idletasks()
        self._autosize_dialog(win, min_w=420, min_h=380)
        win.wait_window()
        return result[0]

    def _clear_sequence(self):
        if not self.sequence:
            return
        win = Toplevel(self.root)
        win.title("Clear Sequence")
        win.configure(bg="#0a0e27")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        f = tk.Frame(win, bg="#0a0e27")
        f.pack(fill="both", expand=True, padx=30, pady=24)

        tk.Label(f, text="🗑  Clear Sequence?", font=("Segoe UI", 13, "bold"),
                 bg="#0a0e27", fg="#e74c3c").pack(pady=(0, 8))
        tk.Label(f, text=f"This will delete all {len(self.sequence)} action(s).\nThis cannot be undone.",
                 font=("Segoe UI", 10), bg="#0a0e27", fg="#8b9dc3", justify="center").pack(pady=(0, 20))

        btn_row = tk.Frame(f, bg="#0a0e27")
        btn_row.pack(fill="x")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        def _do_clear():
            self.sequence.clear()
            self._schedule_refresh()
            self.log("Sequence cleared.")
            win.destroy()

        tk.Button(btn_row, text="Yes, Clear All", font=("Segoe UI", 10, "bold"),
                  bg="#e74c3c", fg="white", relief="flat", cursor="hand2",
                  command=_do_clear).grid(row=0, column=0, sticky="ew", padx=(0, 4), ipady=8)
        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 10),
                  bg="#2a2f4a", fg="#8b9dc3", relief="flat", cursor="hand2",
                  command=win.destroy).grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=8)

        win.update_idletasks()
        self._autosize_dialog(win, min_w=320, min_h=180)

    def _load_sequence(self):
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Support both raw sequence arrays AND config objects {name, sequence, ...}
            if isinstance(data, dict) and "sequence" in data:
                self.sequence = data["sequence"]
                self._loaded_meta = {
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "icon": data.get("icon", "🎮")
                }
                # Apply base resolution from config (default 1920x1080 for old configs)
                res_str = data.get("base_res", "1920x1080")
                try:
                    bw, bh = map(int, res_str.lower().split("x"))
                    _init_scaling(bw, bh)
                    if hasattr(self, "_setting_base_res"):
                        self._setting_base_res.set(res_str)
                    self.log(f"Loaded config: {data.get('name', path)}  |  base res: {res_str}")
                except Exception:
                    self.log(f"Loaded config: {data.get('name', path)}  |  base res defaulted to 1920x1080")
            elif isinstance(data, list):
                self.sequence = data
                self._loaded_meta = {"name": "", "description": "", "icon": "🎮"}
                # Raw list = old format, default to 1920x1080
                _init_scaling(1920, 1080)
                if hasattr(self, "_setting_base_res"):
                    self._setting_base_res.set("1920x1080")
                self.log(f"Loaded: {path}  |  base res defaulted to 1920x1080")
            else:
                messagebox.showerror("Load Error", "Unrecognised file format — expected a sequence array or config object.")
                return
            _reassign_ids(self.sequence)
            self._scroll_to_top_next = True
            self._schedule_refresh()
        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    # ─────────────────────────────────────────────────────────────────
    # Run Overlay — floating log window shown while bot is running
    # ─────────────────────────────────────────────────────────────────
    def _create_run_overlay(self):
        if hasattr(self, "_run_overlay") and self._run_overlay:
            try:
                if self._run_overlay.winfo_exists(): return
            except: pass
        ov = tk.Toplevel(self.root)
        ov.title("")
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.88)
        ov.geometry("420x320+20+20")
        ov.configure(bg="#0a0e1a")
        # Make overlay click-through for focus — never steals focus from game/notepad
        try:
            import ctypes as _ct
            hwnd_ov = int(ov.frame(), 16)
            _BOT_HWNDS.add(hwnd_ov)  # exclude overlay from game searches
            WS_EX_NOACTIVATE   = 0x08000000
            WS_EX_TOOLWINDOW   = 0x00000080
            GWL_EXSTYLE        = -20
            cur = _ct.windll.user32.GetWindowLongW(hwnd_ov, GWL_EXSTYLE)
            _ct.windll.user32.SetWindowLongW(hwnd_ov, GWL_EXSTYLE,
                cur | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        except Exception:
            pass

        hdr = tk.Frame(ov, bg="#1a1f3a", height=28, cursor="fleur")
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🦆  Pato Tool Bot  —  Running",
                 bg="#1a1f3a", fg="#ffd700",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=8, pady=4)
        self._ov_iter_var   = tk.StringVar(value="Cycle: 0")
        self._ov_status_var = tk.StringVar(value="● RUNNING")
        tk.Label(hdr, textvariable=self._ov_status_var,
                 bg="#1a1f3a", fg="#2ecc71",
                 font=("Segoe UI", 8, "bold")).pack(side="right", padx=6)
        tk.Label(hdr, textvariable=self._ov_iter_var,
                 bg="#1a1f3a", fg="#8b9dc3",
                 font=("Segoe UI", 8)).pack(side="right", padx=4)
        close_btn = tk.Label(hdr, text="✕", bg="#1a1f3a", fg="#666",
                             font=("Segoe UI", 10), cursor="hand2", padx=6)
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self._hide_run_overlay())

        log_frame = tk.Frame(ov, bg="#0a0e1a")
        log_frame.pack(fill="both", expand=True, padx=2, pady=(0,2))
        self._ov_log = tk.Text(log_frame, bg="#0a0e1a", fg="#c8d3f0",
                               font=("Consolas", 8), bd=0, highlightthickness=0,
                               state="disabled", wrap="word", cursor="arrow")
        ov_scroll = tk.Scrollbar(log_frame, command=self._ov_log.yview,
                                  bg="#0a0e1a", troughcolor="#0a0e1a",
                                  activebackground="#ffd700", width=6)
        self._ov_log.configure(yscrollcommand=ov_scroll.set)
        ov_scroll.pack(side="right", fill="y")
        self._ov_log.pack(side="left", fill="both", expand=True, padx=(4,0))
        self._ov_log.tag_config("ts",     foreground="#3a4a6a")
        self._ov_log.tag_config("gold",   foreground="#ffd700", font=("Consolas", 8, "bold"))
        self._ov_log.tag_config("green",  foreground="#2ecc71")
        self._ov_log.tag_config("red",    foreground="#e74c3c")
        self._ov_log.tag_config("dim",    foreground="#556070")
        self._ov_log.tag_config("cyan",   foreground="#00bcd4")
        self._ov_log.tag_config("yellow", foreground="#f1c40f")
        self._ov_log.tag_config("action", foreground="#a78bfa", font=("Consolas", 8, "bold"))

        grip = tk.Label(ov, text="⠿", bg="#0a0e1a", fg="#2a3050",
                        font=("Segoe UI", 9), cursor="size_nw_se")
        grip.place(relx=1.0, rely=1.0, anchor="se")

        self._ov_drag = {"x": 0, "y": 0}
        def _ov_drag_start(e):
            self._ov_drag["x"] = e.x_root - ov.winfo_x()
            self._ov_drag["y"] = e.y_root - ov.winfo_y()
        def _ov_drag_move(e):
            ov.geometry(f"+{e.x_root-self._ov_drag['x']}+{e.y_root-self._ov_drag['y']}")
        hdr.bind("<ButtonPress-1>", _ov_drag_start)
        hdr.bind("<B1-Motion>",     _ov_drag_move)
        for w in hdr.winfo_children():
            w.bind("<ButtonPress-1>", _ov_drag_start)
            w.bind("<B1-Motion>",     _ov_drag_move)

        self._ov_resize = {"x":0,"y":0,"w":420,"h":320}
        def _grip_start(e):
            self._ov_resize.update({"x":e.x_root,"y":e.y_root,
                                     "w":ov.winfo_width(),"h":ov.winfo_height()})
        def _grip_drag(e):
            nw = max(280, self._ov_resize["w"]+(e.x_root-self._ov_resize["x"]))
            nh = max(160, self._ov_resize["h"]+(e.y_root-self._ov_resize["y"]))
            ov.geometry(f"{nw}x{nh}")
        grip.bind("<ButtonPress-1>", _grip_start)
        grip.bind("<B1-Motion>",     _grip_drag)

        self._run_overlay  = ov
        self._ov_log_lines = 0

    def _hide_run_overlay(self):
        if hasattr(self, "_run_overlay") and self._run_overlay:
            try: self._run_overlay.destroy()
            except: pass
            self._run_overlay = None

    def _ov_log_write(self, msg: str):
        if not hasattr(self, "_run_overlay") or not self._run_overlay:
            return
        try:
            if not self._run_overlay.winfo_exists(): return
        except: return
        txt = self._ov_log
        txt.config(state="normal")
        txt.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] ", "ts")
        m = msg.strip()
        if m.startswith("━━━"):
            txt.insert(tk.END, m+"\n", "gold")
        elif any(x in m for x in ("✔","Found","✓","success","Success","Activated")):
            txt.insert(tk.END, m+"\n", "green")
        elif any(x in m for x in ("✘","error","Error","FAIL","timeout","not found","🛑")):
            txt.insert(tk.END, m+"\n", "red")
        elif any(x in m for x in ("OCR","Image","click","Click")):
            txt.insert(tk.END, m+"\n", "cyan")
        elif any(x in m for x in ("Cycle","cycle","Loop","loop","iteration")):
            txt.insert(tk.END, m+"\n", "yellow")
        elif any(x in m for x in ("Wait","wait","Sleep","delay")):
            txt.insert(tk.END, m+"\n", "dim")
        elif m.startswith("→") or m.startswith("  →") or m.startswith("⤡"):
            txt.insert(tk.END, m+"\n", "action")
        else:
            txt.insert(tk.END, m+"\n")
        self._ov_log_lines += 1
        if self._ov_log_lines > 200:
            txt.delete("1.0", "3.0")
            self._ov_log_lines -= 2
        txt.see(tk.END)
        txt.config(state="disabled")

    def _ov_update_stats(self, cycle: int):
        if not hasattr(self, "_run_overlay") or not self._run_overlay:
            return
        try:
            if not self._run_overlay.winfo_exists(): return
            self._ov_iter_var.set(f"Cycle: {cycle}")
            self._ov_status_var.set("● RUNNING")
        except: pass

    def start(self):
        if not self.sequence:
            messagebox.showwarning("Empty", "Add actions first")
            return
        cfg = self.game_cfg
        # PID/exe based detection — works in fullscreen
        wins = find_game_by_pid_or_exe(self.game_key)
        if not wins:
            wins = find_game_window_enhanced(cfg["window_title"])

        # Notepad fallback — allows running without the game open
        self._notepad_mode = False
        if not wins:
            wins = _find_notepad_window()
            if wins:
                self._notepad_mode = True

        if not wins:
            messagebox.showwarning("Not found",
                f"{cfg['name']} is not running.\n"
                "Start the game, or open Notepad to test the bot.")
            return
        hwnd = wins[0]['hwnd']
        self._target_hwnd = hwnd  # remember for _focus_game_window_for_action
        if self._notepad_mode:
            self.log(f"📝 Notepad mode — targeting: {wins[0]['title']}")
        else:
            self.log(f"Using: {wins[0]['title']} ({cfg['name']})")
        self.running = True
        self._stop_event.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.variables.clear()
        self.update_status()
        self._create_run_overlay()
        # Minimize bot FIRST, then focus target — bot must not be foreground when we steal focus
        self.root.iconify()
        self.root.update()   # flush the iconify so Windows processes it
        time.sleep(0.15)     # give Windows time to actually minimize
        focus_window_advanced(hwnd)
        if self._notepad_mode:
            self.log("📝 Notepad focused — starting sequence")
        else:
            self.log(f"✓ {cfg['name']} focused — starting sequence")
        self.thread = threading.Thread(target=self._run_sequence, args=(hwnd,), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("STOPPED | Mode: BUY")
        self.log("Stopped")
        # Restore main window
        try:
            self.root.deiconify()
            self.root.lift()
        except: pass
        try:
            if hasattr(self, "_run_overlay") and self._run_overlay and self._run_overlay.winfo_exists():
                self._ov_status_var.set("■ STOPPED")
                self.root.after(3000, self._hide_run_overlay)
        except: pass

    def _run_sequence(self, hwnd):
        cycle = 0
        while self.running and not self._stop_event.is_set():
            cycle += 1
            try:
                self.root.after(0, lambda c=cycle: self._ov_update_stats(c))
            except: pass

            # ── Window guard: stop bot if target window is gone ──────────────
            try:
                if getattr(self, '_notepad_mode', False):
                    # Notepad: check title is non-empty (reliable for normal windows)
                    window_alive = (
                        win32gui.IsWindow(hwnd) and
                        win32gui.IsWindowVisible(hwnd) and
                        bool(win32gui.GetWindowText(hwnd))
                    )
                else:
                    # Game (fullscreen/borderless): check by process still running
                    window_alive = False
                    if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                        try:
                            import psutil
                            pid = ctypes.c_ulong()
                            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                            if pid.value and psutil.pid_exists(pid.value):
                                window_alive = True
                        except Exception:
                            # fallback: just trust IsWindow + IsWindowVisible
                            window_alive = True
            except Exception:
                window_alive = True  # don't stop on check error
            if not window_alive:
                self.log("🛑 Target window closed — stopping bot")
                self.root.after(0, self.stop)
                return

            # ── Re-focus target window on cycle 1 and every 5 cycles ──────────
            if cycle == 1 or cycle % 5 == 0:
                focus_window_advanced(hwnd)

            try:
                for act in self.sequence:
                    if not self.running:
                        break
                    self._execute_action(act)
            except _ReturnEnd:
                self.log("⏹ Sequence ended (Return)")
            except _BreakLoop:
                self.log("↩ Break at top level — stopping bot")
                break
            except _StopSequence:
                self.log("🛑 Sequence stopped")
                self.running = False
                break

            time.sleep(self._setting_loop_delay.get() if hasattr(self, "_setting_loop_delay") else 0.08)

            # Tiered GC — gen-0 every cycle (free short-lived numpy/PIL/cv2 objects)
            gc.collect(0)

            # gen-1 every 10 cycles
            if cycle % 10 == 0:
                gc.collect(1)

            # Full GC + OS RAM trim every 30 cycles
            if cycle % 30 == 0:
                _trim_ram()
                self._last_gc_time = time.time()

    def _schedule_refresh(self):
        """Debounced refresh — collapses rapid successive calls into one."""
        if self._refresh_pending:
            try:
                self.root.after_cancel(self._refresh_pending)
            except Exception:
                pass
        self._refresh_pending = self.root.after(30, self._refresh_sequence)

    def _refresh_sequence(self):
        self._refresh_pending = None
        # Ensure every action has a unique _id before rendering
        _ensure_ids(self.sequence)

        # ── Save current scroll position before rebuild ───────────────────
        try:
            _saved_scroll = self.canvas.yview()[0]
        except Exception:
            _saved_scroll = 0.0

        # ── Hide inner frame while rebuilding to prevent flicker ──────────
        self.canvas.itemconfig(self.canvas_window_id, state="hidden")

        # Destroy old widgets
        for widget in self.inner.winfo_children():
            widget.destroy()

        # Clear map
        self.frame_map = {}

        def create_frame(act, level=0, is_then=False, is_else=False, parent_frame=None, parent_list=None, index=None):
            bg_color = "#0f1824" if level % 2 == 0 else "#0a1420"
            if is_then: bg_color = "#1a3a1a"
            if is_else: bg_color = "#3a1a1a"
            parent = self.inner if parent_frame is None else parent_frame
            pad_x = (level*28 + 12, 12) if parent_frame is None or not (is_then or is_else) else (8, 8)
            frame = tk.Frame(parent, bg=bg_color, bd=1, relief="solid", pady=6, padx=12)
            frame.pack(fill="x", pady=2, padx=pad_x)
            frame_id = act.get("_id") or id(frame)
            self.frame_map[frame_id] = {
                "action": act,
                "parent_list": parent_list if parent_list is not None else self.sequence,
                "index": index if index is not None else len(parent_list or self.sequence) - 1,
                "frame": frame,
                "level": level,
                "is_then": is_then,
                "is_else": is_else
            }

            header_frame = tk.Frame(frame, bg=bg_color)
            header_frame.pack(fill="x", expand=False)
            handle = tk.Label(header_frame, text="≡", font=("Consolas", 14, "bold"),
                              bg="#2c3e50", fg="#bdc3c7", width=2, cursor="fleur")
            handle.pack(side="left", padx=(0,10))

            t = act["type"]
            # Color coding by action category
            if t in ("Single Click", "Double Click", "Right Click", "Manual Coordinates",
                     "OCR Click (Search Text)", "OCR Right Click (Search Text)"):
                color = "#7ec8e3"   # blue — clicks
            elif t in ("Type Text", "Click & Write Text", "Press Key", "Press & Release"):
                color = "#b8e0a0"   # green — keyboard
            elif t in ("Wait (milliseconds)", "Wait Random (min-max ms)"):
                color = "#aaaaaa"   # grey — waits
            elif t == "Move Mouse & Scroll":
                color = "#7ec8e3"
            elif t in ("Clear & Write Price", "Clear & Write Text"):
                color = "#ffd700"   # gold — price
            elif "Variable" in t or "Bool" in t or "Append" in t:
                color = "#88ffcc"   # mint — variables
            elif "Loop" in t or "Counter" in t:
                color = "#44ffaa"   # bright green — loops
            elif "If " in t or "Else" in t or "Switch" in t:
                color = "#ffdd44"   # yellow — conditions
            elif "Comment" in t:
                color = "#95a5a6"   # dim — comments
            elif t in ("Screenshot & Save",):
                color = "#e8a0e8"   # purple — screenshot
            elif t in ("Break", "Return / End"):
                color = "#ff5555"   # red — control flow
            else:
                color = "#e0e0e0"

            summary = self._action_summary(act)
            comment = act.get("comment", "")
            label_text = summary if not comment else f"{summary}  # {comment}"
            label_color = color if not comment else color
            tk.Label(header_frame, text=summary, font=("Consolas", 11),
                     bg=bg_color, fg=color, anchor="w").pack(side="left")
            if comment:
                tk.Label(header_frame, text=f"  # {comment}", font=("Consolas", 10, "italic"),
                         bg=bg_color, fg="#7f8fa6", anchor="w").pack(side="left", fill="x", expand=True)
            else:
                tk.Label(header_frame, text="", bg=bg_color).pack(side="left", fill="x", expand=True)

            tk.Button(header_frame, text="✎", font=("Consolas", 10), bg="#3498db", fg="white",
                      width=2, relief="flat", cursor="hand2",
                      command=lambda a=act: self._edit_action(a)).pack(side="right", padx=2)
            tk.Button(header_frame, text="×", font=("Consolas", 11), bg="#e74c3c", fg="white",
                      width=3, relief="flat", cursor="hand2",
                      command=lambda a=act: self._delete_action(a)).pack(side="right", padx=8)

            handle.bind("<Button-1>", lambda e, f=frame, fid=frame_id: self._start_drag(e, f, fid))  # fid=action _id
            handle.bind("<B1-Motion>", self._drag_motion)
            handle.bind("<ButtonRelease-1>", lambda e, fid=frame_id: self._drop(e, fid))

            # Right-click context menu on entire frame
            def _show_ctx(e, a=act, fid=frame_id):
                self._show_action_context_menu(e, a, fid)
            for _w in (frame, header_frame, handle):
                _w.bind("<Button-3>", _show_ctx)

            p = act.get("params", {})
            if "body" in p:
                body_frame = tk.Frame(frame, bg="#1a2a3a", bd=2, relief="ridge")
                body_frame.pack(fill="both", expand=True, pady=(8,4), padx=(8, 8))
                body_header = tk.Frame(body_frame, bg="#1a2a3a")
                body_header.pack(fill="x", padx=10, pady=4)
                tk.Label(body_header, text="▼ LOOP BODY", bg="#1a2a3a", fg="#88ccff", font=("Consolas", 10, "bold")).pack(side="left")
                tk.Button(body_header, text="+", font=("Consolas", 9, "bold"), bg="#2ecc71", fg="white", width=2, relief="flat",
                          command=lambda plist=p["body"]: self._set_target_and_show_menu(plist, "logic")).pack(side="right", padx=5)
                body_items = tk.Frame(body_frame, bg="#0d1d2d")
                body_items.pack(fill="both", expand=True, padx=6, pady=4)
                if not p["body"]:
                    placeholder = tk.Label(
                        body_items,
                        text="(drop actions here)",
                        bg="#0d1d2d", fg="#66aaff",
                        font=("Consolas", 10, "italic"),
                        height=8, anchor="center"
                    )
                    placeholder.pack(fill="both", expand=True, padx=10, pady=20)
                    placeholder.drop_target = {"parent_list": p["body"], "insert_before_index": 0}
                    for evt in ["<Enter>", "<Leave>"]:
                        placeholder.bind(evt, lambda e, z=placeholder: self._highlight_drop_zone(z, e.type == "9"))
                else:
                    for i, sub in enumerate(p["body"]):
                        create_frame(sub, level + 1, parent_frame=body_items, parent_list=p["body"], index=i)

            if "true_branch" in p:
                then_frame = tk.Frame(frame, bg="#1a3a1a", bd=2, relief="ridge")
                then_frame.pack(fill="both", expand=True, pady=(8,4), padx=(8, 8))
                then_header = tk.Frame(then_frame, bg="#1a3a1a")
                then_header.pack(fill="x", padx=10, pady=4)
                tk.Label(then_header, text="▼ THEN (true)", bg="#1a3a1a", fg="#55ff88", font=("Consolas", 10, "bold")).pack(side="left")
                tk.Button(then_header, text="+", font=("Consolas", 9, "bold"), bg="#2ecc71", fg="white", width=2, relief="flat",
                          command=lambda plist=p["true_branch"]: self._set_target_and_show_menu(plist, "logic")).pack(side="right", padx=5)
                then_items = tk.Frame(then_frame, bg="#0d2d0d")
                then_items.pack(fill="both", expand=True, padx=6, pady=4)
                if not p["true_branch"]:
                    placeholder = tk.Label(
                        then_items,
                        text="(drop here - true branch)",
                        bg="#0d2d0d", fg="#44aa44",
                        font=("Consolas", 10, "italic"),
                        height=8, anchor="center"
                    )
                    placeholder.pack(fill="both", expand=True, padx=10, pady=20)
                    placeholder.drop_target = {"parent_list": p["true_branch"], "insert_before_index": 0}
                    for evt in ["<Enter>", "<Leave>"]:
                        placeholder.bind(evt, lambda e, z=placeholder: self._highlight_drop_zone(z, e.type == "9"))
                else:
                    for i, sub in enumerate(p["true_branch"]):
                        create_frame(sub, level + 1, is_then=True, parent_frame=then_items, parent_list=p["true_branch"], index=i)

            if "false_branch" in p:
                else_frame = tk.Frame(frame, bg="#3a1a1a", bd=2, relief="ridge")
                else_frame.pack(fill="both", expand=True, pady=(4,8), padx=(8, 8))
                else_header = tk.Frame(else_frame, bg="#3a1a1a")
                else_header.pack(fill="x", padx=10, pady=4)
                tk.Label(else_header, text="▼ ELSE (false)", bg="#3a1a1a", fg="#ff8888", font=("Consolas", 10, "bold")).pack(side="left")
                tk.Button(else_header, text="+", font=("Consolas", 9, "bold"), bg="#2ecc71", fg="white", width=2, relief="flat",
                          command=lambda plist=p["false_branch"]: self._set_target_and_show_menu(plist, "logic")).pack(side="right", padx=5)
                else_items = tk.Frame(else_frame, bg="#2d0d0d")
                else_items.pack(fill="both", expand=True, padx=6, pady=4)
                if not p["false_branch"]:
                    placeholder = tk.Label(
                        else_items,
                        text="(drop here - false branch)",
                        bg="#2d0d0d", fg="#aa4444",
                        font=("Consolas", 10, "italic"),
                        height=8, anchor="center"
                    )
                    placeholder.pack(fill="both", expand=True, padx=10, pady=20)
                    placeholder.drop_target = {"parent_list": p["false_branch"], "insert_before_index": 0}
                    for evt in ["<Enter>", "<Leave>"]:
                        placeholder.bind(evt, lambda e, z=placeholder: self._highlight_drop_zone(z, e.type == "9"))
                else:
                    for i, sub in enumerate(p["false_branch"]):
                        create_frame(sub, level + 1, is_else=True, parent_frame=else_items, parent_list=p["false_branch"], index=i)

            # Store drop metadata — exact list ref + index so nested frames work correctly
            _plist = parent_list if parent_list is not None else self.sequence
            _idx   = index if index is not None else 0
            frame.drop_target = {"parent_list": _plist, "insert_before_index": _idx, "list_id": id(_plist)}

        for i, act in enumerate(self.sequence):
            create_frame(act, parent_list=self.sequence, index=i)

        # ── Restore visibility and update scroll region in one shot ───────
        self.canvas.itemconfig(self.canvas_window_id, state="normal")
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if hasattr(self, '_update_scrollbar'):
            self._update_scrollbar()
        # Restore scroll position — defer so geometry is fully committed first
        def _restore_scroll():
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            if hasattr(self, '_update_scrollbar'):
                self._update_scrollbar()
            if getattr(self, '_scroll_to_top_next', False):
                self._scroll_to_top_next = False
                self.canvas.yview_moveto(0)
            else:
                self.canvas.yview_moveto(_saved_scroll)
        self.root.after(50, _restore_scroll)

    def _highlight_drop_zone(self, zone, highlight):
        if highlight:
            zone.config(bg="#00aaff", relief="raised", bd=1)
        else:
            zone.config(bg="#1a1f3a", relief="flat", bd=0)

    def _start_drag(self, event, frame, frame_id):
        self.drag_data = {
            "frame_id": frame_id,
            "frame": frame,
            "start_x": event.x_root,
            "start_y": event.y_root,
            "offset_x": event.x,
            "offset_y": event.y,
            "drop_line_frame": None,
            "drop_target": None,
        }
        act = self.frame_map[frame_id]["action"]
        ghost = Toplevel(self.root)
        ghost.overrideredirect(True)
        ghost.attributes("-alpha", 0.72)
        ghost.geometry(f"+{event.x_root - event.x}+{event.y_root - event.y}")
        ghost_frame = tk.Frame(ghost, bg="#2c3e50", bd=2, relief="raised")
        ghost_frame.pack()
        tk.Label(ghost_frame, text="≡ " + self._action_summary(act), font=("Consolas", 10),
                 bg="#2c3e50", fg="#ecf0f1").pack(padx=10, pady=5)
        self.drag_data["ghost"] = ghost
        frame.config(relief="flat", bd=0)

    def _drag_motion(self, event):
        if not self.drag_data:
            return
        ghost = self.drag_data["ghost"]
        ghost.geometry(f"+{event.x_root - self.drag_data['offset_x']}+{event.y_root - self.drag_data['offset_y']}")
        # Throttle indicator updates to ~30fps to avoid lag on large sequences
        now = time.time()
        last = self.drag_data.get("_last_indicator_t", 0)
        if now - last >= 0.033:
            self.drag_data["_last_indicator_t"] = now
            self._update_drop_indicator(event.x_root, event.y_root)
            self._start_auto_scroll_if_needed()

    def _update_drop_indicator(self, mouse_x, mouse_y):
        if not self.drag_data:
            return

        inner_root_y = self.inner.winfo_rooty()
        dragged_frame = self.drag_data.get("frame")
        dragged_act   = self.drag_data.get("frame_id")  # == action _id

        # ── Build a flat list of every valid insertion slot ───────────────
        # Each slot: (screen_y_of_line, line_y_in_inner, parent_list, insert_idx)
        # We generate one slot ABOVE each frame (insert before it) and one slot
        # BELOW the last frame in each sibling group (insert after it).
        # Slots belonging to the dragged frame itself are skipped.

        slots = []  # (screen_y, inner_y, parent_list, insert_idx)

        def scan(widget):
            if not hasattr(widget, "drop_target"):
                for child in widget.winfo_children():
                    scan(child)
                return

            tgt = widget.drop_target
            plist = tgt["parent_list"]
            idx   = tgt["insert_before_index"]

            # Skip the dragged frame's own slot
            if widget is dragged_frame:
                for child in widget.winfo_children():
                    scan(child)
                return

            try:
                wy = widget.winfo_rooty()
                wh = widget.winfo_height()
                if wh < 5:
                    return
                # Slot ABOVE this frame → insert at idx
                slots.append((wy, wy - inner_root_y, plist, idx))
                # Slot BELOW this frame → insert at idx+1
                # Only add if this is the last frame in its parent group
                # (we check by comparing idx to len(plist)-1)
                if idx == len(plist) - 1:
                    slots.append((wy + wh, wy + wh - inner_root_y, plist, idx + 1))
            except Exception:
                pass

            for child in widget.winfo_children():
                scan(child)

        scan(self.inner)

        if not slots:
            return

        # ── Find closest slot to mouse ────────────────────────────────────
        best = min(slots, key=lambda s: abs(mouse_y - s[0]))
        screen_y, inner_y, best_plist, best_idx = best

        self.drag_data["drop_target"] = {
            "parent_list": best_plist,
            "insert_before_index": min(best_idx, len(best_plist))
        }

        # ── Draw / move overlay line ──────────────────────────────────────
        line_frame = self.drag_data.get("drop_line_frame")
        inner_w = self.inner.winfo_width() or 400
        if line_frame is None or not line_frame.winfo_exists():
            line_frame = tk.Frame(self.inner, bg="#00e5ff", height=3, bd=0)
            self.drag_data["drop_line_frame"] = line_frame
        line_frame.place(x=0, y=inner_y, width=inner_w, height=3)
        line_frame.lift()

    def _start_auto_scroll_if_needed(self):
        if not self.drag_data:
            self._drag_scroll_after = None
            return
        try:
            x_root, y_root = self.root.winfo_pointerx(), self.root.winfo_pointery()
            canvas_y = y_root - self.canvas.winfo_rooty()
        except:
            return
        SCROLL_MARGIN = 60
        direction = 0
        if canvas_y < SCROLL_MARGIN:
            direction = -1
        elif canvas_y > self.canvas.winfo_height() - SCROLL_MARGIN:
            direction = 1
        if direction != 0:
            self.canvas.yview_scroll(direction, "units")
        self._drag_scroll_after = self.root.after(80, self._start_auto_scroll_if_needed)

    def _drop(self, event, frame_id):
        if not self.drag_data or frame_id not in self.frame_map:
            return
        # Clean up indicator line overlay
        line_frame = self.drag_data.get("drop_line_frame")
        if line_frame and line_frame.winfo_exists():
            line_frame.destroy()
        try:
            if hasattr(self, '_drag_scroll_after') and self._drag_scroll_after:
                self.root.after_cancel(self._drag_scroll_after)
                self._drag_scroll_after = None
        except:
            pass
        if self.drag_data.get("ghost"):
            self.drag_data["ghost"].destroy()

        dragged_act = self.frame_map[frame_id]["action"]
        old_parent = self.frame_map[frame_id]["parent_list"]
        # Remove by identity (not equality) to avoid removing a duplicate action
        for i, item in enumerate(old_parent):
            if item is dragged_act:
                old_parent.pop(i)
                break

        best_zone = self.drag_data.get("drop_target")

        if best_zone is not None:
            target_list = best_zone["parent_list"]
            insert_idx = min(best_zone["insert_before_index"], len(target_list))
            target_list.insert(insert_idx, dragged_act)
            self.log(f"Moved to index {insert_idx}")
        else:
            self.sequence.append(dragged_act)
            self.log("Moved to end")

        self._schedule_refresh()
        self.drag_data = None

    def _action_summary(self, act: dict) -> str:
        t = act["type"]
        p = act.get("params", {})

        # Clicks
        if t in ("Single Click", "Double Click", "Right Click"):
            icons = {"Single Click": "🖱", "Double Click": "🖱🖱", "Right Click": "🖱R"}
            return icons[t] + f' {t}  →  pos ({p.get("x","?")}, {p.get("y","?")})'
        if t == "Right Click → Click Menu Item":
            return (f'🖱R▶ RClick  ({p.get("x","?")},{p.get("y","?")})'
                    f'  →  menu "{p.get("menu_text","?")}"'
                    f'  wait={p.get("wait_ms",300):.0f}ms')
        if t == "Manual Coordinates":
            return f'🖱 Click  →  pos ({p.get("x","?")}, {p.get("y","?")})'
        if t == "OCR Click (Search Text)":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            return f'🔍 OCR Click  →  "{p.get("text","?")}"' + rstr
        if t == "OCR Right Click (Search Text)":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            return f'🔍 OCR RClick  →  "{p.get("text","?")}"' + rstr

        # Keyboard
        if t == "Type Text":
            return f'⌨  Type  →  "{p.get("text","?")}"'
        if t == "Click & Write Text":
            return f'🖱⌨  Click & Type  →  ({p.get("x","?")},{p.get("y","?")})  "{p.get("text","?")}"'
        if t == "Press Key":
            return f'⌨  Press key  →  [{p.get("key","?")}]'
        if t == "Press & Release":
            return f'⌨  Press & Release  →  [{p.get("key","?")}]'

        # Waits
        if t == "Wait (milliseconds)":
            ms = p.get("milliseconds", 0)
            sec = f"  ({float(ms)/1000:.2f}s)" if ms else ""
            return f"⏱  Wait  →  {ms} ms" + sec
        if t == "Wait Random (min-max ms)":
            return f'⏱  Wait random  →  {p.get("min_ms","800")} – {p.get("max_ms","1600")} ms'
        if t == "Wait for Text (OCR)":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            tms  = p.get("timeout_ms", 10000)
            return f'⏳ Wait for Text  →  "{p.get("text","?")}"  timeout={tms:.0f}ms' + rstr

        # Mouse move
        if t == "Move Mouse & Scroll":
            d = p.get("direction","?").upper()
            return f'🖱 Move  →  ({p.get("x","?")},{p.get("y","?")})  scroll {d} x{p.get("steps","?")}  {p.get("delay_ms","?")}ms/step'

        # Price
        if t == "Clear & Write Text":
            return f'⌨  Clear & Type  →  "{p.get("text","?")}"  pos ({p.get("x","?")},{p.get("y","?")})'
        if t == "Clear & Write Price":
            return f'💰 Write price  →  "{p.get("price","?")}"  pos ({p.get("x","?")},{p.get("y","?")})'

        # Variables
        if t == "Declare Variable (int/float/bool/string)":
            return f'📦 Declare  →  {p.get("type","?")} "{p.get("name","?")}" = {p.get("value","?")}'
        if t == "Set Variable":
            return f'📦 Set  →  "{p.get("name","?")}" = {p.get("value","?")}'
        if t == "Add To Variable":
            return f'📦 Add  →  "{p.get("name","?")}" += {p.get("amount","?")}'
        if t == "Subtract From Variable":
            return f'📦 Sub  →  "{p.get("name","?")}" -= {p.get("amount","?")}'
        if t == "Multiply Variable":
            return f'📦 Mul  →  "{p.get("name","?")}" *= {p.get("amount","?")}'
        if t == "Divide Variable":
            return f'📦 Div  →  "{p.get("name","?")}" /= {p.get("amount","?")}'
        if t == "Modulo Variable":
            return f'📦 Mod  →  "{p.get("name","?")}" %= {p.get("amount","?")}'
        if t == "Increment Variable":
            return f'📦 Increment  →  "{p.get("name","?")}" += 1'
        if t == "Decrement Variable":
            return f'📦 Decrement  →  "{p.get("name","?")}" -= 1'
        if t == "Toggle Bool (True ↔ False)":
            return f'📦 Toggle bool  →  "{p.get("name","?")}"'
        if t == "Set Bool To True":
            return f'📦 Set bool TRUE  →  "{p.get("name","?")}"'
        if t == "Set Bool To False":
            return f'📦 Set bool FALSE  →  "{p.get("name","?")}"'
        if t == "Reset Variable":
            return f'📦 Reset  →  "{p.get("name","?")}"'
        if t == "Delete Variable":
            return f'📦 Delete  →  "{p.get("name","?")}"'
        if t == "Append String":
            return f'📦 Append  →  "{p.get("name","?")}" += "{p.get("text","?")}"'

        # Loops
        if t == "Loop Start (repeat X times)":
            return f'🔄 Loop  →  repeat x{p.get("times","?")}'
        if t == "Loop For (var from X to Y)":
            return f'🔄 For  →  {p.get("var","?")} from {p.get("start","?")} to {p.get("end","?")}'
        if t == "Loop While (var condition)":
            return f'🔄 While  →  "{p.get("var","?")}" {p.get("operator","?")} {p.get("threshold","?")}'
        if t == "Increment Loop Counter":
            return f'🔄 Counter++  →  "{p.get("counter","?")}"'

        # Conditions
        if t == "If OCR any text (branch)":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            wms = p.get("wait_ms", 300)
            return f"\U0001f50d OCR any text  wait={wms:.0f}ms" + rstr
        if t == "If OCR text exists (branch)":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            tb = len(p.get("true_branch", []))
            fb = len(p.get("false_branch", []))
            return f'❓ If OCR  →  "{p.get("text","?")}"' + rstr + f"  [✔{tb} / ✘{fb}]"
        if t == "If Image Exists (branch)":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            image_name = p.get("image_name") or (os.path.basename(p.get("image_path", "?")) if p.get("image_path") else "screenshot")
            tb = len(p.get("true_branch", []))
            fb = len(p.get("false_branch", []))
            return f'❓ If Image  →  "{image_name}"' + rstr + f"  [✔{tb} / ✘{fb}]"
        if t == "If OCR number ≥ X (branch)":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            tb = len(p.get("true_branch", []))
            fb = len(p.get("false_branch", []))
            return f'❓ If OCR ≥  →  {p.get("min_value","?")}' + rstr + f"  [✔{tb} / ✘{fb}]"
        if t in ("If Variable > X (branch)", "If Variable < X (branch)",
                 "If Variable == X (branch)", "If Variable != X (branch)"):
            op = t.split("If Variable ")[1].split(" (")[0]
            tb = len(p.get("true_branch", []))
            fb = len(p.get("false_branch", []))
            return f'❓ If var  →  "{p.get("var","?")}" {op} {p.get("threshold","?")}  [✔{tb} / ✘{fb}]'
        if t in ("If Bool True (branch)", "If Bool False (branch)"):
            val = "TRUE" if "True" in t else "FALSE"
            tb = len(p.get("true_branch", []))
            fb = len(p.get("false_branch", []))
            return f'❓ If bool {val}  →  "{p.get("var","?")}"  [✔{tb} / ✘{fb}]'
        if t == "Else (branch)":
            return "❓ ELSE"
        if t == "Else If (branch)":
            return f'❓ Else If  →  "{p.get("var","?")}" {p.get("operator","?")} {p.get("threshold","?")}'

        # Counters
        if t == "Counter: Reset":
            return f'🔢 Counter reset  →  "{p.get("name","?")}"'
        if t == "Counter: Add 1":
            return f'🔢 Counter +1  →  "{p.get("name","?")}"'
        if t == "Counter: Subtract 1":
            return f'🔢 Counter -1  →  "{p.get("name","?")}"'

        # Misc
        if t == "Screenshot & Save":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            return f'📸 Screenshot  →  "{p.get("filename","?")}"' + rstr
        if t == "Comment":
            return f'// {p.get("text","")}'
        if t == "Return / End":
            return "⏹ Return / End"
        if t == "Stop Sequence":
            return "🛑 Stop Sequence"
        if t == "Break Loop":
            return "↩ Break Loop"
        if t == "Continue Loop":
            return "↻ Continue Loop"
        if t == "Break":
            return "■ Break loop"
        if t == "Read OCR Number → Variable":
            r = p.get("region", [])
            rstr = f"  rgn ({r[0]},{r[1]}) {r[2]}x{r[3]}" if len(r) == 4 else ""
            return f'🔢 Read OCR Number  →  "{p.get("var","?")}"' + rstr
        if t == "If Variable Changed (branch)":
            tb = len(p.get("true_branch", []))
            fb = len(p.get("false_branch", []))
            tol = p.get("tolerance", 0)
            return f'🔄 If "{p.get("var","?")}" changed  (±{tol})  [✔{tb} / ✘{fb}]'

        return t[:48] + "..." if len(t) > 48 else t
    def _edit_action(self, act):
        t = act["type"]
        p = act.get("params", {})
        preserve_keys = ["body", "true_branch", "false_branch", "cases", "default"]
        preserved = {k: p[k] for k in preserve_keys if k in p}

        def apply_params(new_params):
            new_params.update(preserved)
            act["params"] = new_params
            self._schedule_refresh()
            self.log(f"Edited: {t}")
        
        # ... (Same edit logic as original, just condensed for brevity in display) ...
        # [Full edit logic kept intact]
        if t == "Loop Start (repeat X times)":
            cnt = simpledialog.askinteger("Loop", "Repeat how many times?", initialvalue=p.get("times", 5), minvalue=1)
            if cnt is None: return
            apply_params({"times": cnt})

        elif t == "If OCR any text (branch)":
            wait_ms = simpledialog.askfloat("UI Wait", "Wait before screenshot (ms):",
                                             initialvalue=p.get("wait_ms", 300), minvalue=0, maxvalue=5000)
            if wait_ms is None: wait_ms = p.get("wait_ms", 300)
            region = self._pick_region()
            if region is None: region = p.get("region", list(DEFAULT_REGION))
            apply_params({"region": region, "wait_ms": wait_ms})

        elif t == "If OCR text exists (branch)":
            text = simpledialog.askstring("OCR Text", "Text to search:", initialvalue=p.get("text", ""))
            if text is None: return
            region = self._pick_region()
            if region is None: region = p.get("region", list(DEFAULT_REGION))
            apply_params({"text": text, "region": region})

        elif t == "Wait for Text (OCR)":
            text = simpledialog.askstring("Wait for Text", "Text to wait for:", initialvalue=p.get("text", ""))
            if text is None: return
            timeout_ms = simpledialog.askfloat(
                "Timeout", "Max wait time (ms):",
                initialvalue=p.get("timeout_ms", 10000), minvalue=500, maxvalue=9999999)
            if timeout_ms is None: timeout_ms = p.get("timeout_ms", 10000)
            interval_ms = simpledialog.askfloat(
                "Check Interval", "How often to check (ms):",
                initialvalue=p.get("interval_ms", 300), minvalue=50, maxvalue=9999999)
            if interval_ms is None: interval_ms = p.get("interval_ms", 300)
            region = self._pick_region()
            if region is None: region = p.get("region", list(DEFAULT_REGION))
            apply_params({"text": text, "region": region,
                          "timeout_ms": timeout_ms, "interval_ms": interval_ms})

        elif t == "Loop While (var condition)":
            var = self._show_var_selection("Loop While Variable")
            if var is None: return
            op = simpledialog.askstring("Operator", "Operator (> < == !=):", initialvalue=p.get("operator", ">"))
            thresh = simpledialog.askfloat("Threshold", "Compare to:", initialvalue=p.get("threshold", 10))
            if op is None or thresh is None: return
            apply_params({"var": var, "operator": op.strip(), "threshold": thresh})

        elif t == "If OCR number ≥ X (branch)":
            min_value = simpledialog.askfloat("Minimum Value", "If number ≥ this value → true", initialvalue=p.get("min_value", 1500.0))
            if min_value is None: return
            comma_mode = self._pick_comma_mode(p.get("comma_mode", "decimal"))
            region = self._pick_region()
            if region is None: region = p.get("region", list(DEFAULT_REGION))
            apply_params({"min_value": min_value, "comma_mode": comma_mode, "region": region})

        elif t in ("If Variable > X (branch)", "If Variable < X (branch)", "If Variable == X (branch)", "If Variable != X (branch)"):
            var = self._show_var_selection("If Variable")
            if var is None: return
            thresh = simpledialog.askfloat("Threshold", "Value:", initialvalue=p.get("threshold", 5))
            if thresh is None: return
            apply_params({"var": var, "threshold": thresh})

        elif t in ("If Bool True (branch)", "If Bool False (branch)"):
            var = self._show_var_selection("Bool Variable", "bool")
            if var is None: return
            apply_params({"var": var})

        elif t == "If Variable Exists (branch)":
            var = self._show_var_selection("If Variable Exists")
            if var is None: return
            apply_params({"var": var})

        elif t == "Declare Variable (int/float/bool/string)":
            name = simpledialog.askstring("Declare", "Variable name:", initialvalue=p.get("name", "myVar"))
            if name is None: return
            selected_type = p.get("type", "int")
            if selected_type == "bool":
                bool_val = tk.StringVar(value="true" if p.get("value") else "false")
                bool_win = Toplevel(self.root)
                bool_win.title("Set Value")
                bool_win.geometry("250x150")
                bool_win.configure(bg="#0a0e27")
                bool_win.transient(self.root)
                bool_win.grab_set()
                self._center_dialog(bool_win)
                main_f = tk.Frame(bool_win, bg="#0a0e27")
                main_f.pack(fill="both", expand=True, padx=40, pady=20)
                tk.Label(main_f, text="Initial Value:", font=("Consolas", 12, "bold"), bg="#0a0e27", fg="#ffd700").pack(pady=(0,15))
                tk.Radiobutton(main_f, text="True", variable=bool_val, value="true", font=("Consolas", 11), bg="#0a0e27", fg="#fff", selectcolor="#1a1f3a").pack(anchor="w", pady=5)
                tk.Radiobutton(main_f, text="False", variable=bool_val, value="false", font=("Consolas", 11), bg="#0a0e27", fg="#fff", selectcolor="#1a1f3a").pack(anchor="w", pady=5)
                def confirm_bool():
                    bool_win.destroy()
                tk.Button(main_f, text="OK", font=("Consolas", 11, "bold"), bg="#2ecc71", fg="white", relief="flat", command=confirm_bool).pack(pady=(10,0), ipady=5, fill="x")
                bool_win.wait_window()
                value = bool_val.get() == "true"
                apply_params({"name": name.strip(), "type": selected_type, "value": value})
                return
            else:
                if selected_type == "int":
                    value = simpledialog.askinteger("Value", "Initial value:", initialvalue=p.get("value", 0))
                elif selected_type == "float":
                    value = simpledialog.askfloat("Value", "Initial value:", initialvalue=p.get("value", 0.0))
                else:
                    value = simpledialog.askstring("Value", "Initial value:", initialvalue=str(p.get("value", "")))
                if value is None: return
            apply_params({"name": name.strip(), "type": selected_type, "value": value})

        elif t == "Set Variable":
            name = self._show_var_selection("Set Variable")
            if name is None: return
            value = simpledialog.askfloat("Value", "Set to:", initialvalue=p.get("value", 0))
            if value is None: return
            apply_params({"name": name, "value": value})

        elif t in ("Add To Variable", "Subtract From Variable", "Multiply Variable", "Divide Variable", "Modulo Variable"):
            name = self._show_var_selection(t)
            if name is None: return
            amount = simpledialog.askfloat("Amount", "Value:", initialvalue=p.get("amount", 1))
            if amount is None: return
            apply_params({"name": name, "amount": amount})

        elif t in ("Increment Variable", "Decrement Variable", "Toggle Bool (True ↔ False)", "Set Bool To True", "Set Bool To False", "Reset Variable", "Delete Variable"):
            name = self._show_var_selection(t.split()[0])
            if name is None: return
            apply_params({"name": name})

        elif t == "Append String":
            name = self._show_var_selection("Append String", "string")
            if name is None: return
            text = simpledialog.askstring("Text", "Append:", initialvalue=p.get("text", ""))
            if text is None: return
            apply_params({"name": name, "text": text})

        elif t == "Comment":
            text = simpledialog.askstring("Comment", "Comment text:", initialvalue=p.get("text", ""))
            if text is None: return
            apply_params({"text": text})

        elif t == "Wait Random (min-max ms)":
            min_ms = simpledialog.askinteger("Min", "Min ms:", initialvalue=p.get("min_ms", 800))
            max_ms = simpledialog.askinteger("Max", "Max ms:", initialvalue=p.get("max_ms", 1600))
            if min_ms is None or max_ms is None: return
            apply_params({"min_ms": min_ms, "max_ms": max_ms})

        elif t in ("Counter: Reset", "Counter: Add 1", "Counter: Subtract 1"):
            name = simpledialog.askstring("Counter", "Name:", initialvalue=p.get("name", "count"))
            if name is None: return
            apply_params({"name": name.strip() or "default"})

        elif t == "Type Text":
            text = simpledialog.askstring("Text", "Type:", initialvalue=p.get("text", "hello"))
            if text is None: return
            apply_params({"text": text})

        elif t in ("Press Key", "Press & Release"):
            key = simpledialog.askstring("Key", "Key name:", initialvalue=p.get("key", "enter"))
            if key is None: return
            apply_params({"key": key.strip().lower()})

        elif t == "Screenshot & Save":
            filename = simpledialog.askstring("Save As", "Filename:", initialvalue=p.get("filename", "screenshot.png"))
            if filename is None: return
            region = self._pick_region()
            if region is None: region = p.get("region", list(DEFAULT_REGION))
            apply_params({"filename": filename.strip(), "region": region})

        elif t == "If Image Exists (branch)":
            image_data = None
            image_name = p.get("image_name")
            if messagebox.askyesno("Update Template", "Capture a new image template from screen?"):
                messagebox.showinfo("Capture Template", "Select the region containing the image template to search for.")
                template_region = self._pick_region()
                if template_region is None:
                    return
                image_data = _screenshot_to_base64(template_region)
                image_name = f"screenshot {template_region[2]}x{template_region[3]}"
            elif "image_data" in p:
                image_data = p.get("image_data")
                image_name = p.get("image_name")
            elif "image_path" in p:
                image_name = os.path.basename(p.get("image_path", ""))

            region = self._pick_region()
            if region is None:
                region = p.get("region", list(DEFAULT_REGION))
            new_params = {"region": region}
            if image_data:
                new_params["image_data"] = image_data
            if image_name:
                new_params["image_name"] = image_name
            if "image_path" in p:
                new_params["image_path"] = p.get("image_path")
            apply_params(new_params)

        elif t == "Find Image & Click":
            image_data = None
            image_name = p.get("image_name")
            if messagebox.askyesno("Update Template", "Capture a new image template from screen?"):
                messagebox.showinfo("Capture Template", "Select the region containing the image template to click.")
                template_region = self._pick_region()
                if template_region is None:
                    return
                image_data = _screenshot_to_base64(template_region)
                image_name = f"screenshot {template_region[2]}x{template_region[3]}"
            elif "image_data" in p:
                image_data = p.get("image_data")
                image_name = p.get("image_name")
            elif "image_path" in p:
                image_name = os.path.basename(p.get("image_path", ""))

            region = self._pick_region()
            if region is None:
                region = p.get("region", list(DEFAULT_REGION))
            new_params = {"region": region}
            if image_data:
                new_params["image_data"] = image_data
            if image_name:
                new_params["image_name"] = image_name
            if "image_path" in p:
                new_params["image_path"] = p.get("image_path")
            apply_params(new_params)

        elif t == "Increment Loop Counter":
            name = simpledialog.askstring("Counter", "Counter name:", initialvalue=p.get("counter", "loop_counter"))
            if name is None: return
            apply_params({"counter": name.strip()})

        elif t == "Read OCR Number → Variable":
            name = simpledialog.askstring("Variable Name",
                "Store the number in variable named:", initialvalue=p.get("var", "ocr_value"))
            if not name: return
            comma_mode = self._pick_comma_mode(p.get("comma_mode", "decimal"))
            region = self._pick_region()
            if region is None: region = p.get("region", list(DEFAULT_REGION))
            apply_params({"var": name.strip(), "comma_mode": comma_mode, "region": region})

        elif t == "If Variable Changed (branch)":
            var = self._show_var_selection("Select Variable to Check")
            if var is None: return
            tolerance = simpledialog.askfloat("Tolerance",
                "Min change to count as 'changed'\n(0 = any change, 10 = must differ by >10):",
                initialvalue=p.get("tolerance", 0.0), minvalue=0.0)
            if tolerance is None: tolerance = 0.0
            apply_params({"var": var, "tolerance": tolerance})

        elif t in ("OCR Click (Search Text)", "OCR Right Click (Search Text)"):
            txt = simpledialog.askstring("Text", "Find & click:", initialvalue=p.get("text", "Buy"))
            if txt is None: return
            region = self._pick_region()
            if region is None: region = p.get("region", list(DEFAULT_REGION))
            apply_params({"text": txt.strip(), "region": region})

        elif t == "Clear & Write Price":
            pos = self._pick_position()
            if pos is None: return
            price = simpledialog.askstring("Price", "Value:", initialvalue=p.get("price", "1200"))
            if price is None: return
            apply_params({"x": pos[0], "y": pos[1], "price": price.strip()})

        elif t == "Clear & Write Text":
            pos = self._pick_position()
            if pos is None: return
            text = simpledialog.askstring("Text", "Text to type:", initialvalue=p.get("text", ""))
            if text is None: return
            apply_params({"x": pos[0], "y": pos[1], "text": text})

        elif t in ("Single Click", "Double Click", "Right Click"):
            pos = self._pick_position()
            if pos is None: return
            apply_params({"x": pos[0], "y": pos[1]})

        elif t == "Right Click → Click Menu Item":
            pos = self._pick_position()
            if pos is None: return
            menu_text = simpledialog.askstring(
                "Menu Item Text",
                "Text of the menu item to click:",
                initialvalue=p.get("menu_text", "Inspect")
            )
            if not menu_text: return
            wait_ms = simpledialog.askfloat(
                "Menu Open Delay",
                "Wait (ms) after right-click for menu to appear:",
                initialvalue=p.get("wait_ms", 300.0), minvalue=50.0, maxvalue=2000.0
            )
            apply_params({
                "x": pos[0], "y": pos[1],
                "menu_text": menu_text.strip(),
                "wait_ms": wait_ms if wait_ms is not None else 300.0
            })

        elif t == "Manual Coordinates":
            x = simpledialog.askinteger("X", "X:", initialvalue=p.get("x", 960))
            y = simpledialog.askinteger("Y", "Y:", initialvalue=p.get("y", 540))
            if x is None or y is None: return
            apply_params({"x": x, "y": y})

        elif t == "Wait (milliseconds)":
            ms = simpledialog.askfloat("Delay", "ms", initialvalue=p.get("milliseconds", 1200.0))
            if ms is None: return
            apply_params({"milliseconds": ms})

        elif t == "Loop For (var from X to Y)":
            var = self._show_var_selection("Loop For Variable")
            if var is None: return
            start_val = simpledialog.askinteger("Start", "From:", initialvalue=p.get("start", 0))
            if start_val is None: return
            end_val = simpledialog.askinteger("End", "To:", initialvalue=p.get("end", 10))
            if end_val is None: return
            apply_params({"var": var, "start": start_val, "end": end_val})

        elif t == "Else (branch)":
            apply_params({})

        elif t == "Else If (branch)":
            var = self._show_var_selection("Else If Variable")
            if var is None: return
            op = simpledialog.askstring("Operator", "Operator (> < == !=):", initialvalue=p.get("operator", "=="))
            thresh = simpledialog.askfloat("Threshold", "Compare to:", initialvalue=p.get("threshold", 0))
            if op is None or thresh is None: return
            apply_params({"var": var, "operator": op.strip(), "threshold": thresh})

        elif t == "Switch Case (multiple branches)":
            var = self._show_var_selection("Switch Variable")
            if var is None: return
            num_cases = simpledialog.askinteger("Cases", "Number of cases:", initialvalue=len(p.get("cases", [])), minvalue=1)
            if num_cases is None: return
            existing = p.get("cases", [])
            cases = []
            for i in range(num_cases):
                if i < len(existing):
                    cases.append(existing[i])
                else:
                    cases.append({"value": i, "body": []})
            apply_params({"var": var, "cases": cases, "default": p.get("default", [])})

        elif t == "Return / End":
            apply_params({})

        else:
            messagebox.showinfo("Edit", f"No editable parameters for '{t}'")

    # ─────────────────────────────────────────────
    # Right-click context menu
    # ─────────────────────────────────────────────
    def _show_action_context_menu(self, event, act, frame_id):
        import copy
        menu = tk.Menu(self.root, tearoff=0, bg="#1a1f3a", fg="#ffffff",
                       activebackground="#ffd700", activeforeground="#0a0e27",
                       font=("Segoe UI", 10), relief="flat", bd=1)

        # ── Edit ──────────────────────────────────
        menu.add_command(label="  ✎  Edit", command=lambda: self._edit_action(act))
        menu.add_separator()

        # ── Cut ───────────────────────────────────
        def _cut():
            self._clipboard_action = copy.deepcopy(act)
            self._delete_action(act)
            self.log(f"Cut: {act['type']}")
        menu.add_command(label="  ✂  Cut", command=_cut)

        # ── Copy ──────────────────────────────────
        def _copy():
            self._clipboard_action = copy.deepcopy(act)
            self.log(f"Copied: {act['type']}")
        menu.add_command(label="  ⎘  Copy", command=_copy)

        # ── Paste above ───────────────────────────
        def _paste_above():
            if not self._clipboard_action:
                return
            pasted = copy.deepcopy(self._clipboard_action)
            _reassign_ids([pasted])
            info = self.frame_map.get(frame_id)
            if info:
                parent_list = info["parent_list"]
                idx = info["index"]
                parent_list.insert(idx, pasted)
            else:
                self.sequence.append(pasted)
            self._schedule_refresh()
            self.log(f"Pasted above: {pasted['type']}")

        # ── Paste below ───────────────────────────
        def _paste_below():
            if not self._clipboard_action:
                return
            pasted = copy.deepcopy(self._clipboard_action)
            _reassign_ids([pasted])
            info = self.frame_map.get(frame_id)
            if info:
                parent_list = info["parent_list"]
                idx = info["index"]
                parent_list.insert(idx + 1, pasted)
            else:
                self.sequence.append(pasted)
            self._schedule_refresh()
            self.log(f"Pasted below: {pasted['type']}")

        has_clip = self._clipboard_action is not None
        menu.add_command(label="  ⬆  Paste Above", command=_paste_above,
                         state="normal" if has_clip else "disabled")
        menu.add_command(label="  ⬇  Paste Below", command=_paste_below,
                         state="normal" if has_clip else "disabled")

        menu.add_separator()

        # ── Duplicate ─────────────────────────────
        def _duplicate():
            duped = copy.deepcopy(act)
            _reassign_ids([duped])
            info = self.frame_map.get(frame_id)
            if info:
                info["parent_list"].insert(info["index"] + 1, duped)
            else:
                self.sequence.append(duped)
            self._schedule_refresh()
            self.log(f"Duplicated: {act['type']}")
        menu.add_command(label="  ⧉  Duplicate", command=_duplicate)

        menu.add_separator()

        # ── Comment ───────────────────────────────
        def _set_comment():
            current = act.get("comment", "")
            new_comment = simpledialog.askstring(
                "Comment", "Add a comment (leave empty to remove):",
                initialvalue=current, parent=self.root
            )
            if new_comment is None:
                return
            if new_comment.strip():
                act["comment"] = new_comment.strip()
            else:
                act.pop("comment", None)
            self._schedule_refresh()
        has_comment = bool(act.get("comment", ""))
        menu.add_command(label=f"  {'✏' if has_comment else '📝'}  {'Edit' if has_comment else 'Add'} Comment",
                         command=_set_comment)

        menu.add_separator()

        # ── Debug Overlay ─────────────────────────
        def _show_debug_overlay():
            self._open_debug_overlay(act)
        menu.add_command(label="  🎯  Show Click & Region Overlay", command=_show_debug_overlay)

        menu.add_separator()

        # ── Delete ────────────────────────────────
        menu.add_command(label="  ✕  Delete",
                         command=lambda: self._delete_action(act),
                         foreground="#ff5555", activeforeground="#ff5555")

        menu.tk_popup(event.x_root, event.y_root)

    def _open_debug_overlay(self, act):
        """Draw a fullscreen transparent overlay showing click points and regions for this action."""
        import tkinter as _tk_ov
        params = act.get("params", {})
        atype  = act.get("type", "")

        # ── Collect what to draw ─────────────────────────────────────────
        click_points = []   # list of (x, y, label)
        regions      = []   # list of (x1, y1, x2, y2, label, color)

        def _sr(v):
            """Apply resolution scale using global _SCALE_X/_SCALE_Y."""
            try:
                if isinstance(v, (list, tuple)) and len(v) == 4:
                    # region: (x1, y1, x2, y2) — scale x and y separately
                    return [int(v[0]*_SCALE_X), int(v[1]*_SCALE_Y),
                            int(v[2]*_SCALE_X), int(v[3]*_SCALE_Y)]
                elif isinstance(v, (list, tuple)):
                    return [int(x * _SCALE_X) for x in v]
                return int(v * _SCALE_X)
            except Exception:
                return v

        def _sx(v):
            try: return int(v * _SCALE_X)
            except: return v
        def _sy(v):
            try: return int(v * _SCALE_Y)
            except: return v

        # Click / Move actions
        if atype in ("Click", "Right Click", "Double Click", "Move Mouse"):
            x = params.get("x"); y = params.get("y")
            if x is not None and y is not None:
                click_points.append((_sx(x), _sy(y), atype))

        # Type text at position
        if atype in ("Type Text", "Clear & Write Text", "Write Text"):
            x = params.get("x"); y = params.get("y")
            if x is not None and y is not None:
                click_points.append((_sx(x), _sy(y), "Text target"))

        def _to_rect(r):
            """Convert region (x, y, w, h) -> scaled (x1, y1, x2, y2)."""
            x1 = int(r[0] * _SCALE_X)
            y1 = int(r[1] * _SCALE_Y)
            x2 = int((r[0] + r[2]) * _SCALE_X)
            y2 = int((r[1] + r[3]) * _SCALE_Y)
            return x1, y1, x2, y2

        # OCR regions
        for key in ("region", "ocr_region", "search_region"):
            r = params.get(key)
            if r and len(r) == 4:
                x1, y1, x2, y2 = _to_rect(r)
                color = "#00ff88"
                label = key.replace("_", " ").title()
                regions.append((x1, y1, x2, y2, label, color))

        # Click image / find image region
        if "image_region" in params:
            r = params["image_region"]
            if r and len(r) == 4:
                x1, y1, x2, y2 = _to_rect(r)
                regions.append((x1, y1, x2, y2, "Image Region", "#ff9900"))

        # If nothing to show
        if not click_points and not regions:
            # Try to show any x,y and region-like keys found
            for k, v in params.items():
                if k in ("x", "y"):
                    pass  # handled above
                elif isinstance(v, (list, tuple)) and len(v) == 4:
                    try:
                        rv = [int(i) for i in v]
                        x1 = int(rv[0] * _SCALE_X)
                        y1 = int(rv[1] * _SCALE_Y)
                        x2 = int((rv[0] + rv[2]) * _SCALE_X)
                        y2 = int((rv[1] + rv[3]) * _SCALE_Y)
                        regions.append((x1, y1, x2, y2, k, "#8888ff"))
                    except Exception:
                        pass
            x = params.get("x"); y = params.get("y")
            if x is not None and y is not None:
                click_points.append((_sx(x), _sy(y), "Target"))
            if not click_points and not regions:
                import tkinter.messagebox as _mb
                _mb.showinfo("Debug Overlay", f"No click coords or regions found for:\n{atype}", parent=self.root)
                return

        # ── Build fullscreen overlay ─────────────────────────────────────
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # Use a transparent colour key so the background is see-through
        TRANS = "#010101"
        ov = _tk_ov.Toplevel()
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-transparentcolor", TRANS)
        ov.attributes("-alpha", 1.0)
        ov.geometry(f"{sw}x{sh}+0+0")
        ov.configure(bg=TRANS)

        canvas = _tk_ov.Canvas(ov, width=sw, height=sh, bg=TRANS,
                                highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)

        # ── Top info bar (opaque strip) ──────────────────────────────────
        base_w, base_h = BASE_RES
        scale_info = f"Base: {base_w}x{base_h}  →  Screen: {sw}x{sh}  |  Scale X:{_SCALE_X:.3f}  Y:{_SCALE_Y:.3f}"
        canvas.create_rectangle(0, 0, sw, 54, fill="#0a0e27", outline="")
        canvas.create_rectangle(0, 52, sw, 54, fill="#ffd700", outline="")
        canvas.create_text(sw//2, 18,
            text=f"🎯  {atype}   —   Click anywhere or ESC to close",
            fill="#ffd700", font=("Segoe UI", 11, "bold"))
        canvas.create_text(sw//2, 38,
            text=scale_info,
            fill="#8b9dc3", font=("Segoe UI", 8))

        # ── Params info panel (top-right, below the info bar) ───────────
        info_lines = [f"Action: {atype}"]
        for k, v in params.items():
            info_lines.append(f"  {k}: {v}")
        panel_h = len(info_lines) * 18 + 16
        panel_w = 320
        panel_x = sw - panel_w - 8
        panel_y = 58   # just below the top info bar
        canvas.create_rectangle(panel_x, panel_y, panel_x + panel_w, panel_y + panel_h,
                                 fill="#0a0e27", outline="#ffd700", width=1)
        for i, line in enumerate(info_lines):
            col = "#ffd700" if i == 0 else "#cccccc"
            canvas.create_text(panel_x + 8, panel_y + 10 + i * 18,
                               text=line, anchor="w", fill=col,
                               font=("Consolas", 9, "bold" if i == 0 else "normal"))

        # ── Draw regions ────────────────────────────────────────────────
        for (x1, y1, x2, y2, label, color) in regions:
            # Filled tinted background
            canvas.create_rectangle(x1, y1, x2, y2,
                                    fill=color, stipple="gray12",
                                    outline="", width=0)
            # Solid border
            canvas.create_rectangle(x1, y1, x2, y2,
                                    outline=color, width=2, dash=(8, 4))
            # Corner brackets
            T = 14
            for bx, by in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
                dx = T if bx == x1 else -T
                dy = T if by == y1 else -T
                canvas.create_line(bx, by, bx + dx, by, fill=color, width=3)
                canvas.create_line(bx, by, bx, by + dy, fill=color, width=3)
            # Label pill
            mid_x = (x1 + x2) // 2
            lw = max(120, len(label) * 8 + 20)
            canvas.create_rectangle(mid_x - lw//2, y1 - 18,
                                     mid_x + lw//2, y1 + 2,
                                     fill="#0a0e27", outline=color, width=1)
            canvas.create_text(mid_x, y1 - 8, text=label,
                                fill=color, font=("Segoe UI", 8, "bold"))
            # Size + coords inside region (show both screen px and raw config values)
            w_px = x2 - x1; h_px = y2 - y1
            info_txt = f"{w_px} x {h_px} px"
            canvas.create_text((x1+x2)//2, (y1+y2)//2,
                                text=info_txt,
                                fill=color, font=("Consolas", 9, "bold"),
                                justify="center")

        # ── Draw click points ────────────────────────────────────────────
        for (cx, cy, label) in click_points:
            R = 14
            # Full-screen dashed crosshair lines
            canvas.create_line(0,  cy, cx - R, cy,  fill="#ff4444", width=1, dash=(4, 4))
            canvas.create_line(cx + R, cy, sw, cy,  fill="#ff4444", width=1, dash=(4, 4))
            canvas.create_line(cx, 54, cx, cy - R,  fill="#ff4444", width=1, dash=(4, 4))
            canvas.create_line(cx, cy + R, cx, sh,  fill="#ff4444", width=1, dash=(4, 4))
            # Solid inner crosshair arms
            canvas.create_line(cx - R, cy, cx + R, cy, fill="#ff4444", width=2)
            canvas.create_line(cx, cy - R, cx, cy + R, fill="#ff4444", width=2)
            # Outer ring
            canvas.create_oval(cx - R, cy - R, cx + R, cy + R,
                                outline="#ff4444", width=2)
            # Inner ring
            canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6,
                                outline="#ff4444", width=1)
            # Centre dot (filled)
            canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                                fill="#ff4444", outline="")
            # Coordinate label pill — keep on screen
            pill_x = cx + 20 if cx + 180 < sw else cx - 180
            pill_y = cy - 12
            ltext = f"{label}  ({cx}, {cy})"
            pw = len(ltext) * 7 + 20
            canvas.create_rectangle(pill_x, pill_y - 2,
                                     pill_x + pw, pill_y + 16,
                                     fill="#0a0e27", outline="#ff4444", width=1)
            canvas.create_text(pill_x + 8, pill_y + 7,
                                text=ltext, anchor="w",
                                fill="#ff4444", font=("Consolas", 9, "bold"))

        # ── Live mouse tracker (bottom-right) ───────────────────────────
        tracker_bg = canvas.create_rectangle(sw - 220, sh - 40,
                                              sw - 4, sh - 4,
                                              fill="#0a0e27", outline="#ffd700", width=1)
        mouse_lbl = canvas.create_text(sw - 112, sh - 22,
                                        text="🖱  X=0   Y=0",
                                        fill="#ffd700", font=("Consolas", 10, "bold"))

        def _on_mouse(e):
            canvas.itemconfig(mouse_lbl, text=f"🖱  X={e.x}   Y={e.y}")

        canvas.bind("<Motion>", _on_mouse)

        # ── Close on click or ESC ────────────────────────────────────────
        canvas.bind("<Button-1>", lambda e: ov.destroy())
        canvas.bind("<Button-3>", lambda e: ov.destroy())
        ov.bind("<Escape>",       lambda e: ov.destroy())
        ov.focus_force()

    def _delete_action(self, act_to_delete):
        def recursive_delete(actions):
            for i, act in enumerate(actions):
                if act is act_to_delete:
                    del actions[i]
                    return True
                p = act.get("params", {})
                if "body" in p and recursive_delete(p["body"]): return True
                if "true_branch" in p and recursive_delete(p["true_branch"]): return True
                if "false_branch" in p and recursive_delete(p["false_branch"]): return True
            return False
        recursive_delete(self.sequence)
        self._schedule_refresh()
        self.log("Action deleted")

def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def _relaunch_as_admin():
    """Re-launch this process with UAC elevation and exit."""
    exe = sys.executable
    params = " ".join(f'"{a}"' for a in sys.argv)
    _slog(f"Relaunching elevated: {exe} {params} (dir={APP_DIR})")
    # Pass APP_DIR as the working directory — elevated processes otherwise
    # start in System32 and relative paths (logs, configs) break.
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, APP_DIR, 1)
    if ret <= 32:
        _slog(f"Elevation failed/cancelled (ShellExecuteW={ret}). Exiting.")
    sys.exit(0)

def _set_icon(win):
    """Apply icon.ico to any Tk window if found next to the exe."""
    try:
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(ico):
            win.iconbitmap(ico)
    except Exception:
        pass

if __name__ == "__main__":
    import sys
    import traceback
    import datetime

    # ── Top-level crash handler — writes to file AND shows a dialog ──────
    def _fatal(exc):
        msg = f"FATAL ERROR: {type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        try:
            log_path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PatoToolBot")
            os.makedirs(log_path, exist_ok=True)
            with open(os.path.join(log_path, "error_log.txt"), "a", encoding="utf-8") as f:
                f.write(f"\n\n=== CRASH {datetime.datetime.now()} ===\n{msg}\n")
        except Exception:
            pass
        try:
            import tkinter.messagebox as _mb
            _r = tk.Tk(); _r.withdraw()
            _mb.showerror("PatoToolBot — Fatal Error", msg[:1500], parent=_r)
            _r.destroy()
        except Exception:
            pass
        print(msg, file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        print(f"[STARTUP] PatoToolBot v{CURRENT_VERSION} starting on {platform.system()}", file=sys.stderr, flush=True)

        # ── Request admin FIRST ───────────────────────────────────────────
        if not _is_admin():
            print("[STARTUP] Requesting admin privileges...", file=sys.stderr, flush=True)
            _relaunch_as_admin()

        # ── Single instance check ─────────────────────────────────────────
        print("[STARTUP] Creating mutex for single-instance check...", file=sys.stderr, flush=True)
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "PatoToolBotMutex_2026")
        if ctypes.windll.kernel32.GetLastError() == 183:
            try:
                def _enum_cb(h, _):
                    buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(h, buf, 256)
                    if "PatoArena" in buf.value or "Pato" in buf.value:
                        ctypes.windll.user32.ShowWindow(h, 9)
                        ctypes.windll.user32.SetForegroundWindow(h)
                    return True
                _EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
                ctypes.windll.user32.EnumWindows(_EnumProc(_enum_cb), 0)
            except Exception:
                pass
            _slog("Another instance is already running (mutex exists). Exiting.")
            sys.exit(0)

        # ── Coordinate scaling ────────────────────────────────────────────
        _saved_res = _load_base_res()
        try:
            _bw, _bh = map(int, _saved_res.lower().split("x"))
        except Exception:
            _bw, _bh = 1920, 1080
        _init_scaling(_bw, _bh)

        # ── Single persistent Tk root — created ONCE, never destroyed ─────
        # All windows (splash, auth, launcher, main) are Toplevels on this root.
        _root = tk.Tk()
        _root.withdraw()

        # ── Splash screen ─────────────────────────────────────────────────
        exe_dir = os.path.dirname(os.path.abspath(__file__))
        gif_path = None
        for _f in os.listdir(exe_dir):
            if _f.lower().endswith('.gif'):
                gif_path = os.path.join(exe_dir, _f)
                break

        splash = SplashScreen(gif_path, master=_root)
        splash.show_and_wait(3000)

        if "--updated" not in sys.argv:
            check_for_update()
        else:
            print(f"[Updater] Launched after update — skipping version check (v{CURRENT_VERSION})")

        # ── Auth ──────────────────────────────────────────────────────────
        print("[STARTUP] Showing AuthWindow...", file=sys.stderr, flush=True)
        auth = AuthWindow(_master=_root)
        ok, user = auth.show()
        lic_info = getattr(auth, '_license_info', {})
        print(f"[STARTUP] AuthWindow closed: ok={ok}, user={user}", file=sys.stderr, flush=True)

        if not ok:
            print("[STARTUP] Authentication cancelled. Exiting.", file=sys.stderr, flush=True)
            sys.exit(0)

        # ── Game Launcher ─────────────────────────────────────────────────
        launcher = GameLauncherWindow(user, lic_info, master=_root)
        game_key, game_cfg = launcher.show()

        if not game_key:
            print("[STARTUP] No game selected. Exiting.", file=sys.stderr, flush=True)
            sys.exit(0)

        print(f"[STARTUP] Game selected: {game_key}", file=sys.stderr, flush=True)

        # ── OCR splash ────────────────────────────────────────────────────
        _slog("Loading OCR engine (first run downloads models)...")
        ocr_splash = SplashScreen(gif_path, master=_root)
        ocr_splash.set_status("Loading OCR engine...", 10)

        ocr_done = [False]
        ocr_error = [None]

        def _load_ocr():
            try:
                _get_reader()
            except Exception as e:
                ocr_error[0] = e
            finally:
                ocr_done[0] = True

        import threading as _ocr_thread
        _ocr_thread.Thread(target=_load_ocr, daemon=True).start()

        _pct = [30]
        while not ocr_done[0]:
            if _pct[0] < 90:
                _pct[0] += 0.3
            ocr_splash.set_status("Loading OCR engine...", _pct[0])
            time.sleep(0.05)

        time.sleep(0.4)
        ocr_splash.close()

        if ocr_error[0] is not None:
            _slog(f"OCR init FAILED: {ocr_error[0]}")
            print(f"[STARTUP] OCR init failed: {ocr_error[0]}", file=sys.stderr, flush=True)
        else:
            _slog("OCR ready")

        # ── Main window ───────────────────────────────────────────────────
        _slog("Creating main GUI window...")
        main_win = tk.Toplevel(_root)
        _slog("Initializing AutoClickBot...")
        app = AutoClickBot(main_win, user, license_info=lic_info, game_key=game_key)
        _slog("Entering mainloop...")

        def _on_main_close():
            app._on_close()
            try:
                _root.destroy()
            except Exception:
                pass
        main_win.protocol("WM_DELETE_WINDOW", _on_main_close)
        _root.mainloop()

    except SystemExit:
        raise
    except Exception as _e:
        _fatal(_e)