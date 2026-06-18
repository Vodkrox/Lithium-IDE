import ctypes
import os
import subprocess
import sys

AI_LEVELS = [
    "Ultra-Low",
    "Low",
    "Low-Medium",
    "Medium",
    "Medium-High",
    "High",
    "Ultra-High",
]

DEFAULT_MODEL_NAME = "Qwen2.5-Coder-7B-GGUF"
DEFAULT_MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/"
    "resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
)

# RAM upper bounds (GB) for each level except Ultra-High (64 GB+).
_RAM_THRESHOLDS_GB = [4, 8, 12, 16, 24, 63]

# Effective billions = how much of the 7B model capacity is used at each level.
LEVEL_CONFIG = {
    "Ultra-Low": {
        "billions": 1,
        "max_tokens": 160,
        "n_ctx": 2560,
        "n_batch": 160,
        "n_threads": 2,
        "temperature": 0.45,
        "top_p": 0.88,
        "repeat_penalty": 1.12,
    },
    "Low": {
        "billions": 2,
        "max_tokens": 224,
        "n_ctx": 3584,
        "n_batch": 224,
        "n_threads": 3,
        "temperature": 0.47,
        "top_p": 0.89,
        "repeat_penalty": 1.11,
    },
    "Low-Medium": {
        "billions": 3,
        "max_tokens": 288,
        "n_ctx": 4608,
        "n_batch": 288,
        "n_threads": 4,
        "temperature": 0.48,
        "top_p": 0.90,
        "repeat_penalty": 1.10,
    },
    "Medium": {
        "billions": 4,
        "max_tokens": 352,
        "n_ctx": 5632,
        "n_batch": 352,
        "n_threads": 4,
        "temperature": 0.50,
        "top_p": 0.90,
        "repeat_penalty": 1.10,
    },
    "Medium-High": {
        "billions": 5,
        "max_tokens": 416,
        "n_ctx": 6656,
        "n_batch": 416,
        "n_threads": 6,
        "temperature": 0.52,
        "top_p": 0.91,
        "repeat_penalty": 1.09,
    },
    "High": {
        "billions": 6,
        "max_tokens": 512,
        "n_ctx": 7680,
        "n_batch": 480,
        "n_threads": 6,
        "temperature": 0.54,
        "top_p": 0.92,
        "repeat_penalty": 1.08,
    },
    "Ultra-High": {
        "billions": 7,
        "max_tokens": 640,
        "n_ctx": 8192,
        "n_batch": 512,
        "n_threads": 8,
        "temperature": 0.55,
        "top_p": 0.93,
        "repeat_penalty": 1.07,
    },
}


def get_system_ram_gb():
    """Return total physical RAM in gigabytes, or None if detection fails."""
    try:
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return None
            return stat.ullTotalPhys / (1024 ** 3)

        if sys.platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                return int(result.stdout.strip()) / (1024 ** 3)

        meminfo_path = "/proc/meminfo"
        if os.path.exists(meminfo_path):
            with open(meminfo_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024 ** 2)
    except Exception:
        pass
    return None


def detect_ai_level_from_ram(ram_gb=None):
    """Map installed RAM to an AI strength tier."""
    if ram_gb is None:
        ram_gb = get_system_ram_gb()
    if ram_gb is None:
        return "Medium"

    for index, threshold in enumerate(_RAM_THRESHOLDS_GB):
        if ram_gb <= threshold:
            return AI_LEVELS[index]
    return AI_LEVELS[-1]


def normalize_level(level_name):
    if level_name in LEVEL_CONFIG:
        return level_name
    return "Medium"


def get_level_config(level_name):
    return dict(LEVEL_CONFIG[normalize_level(level_name)])


def get_effective_level(mode, manual_level=None, ram_gb=None):
    mode = (mode or "auto").strip().lower()
    if mode == "manual" and manual_level:
        return normalize_level(manual_level)
    return detect_ai_level_from_ram(ram_gb)


def get_default_model():
    return DEFAULT_MODEL_NAME, DEFAULT_MODEL_URL


def get_inference_params(level_name):
    config = get_level_config(level_name)
    return {
        "max_tokens": config["max_tokens"],
        "n_ctx": config["n_ctx"],
        "n_batch": config["n_batch"],
        "n_threads": config["n_threads"],
        "temperature": config["temperature"],
        "top_p": config["top_p"],
        "repeat_penalty": config["repeat_penalty"],
    }


def format_billions_label(level_name):
    billions = get_level_config(level_name)["billions"]
    return f"{billions}B"
