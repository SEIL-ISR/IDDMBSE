import sys
from pathlib import Path

WAREHOUSE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(WAREHOUSE), str(WAREHOUSE / "tools")]
