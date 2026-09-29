import getpass
import hashlib
import json
import secrets
from pathlib import Path


PASSWORD_HASH_ITERATIONS = 310_000
TEACHERS_FILE = Path(__file__).with_name("teachers.json")


def main():
    username = input("Teacher username: ").strip()
    if not username:
        raise SystemExit("Username cannot be empty")

    password = getpass.getpass("Teacher password: ")
    if not password:
        raise SystemExit("Password cannot be empty")

    if TEACHERS_FILE.exists():
        try:
            credentials = json.loads(TEACHERS_FILE.read_text(encoding="utf-8"))
            teachers = credentials["teachers"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            raise SystemExit("Existing teacher credentials file is invalid")
        if not isinstance(teachers, dict):
            raise SystemExit("Existing teacher credentials file is invalid")
    else:
        teachers = {}

    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    teachers[username] = {
        "salt": salt.hex(),
        "password_hash": password_hash.hex(),
    }

    TEACHERS_FILE.write_text(
        json.dumps({"teachers": teachers}, indent=2) + "\n",
        encoding="utf-8",
    )
    TEACHERS_FILE.chmod(0o600)
    print(f"Saved credentials for {username} in {TEACHERS_FILE}")


if __name__ == "__main__":
    main()
