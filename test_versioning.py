import sys
from pathlib import Path
sys.path.append(str(Path.cwd() / "backend"))

try:
    from app.core.versioning import get_system_version_header
    print(f"Header: {get_system_version_header()}")
except Exception as e:
    import traceback
    traceback.print_exc()
