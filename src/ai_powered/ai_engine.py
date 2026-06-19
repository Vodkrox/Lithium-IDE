import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from urllib.parse import urlparse

from src.ai_powered.ai_level import get_default_model


def _get_appdata_dir():
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.getenv("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "LithiumIDE")


def get_models_dir():
    return os.path.join(_get_appdata_dir(), "models")

_model_cache = {}
_model_cache_lock = threading.Lock()
_model_cache_pending = {}

MODEL_CANDIDATES = [get_default_model()]

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert code-editing assistant inside Lithium IDE. "
    "You respond in the same language the user uses (English, Spanish, etc.). "
    "When the user asks you to change the current file, you MUST output only executable skill XML tags, not explanations. "
    "Prefer minimal, correct, production-ready changes over verbose rewrites. "
    "If the current file contains invalid syntax or unrelated text, fix it by deleting/replacing lines before adding new code. "
    "If needed, replace the entire file content using replace_file when the current content is not salvageable. "
    "Never answer with meta-instructions like 'XML tags must be well-formed' or 'Propose the changes'; emit the actual <skill> blocks instead. "
    "Be concise, precise, and complete."
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
        repo_id = source[len("hf://"):]
        model_name = repo_id.replace("/", "-")
        target_dir = os.path.join(get_models_dir(), model_name)
        if os.path.exists(target_dir):
            return target_dir
        raise FileNotFoundError(f"Model has not been downloaded yet. Please download it from the AI menu.")

    if source.startswith("http://") or source.startswith("https://"):
        return _download_model_url(source)

    if os.path.exists(source):
        return source

    raise FileNotFoundError(f"Local model not found: {source}")


def _download_model_url(url, progress_callback=None):
    if url.startswith("hf://"):
        repo_id = url[len("hf://"):]
        if not repo_id:
            raise ValueError("Hugging Face repo id not provided in hf:// URL")

        model_name = repo_id.replace("/", "-")
        target_dir = os.path.join(get_models_dir(), model_name)
        os.makedirs(target_dir, exist_ok=True)

        try:
            from huggingface_hub import HfApi, get_token
        except Exception:
            import subprocess
            import importlib
            from src.utils import get_python_executable
            try:
                subprocess.check_call([get_python_executable(), "-m", "pip", "install", "huggingface_hub"])
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
            progress_callback(os.path.getsize(target_path), os.path.getsize(target_path))
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
    return _download_model_url(url, progress_callback=progress_callback)


def clear_model_cache():
    with _model_cache_lock:
        for ready_event in _model_cache_pending.values():
            ready_event.set()
        _model_cache_pending.clear()
        _model_cache.clear()


def _get_cached_model(cache_key, factory):
    should_create = False
    with _model_cache_lock:
        cached_model = _model_cache.get(cache_key)
        if cached_model is not None:
            return cached_model

        ready_event = _model_cache_pending.get(cache_key)
        if ready_event is None:
            ready_event = threading.Event()
            _model_cache_pending[cache_key] = ready_event
            should_create = True

    if should_create:
        try:
            cached_model = factory()
        except Exception:
            with _model_cache_lock:
                _model_cache_pending.pop(cache_key, None)
                ready_event.set()
            raise

        with _model_cache_lock:
            _model_cache[cache_key] = cached_model
            _model_cache_pending.pop(cache_key, None)
            ready_event.set()
            return cached_model

    ready_event.wait()
    with _model_cache_lock:
        cached_model = _model_cache.get(cache_key)

    if cached_model is None:
        raise RuntimeError(
            "Model initialization failed because another thread hit an error while loading the model."
        )

    return cached_model


def list_model_candidates():
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
    models_dir = get_models_dir()
    if not os.path.isdir(models_dir):
        return None

    for root, _, files in os.walk(models_dir):
        for filename in files:
            if filename.endswith(".gguf"):
                return os.path.join(root, filename)

    return None


_LLAMA_CPP_RUNNER = r"""
import sys
from llama_cpp import Llama

model_path = sys.argv[1]
prompt_path = sys.argv[2]
max_tokens = int(sys.argv[3])

with open(prompt_path, "r", encoding="utf-8") as handle:
    prompt = handle.read()

llm = Llama(
    model_path=model_path,
    n_ctx=8192,
    n_batch=512,
    verbose=False,
)
response = llm(
    prompt=prompt,
    max_tokens=max_tokens,
    temperature=0.5,
    top_p=0.85,
    repeat_penalty=1.1,
    stop=["<|im_end|>", "<|im_start|>user", "<|im_start|>system"],
)
if isinstance(response, dict):
    choices = response.get("choices") or []
    if choices:
        print(choices[0].get("text", "").strip())
    else:
        print("")
else:
    print(str(response).strip())
"""


def _extract_llama_cpp_text(response):
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            return choices[0].get("text", "").strip()
    return str(response).strip()


def _generate_with_llama_cpp_external(model_path, prompt, max_tokens=256):
    from src.utils import get_python_executable

    python_exe = get_python_executable()
    if python_exe == sys.executable:
        raise RuntimeError(
            "The model is a GGUF model, but llama-cpp-python is not available. "
            "Install Python 3 and run: pip install llama-cpp-python"
        )

    prompt_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            delete=False,
        ) as handle:
            handle.write(prompt)
            prompt_path = handle.name

        result = subprocess.run(
            [python_exe, "-c", _LLAMA_CPP_RUNNER, model_path, prompt_path, str(max_tokens)],
            capture_output=True,
            text=True,
            timeout=900,
            creationflags=_subprocess_creationflags(),
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
):
    Llama = _safe_import_llama_cpp()
    if Llama is None:
        if _can_use_external_llama_cpp():
            return _generate_with_llama_cpp_external(model_path, prompt, max_tokens=max_tokens)
        raise RuntimeError("The llama-cpp backend is not installed.")

    cache_key = (model_path, n_ctx, n_batch, n_threads)

    def create_llama():
        llama_kwargs = {
            "model_path": model_path,
            "n_ctx": n_ctx,
            "n_batch": n_batch,
            "verbose": False,
        }
        if n_threads is not None:
            llama_kwargs["n_threads"] = n_threads
        return Llama(**llama_kwargs)

    llm = _get_cached_model(cache_key, create_llama)
    response = llm(
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        repeat_penalty=repeat_penalty,
        stop=["<|im_end|>", "<|im_start|>user", "<|im_start|>system"],
    )

    return _extract_llama_cpp_text(response)


