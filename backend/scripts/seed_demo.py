"""Create or refresh a deterministic demo login (password hash bcrypt)."""

import os

from sqlalchemy import text

from app.auth_utils import hash_password
from app.database import SessionLocal

DEMO_USER_ID = "a0000001-0000-4000-8000-000000000001"
DEMO_EMAIL = "demo.user@example.com"



def main() -> None:
    password = os.getenv("DEMO_PASSWORD", "DemoPass123!")
    ph = hash_password(password)
    db = SessionLocal()
    try:


        
        db.execute(
            text("DELETE FROM reservations WHERE user_id IN (SELECT id FROM users WHERE email = :email)"),
            {"email": DEMO_EMAIL},
        )
        db.execute(text("DELETE FROM vehicles WHERE user_id IN (SELECT id FROM users WHERE email = :email)"), {"email": DEMO_EMAIL})
        db.execute(text("DELETE FROM users WHERE email = :email"), {"email": DEMO_EMAIL})
        db.execute(
            text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :ph)"),
            {"id": DEMO_USER_ID, "email": DEMO_EMAIL, "ph": ph},
        )
        db.commit()
        print(f"Demo account ready: {DEMO_EMAIL} (id={DEMO_USER_ID})")
        print("Log in with the password from DEMO_PASSWORD or default DemoPass123!")
    finally:
        db.close()


if __name__ == "__main__":
    main()
