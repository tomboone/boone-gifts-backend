# Boone Gifts Backend

REST API for Boone Gifts, a gift list and wishlist platform. Users create gift lists, share them with connections, and claim gifts from shared lists.

## Tech Stack

- **Python 3.14** / **FastAPI** / **Uvicorn**
- **SQLAlchemy 2.0** (ORM) + **Alembic** (migrations)
- **MySQL 8** (shared container)
- **Pydantic v2** (validation & serialization)
- **PyJWT** + **bcrypt** (auth)
- **Docker Compose** + **Traefik** (reverse proxy)
- **uv** (package management)
- **go-task** (task runner)

## Prerequisites

- Docker Desktop
- [go-task](https://taskfile.dev/)
- A running MySQL container on the external `proxy` Docker network
- A running Traefik instance on the same `proxy` network

## Setup

1. Clone the repo and copy the environment template:

   ```
   cp .env.example .env
   ```

2. Edit `.env` with your MySQL credentials and a JWT secret.

3. Build and start the container:

   ```
   task app:up
   ```

4. Run database migrations:

   ```
   task app:migrate
   ```

5. Create the first admin user:

   ```
   task app:create-admin
   ```

6. Start the dev server:

   ```
   task app:run
   ```

The API is available at `https://boone-gifts-api.localhost` (via Traefik).

## Development

```
task app:up          # Build image and start container
task app:run         # Start FastAPI with --reload
task app:test        # Run test suite
task app:test-file -- <path>  # Run a specific test file
task app:migrate     # Apply database migrations
task app:migration -- 'description'  # Generate a new migration
```

### Dependency Management

```
task app:add -- <package>      # Add a package
task app:remove -- <package>   # Remove a package
task app:sync                  # Install all deps from lock file
task app:lock                  # Regenerate lock file
```

## API Overview

### Auth (`/auth`)
- `POST /auth/login` -- Login with email and password
- `POST /auth/register` -- Register with an invite token
- `POST /auth/refresh` -- Refresh an access token

### Users (`/users`) -- admin only
- `GET /users` -- List all users
- `GET /users/{id}` -- Get user details
- `PUT /users/{id}` -- Update a user
- `DELETE /users/{id}` -- Delete a user

### Invites (`/invites`) -- admin only
- `POST /invites` -- Create an invite
- `GET /invites` -- List invites
- `DELETE /invites/{id}` -- Delete an invite

### Connections (`/connections`)
- `POST /connections` -- Send a connection request (by user_id or email)
- `GET /connections` -- List accepted connections
- `GET /connections/requests` -- List pending incoming requests
- `POST /connections/{id}/accept` -- Accept a request
- `DELETE /connections/{id}` -- Remove connection, reject, or cancel request

### Lists (`/lists`)
- `POST /lists` -- Create a gift list
- `GET /lists` -- List your owned and shared lists
- `GET /lists/{id}` -- Get list with gifts
- `PUT /lists/{id}` -- Update a list
- `DELETE /lists/{id}` -- Delete a list

### Gifts (`/lists/{list_id}/gifts`)
- `POST /lists/{id}/gifts` -- Add a gift
- `PUT /lists/{id}/gifts/{gift_id}` -- Update a gift
- `DELETE /lists/{id}/gifts/{gift_id}` -- Delete a gift
- `POST /lists/{id}/gifts/{gift_id}/claim` -- Claim a gift
- `DELETE /lists/{id}/gifts/{gift_id}/claim` -- Unclaim a gift

### Shares (`/lists/{list_id}/shares`)
- `POST /lists/{id}/shares` -- Share a list (requires connection)
- `GET /lists/{id}/shares` -- List shares
- `DELETE /lists/{id}/shares/{user_id}` -- Revoke a share

## Environment Variables

| Variable | Description |
|---|---|
| `APP_DATABASE_URL` | MySQL connection string |
| `APP_TEST_DATABASE_URL` | MySQL connection string for tests |
| `APP_JWT_SECRET` | Secret key for JWT signing |
| `APP_CORS_ORIGINS` | Allowed CORS origins (JSON array) |

## Testing

```
task app:test
```

106 tests run against a separate test database. Each test is wrapped in a transaction that rolls back, leaving no persistent data.
