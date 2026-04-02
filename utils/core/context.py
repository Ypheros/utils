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

# class Vars(BaseModel):
#     """Project-specific variables.
#     - Dot-access: ctx.vars.some_var
#     - Allows arbitrary additional fields so each project can add new vars without changing company-
#     - Enforces that keys are valid python identifiers by validating input keys (see _validate_vars_
#     """
#     model_config = ConfigDict(extra="allow")

#     # This variables are only level above above project context
#     # so they can be accessed as ctx.some_var instead of ctx.vars.some_var for convenience

#     timezone: str = "UTC"
#     source_system: Optional[str] = None
#     pii_enabled: bool = False

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
    
    # def __dir__(self):
    #     """Return list of attributes for autocomplete support"""
    #     return list(self.__dict__.keys())
    
    def _ipython_key_completions_(self):
        """IPython-specific completion method for Databricks/Jupyter."""
        return list(self.__dict__.keys())
    
    def __getattr__(self, name):
        """Enhanced getattr that provides better introspection for autocomplete."""
        # This will be called when an attribute doesn't exist
        # We raise AttributeError but first, let's make our attributes visible
        if hasattr(self, '__dict__') and name in self.__dict__:
            return self.__dict__[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

@dataclass()
class ProjectContext:
    
    def __setattr__(self, name: str, value) -> None:
        """Allow dynamic attribute assignment despite frozen=True."""
        object.__setattr__(self, name, value)
    
    # def __dir__(self):
    #     """Return list of attributes for autocomplete support"""
    #     # Get both instance attributes and class properties
    #     attrs = list(self.__dict__.keys())
    #     # Add property names
    #     for name in dir(self.__class__):
    #         if isinstance(getattr(self.__class__, name, None), property):
    #             attrs.append(name)
    #     return attrs
    
    def _ipython_key_completions_(self):
        """IPython-specific completion method for Databricks/Jupyter."""
        attrs = list(self.__dict__.keys())
        # Add property names
        for name in dir(self.__class__):
            if isinstance(getattr(self.__class__, name, None), property):
                attrs.append(name)
        return attrs
    
    def __getattr__(self, name):
        """Enhanced getattr for better introspection."""
        # First check if it's in our dict
        if hasattr(self, '__dict__') and name in self.__dict__:
            return self.__dict__[name]  
        # Then check if it's a property
        if hasattr(self.__class__, name):
            return getattr(self.__class__, name).__get__(self, self.__class__)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
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

def _normalize_project_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")
    
def _read_workspace_config(path: str) -> Optional[str]:
    """Read a text file from Databricks Workspace (Repos/Workspace)."""
    try:
        with open(path, "r") as f:
            content = f.read()
            print(f"Reading config from {path}:{content}")
        return content
    except Exception:
        return None

def _validate_vars_keys(raw_vars: dict) -> dict:
    """Ensure keys are valid python identifiers for dot-access."""
    if not isinstance(raw_vars, dict):
        return {}
    bad = [k for k in raw_vars.keys() if not (isinstance(k, str) and k.isidentifier())]
    if bad:
        raise ValueError(
            "Invalid keys in [vars]. Keys must be valid python identifiers for dot-access. "
            f"Bad keys: {bad}"
        )
    return raw_vars

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

    # # Dynamically load all top-level sections as variables
    # raw_vars = {}
    # for key, value in cfg.items():
    #     raw_vars[key] = value
    
    # raw_vars = _validate_vars_keys(raw_vars)
    # try:
    #     # Pydantic: validates known fields + allows extra fields for project-specific additions
    #     return Vars.model_validate(raw_vars)
    # except ValidationError as e:
    #     raise ValueError(f"Invalid project_config.toml in {cfg_path}: {e}") from e

_CTX: Optional[ProjectContext] = None

def build_context(cfg: dict) -> ProjectContext:
    ctx = ProjectContext()

    for k, v in cfg.items():
        setattr(ctx, k, Namespace(**v) if isinstance(v, dict) else v)

    return ctx

def get_project_context(dbutils) -> ProjectContext:
    """Public entrypoint: infer project + load vars + expose schemas."""
    global _DBUTILS
    global _CTX

    _DBUTILS = dbutils
    
    nb_path = get_notebook_path()
    print(nb_path)
    if not nb_path:
        raise RuntimeError("Could not read notebook path (are you running on Databricks?).")
    
    project_root = infer_project_root(nb_path)

    if not project_root:
        raise RuntimeError(f"Could not infer project root from notebook path: {nb_path!r}")
    
    project_name = _normalize_project_name(project_root.split("/")[-1])
    cfg = load_project_config(project_root)
    _CTX = build_context(cfg.__dict__)
    
    return _CTX