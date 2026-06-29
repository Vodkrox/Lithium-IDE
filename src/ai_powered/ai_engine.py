import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from src.ai_powered.ai_level import get_default_model


def _get_appdata_dir():
    """Return the LithiumIDE appdata directory."""
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.getenv("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config"
        )
    return os.path.join(base, "LithiumIDE")


def get_models_dir():
    """Return the path to the models storage directory inside appdata."""
    return os.path.join(_get_appdata_dir(), "models")


_model_cache = {}

MODEL_CANDIDATES = [get_default_model()]

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert code-editing assistant and elite full-stack developer inside Lithium IDE. "
    "You respond in the same language the user uses (English, Spanish, etc.). "
    "When the user asks you to change code, output executable skill XML tags — never explanations of what XML is. "
    "Give COMPLETE, PRODUCTION-READY implementations. Do NOT output skeletons, placeholders, or stubs. "
    "If the user asks for a GUI app, build it fully with all features, proper error handling, and a polished UI. "
    "If the current file contains invalid syntax or unrelated text, fix it by deleting/replacing lines before adding new code. "
    "If needed, replace the entire file content using replace_file when the current content is not salvageable. "
    "Never answer with meta-instructions like 'XML tags must be well-formed' or 'Propose the changes'; emit the actual <skill> blocks instead. "
    "INCLUDE ALL IMPORTS your code needs. Never use a library without importing it first. "
    "The project uses tkinter for GUI; import ttk as: from tkinter import ttk. "
    "BEFORE emitting any code, mentally review it: verify imports are complete, logic is correct, "
    "there are no obvious bugs, and the code actually runs end-to-end. Only emit the skill blocks after this review. "
    "Be thorough and complete — write real, working code, not simplified examples."
)


def _safe_import_transformers():
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        return torch, AutoModelForCausalLM, AutoTokenizer
    except Exception:
        return None


def _subprocess_creationflags():
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _safe_import_llama_cpp():
    from src.utils import prepare_frozen_python_runtime, register_package_dll_dirs

    if getattr(sys, "frozen", False):
        prepare_frozen_python_runtime()
    else:
        register_package_dll_dirs("llama_cpp")

    try:
        from llama_cpp import Llama

        return Llama
    except Exception:
        pass

    return None


def _can_use_external_llama_cpp():
    from src.utils import can_import_module, get_python_executable

    if not getattr(sys, "frozen", False):
        return False
    if get_python_executable() == sys.executable:
        return False
    return can_import_module("llama_cpp")


def _normalize_source(source):
    if not source:
        return None
    source = source.strip()
    if source.startswith("file://"):
        source = source[7:]
    return source


def resolve_model_source(source):
    source = _normalize_source(source)
    if not source:
        raise ValueError("No AI model source has been configured.")

    if source.startswith("hf://"):
        repo_id = source[len("hf://") :]
        model_name = repo_id.replace("/", "-")
        target_dir = os.path.join(get_models_dir(), model_name)
        if os.path.exists(target_dir):
            return target_dir
        raise FileNotFoundError(
            f"Model has not been downloaded yet. Please download it from the AI menu."
        )

    if source.startswith("http://") or source.startswith("https://"):
        return _download_model_url(source)

    if os.path.exists(source):
        return source

    raise FileNotFoundError(f"Local model not found: {source}")


