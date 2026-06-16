import os
import urllib.request
from urllib.parse import urlparse

_model_cache = {}

# Hardcoded single built-in model (only one option will be offered).
# Edit these values here to change the built-in model candidate and prompt.
# Use the `hf://<repo_id>` scheme to let Lithium download from Hugging Face directly.
# Replace <REPO_ID> with the official Hugging Face repo id you intend to use.
MODEL_CANDIDATES = [
    ("Qwen2.5-Coder-7B-GGUF", "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf"),
]

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful programming assistant. You help users write, edit, and understand code. "
    "You respond in the same language the user uses (English, Spanish, etc.). "
    "You are concise and clear in your responses. "
    "You have special skills to modify code and files when needed - use them when the user asks you to make changes."
)


def _safe_import_transformers():
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        return torch, AutoModelForCausalLM, AutoTokenizer
    except Exception:
        return None


def _safe_import_llama_cpp():
    try:
        from llama_cpp import Llama
        return Llama
    except Exception:
        return None


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
        target_dir = os.path.join(".models", model_name)
        if os.path.exists(target_dir):
            return target_dir
        raise FileNotFoundError(f"Model has not been downloaded yet. Please download it from the AI menu.")

    if source.startswith("http://") or source.startswith("https://"):
        return _download_model_url(source)

    if os.path.exists(source):
        return source

    raise FileNotFoundError(f"Local model not found: {source}")


def _download_model_url(url, progress_callback=None):
    # Hugging Face scheme: hf://<repo_id>
    if url.startswith("hf://"):
        repo_id = url[len("hf://"):]
        if not repo_id:
            raise ValueError("Hugging Face repo id not provided in hf:// URL")

        model_name = repo_id.replace("/", "-")
        target_dir = os.path.join(".models", model_name)
        os.makedirs(target_dir, exist_ok=True)

        try:
            from huggingface_hub import HfApi, get_token
        except Exception:
            import subprocess
            import sys
            import importlib
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
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

    # HTTP/HTTPS download (file-level)
    parsed = urlparse(url)
    file_name = os.path.basename(parsed.path) or parsed.netloc
    file_name = file_name.split("/")[0]
    if not file_name:
        file_name = "model.bin"

    model_name = os.path.splitext(file_name)[0]
    target_dir = os.path.join(".models", model_name)
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
    """Public wrapper to download a model URL with optional progress callback."""
    return _download_model_url(url, progress_callback=progress_callback)


def list_model_candidates():
    """Return a list of model candidates."""
    return [MODEL_CANDIDATES[0]] if MODEL_CANDIDATES else []


def get_runtime_status():
    llama_cpp = _safe_import_llama_cpp()
    if llama_cpp is not None:
        return "llama_cpp"

    transformers_impl = _safe_import_transformers()
    if transformers_impl is not None:
        return "transformers"

    return None


def _generate_with_llama_cpp(model_path, prompt, max_tokens=256):
    Llama = _safe_import_llama_cpp()
    if Llama is None:
        raise RuntimeError("The llama-cpp backend is not installed.")

    if model_path not in _model_cache:
        # Optimize for speed while utilizing model capacity
        _model_cache[model_path] = Llama(
            model_path=model_path,
            n_ctx=8192,  # Good balance of speed and context
            n_batch=512,  # Larger batch for speed
            verbose=False
        )

    llm = _model_cache[model_path]
    response = llm(
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=0.5,  # Lower temperature for faster, more focused responses
        top_p=0.85,
        repeat_penalty=1.1,
    )

    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            return choices[0].get("text", "").strip()
    return str(response).strip()


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
            torch_dtype=\
                None,
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

    outputs = model.generate(
        input_ids,
        max_new_tokens=max_tokens,
        do_sample=True,
        top_p=0.9,
        temperature=0.7,
    )
    output = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return output.strip()


def generate_text_from_model(model_source, system_prompt, user_prompt, max_tokens=256):
    resolved_source = resolve_model_source(model_source)
    if not resolved_source:
        raise RuntimeError("Could not resolve the AI model path.")

    prompt_text = system_prompt.strip()
    if prompt_text:
        prompt_text += "\n\n"
    prompt_text += user_prompt.strip()

    # Determine if the resolved model is a GGUF file or contains one
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
        llama_cpp = _safe_import_llama_cpp()
        if llama_cpp is None:
            raise RuntimeError(
                "The model is a GGUF model, but llama-cpp-python is not installed. "
                "Install it to run this model."
            )
        return _generate_with_llama_cpp(gguf_path, prompt_text, max_tokens=max_tokens)
    else:
        transformers_impl = _safe_import_transformers()
        if transformers_impl is None:
            raise RuntimeError(
                "The model is a Safetensors/PyTorch model, but transformers and torch are not installed. "
                "Install them or download a GGUF model (.gguf) to use with llama-cpp-python."
            )
        return _generate_with_transformers(resolved_source, prompt_text, max_tokens=max_tokens)



