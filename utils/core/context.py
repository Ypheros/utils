from __future__ import annotations

from ast import Try
import builtins
from dataclasses import dataclass
from sys import path
from typing import Optional
import re
import base64

from pydantic import BaseModel, ConfigDict, ValidationError

#A valid project name must start with a letter or number, and then can contain letters, numbers, underscores, or hyphens
_PROJECT_NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]*"

class Vars(BaseModel):
    """Project-specific variables.
    - Dot-access: ctx.vars.some_var
    - Allows arbitrary additional fields so each project can add new vars without changing company-
    - Enforces that keys are valid python identifiers by validating input keys (see _validate_vars_
    """
    model_config = ConfigDict(extra="allow")

    # Optional defaults for commonly used fields (customize as you learn common needs)

    timezone: str = "UTC"
    source_system: Optional[str] = None
    pii_enabled: bool = False

@dataclass(frozen=True)
class ProjectContext:
    project_name: str
    vars: Vars
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

def load_project_config(project_root: str) -> Vars:
    """Load TOML from <project_root>/project_config.toml and return Vars."""
    cfg_path = f"{project_root}/project_config.toml"
    txt = _read_workspace_config(cfg_path)
    print(f"Tentar aceder ao conteudo retornado da fun: {_read_workspace_config(cfg_path)}")
    print(f"Config text from {cfg_path}: {txt}")
    if not txt:
        print(f"No config found at {cfg_path}, using defaults.")
        # no config file: return defaults
        return Vars()
    import tomllib
    cfg = tomllib.loads(txt)
    raw_vars = cfg.get("vars") or {}
    print(f"Raw vars from config before _validate_vars_keys: {raw_vars}")
    raw_vars = _validate_vars_keys(raw_vars)
    print(f"Raw vars from config after _validate_vars_keys: {raw_vars}")
    try:
        # Pydantic: validates known fields + allows extra fields for project-specific additions
        return Vars.model_validate(raw_vars)
    except ValidationError as e:
        raise ValueError(f"Invalid project_config.toml vars section in {cfg_path}: {e}") from e

_CTX: Optional[ProjectContext] = None

def get_project_context(dbutils) -> ProjectContext:
    """Public entrypoint: infer project + load vars + expose schemas."""
    global _DBUTILS
    global _CTX

    _DBUTILS = dbutils

    if _CTX is not None:
        return _CTX
    
    nb_path = get_notebook_path()
    print(nb_path)
    if not nb_path:
        raise RuntimeError("Could not read notebook path (are you running on Databricks?).")
    
    project_root = infer_project_root(nb_path)

    if not project_root:
        raise RuntimeError(f"Could not infer project root from notebook path: {nb_path!r}")
    
    project_name = _normalize_project_name(project_root.split("/")[-1])
    vars_model = load_project_config(project_root)

    _CTX = ProjectContext(project_name=project_name, vars=vars_model)
    
    return _CTX