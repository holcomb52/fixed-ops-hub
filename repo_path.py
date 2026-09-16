"""Keep this repo first on sys.path so ``lib`` is our package, not a venv folder."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List

REPO_ROOT = Path(__file__).resolve().parent
LOCAL_LIB = REPO_ROOT / "lib"
LOCAL_LIB_INIT = LOCAL_LIB / "__init__.py"

# Community Cloud 3.13/3.14 has historically crashed this app with a redacted
# KeyError/dataclass ImportError. Require the versions we deploy against.
SUPPORTED_CLOUD_PYTHON = ((3, 11), (3, 12))


def cloud_python_supported(info: object | None = None) -> bool:
    ver = info or sys.version_info
    return (int(ver.major), int(ver.minor)) in SUPPORTED_CLOUD_PYTHON


def ensure_repo_root_on_sys_path() -> str:
    """Put the directory that contains ``lib/`` at sys.path[0]."""
    root = str(REPO_ROOT)
    if sys.path[:1] != [root]:
        try:
            sys.path.remove(root)
        except ValueError:
            pass
        sys.path.insert(0, root)
    return root


def _path_is_local_lib(path: str) -> bool:
    try:
        resolved = Path(path).resolve()
    except OSError:
        return False
    return resolved == LOCAL_LIB.resolve() or resolved == LOCAL_LIB_INIT.resolve()


def _cached_lib_is_local() -> bool:
    cached = sys.modules.get("lib")
    if cached is None:
        return True
    cached_file = getattr(cached, "__file__", None)
    if cached_file and _path_is_local_lib(str(cached_file)):
        return True
    for item in getattr(cached, "__path__", []) or []:
        if _path_is_local_lib(str(item)):
            return True
    return False


def evict_foreign_lib_modules() -> List[str]:
    """Drop a previously imported ``lib`` that is not this repo's package."""
    if _cached_lib_is_local():
        return []
    removed = [key for key in list(sys.modules) if key == "lib" or key.startswith("lib.")]
    for key in removed:
        del sys.modules[key]
    return removed


def prepare_local_lib_imports() -> str:
    """Make ``from lib.app_auth import ...`` resolve to this repository."""
    root = ensure_repo_root_on_sys_path()
    evict_foreign_lib_modules()
    return root


def local_app_auth_path() -> Path:
    return LOCAL_LIB / "app_auth.py"


def describe_lib_resolution() -> str:
    """Safe diagnostic for Cloud logs / on-screen import failures."""
    cached = sys.modules.get("lib")
    if cached is None:
        return "lib is not cached in sys.modules"
    return (
        f"lib.__file__={getattr(cached, '__file__', None)!r} "
        f"lib.__path__={list(getattr(cached, '__path__', []) or [])!r}"
    )


def filter_secret_text(text: str) -> str:
    """Avoid echoing JWTs or service-role material if an exception includes them."""
    lowered = text.lower()
    if "eyj" in lowered or "service_role" in lowered or "sb_secret" in lowered:
        return "[redacted: exception text looked like a secret]"
    return text


def format_import_error(exc: BaseException, *, extra: Iterable[str] = ()) -> str:
    parts = [
        f"{type(exc).__name__}: {filter_secret_text(str(exc) or 'no message')[:400]}",
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        f"app_auth file exists: {local_app_auth_path().is_file()}",
        describe_lib_resolution(),
        *extra,
    ]
    return "\n".join(parts)
