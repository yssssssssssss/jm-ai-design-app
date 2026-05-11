# JM AI Design Web App Design

Date: 2026-05-07

## Context

The current project is a JM AI design-audit skill package, not a web application. It contains:

- `SKILL.md`: audit workflow and artifact requirements.
- `references/jm-ai-design-spec.md`: canonical JM AI design tokens and audit rules.
- `references/report-template.md`: Markdown report structure.
- `references/html-report-template.md`: standalone HTML report structure.
- `scripts/analyze_image_tokens.py`: image size, dominant color, sample-point, and token-distance evidence.
- `scripts/measure_regions.py`: bbox, spacing, type-scale, distance, and crop evidence.
- `scripts/annotate_issues.py`: annotated full screenshots and issue crops.

No `CLAUDE.md` file was found. The current directory is not a git repository.

## Goal

Build a single-port web application for the first product phase:

1. Authenticated users upload multiple UI screenshots.
2. The app audits each image against the existing JM AI design skill workflow.
3. The app generates one aggregate `report.html` for the task.
4. Each image section in the report includes conclusions, issues, annotated screenshots, crops, and measurement evidence.
5. Users can manage historical tasks.
6. Admin users can view all tasks and reports; normal users can only view their own.

URL crawling and multi-page website audit are intentionally out of scope for phase 1.

## Recommended Approach

Use a FastAPI monolith with Jinja2 templates, SQLite, and local file storage.

Reasons:

- The existing reusable tooling is Python.
- Deployment requires only one open port.
- A single process can serve pages, APIs, reports, and artifacts.
- SQLite and local files are enough for tens of intermittent users.
- The design keeps task execution and storage boundaries clear enough to replace SQLite or add a worker later.

Do not introduce React, Next.js, Celery/RQ, object storage, SSO, or a separate database service in phase 1.

## Architecture

Main modules:

- `web`: FastAPI routes, Jinja2 templates, static assets, form handling.
- `auth`: registration, login, logout, password hashing, current-user loading, role checks.
- `task_service`: task creation, task queries, permissions, state transitions.
- `audit_engine`: OpenAI vision-model adapter and structured audit generation.
- `evidence_tools`: wrappers around the existing Python evidence and annotation scripts.
- `report_renderer`: aggregate task-level HTML report generation.
- `storage`: controlled paths for originals, artifacts, reports, and static file responses.
- `db`: SQLite models, migrations or schema initialization, and query helpers.

Request flow:

1. User logs in and uploads multiple screenshots.
2. The backend creates one task and stores the original images under a task directory.
3. A background executor processes each image.
4. The model reads the JM AI design spec and produces structured image-level audit JSON.
5. Evidence tools generate `tokens.json`, `measurements.json`, `issues.json`, `annotated.png`, and `issue-*.png` where possible.
6. The report renderer combines all image-level results into one task-level `report.html`.
7. The task detail page exposes status and the final report link.

Keep design judgment, evidence generation, and HTML rendering separate. The model judges design compliance; scripts produce evidence; the renderer presents results.

## Data Model

Use three core tables.

### `users`

- `id`
- `username`
- `password_hash`
- `role`: `admin` or `user`
- `status`: `active` or `disabled`
- `created_at`
- `last_login_at`

### `tasks`

- `id`
- `owner_id`
- `title`
- `status`: `queued`, `running`, `succeeded`, or `failed`
- `image_count`
- `summary`
- `report_path`
- `error_message`
- `created_at`
- `updated_at`
- `completed_at`

### `task_images`

- `id`
- `task_id`
- `filename`
- `original_path`
- `annotated_path`
- `tokens_path`
- `measurements_path`
- `issues_path`
- `audit_json_path`
- `sort_order`
- `status`: `queued`, `running`, `succeeded`, or `failed`
- `error_message`

Paths stored in the database should be relative paths or controlled artifact keys, not user-controlled absolute paths.

## Authentication And Authorization

Users self-register with a shared invite code. Successful registration creates an active normal `user`.

Rules:

- Unauthenticated users may only access login and registration.
- Registration requires `REGISTER_INVITE_CODE`.
- Normal users can create tasks.
- Normal users can only list, open, and download artifacts for tasks where `tasks.owner_id` equals their user ID.
- Admin users can list and open all tasks and reports.
- Admin users can list users, enable or disable users, reset passwords, and promote or demote roles.
- The app must prevent disabling or demoting the last active admin.
- Disabled users cannot log in.

Authorization must be enforced server-side for task pages, report HTML, and all artifact files. Frontend hiding is not a security boundary.

## Audit Pipeline

Each task contains multiple images. Execution is task-level orchestration with image-level processing.

### `create_task`

- Validate file type and size.
- Rename uploaded files to controlled names.
- Store originals under the task directory.
- Insert `tasks` and `task_images` rows.
- Set the task status to `queued`.

### `run_task`

- Mark the task `running`.
- Process images in order.
- Use FastAPI `BackgroundTasks` or a small in-process executor for phase 1.
- Avoid Celery/RQ until concurrency or retry needs justify it.
- Run the phase-1 service as a single worker while using an in-process executor. Multiple web workers need an external queue or a separate task runner, which is out of scope for phase 1.

### `audit_image_with_model`

The OpenAI vision model receives:

- The JM AI design spec summary.
- The current image.
- Structured JSON output requirements.
- Rules for evidence versus inference.

The image-level audit JSON should include:

- Screen context.
- Overall conclusion.
- Major issues.
- Passes.
- Detailed issue list.
- Issue severity, category, location, current observation, spec expectation, recommendation, confidence, and optional bbox.
- Color sample points or regions when useful.
- Regions and distances to measure.
- Checklist status.
- Cannot-verify items.