def _download_model_url(url, progress_callback=None):
    if url.startswith("hf://"):
        repo_id = url[len("hf://") :]
        if not repo_id:
            raise ValueError("Hugging Face repo id not provided in hf:// URL")

        model_name = repo_id.replace("/", "-")
        target_dir = os.path.join(get_models_dir(), model_name)
        os.makedirs(target_dir, exist_ok=True)

        try:
            from huggingface_hub import HfApi, get_token
        except Exception:
            import importlib

            from src.utils import get_python_executable

            try:
                subprocess.check_call(
                    [get_python_executable(), "-m", "pip", "install", "huggingface_hub"]
                )
                importlib.invalidate_caches()
                from huggingface_hub import HfApi, get_token
            except Exception as e:
                raise RuntimeError(
                    f"The 'huggingface_hub' package is required to download from Hugging Face. "
                    f"Failed to install it automatically: {e}. Install it manually with 'pip install huggingface_hub'"
                )

        api = HfApi()
        revision = "main"
        try:
            model_info = api.model_info(repo_id, revision=revision)
        except Exception as exc:
            raise RuntimeError(f"Hugging Face model info query failed: {exc}")

        repo_files = []
        total_size = 0
        file_sizes = {}
        for sibling in getattr(model_info, "siblings", []) or []:
            path = getattr(sibling, "rfilename", None) or getattr(sibling, "path", None)
            size = getattr(sibling, "size", None)
            if path is None:
                continue
            repo_files.append(path)
            file_sizes[path] = size
            if size is None:
                total_size = -1
            elif total_size != -1:
                total_size += size

        if not repo_files:
            raise RuntimeError(f"No files found for Hugging Face repo {repo_id}")

        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            token = get_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        except Exception:
            token = None

        downloaded = 0
        for path in repo_files:
            file_url = f"https://huggingface.co/{repo_id}/resolve/{revision}/{path}"
            path_target = os.path.join(target_dir, path)
            os.makedirs(os.path.dirname(path_target), exist_ok=True)
            if os.path.exists(path_target):
                existing_size = os.path.getsize(path_target)
                expected_size = file_sizes.get(path)
                if expected_size is not None and existing_size == expected_size:
                    downloaded += existing_size
                    if progress_callback:
                        progress_callback(downloaded, total_size)
                    continue

            request = urllib.request.Request(file_url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                with open(path_target, "wb") as out_file:
                    chunk_size = 8192
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

        if progress_callback:
            try:
                progress_callback(downloaded, total_size)
            except Exception:
                pass

        return target_dir

    parsed = urlparse(url)
    file_name = os.path.basename(parsed.path) or parsed.netloc
    file_name = file_name.split("/")[0]
    if not file_name:
        file_name = "model.bin"

    model_name = os.path.splitext(file_name)[0]
    target_dir = os.path.join(get_models_dir(), model_name)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, file_name)

    if os.path.exists(target_path):
        if progress_callback:
            progress_callback(
                os.path.getsize(target_path), os.path.getsize(target_path)
            )
        return target_path

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        total_size = response.getheader("Content-Length")
        try:
            total_size = int(total_size)
        except Exception:
            total_size = -1

        downloaded = 0
        chunk_size = 8192
        with open(target_path, "wb") as out_file:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size)

    return target_path


def download_model_url(url, progress_callback=None):
    """Public wrapper to download a model URL with optional progress callback."""
    return _download_model_url(url, progress_callback=progress_callback)


def clear_model_cache():
    """Unload cached llama-cpp / transformers models."""
    _model_cache.clear()


def list_model_candidates():
    """Return the built-in model candidate."""
    return [MODEL_CANDIDATES[0]] if MODEL_CANDIDATES else []


def get_runtime_status():
    llama_cpp = _safe_import_llama_cpp()
    if llama_cpp is not None:
        return "llama_cpp"

    transformers_impl = _safe_import_transformers()
    if transformers_impl is not None:
        return "transformers"

    from src.utils import can_import_module

    if can_import_module("llama_cpp"):
        return "llama_cpp"
    if can_import_module("transformers"):
        return "transformers"

    return None


def find_local_model():
    """Return the path to a previously downloaded local model, if any."""
    models_dir = get_models_dir()
    if not os.path.isdir(models_dir):
        return None

    for root, _, files in os.walk(models_dir):
        for filename in files:
            if filename.endswith(".gguf"):
                return os.path.join(root, filename)

    return None


# ---------------------------------------------------------------------------
# Token estimation utilities
# ---------------------------------------------------------------------------


