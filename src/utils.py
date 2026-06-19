
import subprocess
import sys
import os
import shutil


def resource_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):

        base_path = sys._MEIPASS
    else:

        base_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)


def get_python_executable() -> str:
    if not getattr(sys, "frozen", False):

        return sys.executable



    for name in ("py", "python3", "python"):
        found = shutil.which(name)
        if found:
            return found


    if sys.platform == "win32":
        import glob
        patterns = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python*", "python.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Python*", "python.exe"),
            os.path.join(os.environ.get("APPDATA", ""), "Python", "Python*", "python.exe"),
        ]
        for pattern in patterns:
            matches = glob.glob(pattern)
            if matches:
                return matches[0]


    return "python"


def _subprocess_creationflags():
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def can_import_module(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        pass

    python_exe = get_python_executable()
    if python_exe == sys.executable:
        return False

    try:
        result = subprocess.run(
            [python_exe, "-c", f"import {module_name}"],
            capture_output=True,
            timeout=30,
            creationflags=_subprocess_creationflags(),
        )
        return result.returncode == 0
    except Exception:
        return False


_external_site_packages_applied = False


def register_package_dll_dirs(package_name: str) -> None:
    if not hasattr(os, "add_dll_directory"):
        return

    normalized = package_name.replace(".", os.sep)
    seen = set()
    for search_path in sys.path:
        pkg_dir = os.path.join(search_path, normalized)
        if not os.path.isdir(pkg_dir):
            continue
        for candidate in (os.path.join(pkg_dir, "lib"), pkg_dir):
            if not os.path.isdir(candidate) or candidate in seen:
                continue
            seen.add(candidate)
            try:
                os.add_dll_directory(candidate)
            except Exception:
                pass


def extend_path_with_external_site_packages() -> None:
    global _external_site_packages_applied
    if _external_site_packages_applied or not getattr(sys, "frozen", False):
        return

    python_exe = get_python_executable()
    if python_exe == sys.executable:
        return

    cmd = (
        "import site; "
        "paths = site.getsitepackages(); "
        "paths.append(site.getusersitepackages()); "
        "print('\\n'.join(p for p in paths if p))"
    )
    try:
        result = subprocess.run(
            [python_exe, "-c", cmd],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_subprocess_creationflags(),
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                path = line.strip()
                if path and path not in sys.path:
                    sys.path.insert(0, path)
            register_package_dll_dirs("llama_cpp")
        _external_site_packages_applied = True
    except Exception:
        pass


def prepare_frozen_python_runtime() -> None:
    if getattr(sys, "frozen", False):
        extend_path_with_external_site_packages()
        register_package_dll_dirs("llama_cpp")
