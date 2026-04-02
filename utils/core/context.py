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

@dataclass()
class ProjectContext:
    
    def __setattr__(self, name: str, value) -> None:
        """Allow dynamic attribute assignment despite frozen=True."""
        object.__setattr__(self, name, value)
    
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

def generate_config_stub(toml_path: str, output_path: str = "config.pyi") -> None:
    """Generate a .pyi stub file from TOML configuration for perfect autocomplete.
    
    Args:
        toml_path: Path to the TOML configuration file
        output_path: Path where to write the .pyi stub file (default: config.pyi)
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    
    # Load TOML configuration
    with open(toml_path, 'rb') as f:
        config = tomllib.load(f)
    
    # Generate stub content
    lines = [
        '"""Generated stub file for TOML configuration autocomplete."""',
        "from typing import Any, Optional",
        "",
        "class Namespace:",
        "    def __init__(self, **kwargs: Any) -> None: ...",
    ]
    
    # Generate namespace classes for each TOML section
    namespace_classes = []
    
    def generate_class_for_section(section_name: str, section_data: dict, indent: str = "") -> list[str]:
        """Generate class definition for a TOML section."""
        class_lines = [f"{indent}class {section_name.capitalize()}Namespace(Namespace):"]
        
        if not section_data:
            class_lines.append(f"{indent}    pass")
            return class_lines
        
        # Add attributes
        for key, value in section_data.items():
            if isinstance(value, dict):
                # Nested namespace
                class_lines.append(f"{indent}    {key}: {key.capitalize()}Namespace")
                # Generate the nested class
                nested_class = generate_class_for_section(key, value, indent + "    ")
                namespace_classes.extend(nested_class + [""])
            else:
                # Regular attribute
                type_hint = get_type_hint(value)
                class_lines.append(f"{indent}    {key}: {type_hint}")
        
        return class_lines
    
    def get_type_hint(value: Any) -> str:
        """Get appropriate type hint for a value."""
        if value is None:
            return "Optional[Any]"
        elif isinstance(value, bool):
            return "bool"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "str"
        elif isinstance(value, list):
            return "list[Any]"
        elif isinstance(value, dict):
            return "dict[str, Any]"
        else:
            return "Any"
    
    # Generate ProjectContext class
    lines.append("")
    lines.append("class ProjectContext:")
    lines.append("    def __init__(self) -> None: ...")
    lines.append("    def __setattr__(self, name: str, value: Any) -> None: ...")
    
    # Add properties
    lines.append("    @property")
    lines.append("    def bronze(self) -> str: ...")
    lines.append("    @property") 
    lines.append("    def silver(self) -> str: ...")
    lines.append("    @property")
    lines.append("    def gold(self) -> str: ...")
    
    # Add dynamic attributes based on TOML sections
    for section_name, section_data in config.items():
        if isinstance(section_data, dict):
            lines.append(f"    {section_name}: {section_name.capitalize()}Namespace")
            # Generate the namespace class
            class_def = generate_class_for_section(section_name, section_data)
            namespace_classes.extend(class_def + [""])
        else:
            type_hint = get_type_hint(section_data)
            lines.append(f"    {section_name}: {type_hint}")
    
    # Add all namespace classes
    lines.extend([""] + namespace_classes)
    
    # Add factory function
    lines.extend([
        "def get_project_context(dbutils: Any) -> ProjectContext: ...",
        ""
    ])
    
    # Write stub file
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"✅ Generated stub file: {output_path}")
    print(f"📝 Add this to your imports: from config import ProjectContext")
    print(f"🚀 Now you'll have full autocomplete for all TOML configuration!")

def create_stub_from_context(ctx: ProjectContext, output_path: str = "config.pyi") -> None:
    """Generate .pyi stub from an existing ProjectContext for autocomplete."""
    lines = [
        '"""Generated stub file for project context autocomplete."""',
        "from typing import Any, Optional",
        "",
        "class Namespace:",
        "    def __init__(self, **kwargs: Any) -> None: ...",
        "",
    ]
    
    # Analyze the context
    namespace_classes = []
    
    lines.append("class ProjectContext:")
    lines.append("    @property")
    lines.append("    def bronze(self) -> str: ...")
    lines.append("    @property")
    lines.append("    def silver(self) -> str: ...")
    lines.append("    @property") 
    lines.append("    def gold(self) -> str: ...")
    
    # Add attributes from context
    if hasattr(ctx, '__dict__'):
        for attr_name, attr_value in ctx.__dict__.items():
            if isinstance(attr_value, Namespace):
                lines.append(f"    {attr_name}: {attr_name.capitalize()}Namespace")
                
                # Generate class for this namespace
                class_lines = [f"class {attr_name.capitalize()}Namespace(Namespace):"]
                if hasattr(attr_value, '__dict__'):
                    for key, value in attr_value.__dict__.items():
                        if key != '_locked':
                            type_hint = "str" if isinstance(value, str) else "Any"
                            class_lines.append(f"    {key}: {type_hint}")
                else:
                    class_lines.append("    pass")
                
                namespace_classes.extend(class_lines + [""])
    
    lines.extend([""] + namespace_classes)
    lines.append("def get_project_context(dbutils: Any) -> ProjectContext: ...")
    
    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"✅ Generated stub file from context: {output_path}")