def estimate_tokens(text):
    """Estimate the number of tokens in a text (~4 characters per token).

    Args:
        text: The text string to estimate.

    Returns:
        Estimated token count (minimum 0).
    """
    if not text:
        return 0
    return max(1, len(str(text)) // 4)


def truncate_context(messages, max_tokens):
    """Truncate older messages when the estimated token count exceeds max_tokens.

    Keeps the most recent messages intact and truncates (summarizes) older ones
    to fit within the context budget.

    Args:
        messages: List of dicts with 'role' and 'content' keys, oldest first.
        max_tokens: Maximum allowed total tokens.

    Returns:
        Truncated list of messages fitting within the token budget.
    """
    if not messages:
        return messages

    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    if total <= max_tokens:
        return messages

    # Work from most recent backwards, keeping as many full messages as possible
    truncated = []
    kept_tokens = 0
    for m in reversed(messages):
        content = m.get("content", "")
        msg_tokens = estimate_tokens(content)
        if kept_tokens + msg_tokens <= max_tokens:
            truncated.insert(0, m)
            kept_tokens += msg_tokens
        else:
            # Partial inclusion with truncation notice
            budget = max_tokens - kept_tokens
            if budget > 2:
                max_chars = budget * 4
                truncated_content = content[:max_chars] + "\n...[truncated]"
                truncated.insert(0, {**m, "content": truncated_content})
            break

    return truncated


def _fit_prompt_to_context(system_prompt, user_prompt, max_tokens, n_ctx):
    """Trim prompt content and completion budget so the request fits the model window."""
    system_prompt = system_prompt or ""
    user_prompt = user_prompt or ""

    reserve_tokens = 256
    max_tokens = max(1, int(max_tokens or 0))
    n_ctx = max(1, int(n_ctx or 0))

    def _prompt_tokens(sys_text, user_text):
        return estimate_tokens(_format_chat_prompt(sys_text, user_text))

    prompt_tokens = _prompt_tokens(system_prompt, user_prompt)

    # Keep enough room for the reply and a small safety margin.
    max_prompt_tokens = max(1, n_ctx - max_tokens - reserve_tokens)
    if prompt_tokens > max_prompt_tokens:
        system_tokens = estimate_tokens(system_prompt)
        user_budget = max(0, max_prompt_tokens - system_tokens)
        if estimate_tokens(user_prompt) > user_budget:
            trimmed_chars = max(0, user_budget * 4)
            if trimmed_chars > 0:
                user_prompt = (
                    "[Earlier context trimmed to fit the model context window]\n"
                    + user_prompt[-trimmed_chars:]
                )
            else:
                user_prompt = "[Earlier context trimmed to fit the model context window]"

        prompt_tokens = _prompt_tokens(system_prompt, user_prompt)

    allowed_max_tokens = max(1, n_ctx - prompt_tokens - reserve_tokens)
    adjusted_max_tokens = min(max_tokens, allowed_max_tokens)
    return system_prompt, user_prompt, adjusted_max_tokens


# ---------------------------------------------------------------------------
# Subprocess runner script for the external Python interpreter
# ---------------------------------------------------------------------------

_LLAMA_CPP_RUNNER = r"""
import sys
from llama_cpp import Llama

model_path = sys.argv[1]
prompt_path = sys.argv[2]
max_tokens = int(sys.argv[3])
n_ctx = int(sys.argv[4]) if len(sys.argv) > 4 else 8192
temperature = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
top_p = float(sys.argv[6]) if len(sys.argv) > 6 else 0.85
repeat_penalty = float(sys.argv[7]) if len(sys.argv) > 7 else 1.1
top_k = int(sys.argv[8]) if len(sys.argv) > 8 else 40
repeat_last_n = int(sys.argv[9]) if len(sys.argv) > 9 else 64
mirostat_mode = int(sys.argv[10]) if len(sys.argv) > 10 else 2
mirostat_tau = float(sys.argv[11]) if len(sys.argv) > 11 else 3.0
mirostat_eta = float(sys.argv[12]) if len(sys.argv) > 12 else 0.1
min_p = float(sys.argv[13]) if len(sys.argv) > 13 else 0.0
grammar_path = sys.argv[14] if len(sys.argv) > 14 else ""
frequency_penalty = float(sys.argv[15]) if len(sys.argv) > 15 else 0.0
presence_penalty = float(sys.argv[16]) if len(sys.argv) > 16 else 0.0

with open(prompt_path, "r", encoding="utf-8") as handle:
    prompt = handle.read()

grammar = None
if grammar_path:
    with open(grammar_path, "r", encoding="utf-8") as handle:
        grammar = handle.read()

try:
    llm = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_batch=512,
        repeat_last_n=repeat_last_n,
        verbose=False,
    )
except TypeError:
    llm = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_batch=512,
        verbose=False,
    )
_kwargs = dict(
    prompt=prompt,
    max_tokens=max_tokens,
    temperature=temperature,
    top_p=top_p,
    top_k=top_k,
    repeat_penalty=repeat_penalty,
    mirostat_mode=mirostat_mode,
    mirostat_tau=mirostat_tau,
    mirostat_eta=mirostat_eta,
    min_p=min_p,
    frequency_penalty=frequency_penalty,
    presence_penalty=presence_penalty,
    grammar=grammar,
    stop=["<|im_end|>", "<|im_start|>user", "<|im_start|>system", "<|im_start|>assistant", "<|endoftext|>", "<|end|>", "</s>"],
)
try:
    response = llm(**_kwargs)
except TypeError:
    _kwargs.pop("frequency_penalty", None)
    _kwargs.pop("presence_penalty", None)
    try:
        response = llm(**_kwargs)
    except TypeError:
        _kwargs.pop("mirostat_mode", None)
        _kwargs.pop("mirostat_tau", None)
        _kwargs.pop("mirostat_eta", None)
        response = llm(**_kwargs)
if isinstance(response, dict):
    choices = response.get("choices") or []
    if choices:
        print(choices[0].get("text", "").strip())
    else:
        print("")
else:
    print(str(response).strip())
"""


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def _extract_llama_cpp_text(response):
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            return choices[0].get("text", "").strip()
    return str(response).strip()


def _find_gguf_path(resolved_source):
    """Find a .gguf file path from a resolved model source."""
    if os.path.isfile(resolved_source) and resolved_source.endswith(".gguf"):
        return resolved_source
    if os.path.isdir(resolved_source):
        for f in os.listdir(resolved_source):
            if f.endswith(".gguf"):
                return os.path.join(resolved_source, f)
    return None


def _build_stream_completion_kwargs(prompt, **kwargs):
    """Build kwargs dict for llama.cpp completion calls (both stream and non-stream)."""
    completion_kwargs = {
        "prompt": prompt,
        "max_tokens": kwargs.get("max_tokens", 512),
        "temperature": kwargs.get("temperature", 0.5),
        "top_p": kwargs.get("top_p", 0.85),
        "top_k": kwargs.get("top_k", 40),
        "repeat_penalty": kwargs.get("repeat_penalty", 1.1),
        "mirostat_mode": kwargs.get("mirostat_mode", 2),
        "stop": [
            "<|im_end|>",
            "<|im_start|>user",
            "<|im_start|>system",
            "<|im_start|>assistant",
            "<|endoftext|>",
            "<|end|>",
            "</s>",
        ],
    }
    if kwargs.get("mirostat_mode", 2) > 0:
        completion_kwargs["mirostat_tau"] = kwargs.get("mirostat_tau", 3.0)
        completion_kwargs["mirostat_eta"] = kwargs.get("mirostat_eta", 0.1)
    if kwargs.get("min_p", 0) > 0:
        completion_kwargs["min_p"] = kwargs.get("min_p", 0.0)
    if kwargs.get("grammar") is not None:
        completion_kwargs["grammar"] = kwargs.get("grammar")
    return completion_kwargs


def stream_generate_text(
    model_source,
    system_prompt,
    user_prompt,
    **kwargs,
):
    """Generator that yields text tokens one at a time from the model.

    Uses llama.cpp's streaming mode for GGUF models.
    For other backends (transformers, external subprocess), yields the
    complete response as a single token as a fallback.

    Args:
        model_source: Path or URL to the model.
        system_prompt: System-level instructions.
        user_prompt: The user's request.
        **kwargs: Inference parameters (max_tokens, temperature, etc.).

    Yields:
        str: Text tokens as they are generated.
    """
    resolved_source = resolve_model_source(model_source)
    if not resolved_source:
        raise RuntimeError("Could not resolve the AI model path.")

    n_ctx = kwargs.get("n_ctx", 8192)
    max_tokens = kwargs.get("max_tokens", 512)
    system_prompt, user_prompt, max_tokens = _fit_prompt_to_context(
        system_prompt, user_prompt, max_tokens, n_ctx
    )
    kwargs["max_tokens"] = max_tokens

    prompt_text = _format_chat_prompt(system_prompt, user_prompt)
    gguf_path = _find_gguf_path(resolved_source)

    if gguf_path:
        Llama = _safe_import_llama_cpp()
        if Llama is not None:
            yield from _stream_from_llama_cpp_inprocess(
                gguf_path, prompt_text, **kwargs
            )
            return
        # fallback: external subprocess or full generation
        result = _generate_with_llama_cpp(gguf_path, prompt_text, **kwargs)
        if result:
            yield result
        return

    # Fallback for non-GGUF models
    response = generate_text_from_model(
        model_source, system_prompt, user_prompt, **kwargs
    )
    if response:
        yield response


def _stream_from_llama_cpp_inprocess(model_path, prompt, **kwargs):
    """Stream tokens from llama.cpp in the current process."""
    Llama = _safe_import_llama_cpp()
    if Llama is None:
        raise RuntimeError("llama-cpp-python is not installed.")

    n_ctx = kwargs.get("n_ctx", 8192)
    n_batch = kwargs.get("n_batch", 512)
    n_threads = kwargs.get("n_threads")

    cache_key = (model_path, n_ctx, n_batch, n_threads)
    if cache_key in _model_cache:
        llm = _model_cache[cache_key]
    else:
        llama_kwargs = {
            "model_path": model_path,
            "n_ctx": n_ctx,
            "n_batch": n_batch,
            "repeat_last_n": kwargs.get("repeat_last_n", 64),
            "verbose": False,
        }
        if n_threads is not None:
            llama_kwargs["n_threads"] = n_threads
        try:
            llm = Llama(**llama_kwargs)
            _model_cache[cache_key] = llm
        except TypeError as e:
            match = re.search(r"unexpected keyword argument '(\w+)'", str(e))
            if match and match.group(1) in llama_kwargs:
                _ = llama_kwargs.pop(match.group(1))
                llm = Llama(**llama_kwargs)
                _model_cache[cache_key] = llm
            else:
                raise RuntimeError(f"Failed to load model: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to load model: {e}")

    completion_kwargs = _build_stream_completion_kwargs(prompt, **kwargs)
    completion_kwargs["stream"] = True

    start_time = time.time()
    token_count = 0
    try:
        for chunk in llm(**completion_kwargs):
            if not isinstance(chunk, dict):
                continue
            choices = chunk.get("choices", [])
            if choices:
                token = choices[0].get("text", "")
                if token:
                    token_count += 1
                    yield token

        elapsed = time.time() - start_time
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
            f"Streaming: {elapsed:.2f}s, {token_count} tokens"
        )
    except Exception as e:
        err_str = str(e).lower()
        oom_keywords = ["out of memory", "cuda out of memory", "cuda oom"]
        if any(kw in err_str for kw in oom_keywords):
            if cache_key in _model_cache:
                del _model_cache[cache_key]
            reduced_ctx = max(512, n_ctx // 2)
            reduced_kwargs = dict(llama_kwargs)
            reduced_kwargs["n_ctx"] = reduced_ctx
            try:
                llm_recovery = Llama(**reduced_kwargs)
                completion_kwargs["max_tokens"] = min(
                    kwargs.get("max_tokens", 512), 128
                )
                for chunk in llm_recovery(**completion_kwargs):
                    if isinstance(chunk, dict):
                        choices = chunk.get("choices", [])
                        if choices:
                            token = choices[0].get("text", "")
                            if token:
                                yield token
                return
            except Exception as e2:
                raise RuntimeError(f"Model still OOM after reducing context: {e2}")
        raise RuntimeError(f"Streaming generation failed: {e}")


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------


def _generate_with_llama_cpp_external(
    model_path,
    prompt,
    max_tokens=256,
    n_ctx=8192,
    temperature=0.5,
    top_p=0.85,
    repeat_penalty=1.1,
    top_k=40,
    repeat_last_n=64,
    mirostat_mode=2,
    mirostat_tau=3.0,
    mirostat_eta=0.1,
    min_p=0.0,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    grammar=None,
):
    from src.utils import get_python_executable

    python_exe = get_python_executable()
    if python_exe == sys.executable:
        raise RuntimeError(
            "The model is a GGUF model, but llama-cpp-python is not available. "
            "Install Python 3 and run: pip install llama-cpp-python"
        )

    prompt_path = None
    grammar_temp = None
    grammar_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            delete=False,
        ) as handle:
            handle.write(prompt)
            prompt_path = handle.name

        if grammar:
            grammar_temp = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".gbnf",
                delete=False,
            )
            grammar_temp.write(grammar)
            grammar_path = grammar_temp.name
            grammar_temp.close()

        start_time = time.time()
        result = subprocess.run(
            [
                python_exe,
                "-c",
                _LLAMA_CPP_RUNNER,
                model_path,
                prompt_path,
                str(max_tokens),
                str(n_ctx),
                str(temperature),
                str(top_p),
                str(repeat_penalty),
                str(top_k),
                str(repeat_last_n),
                str(mirostat_mode),
                str(mirostat_tau),
                str(mirostat_eta),
                str(min_p),
                grammar_path,
                str(frequency_penalty),
                str(presence_penalty),
            ],
            capture_output=True,
            text=True,
            timeout=900,
            creationflags=_subprocess_creationflags(),
        )
        elapsed = time.time() - start_time
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
            f"External llama_cpp completed in {elapsed:.2f}s "
            f"(max_tokens={max_tokens}, n_ctx={n_ctx})"
        )

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                "llama-cpp-python failed while running from the external Python interpreter. "
                f"{detail}"
            )
        return result.stdout.strip()
    finally:
        if prompt_path and os.path.exists(prompt_path):
            os.remove(prompt_path)
        if grammar_path and os.path.exists(grammar_path):
            os.remove(grammar_path)


