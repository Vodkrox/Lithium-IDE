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
        "max_tokens": 256,
        "n_ctx": 4096,
        "n_batch": 256,
        "n_threads": 2,
        "temperature": 0.30,
        "top_p": 0.85,
        "top_k": 40,
        "min_p": 0.05,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.12,
        "repeat_last_n": 64,
    },
    "Low": {
        "billions": 2,
        "max_tokens": 384,
        "n_ctx": 6144,
        "n_batch": 384,
        "n_threads": 3,
        "temperature": 0.35,
        "top_p": 0.87,
        "top_k": 40,
        "min_p": 0.05,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.11,
        "repeat_last_n": 64,
    },
    "Low-Medium": {
        "billions": 3,
        "max_tokens": 512,
        "n_ctx": 8192,
        "n_batch": 512,
        "n_threads": 4,
        "temperature": 0.40,
        "top_p": 0.88,
        "top_k": 40,
        "min_p": 0.05,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.1,
        "repeat_penalty": 1.10,
        "repeat_last_n": 64,
    },
    "Medium": {
        "billions": 4,
        "max_tokens": 768,
        "n_ctx": 12288,
        "n_batch": 768,
        "n_threads": 4,
        "temperature": 0.45,
        "top_p": 0.90,
        "top_k": 50,
        "min_p": 0.03,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.1,
        "repeat_penalty": 1.10,
        "repeat_last_n": 64,
    },
    "Medium-High": {
        "billions": 5,
        "max_tokens": 1024,
        "n_ctx": 16384,
        "n_batch": 1024,
        "n_threads": 6,
        "temperature": 0.50,
        "top_p": 0.91,
        "top_k": 50,
        "min_p": 0.03,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.2,
        "repeat_penalty": 1.09,
        "repeat_last_n": 64,
    },
    "High": {
        "billions": 6,
        "max_tokens": 1536,
        "n_ctx": 24576,
        "n_batch": 1536,
        "n_threads": 6,
        "temperature": 0.60,
        "top_p": 0.92,
        "top_k": 60,
        "min_p": 0.01,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.2,
        "repeat_penalty": 1.08,
        "repeat_last_n": 64,
    },
    "Ultra-High": {
        "billions": 7,
        "max_tokens": 2048,
        "n_ctx": 32768,
        "n_batch": 2048,
        "n_threads": 8,
        "temperature": 0.70,
        "top_p": 0.93,
        "top_k": 60,
        "min_p": 0.01,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.2,
        "repeat_penalty": 1.07,
        "repeat_last_n": 64,
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
            return stat.ullTotalPhys / (1024**3)

        if sys.platform == "darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                return int(result.stdout.strip()) / (1024**3)

        meminfo_path = "/proc/meminfo"
        if os.path.exists(meminfo_path):
            with open(meminfo_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024**2)
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
        "top_k": config["top_k"],
        "min_p": config["min_p"],
        "frequency_penalty": config["frequency_penalty"],
        "presence_penalty": config["presence_penalty"],
        "repeat_penalty": config["repeat_penalty"],
        "repeat_last_n": config["repeat_last_n"],
    }


def format_billions_label(level_name):
    billions = get_level_config(level_name)["billions"]
    return f"{billions}B"


