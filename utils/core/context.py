from __future__ import annotations

from ast import Try
import builtins
from dataclasses import dataclass
from sys import path
from typing import Any, Optional
import re
import base64

from pydantic import BaseModel, ConfigDict, ValidationError

#A valid project name must start with a letter or number, and then can contain letters, numbers, underscores, or hyphens
_PROJECT_NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]*"

class Namespace:
    """Helper class to allow dot-access to arbitrary dict keys."""

    __slots__ = ('__dict__',)

    def __init__(self, **kwargs):
        object.__setattr__(self, "_locked", False)

        for k, v in kwargs.items():
            try:
                setattr(self, k, self._wrap(v))
            except Exception:
                setattr(self, k, v)
        
        object.__setattr__(self, "_locked", True)

    def _wrap(self, value):
        if isinstance(value, dict):
            return Namespace(**value)
        return value
    
    def __repr__(self):
        return f"Namespace({self.__dict__})"
    
    def __setattr__(self, name, value) -> Any:
        if getattr(self, "_locked", False):
            raise AttributeError("Namespace is frozen. Cannot set attribute after initialization.")
        object.__setattr__(self, name, value)

    # THIS is the key for IPython/Databricks tab-completion
    def __dir__(self):
        return list(self.__dict__.keys())

@dataclass()
class ProjectContext:
    
    def __setattr__(self, name: str, value) -> None:
        """Allow dynamic attribute assignment despite frozen=True."""
        object.__setattr__(self, name, value)

    def __dir__(self):
        # Expose all dynamic attributes + the properties (bronze, silver, gold)
        dynamic = list(self.__dict__.keys())
        props = [k for k, v in type(self).__dict__.items() if isinstance(v, property)]
        return dynamic + props
        
    @property
    def bronze(self) -> str:
        return f"{self.project_name}_bronze"
    @property
    def silver(self) -> str:
        return f"{self.project_name}_silver"
    @property
    def gold(self) -> str:
        return f"{self.project_name}_gold"

def get_notebook_path() -> Optional[str]:
    try:
        return (_DBUTILS.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get())
    except Exception:
        return None

def infer_project_root(nb_path: str) -> Optional[str]:
    """Return project root path in Databricks Workspace.
    DEV: /Repos/a4d_<project>/adb_<project>/notebooks/<project>
    PROD: /Workspace/<project>
    USER_FOLDER: /Users/username (no project root, but still want to use context for vars)
    """
    if not nb_path:
        return None
    # DEV: /Repos/a4d_<project>/adb_<project>/notebooks/<project>/...
    m = re.match(rf"^(/Repos/[^/]+/[^/]+/(?P<project>{_PROJECT_NAME_PATTERN}))(?:/|$)", nb_path)
    if m:
        return "/Workspace"+m.group(1)
    # PROD: /Workspace/<project>/...
    m = re.match(rf"^(/Workspace/(?P<project>{_PROJECT_NAME_PATTERN}))(?:/|$)", nb_path)
    if m:
        return "/Workspace"+m.group(1)
    # USER_FOLDER: /Users/username/... (no project root)
    m = re.match(r"^(/Users/[^/]+)(?:/|$)", nb_path)
    if m:
        return "/Workspace"+m.group(1)
    return None
    
def _read_workspace_config(path: str) -> Optional[str]:
    """Read a text file from Databricks Workspace (Repos/Workspace)."""
    try:
        with open(path, "r") as f:
            content = f.read()
            print(f"Reading config from {path}:{content}")
        return content
    except Exception:
        return None

def load_project_config(project_root: str) -> Namespace:
    """Load TOML from <project_root>/project_config.toml and return Vars.
    Dynamically loads all top-level sections (vars, configs, libs, etc.) into Vars."""

    cfg_path = f"{project_root}/project_config.toml"
    txt = _read_workspace_config(cfg_path)

    if not txt:
        # no config file: return defaults
        return Namespace()
    
    import tomllib

    cfg = tomllib.loads(txt)

    return Namespace(**cfg)

_CTX: Optional[ProjectContext] = None

def build_context(cfg: dict) -> ProjectContext:
    ctx = ProjectContext()

    for k, v in cfg.items():
        setattr(ctx, k, Namespace(**v) if isinstance(v, dict) else v)

    return ctx

def get_project_context(dbutils) -> ProjectContext:
    """Public entrypoint: infer project + load vars + expose schemas."""
    global _DBUTILS, _CTX

    _DBUTILS = dbutils
    
    nb_path = get_notebook_path()
    if not nb_path:
        raise RuntimeError("Could not read notebook path (are you running on Databricks?).")
    
    project_root = infer_project_root(nb_path)

    if not project_root:
        raise RuntimeError(f"Could not infer project root from notebook path: {nb_path!r}")
    
    cfg = load_project_config(project_root)
    _CTX = build_context(cfg.__dict__)
    
    return _CTX