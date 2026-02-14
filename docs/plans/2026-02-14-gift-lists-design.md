# Gift Lists Feature Design

## Overview

Gift list system where authenticated users create themed wishlists, add gifts to them, and share lists with specific users. Shared users can claim gifts to avoid duplicate purchases — but claim info is hidden from the list owner to preserve the surprise.

## Data Models

### List

| Field | Type | Notes |
|---|---|---|
| id | int | PK |
| name | str(255) | e.g. "Christmas 2026" |
| description | str(500) | Nullable, optional |
| owner_id | int | FK → users.id |
| created_at | datetime | server default |
| updated_at | datetime | server default + onupdate |

### Gift

| Field | Type | Notes |
|---|---|---|
| id | int | PK |
| list_id | int | FK → lists.id |
| name | str(255) | What the gift is |
| description | str(500) | Nullable, optional details |
| url | str(2048) | Nullable, link to product |
| price | Decimal(10,2) | Nullable, approximate price |
| claimed_by_id | int | Nullable, FK → users.id |
| claimed_at | datetime | Nullable |
| created_at | datetime | server default |
| updated_at | datetime | server default + onupdate |

### ListShare

| Field | Type | Notes |
|---|---|---|
| id | int | PK |
| list_id | int | FK → lists.id |
| user_id | int | FK → users.id |
| created_at | datetime | server default |
| Unique constraint | | (list_id, user_id) |

## API Endpoints

### Lists (`/lists`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/lists` | Any user | Create a new list (owner = current user) |
| GET | `/lists` | Any user | List all lists visible to current user (owned + shared) |
| GET | `/lists/{id}` | Owner or shared | Get a single list with its gifts |
| PUT | `/lists/{id}` | Owner only | Update list name/description |
| DELETE | `/lists/{id}` | Owner only | Delete list and all its gifts |

### Gifts (`/lists/{list_id}/gifts`)

Nested under lists — gifts are always created in context of a specific list.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/lists/{list_id}/gifts` | Owner only | Add a gift to the list |
| PUT | `/lists/{list_id}/gifts/{id}` | Owner only | Update gift details |
| DELETE | `/lists/{list_id}/gifts/{id}` | Owner only | Remove a gift |
| POST | `/lists/{list_id}/gifts/{id}/claim` | Shared user (not owner) | Claim a gift |
| DELETE | `/lists/{list_id}/gifts/{id}/claim` | Claimer only | Unclaim a gift |

### Sharing (`/lists/{list_id}/shares`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/lists/{list_id}/shares` | Owner only | Share list with a user (by user id or email) |
| GET | `/lists/{list_id}/shares` | Owner only | List who the list is shared with |
| DELETE | `/lists/{list_id}/shares/{user_id}` | Owner only | Revoke a user's access |

## Authorization

### Access Dependencies

Two reusable dependencies for list access control:

- **`get_list_for_owner(list_id, current_user, db)`** — Returns the list if the current user owns it, else 403. Used by: create gift, update/delete list, manage shares.
- **`get_list_for_viewer(list_id, current_user, db)`** — Returns the list if the current user owns it OR has a share record, else 403. Used by: get list, claim/unclaim gift.

Both return 404 if the list doesn't exist.

### Claim Rules

- Only shared users (not the owner) can claim
- A gift can only be claimed by one user at a time
- Only the claimer can unclaim
- Admins get no special override — this is user-to-user, not admin functionality

### Response Filtering

When the owner requests their own list, gift responses exclude `claimed_by_id` and `claimed_at` (return null). When a shared user requests the list, they see full claim info. This is handled with two schema variants: `GiftOwnerRead` (no claim fields) and `GiftRead` (with claim fields), selected based on who's asking.

## Testing Strategy

### Model Tests (`tests/models/`)

- `test_list.py` — create list, owner association
- `test_gift.py` — create gift in list, claim/unclaim, nullable fields
- `test_list_share.py` — create share, unique constraint on (list_id, user_id)

### Router Tests (`tests/routers/`)

- `test_lists.py` — CRUD, visibility (only owned + shared appear), owner-only mutations, 403 for unshared users
- `test_gifts.py` — create/update/delete within list, claim by shared user, claim hidden from owner in response, can't claim own gift, unclaim by claimer only
- `test_list_shares.py` — share/unshare, duplicate share rejected, can't share with yourself

### New Fixtures

- `sample_list(db, member_user)` — a list owned by the member user
- `shared_list(db, sample_list, admin_user)` — sample_list shared with admin

Use member as list owner and admin as shared viewer to exercise both roles without conflating "admin" with "list owner."
