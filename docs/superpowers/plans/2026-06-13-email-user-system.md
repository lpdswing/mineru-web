# Email User System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace random local-storage user identity with a simple email/password user system and cookie-backed authentication.

**Architecture:** The backend owns identity with a `users` table, standard-library password hashing, and an HTTP-only signed auth cookie. Existing business endpoints keep using `get_user_id()`, but that dependency resolves the user from the auth cookie for the frontend path. The frontend gets a standalone login/register page, route guard, auth API wrapper, and a logout entry in the existing sidebar.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest/TestClient, Vue 3, Vue Router, Axios, Element Plus.

---

### Task 1: Backend Auth Contract

**Files:**
- Create: `backend/tests/test_auth_api.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/api/auth.py`
- Create: `backend/app/services/auth.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/utils/user_dep.py`
- Modify: `backend/main.py`
- Create: `backend/alembic/versions/20260613_add_users.py`

- [ ] **Step 1: Write failing auth API tests**

Add tests that assert email registration logs the user in, duplicate email is rejected, login returns the same user, `/api/auth/me` requires a cookie session, and `/api/files` returns 401 without auth.

- [ ] **Step 2: Run auth API tests and verify RED**

Run: `cd backend && uv run pytest tests/test_auth_api.py -v`
Expected: FAIL because `/api/auth/register` and related code do not exist.

- [ ] **Step 3: Implement minimal backend auth**

Add the `User` model, auth helpers for password hashing and signed cookie tokens, auth router endpoints, auth dependency, main router inclusion, and Alembic migration.

- [ ] **Step 4: Run auth API tests and verify GREEN**

Run: `cd backend && uv run pytest tests/test_auth_api.py -v`
Expected: PASS.

### Task 2: User-Scoped Stats

**Files:**
- Create: `backend/tests/test_stats_api.py`
- Modify: `backend/app/services/stats.py`
- Modify: `backend/app/api/stats.py`

- [ ] **Step 1: Write failing stats isolation test**

Add a test with files for two different users and assert `/api/stats` reports only the authenticated user's rows.

- [ ] **Step 2: Run stats test and verify RED**

Run: `cd backend && uv run pytest tests/test_stats_api.py -v`
Expected: FAIL because `StatsService.get_stats()` counts all files.

- [ ] **Step 3: Filter stats by user**

Pass `user_id` from the API into `StatsService.get_stats(user_id)` and filter total files, today's uploads, and used space by `File.user_id == user_id`.

- [ ] **Step 4: Run stats test and verify GREEN**

Run: `cd backend && uv run pytest tests/test_stats_api.py -v`
Expected: PASS.

### Task 3: Frontend Login Flow

**Files:**
- Create: `frontend/src/api/auth.ts`
- Replace: `frontend/src/utils/user.ts`
- Create: `frontend/src/views/Login.vue`
- Modify: `frontend/src/api/index.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/main.ts`

- [ ] **Step 1: Remove random user ID behavior**

Replace the local-storage UUID utility with current-user state helpers that call `/api/auth/me`, `/api/auth/login`, `/api/auth/register`, and `/api/auth/logout`.

- [ ] **Step 2: Add login/register UI**

Create a standalone `/login` page using the existing System Light tokens: centered panel, email/password fields, login/register mode switch, and compact validation messages.

- [ ] **Step 3: Protect app routes**

Add router guards so protected pages require `auth.me`; public `/login` redirects to `/` when already logged in.

- [ ] **Step 4: Add sidebar identity and logout**

Show the current user's email in the sidebar bottom and add a logout action that calls `/api/auth/logout`, clears frontend state, and routes to `/login`.

### Task 4: Verification

**Files:**
- Modify only files touched by Tasks 1-3 if verification exposes issues.

- [ ] **Step 1: Run backend focused tests**

Run: `cd backend && uv run pytest tests/test_auth_api.py tests/test_stats_api.py tests/test_settings_api.py -v`
Expected: PASS.

- [ ] **Step 2: Run frontend checks**

Run: `cd frontend && npm run test:theme`
Expected: PASS.

Run: `cd frontend && npm run build`
Expected: PASS.

- [ ] **Step 3: Update graph**

Run: `graphify update .`
Expected: graph update completes.

- [ ] **Step 4: Browser check**

Open the app, confirm unauthenticated users land on `/login`, register/login works, pages load under the new cookie session, logout returns to `/login`, and the Apple-style palette remains intact.
