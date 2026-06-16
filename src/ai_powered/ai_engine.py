import os
import urllib.request
from urllib.parse import urlparse

_model_cache = {}

# Hardcoded single built-in model (only one option will be offered).
# Edit these values here to change the built-in model candidate and prompt.
# Use the `hf://<repo_id>` scheme to let Lithium download from Hugging Face directly.
# Replace <REPO_ID> with the official Hugging Face repo id you intend to use.
MODEL_CANDIDATES = [
    ("Qwen2.5-Coder-1.5B", "hf://Qwen/Qwen2.5-Coder-1.5B"),
]

DEFAULT_SYSTEM_PROMPT = (
    "You are a programming assistant that responds in English."
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
            from huggingface_hub import HfApi, HfFolder
        except Exception:
            raise RuntimeError("The 'huggingface_hub' package is required to download from Hugging Face. Install it with 'pip install huggingface_hub'")

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
            token = HfFolder.get_token()
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


def list_model_candidates(link_file):
    """Return a list of model candidates from the link file.

    Each entry is a tuple (name, url). If name cannot be derived, url is used as name.
    """
    candidates = []
    if not os.path.exists(link_file):
        # fallback to built-in candidates
        # Always return exactly one candidate (the built-in first entry).
        return [MODEL_CANDIDATES[0]] if MODEL_CANDIDATES else []

    with open(link_file, "r", encoding="utf-8") as f:
        for line in f:
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            for part in entry.split(","):
                part = part.strip()
                if not part:
                    continue
                part = part.split("/=")[0]
                candidate = part.rstrip(".,;\n\r")
                if candidate:
                    # derive a display name from path
                    name = os.path.splitext(os.path.basename(candidate))[0] or candidate
                    candidates.append((name, candidate))
    # Only expose a single candidate to the UI: prefer file entry but return first only.
    if candidates:
        return [candidates[0]]
    return [MODEL_CANDIDATES[0]] if MODEL_CANDIDATES else []


def load_model_source(link_file):
    if not os.path.exists(link_file):
        # fallback to first built-in candidate
        if MODEL_CANDIDATES:
            return MODEL_CANDIDATES[0][1]
        return None

    with open(link_file, "r", encoding="utf-8") as f:
        for line in f:
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            for part in entry.split(","):
                part = part.strip()
                if not part:
                    continue
                part = part.split("/=")[0]
                candidate = part.rstrip(".,;\n\r")
                if candidate.startswith("http://") or candidate.startswith("https://") or candidate.startswith("file://") or os.path.exists(candidate):
                    return candidate
    return None


def load_system_prompt(prompt_file):
    if not os.path.exists(prompt_file):
        return DEFAULT_SYSTEM_PROMPT
    with open(prompt_file, "r", encoding="utf-8") as f:
        return f.read().strip()


def save_model_settings(link_file, prompt_file, model_source, system_prompt):
    os.makedirs(os.path.dirname(link_file), exist_ok=True)
    with open(link_file, "w", encoding="utf-8") as f:
        f.write(model_source.strip() + "\n")

    os.makedirs(os.path.dirname(prompt_file), exist_ok=True)
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(system_prompt.strip() + "\n")


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
        _model_cache[model_path] = Llama(model_path=model_path)

    llm = _model_cache[model_path]
    response = llm.create(
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=0.7,
        top_p=0.9,
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

    runtime = get_runtime_status()
    if runtime == "llama_cpp":
        return _generate_with_llama_cpp(resolved_source, prompt_text, max_tokens=max_tokens)

    if runtime == "transformers":
        return _generate_with_transformers(resolved_source, prompt_text, max_tokens=max_tokens)

    raise RuntimeError(
        "No local backend is installed to run the model. "
        "Install llama-cpp or transformers and torch in your Python environment."
    )


def ensure_ai_files(link_file, prompt_file):
    os.makedirs(os.path.dirname(link_file), exist_ok=True)
    if not os.path.exists(link_file):
        with open(link_file, "w", encoding="utf-8") as f:
            f.write("# Model candidates (name, url)\n")
            # Write only the single built-in candidate.
            if MODEL_CANDIDATES:
                name, url = MODEL_CANDIDATES[0]
                f.write(f"{name}, {url}\n")

    os.makedirs(os.path.dirname(prompt_file), exist_ok=True)
    if not os.path.exists(prompt_file):
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(DEFAULT_SYSTEM_PROMPT + "\n")
