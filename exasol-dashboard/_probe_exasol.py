"""Safe, read-only connectivity probe using the configured OpsNexus API identity."""

from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from api.app import _connect_from_environment


def main():
    connection = _connect_from_environment()
    try:
        current_user = connection.execute("SELECT CURRENT_USER").fetchval()
        if str(current_user).strip().casefold() == "sys":
            raise RuntimeError("SYS is not permitted for this probe.")
        result = connection.execute("SELECT 1").fetchval()
        print(f"Connected as {current_user}; SELECT 1 returned {result}.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()