def get_level_reasoning_instructions(level_name):
    """Return chain-of-thought / reasoning instructions appropriate for the AI level.

    Higher levels get detailed CoT prompting; lower levels get terse, direct
    instructions to stay within tight token budgets.
    """
    level = normalize_level(level_name)

    reasoning_map = {
        "Ultra-Low": (
            "Keep answers extremely short and direct. "
            "Do not explain your reasoning. "
            "Output only the essential information in 1-2 sentences max."
        ),
        "Low": (
            "Respond concisely. "
            "Avoid chain-of-thought or step-by-step reasoning. "
            "Prefer code or data directly without commentary."
        ),
        "Low-Medium": (
            "Provide brief explanations when necessary, but keep them to 1-2 steps. "
            "Prefer showing the answer or code over describing how you got there. "
            "Omit any text that is not strictly needed."
        ),
        "Medium": (
            "You may include a short chain-of-thought (1-3 steps) before answering. "
            "Be efficient: state your reasoning briefly, then the conclusion or code. "
            "Avoid verbose introductions or farewells."
        ),
        "Medium-High": (
            "Use step-by-step reasoning when the task benefits from it. "
            "Break down complex requests into sub-tasks and reason through each one. "
            "Explain trade-offs and alternatives when relevant. "
            "Keep the overall response concise but thorough."
        ),
        "High": (
            "Employ detailed chain-of-thought reasoning for every non-trivial task. "
            "Walk through the problem step by step before arriving at the answer. "
            "Consider edge cases, performance implications, and alternative approaches. "
            "Provide structured explanations with clear sections when helpful."
        ),
        "Ultra-High": (
            "Use full, detailed chain-of-thought reasoning. "
            "Analyze the problem from multiple angles before concluding. "
            "Discuss assumptions, constraints, trade-offs, and edge cases thoroughly. "
            "Structure your response with clear reasoning steps, then the final answer. "
            "Leverage the full context budget to provide comprehensive, well-reasoned answers."
        ),
    }
    return reasoning_map.get(level, reasoning_map["Medium"])


def get_sampling_strategy(level_name):
    """Return recommended sampling configuration (mirostat, tfs, etc.) for the level.

    Returns a dict with strategy name and parameters. Lower levels use simpler,
    more deterministic sampling. Higher levels use more advanced / creative
    sampling methods.
    """
    level = normalize_level(level_name)

    strategies = {
        "Ultra-Low": {
            "sampler": "temperature_top_p",
            "mirostat": 0,
            "mirostat_tau": None,
            "mirostat_eta": None,
            "tfs_z": None,
            "typical_p": None,
            "note": "Greedy-leaning: pure temp+top_p sampling with low temperature for determinism.",
        },
        "Low": {
            "sampler": "temperature_top_p",
            "mirostat": 0,
            "mirostat_tau": None,
            "mirostat_eta": None,
            "tfs_z": None,
            "typical_p": None,
            "note": "Simple temperature + top_p sampling; deterministic enough for constrained contexts.",
        },
        "Low-Medium": {
            "sampler": "temperature_top_p",
            "mirostat": 0,
            "mirostat_tau": None,
            "mirostat_eta": None,
            "tfs_z": 0.95,
            "typical_p": None,
            "note": "Adds light tail-free sampling to trim unlikely tokens without sacrificing determinism.",
        },
        "Medium": {
            "sampler": "mirostat_v2",
            "mirostat": 2,
            "mirostat_tau": 4.0,
            "mirostat_eta": 0.1,
            "tfs_z": None,
            "typical_p": None,
            "note": "Mirostat v2 for adaptive entropy control; good balance of quality and coherence.",
        },
        "Medium-High": {
            "sampler": "mirostat_v2",
            "mirostat": 2,
            "mirostat_tau": 4.5,
            "mirostat_eta": 0.1,
            "tfs_z": None,
            "typical_p": None,
            "note": "Mirostat v2 with slightly higher tau for more creative freedom while maintaining coherence.",
        },
        "High": {
            "sampler": "mirostat_v2",
            "mirostat": 2,
            "mirostat_tau": 5.0,
            "mirostat_eta": 0.15,
            "tfs_z": None,
            "typical_p": None,
            "note": "Mirostat v2 with moderate tau/eta; balances creativity with structured output at scale.",
        },
        "Ultra-High": {
            "sampler": "mirostat_v2",
            "mirostat": 2,
            "mirostat_tau": 5.5,
            "mirostat_eta": 0.2,
            "tfs_z": None,
            "typical_p": None,
            "note": "Mirostat v2 with relaxed tau/eta for maximum creative exploration within the large context.",
        },
    }
    return strategies.get(level, strategies["Medium"])
