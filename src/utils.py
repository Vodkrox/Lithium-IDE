"""
Utility helpers for Lithium IDE.
"""

import subprocess
import sys
import os
import shutil


def resource_path(relative_path: str) -> str:
    """
    Get the absolute path to a resource, compatible with PyInstaller bundles.

    When running from a PyInstaller --onefile bundle, files are extracted to
    a temporary folder referenced by sys._MEIPASS. When running from source,
    the path is resolved relative to the project root.

    Args:
        relative_path: Path relative to the project root (e.g. "src/assets/icon.png")

    Returns:
        Absolute path to the resource.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running inside a PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Running from source — project root is one level above 'src/'
        base_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)


def get_python_executable() -> str:
    """
    Return the path to the real Python interpreter.

    When running inside a PyInstaller bundle, ``sys.executable`` points to the
    frozen ``.exe`` (e.g. ``Lithium.exe``), **not** to ``python.exe``.
    Spawning ``[sys.executable, "-m", "pip", ...]`` in that case would
    re-launch the IDE instead of running pip.

    This helper detects the frozen state and searches for a real Python
    interpreter on the system PATH.

    Returns:
        Absolute path to ``python.exe`` (or equivalent), or ``sys.executable``
        when running from source.
    """
    if not getattr(sys, "frozen", False):
        # Running from source — sys.executable is the real interpreter
        return sys.executable

    # --- Frozen / PyInstaller build ---
    # Try common interpreter names on PATH
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found

    # Fallback: look in common Windows install locations
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

    # Last resort — return "python" and let subprocess raise if missing
    return "python"


def _subprocess_creationflags():
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def can_import_module(module_name: str) -> bool:
    """
    Return True if *module_name* can be imported in the current runtime.

    When running from a PyInstaller bundle, packages installed via pip into
    the system Python are not visible to in-process imports. In that case
    this helper falls back to asking the external interpreter.
    """
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


def extend_path_with_external_site_packages() -> None:
    """
    When frozen, prepend the external Python site-packages directories to
    ``sys.path`` so pip-installed packages become importable in-process.
    """
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
        _external_site_packages_applied = True
    except Exception:
        pass
