# Users Feature Design

## Overview

Invite-based user system with JWT authentication. No public registration — admins create invites, invitees register using a token.

## Project Structure

```
app/
  __init__.py
  main.py              # FastAPI app factory, mounts routers
  config.py            # Settings via pydantic-settings (DB URL, JWT secret, etc.)
  database.py          # SQLAlchemy engine, session factory, Base
  models/
    __init__.py
    user.py            # User model
    invite.py          # Invite model
  schemas/
    __init__.py
    user.py            # User request/response schemas
    invite.py          # Invite request/response schemas
    auth.py            # Login request, token response schemas
  routers/
    __init__.py
    users.py           # User CRUD endpoints (admin-only)
    invites.py         # Invite create/list endpoints (admin-only)
    auth.py            # Login, register-via-invite, refresh token
  dependencies.py      # get_db, get_current_user, require_admin
tests/
  __init__.py
  conftest.py          # Fixtures: test DB, test client, test users
  models/
    __init__.py
    test_user.py
    test_invite.py
  routers/
    __init__.py
    test_auth.py
    test_users.py
    test_invites.py
main.py                # Thin entrypoint: imports app from app.main
```

## Data Models

### User

| Field | Type | Notes |
|---|---|---|
| id | int | Primary key, auto-increment |
| email | string | Unique, indexed |
| name | string | |
| password_hash | string | |
| role | enum | `admin`, `member`; default `member` |
| is_active | boolean | Default true |
| created_at | datetime | Set on create |
| updated_at | datetime | Set on create and update |

### Invite

| Field | Type | Notes |
|---|---|---|
| id | int | Primary key, auto-increment |
| token | string | Unique, indexed (UUID4) |
| email | string | Who the invite is for |
| role | enum | `admin`, `member`; default `member` |
| expires_at | datetime | |
| used_at | datetime | Nullable, set when consumed |
| invited_by_id | int | Foreign key to User |
| created_at | datetime | Set on create |

An invite is valid when `used_at` is null AND `expires_at` is in the future.

## API Endpoints

### Auth (`/auth`)

- `POST /auth/login` — email + password, returns access + refresh tokens
- `POST /auth/register` — invite token + name + password, consumes invite, creates user
- `POST /auth/refresh` — refresh token, returns new access token

### Users (`/users`) — admin only

- `GET /users` — list all users
- `GET /users/{id}` — get a user
- `PUT /users/{id}` — update a user (name, email, role, is_active)
- `DELETE /users/{id}` — delete a user

### Invites (`/invites`) — admin only

- `POST /invites` — create invite (email, role, expiration)
- `GET /invites` — list all invites
- `DELETE /invites/{id}` — revoke a pending invite

## Authentication & Security

- **Access token** — JWT, HS256, 30 min TTL, contains user id/email/role
- **Refresh token** — JWT, HS256, 7 day TTL, contains user id only
- **Password hashing** — bcrypt
- **Route protection** — `get_current_user` dependency (401 if invalid), `require_admin` dependency (403 if not admin)
- **First admin** — created via `task app:create-admin` command

## Database

- Shared MySQL container at `mysql_db:3306` on the `proxy` Docker network
- App database: `boone_gifts`
- Test database: `boone_gifts_test`
- Connection: `mysql+pymysql://user:password@mysql_db:3306/boone_gifts`

## Testing

- pytest + httpx async test client
- Tests run against `boone_gifts_test` database
- Model tests: user/invite creation, validation, expiration logic
- Router tests: full HTTP request/response cycle (auth, CRUD, permissions)
- TDD: tests written before implementation
