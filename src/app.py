"""
High School Management System API

A super simple FastAPI application that allows students to view and sign up
for extracurricular activities at Mergington High School.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app = FastAPI(title="Mergington High School API",
              description="API for viewing and signing up for extracurricular activities")

# Mount the static files directory
current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(Path(__file__).parent,
          "static")), name="static")

TEACHERS_FILE = Path(os.environ.get("TEACHERS_FILE", current_dir / "teachers.json"))
SESSION_SECRET = (os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(32)).encode()
SESSION_COOKIE_NAME = "teacher_session"
SESSION_DURATION_SECONDS = 8 * 60 * 60
PASSWORD_HASH_ITERATIONS = 310_000
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "").lower() in {
    "1", "true", "yes"
}


class TeacherLogin(BaseModel):
    username: str
    password: str


def load_teacher_credentials():
    try:
        credentials = json.loads(TEACHERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=503,
            detail="Teacher accounts are not configured",
        )

    teachers = credentials.get("teachers") if isinstance(credentials, dict) else None
    if not isinstance(teachers, dict) or any(
        not isinstance(username, str)
        or not isinstance(account, dict)
        or not isinstance(account.get("salt"), str)
        or not isinstance(account.get("password_hash"), str)
        for username, account in teachers.items()
    ):
        raise HTTPException(
            status_code=503,
            detail="Teacher credentials file is invalid",
        )
    return teachers


def verify_teacher_password(password: str, account: dict):
    try:
        salt = bytes.fromhex(account["salt"])
        expected_hash = bytes.fromhex(account["password_hash"])
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="Teacher credentials file is invalid",
        )

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return hmac.compare_digest(password_hash, expected_hash)


def create_teacher_session(username: str):
    payload = json.dumps({
        "username": username,
        "expires": int(time.time()) + SESSION_DURATION_SECONDS,
    }, separators=(",", ":")).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(
        SESSION_SECRET,
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{encoded_payload}.{encoded_signature}"


def require_teacher(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    try:
        encoded_payload, provided_signature = token.split(".", 1)
        expected_signature = base64.urlsafe_b64encode(hmac.new(
            SESSION_SECRET,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()).decode("ascii").rstrip("=")
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise ValueError
        payload = base64.urlsafe_b64decode(
            encoded_payload + "=" * (-len(encoded_payload) % 4)
        )
        session = json.loads(payload)
        username = session["username"]
        if not isinstance(username, str) or session["expires"] < time.time():
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Teacher login required")

    if username not in load_teacher_credentials():
        raise HTTPException(status_code=401, detail="Teacher login required")
    return username


@app.post("/auth/login")
def login(teacher: TeacherLogin, response: Response):
    teachers = load_teacher_credentials()
    account = teachers.get(teacher.username)
    if account is None:
        hashlib.pbkdf2_hmac(
            "sha256", teacher.password.encode("utf-8"), b"unknown-teacher-salt",
            PASSWORD_HASH_ITERATIONS,
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not verify_teacher_password(teacher.password, account):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_teacher_session(teacher.username),
        max_age=SESSION_DURATION_SECONDS,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return {"authenticated": True, "username": teacher.username}


@app.get("/auth/me")
def get_teacher_status(request: Request):
    try:
        username = require_teacher(request)
    except HTTPException as error:
        if error.status_code == 401:
            return {"authenticated": False}
        raise
    return {"authenticated": True, "username": username}


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return {"authenticated": False}

# In-memory activity database
activities = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"]
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"]
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"]
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"]
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"]
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"]
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"]
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"]
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"]
    }
}


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def get_activities():
    return activities


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(
    activity_name: str,
    email: str,
    teacher: str = Depends(require_teacher),
):
    """Sign up a student for an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is not already signed up
    if email in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is already signed up"
        )

    # Add student
    activity["participants"].append(email)
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(
    activity_name: str,
    email: str,
    teacher: str = Depends(require_teacher),
):
    """Unregister a student from an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is signed up
    if email not in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is not signed up for this activity"
        )

    # Remove student
    activity["participants"].remove(email)
    return {"message": f"Unregistered {email} from {activity_name}"}