def _generate_with_transformers(model_path, prompt, max_tokens=256):
    impl = _safe_import_transformers()
    if impl is None:
        raise RuntimeError("The transformers/torch libraries are not installed.")

    torch, AutoModelForCausalLM, AutoTokenizer = impl

    def create_transformers_model():
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            device_map="auto",
            torch_dtype="auto",
        )
        return tokenizer, model

    tokenizer, model = _get_cached_model(model_path, create_transformers_model)
    input_ids = tokenizer(prompt, return_tensors="pt").input_ids
    try:
        import torch as _torch
        if _torch.cuda.is_available():
            input_ids = input_ids.cuda()
    except Exception:
        pass

    outputs = model.generate(
        input_ids,
        max_new_tokens=max_tokens,
        do_sample=True,
        top_p=0.9,
        temperature=0.7,
    )
    generated_ids = outputs[0][input_ids.shape[-1]:]
    output = tokenizer.decode(generated_ids, skip_special_tokens=True)
    return output.strip()


def _format_chat_prompt(system_prompt, user_prompt):
    return (
        "<|im_start|>system\n"
        f"{system_prompt.strip()}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"{user_prompt.strip()}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


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
):
    resolved_source = resolve_model_source(model_source)
    if not resolved_source:
        raise RuntimeError("Could not resolve the AI model path.")

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
        return _generate_with_llama_cpp(
            gguf_path,
            prompt_text,
            max_tokens=max_tokens,
            n_ctx=n_ctx,
            n_batch=n_batch,
            n_threads=n_threads,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
        )
    else:
        transformers_impl = _safe_import_transformers()
        if transformers_impl is None:
            raise RuntimeError(
                "The model is a Safetensors/PyTorch model, but transformers and torch are not installed. "
                "Install them or download a GGUF model (.gguf) to use with llama-cpp-python."
            )
        return _generate_with_transformers(resolved_source, prompt_text, max_tokens=max_tokens)