The model is the compliance judge. It must not fabricate measurements; it should mark unmeasurable items as cannot verify.

### `generate_evidence`

Based on model-provided sample points, regions, distances, and issue bboxes:

- Run `analyze_image_tokens.py` to create `tokens.json`.
- Run `measure_regions.py` to create `measurements.json` and region crops.
- Write `issues.json`.
- Run `annotate_issues.py` to create `annotated.png` and `issue-*.png`.

If a problem lacks reliable coordinates, keep it in the report but skip screenshot generation for that problem.

### `reconcile_result`

Merge model output and evidence paths. Evidence strengthens the report; it does not replace the model's role-aware judgment.

### `render_task_report`

Generate one task-level `report.html` with:

- Task summary.
- Per-image sections.
- Per-image conclusions.
- Per-image major issues.
- Per-image annotated screenshots and crops.
- Per-image measurement evidence.
- Detailed issue tables.
- Passes.
- Checklist.
- Cannot-verify items.
- Links to originals and artifacts where authorized.

### Completion Rules

- All images succeeded: task status `succeeded`.
- Some images failed: task status `succeeded`, with summary noting partial failures.
- All images failed: task status `failed`.

## Pages

### `/login`

Username/password login.

### `/register`

Self-registration with username, password, and invite code. Successful users become active normal users.

### `/`

Upload page:

- Task title field.
- Multiple image upload.
- Client-side file list.
- Submit button.

After submission, redirect to task detail.

### `/tasks`

Historical task list:

- Normal users see only their own tasks.
- Admin users see all tasks.
- Admin filters: user, status, and time.
- Columns: title, submitter, image count, status, created time, completed time, report entry.

### `/tasks/{id}`

Task detail:

- Task status.
- Image processing progress.
- Error message if failed.
- Report link when complete.
- Original image list and per-image status.

The page polls a lightweight JSON status endpoint every 2-3 seconds while a task is active.

### `/tasks/{id}/report.html`

Returns the final HTML report after server-side permission checks.

### `/artifacts/{task_id}/{path}`

Returns report-related images and JSON artifacts after server-side permission checks and path normalization.

### `/admin/users`

Admin-only user management:

- List users.
- Enable or disable users.
- Reset password.
- Promote or demote role.
- Prevent removal of the last active admin.

## Storage

Use this layout by default:

```text
data/
  app.db
  uploads/
    <task_id>/
      originals/
      artifacts/
      report.html
```

Each task has one isolated directory. This makes permission checks, cleanup, and backup straightforward.

## Configuration

Use environment variables:

- `OPENAI_API_KEY`
- `APP_SECRET_KEY`
- `REGISTER_INVITE_CODE`
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`
- `DATA_DIR`
- `OPENAI_AUDIT_MODEL`
- `MAX_UPLOAD_FILES`
- `MAX_UPLOAD_MB_PER_FILE`

On first startup, if there is no active admin account, create one from `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD`.

## Deployment

Run one FastAPI service on one port. The same service serves:

- HTML pages.
- Form submissions and JSON status APIs.
- Generated `report.html` files.
- Annotated screenshots and issue crops.
- Static CSS/JS.

Use `uvicorn` with one worker for phase 1. Persist and back up `data/app.db` and `data/uploads`.

## Security Constraints

- Only allow `png`, `jpg`, `jpeg`, and `webp` uploads.
- Enforce `MAX_UPLOAD_FILES`.
- Enforce `MAX_UPLOAD_MB_PER_FILE`.
- Rename all uploaded files.
- Do not trust uploaded filenames.
- Block path traversal for artifact reads.
- Serve reports and artifacts only through permission-checked routes.
- Hash passwords with bcrypt or argon2.
- Use `HttpOnly` session cookies.
- Use `Secure` cookies in production HTTPS.
- Use CSRF tokens for state-changing form submissions.
- Set a reasonable session expiration.
- Do not expose API keys, full prompts, tracebacks, or server absolute paths in user-facing errors.

## Testing

Critical tests:

- Unauthenticated users cannot access tasks, reports, or artifacts.
- Invite code mismatch blocks registration.
- Registered users become normal `user` accounts.
- Disabled users cannot log in.
- Normal users cannot list or open other users' tasks.
- Normal users cannot access other users' report or artifact files.
- Admin users can list and open all tasks.
- The last active admin cannot be disabled or demoted.
- Non-image files are rejected.
- Oversized files and excessive file counts are rejected.
- Uploaded filenames cannot cause path traversal.
- Multi-image tasks generate one task-level `report.html`.
- Each successful image contributes conclusion, issues, screenshots where available, and measurement evidence.
- One image failure does not erase other images' results.
- All image failures mark the task failed.
- OpenAI adapter parses valid structured JSON.
- Malformed model output creates a readable task/image failure.
- Missing bboxes skip screenshots but preserve textual issues.

## Acceptance Criteria

1. A new user can register with the invite code, log in, upload 2-3 screenshots, and receive one aggregate HTML report.
2. The report includes a complete section for each image: conclusion, major issues, detailed issue table, annotated screenshots or crops where available, measurement evidence, passes, checklist, and cannot-verify items.
3. Normal user A cannot access normal user B's tasks, reports, or artifacts.
4. An admin can view all submitted tasks and reports.
5. The app works with one exposed port.
6. The phase-1 app runs without a separate frontend service, external database, object storage, or queue service.

## Out Of Scope

- URL crawling and multi-page website audit.
- Multi-tenant organizations or teams.
- Open registration without invite code.
- SSO.
- Object storage.
- PostgreSQL.
- Celery/RQ or other external queue workers.
- React, Next.js, or other SPA frameworks.
- Fine-grained permission matrices.
- Public share links.