def _generate_with_llama_cpp(
    model_path,
    prompt,
    max_tokens=256,
    n_ctx=8192,
    n_batch=512,
    n_threads=None,
    temperature=0.5,
    top_p=0.85,
    repeat_penalty=1.1,
    top_k=40,
    repeat_last_n=64,
    mirostat_mode=2,
    mirostat_tau=3.0,
    mirostat_eta=0.1,
    min_p=0.0,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    grammar=None,
):
    Llama = _safe_import_llama_cpp()
    if Llama is None:
        if _can_use_external_llama_cpp():
            return _generate_with_llama_cpp_external(
                model_path,
                prompt,
                max_tokens=max_tokens,
                n_ctx=n_ctx,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                top_k=top_k,
                repeat_last_n=repeat_last_n,
                mirostat_mode=mirostat_mode,
                mirostat_tau=mirostat_tau,
                mirostat_eta=mirostat_eta,
                min_p=min_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                grammar=grammar,
            )
        raise RuntimeError("The llama-cpp backend is not installed.")

    cache_key = (model_path, n_ctx, n_batch, n_threads)
    if cache_key not in _model_cache:
        llama_kwargs = {
            "model_path": model_path,
            "n_ctx": n_ctx,
            "n_batch": n_batch,
            "repeat_last_n": repeat_last_n,
            "verbose": False,
        }
        if n_threads is not None:
            llama_kwargs["n_threads"] = n_threads
        try:
            _model_cache[cache_key] = Llama(**llama_kwargs)
        except TypeError as _llama_te:
            _llama_match = re.search(
                r"unexpected keyword argument '(\w+)'", str(_llama_te)
            )
            if _llama_match and _llama_match.group(1) in llama_kwargs:
                _ = llama_kwargs.pop(_llama_match.group(1))
                _model_cache[cache_key] = Llama(**llama_kwargs)
            else:
                raise RuntimeError(f"Failed to load model: {_llama_te}")
        except Exception as e:
            raise RuntimeError(f"Failed to load model: {e}")

    llm = _model_cache[cache_key]
    completion_kwargs = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "repeat_penalty": repeat_penalty,
        "mirostat_mode": mirostat_mode,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
        "stop": [
            "<|im_end|>",
            "<|im_start|>user",
            "<|im_start|>system",
            "<|im_start|>assistant",
            "<|endoftext|>",
            "<|end|>",
            "</s>",
        ],
    }
    if mirostat_mode > 0:
        completion_kwargs["mirostat_tau"] = mirostat_tau
        completion_kwargs["mirostat_eta"] = mirostat_eta
    if min_p > 0:
        completion_kwargs["min_p"] = min_p
    if grammar is not None:
        completion_kwargs["grammar"] = grammar

    start_time = time.time()
    try:
        try:
            response = llm(**completion_kwargs)
        except TypeError as _call_te:
            _call_match = re.search(
                r"unexpected keyword argument '(\w+)'", str(_call_te)
            )
            if _call_match and _call_match.group(1) in completion_kwargs:
                _ = completion_kwargs.pop(_call_match.group(1))
                response = llm(**completion_kwargs)
            else:
                raise
        elapsed = time.time() - start_time

        # Log token usage and timing
        if isinstance(response, dict):
            usage = response.get("usage", {})
            prompt_toks = usage.get("prompt_tokens", "?")
            completion_toks = usage.get("completion_tokens", "?")
            total_toks = usage.get("total_tokens", "?")
        else:
            prompt_toks = "?"
            completion_toks = "?"
            total_toks = "?"
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
            f"llama_cpp: {elapsed:.2f}s, "
            f"prompt={prompt_toks} toks, completion={completion_toks} toks, total={total_toks} toks"
        )

        return _extract_llama_cpp_text(response)
    except Exception as e:
        err_str = str(e).lower()
        elapsed = time.time() - start_time
        oom_keywords = [
            "out of memory",
            "cuda out of memory",
            "cuda oom",
            "memory error",
            "cuda_error",
            "cuda malloc",
        ]
        if any(kw in err_str for kw in oom_keywords):
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
                f"OOM detected after {elapsed:.2f}s: {e}. Reducing context and retrying..."
            )
            # Free the cached model so memory is reclaimed
            if cache_key in _model_cache:
                del _model_cache[cache_key]

            reduced_ctx = max(512, n_ctx // 2)
            reduced_batch = max(64, n_batch // 2)
            reduced_max_tokens = min(max_tokens, 128)
            recovery_kwargs = {
                "model_path": model_path,
                "n_ctx": reduced_ctx,
                "n_batch": reduced_batch,
                "repeat_last_n": repeat_last_n,
                "verbose": False,
            }
            if n_threads is not None:
                recovery_kwargs["n_threads"] = n_threads
            try:
                llm_recovery = Llama(**recovery_kwargs)
                completion_kwargs["max_tokens"] = reduced_max_tokens
                response2 = llm_recovery(**completion_kwargs)
                return _extract_llama_cpp_text(response2)
            except Exception as e2:
                raise RuntimeError(
                    f"Model still OOM after reducing context (n_ctx={reduced_ctx}): {e2}"
                )
        raise RuntimeError(f"llama-cpp generation failed: {e}")


def _generate_with_transformers(model_path, prompt, max_tokens=256):
    impl = _safe_import_transformers()
    if impl is None:
        raise RuntimeError("The transformers/torch libraries are not installed.")

    torch, AutoModelForCausalLM, AutoTokenizer = impl
    if model_path not in _model_cache:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            device_map="auto",
            torch_dtype=None,
        )
        _model_cache[model_path] = (tokenizer, model)

    tokenizer, model = _model_cache[model_path]
    input_ids = tokenizer(prompt, return_tensors="pt").input_ids
    try:
        import torch as _torch

        if _torch.cuda.is_available():
            input_ids = input_ids.cuda()
    except Exception:
        pass

    start_time = time.time()
    outputs = model.generate(
        input_ids,
        max_new_tokens=max_tokens,
        do_sample=True,
        top_p=0.9,
        temperature=0.7,
    )
    elapsed = time.time() - start_time
    generated_ids = outputs[0][input_ids.shape[-1] :]
    output = tokenizer.decode(generated_ids, skip_special_tokens=True)
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
        f"transformers: {elapsed:.2f}s, generated ~{len(generated_ids)} tokens"
    )
    return output.strip()


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def _format_chat_prompt(system_prompt, user_prompt):
    """Format prompts for instruct/chat-tuned models (ChatML format for Qwen)."""
    return (
        "<|im_start|>system\n"
        f"{system_prompt.strip()}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"{user_prompt.strip()}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


# ---------------------------------------------------------------------------
# Public generation API
# ---------------------------------------------------------------------------


def generate_text_from_model(
    model_source,
    system_prompt,
    user_prompt,
    max_tokens=512,
    n_ctx=8192,
    n_batch=512,
    n_threads=None,
    temperature=0.5,
    top_p=0.85,
    repeat_penalty=1.1,
    top_k=40,
    repeat_last_n=64,
    mirostat_mode=2,
    mirostat_tau=3.0,
    mirostat_eta=0.1,
    min_p=0.0,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    grammar=None,
):
    resolved_source = resolve_model_source(model_source)
    if not resolved_source:
        raise RuntimeError("Could not resolve the AI model path.")

    system_prompt, user_prompt, max_tokens = _fit_prompt_to_context(
        system_prompt, user_prompt, max_tokens, n_ctx
    )

    prompt_text = _format_chat_prompt(system_prompt, user_prompt)

    is_gguf = False
    gguf_path = None
    if os.path.isfile(resolved_source) and resolved_source.endswith(".gguf"):
        is_gguf = True
        gguf_path = resolved_source
    elif os.path.isdir(resolved_source):
        for f in os.listdir(resolved_source):
            if f.endswith(".gguf"):
                is_gguf = True
                gguf_path = os.path.join(resolved_source, f)
                break

    if is_gguf:
        current_temp = temperature
        last_error = None
        for attempt in range(2):
            try:
                result = _generate_with_llama_cpp(
                    gguf_path,
                    prompt_text,
                    max_tokens=max_tokens,
                    n_ctx=n_ctx,
                    n_batch=n_batch,
                    n_threads=n_threads,
                    temperature=current_temp,
                    top_p=top_p,
                    repeat_penalty=repeat_penalty,
                    top_k=top_k,
                    repeat_last_n=repeat_last_n,
                    mirostat_mode=mirostat_mode,
                    mirostat_tau=mirostat_tau,
                    mirostat_eta=mirostat_eta,
                    min_p=min_p,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
                    grammar=grammar,
                )
                if result and result.strip():
                    return result
                # Empty response -- retry with lower temperature
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
                    f"Empty response (attempt {attempt + 1}/2), retrying with lower temperature..."
                )
                current_temp = max(0.1, current_temp - 0.1)
            except Exception as e:
                last_error = e
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
                    f"Error on attempt {attempt + 1}/2: {e}"
                )
                if attempt == 0:
                    current_temp = max(0.1, current_temp - 0.1)
                else:
                    raise RuntimeError(
                        f"llama-cpp generation failed after 2 attempts: {last_error}"
                    )
        return ""
    else:
        transformers_impl = _safe_import_transformers()
        if transformers_impl is None:
            raise RuntimeError(
                "The model is a Safetensors/PyTorch model, but transformers and torch are not installed. "
                "Install them or download a GGUF model (.gguf) to use with llama-cpp-python."
            )
        return _generate_with_transformers(
            resolved_source, prompt_text, max_tokens=max_tokens
        )


