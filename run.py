import sys
from pathlib import Path

# Add project root to Python path
ROOT = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import main


if __name__ == "__main__":
    sys.exit(main())