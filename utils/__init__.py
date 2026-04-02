from utils.core import get_project_context, ProjectContext, Namespace
# -------------------------------------------------------------------
# spark.sql.functions as f and types as t
# One-time warning (per Python process) if Spark is missing
# -------------------------------------------------------------------
_SPARK_AVAILABLE = False

try:
    from pyspark.sql import functions as f  # type: ignore
    from pyspark.sql import types as t      # type: ignore
    _SPARK_AVAILABLE = True
except ImportError:
    # Outside Spark environments these will be None (expected)
    # type: ignore allows IDEs to still autocomplete
    import sys
    if "pyspark" not in sys.modules:
        f = None  # type: ignore
        t = None  # type: ignore
    _SPARK_AVAILABLE = False

_SPARK_WARNING_SHOWN = False

if not _SPARK_AVAILABLE and not _SPARK_WARNING_SHOWN:
    print(
        "WARNING: [utils] PySpark is not available. "
    )
    _SPARK_WARNING_SHOWN = True

_BUILTINS_INJECTED = False

def _inject_spark_into_builtins_once() -> None:
    global _BUILTINS_INJECTED
    if _BUILTINS_INJECTED:
        return
    if not _SPARK_AVAILABLE:
        return

    import builtins

    if not hasattr(builtins, "f"):
        setattr(builtins, "f", f)
    if not hasattr(builtins, "t"):
        setattr(builtins, "t", t)

    _BUILTINS_INJECTED = True


_inject_spark_into_builtins_once()

__all__ = [
    "get_project_context",
    "ProjectContext",
    "Namespace",
    "f",
    "t",
]

# -------------------------------------------------------------------
# Optional submodules — only added to __all__ if installed
# -------------------------------------------------------------------
try:
    from utils import time_utils as time_utils
    __all__.append("time_utils")
except ImportError:
    pass

try:
    from utils import geospatial as geospatial
    __all__.append("geospatial")
except ImportError:
    pass