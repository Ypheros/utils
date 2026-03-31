PROJECT_NAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]*"

# -------------------------------------------------------------------
# spark.sql.functions as f and types as t
# One-time warning (per Python process) if Spark is missing
# -------------------------------------------------------------------
_SPARK_AVAILABLE = False

try:
    import pyspark.sql.functions as f  
    import pyspark.sql.types as t      
    _SPARK_AVAILABLE = True
except Exception:
    # Outside Spark environments these will be None (expected)
    f = None
    t = None
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