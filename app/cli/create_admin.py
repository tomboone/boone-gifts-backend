import sys

from sqlalchemy import select

from app.database import SessionLocal, engine, Base
from app.models.user import User


def main():
    Base.metadata.create_all(bind=engine)

    email = input("Email: ").strip()
    name = input("Name: ").strip()
    password = input("Password: ").strip()

    if not all([email, name, password]):
        print("All fields are required.")
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if existing:
            print(f"User with email {email} already exists.")
            sys.exit(1)

        user = User(email=email, name=name, role="admin", password_hash="")
        user.set_password(password)
        db.add(user)
        db.commit()
        print(f"Admin user '{name}' created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