def preload_model(
    model_source,
    n_ctx=8192,
    n_batch=512,
    n_threads=None,
):
    """Preload model into cache without generating text. Useful for warming up the model."""
    try:
       resolved_source = resolve_model_source(model_source)
       if not resolved_source:
           raise RuntimeError("Could not resolve the AI model path.")

       is_gguf = False
       gguf_path = None
       if os.path.isfile(resolved_source) and resolved_source.endswith(".gguf"):
           is_gguf = True
           gguf_path = resolved_source
       elif os.path.isdir(resolved_source):
           for f in os.listdir(resolved_source):
               if f.endswith(".gguf"):
                   is_gguf = True
                   gguf_path = os.path.join(resolved_source, f)
                   break

       if is_gguf:
           # Preload GGUF model
           Llama = _safe_import_llama_cpp()
           if Llama is None:
               if _can_use_external_llama_cpp():
                   return  # External process handles it
               raise RuntimeError("The llama-cpp backend is not installed.")

           cache_key = (gguf_path, n_ctx, n_batch, n_threads)
           if cache_key not in _model_cache:
               llama_kwargs = {
                   "model_path": gguf_path,
                   "n_ctx": n_ctx,
                   "n_batch": n_batch,
                   "verbose": False,
               }
               if n_threads is not None:
                   llama_kwargs["n_threads"] = n_threads
               try:
                   _model_cache[cache_key] = Llama(**llama_kwargs)
                   print(
                       f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
                       f"Model preloaded: {gguf_path}"
                   )
               except TypeError:
                   _llama_match = re.search(
                       r"unexpected keyword argument '(\w+)'", str(sys.exc_info()[1])
                   )
                   if _llama_match and _llama_match.group(1) in llama_kwargs:
                       _ = llama_kwargs.pop(_llama_match.group(1))
                       _model_cache[cache_key] = Llama(**llama_kwargs)
                       print(
                           f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
                           f"Model preloaded: {gguf_path}"
                       )
               except Exception as e:
                   raise RuntimeError(f"Failed to preload model: {e}")
       else:
           # Preload transformers model
           impl = _safe_import_transformers()
           if impl is None:
               raise RuntimeError("The transformers/torch libraries are not installed.")

           torch, AutoModelForCausalLM, AutoTokenizer = impl
           if resolved_source not in _model_cache:
               tokenizer = AutoTokenizer.from_pretrained(
                   resolved_source, trust_remote_code=True
               )
               model = AutoModelForCausalLM.from_pretrained(
                   resolved_source,
                   trust_remote_code=True,
                   device_map="auto",
                   torch_dtype=None,
               )
               _model_cache[resolved_source] = (tokenizer, model)
               print(
                   f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] "
                   f"Model preloaded: {resolved_source}"
               )
    except Exception as e:
       print(f"[AI Engine] Model preload warning (non-critical): {e}")

