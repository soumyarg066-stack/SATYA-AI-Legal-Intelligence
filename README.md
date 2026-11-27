# SATYA — Trustworthy Indian Legal AI

SATYA is a Flask application foundation for an evidence-led Indian legal information experience. The current version includes responsive web pages, user accounts, conversations, a protected admin area, a document library interface, and a MySQL database integration designed for XAMPP.

## Document processing and evidence retrieval

- Administrators can upload text-based PDFs, TXT, CSV, and TSV files (up to 16 MiB). File bytes and metadata are stored in MySQL; a filesystem copy is retained for compatibility with existing uploads. Scanned/image-only PDFs require OCR before upload; SATYA does not pretend OCR succeeded.
- CSV/TSV rows are extracted into page-provenanced source passages. The bundled `backend\data\raw\SATYA_Preprocessing_Input.csv.xls` is tab-delimited text and can be uploaded directly; its `document_id` groups are kept as separate source records.
- New uploads and passages are **unverified** and excluded from chat until an administrator reviews the extracted preview against the original and verifies each source in the Source Library. Administrators may reject a source to exclude it from chat. Verification confirms the reviewed source text, not its current legal force.
- Retrieval uses local weighted keyword matching against verified passages. Without an AI provider, SATYA returns exact retrieved passages with their document and page citations. If an AI provider is configured, its factual claims must cite retrieved evidence and pass a lexical support check; this is not a guarantee of legal entailment.
- When no relevant verified passage is found, chat abstains. It does not invent a rule, clause, quotation, or page reference.

## Requirements

- Python 3.10 or later
- XAMPP for Windows (Apache + MySQL / MariaDB + phpMyAdmin)
- Windows PowerShell

## XAMPP & MySQL Setup (Windows)

### 1. Install XAMPP

1. Download the official Windows installer from [https://www.apachefriends.org/](https://www.apachefriends.org/).
2. Run the installer and select at least **Apache**, **MySQL**, and **phpMyAdmin**.
3. Install to the default folder (`C:\xampp`) or your preferred directory.

### 2. Start Apache and MySQL

1. Open **XAMPP Control Panel**.
2. Click **Start** next to **Apache**.
3. Click **Start** next to **MySQL** (Wait until both turn green and MySQL shows port `3306`).

### 3. Open phpMyAdmin

1. In XAMPP Control Panel, click **Admin** next to **MySQL**, or open your browser and go to:
   `http://localhost/phpmyadmin`

### 4. Create the `satya_db` Database

In phpMyAdmin:
1. Click **New** in the left sidebar (or open the **Databases** tab).
2. Enter database name: `satya_db`
3. Set collation to `utf8mb4_unicode_ci` (or `utf8mb4_general_ci`).
4. Click **Create**.

Alternatively, you can create it from Windows PowerShell using the XAMPP MySQL client (adjust `C:\xampp` if installed elsewhere):

```powershell
C:\xampp\mysql\bin\mysql.exe -u root -e "CREATE DATABASE IF NOT EXISTS satya_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 5. Configure the `.env` File

From the project directory in Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Generate a random `SECRET_KEY` in PowerShell:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Edit `.env` and set your `SECRET_KEY` and MySQL connection string:

```dotenv
SECRET_KEY=<paste-generated-secret-key>
SATYA_ENV=development
DATABASE_URL=mysql+pymysql://root:@localhost:3306/satya_db
```

> **Note:** Default XAMPP MySQL uses username `root` with an empty password (`root:@localhost:3306`). If you configured a MySQL password or a dedicated user, update `DATABASE_URL` accordingly (for example, `mysql+pymysql://satya_user:your_password@localhost:3306/satya_db`). Never commit `.env` or production passwords.

### 6. Install Python Dependencies

From the project directory in Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, you can run commands directly with `.\.venv\Scripts\python.exe` instead of `python`.

### 7. Run Database Migrations

Verify database connectivity and apply Flask-Migrate migrations safely without dropping existing data. The migration links extracted legal source records to their uploaded file and stores the source domain; it does not delete or rewrite existing records.

```powershell
python -m flask --app run.py check-db
python -m flask --app run.py db upgrade
```

When you modify SQLAlchemy models in future development stages, generate and apply incremental migrations using:

```powershell
python -m flask --app run.py db migrate -m "Describe schema change"
python -m flask --app run.py db upgrade
```

> **Migration safety:** Never drop or reset `satya_db` blindly in production or once real data exists. Always inspect newly generated files under `migrations\versions\` before running `db upgrade`.

### 8. Create an Admin User and Start SATYA

Create or promote an administrator interactively (required to upload and verify sources). If your current account already exists, enter the same email to promote it:

```powershell
python -m flask --app run.py create-admin
```

Start the Flask server:

```powershell
python run.py
```

Open `http://127.0.0.1:5000` in your browser. Sign in as an administrator, open **Source Documents**, upload a PDF/TXT/CSV/TSV file, inspect each extracted source preview, and select **Verify source** only after checking it against the original. The bundled legal dataset can be uploaded directly even though its filename ends in `.csv.xls`; it is tab-delimited text. Uploaded files are stored under `uploads\`.

## Running Automated Tests

Tests use isolated SQLite databases (and an optional disposable `satya_test_db` database when XAMPP MySQL is running) so your `satya_db` data is never modified or deleted:

```powershell
python -m pytest -v
```

## Configuration

Copy `.env.example` to `.env`. Important settings:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Flask session and CSRF signing key; set a unique random value |
| `SATYA_ENV` | `development`, `testing`, or `production` (`production` enforces explicit 32+ char `SECRET_KEY` and secure cookies) |
| `DATABASE_URL` | SQLAlchemy URL (`mysql+pymysql://user:password@localhost:3306/satya_db`); falls back to local SQLite if unset |
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | Optional discrete MySQL parameters used when `DATABASE_URL` is omitted |
| `DB_POOL_SIZE` | SQLAlchemy MySQL connection pool size (default `5`) |
| `DB_MAX_OVERFLOW` | Maximum overflow connections above pool size (default `10`) |
| `DB_POOL_TIMEOUT` | Seconds to wait for a pooled connection (default `30`) |
| `DB_POOL_RECYCLE` | Seconds before recycling idle connections (default `1800`) |
| `DB_CONNECT_TIMEOUT` | PyMySQL TCP connection timeout in seconds (default `10`) |
| `UPLOAD_FOLDER` | Private directory for uploaded source files |
| `MAX_UPLOAD_BYTES` | Maximum size of one uploaded file (default 16 MiB) |
| `SESSION_COOKIE_SECURE` | Set to `true` when served over HTTPS |
| `SESSION_LIFETIME_HOURS` | Session cookie lifetime in hours (default `12`) |
| `AI_PROVIDER` | `none` (default) or `openai_compatible` |
| `AI_API_KEY` | Secret key for the configured OpenAI-compatible endpoint; do not commit it |
| `AI_API_URL` | Full chat-completions endpoint URL for the selected provider |
| `AI_MODEL` | Model identifier supported by that endpoint |
| `AI_TIMEOUT_SECONDS` | Provider request timeout (default 30 seconds) |

Never commit `.env` or production credentials. In production, use HTTPS and set `SESSION_COOKIE_SECURE=true`.

### Optional AI provider

The AI integration is disabled by default and makes no external requests. To enable a compatible provider, set `AI_PROVIDER=openai_compatible` and configure `AI_API_KEY`, `AI_API_URL`, and `AI_MODEL` in the local `.env`. Provider output is required to be JSON containing only claims and IDs of evidence supplied by SATYA. Evidence retrieval currently uses a small lexical matcher; it is intentionally replaceable and is not an embedding/vector-search implementation. Records created through the future ingestion interface are always unverified and are excluded from retrieval until a separate verification process marks both the source document and its chunks verified.

The provider receives the question and the last eight conversation messages, along with retrieved excerpts. Source text and conversation history are treated as untrusted content. Do not send sensitive case details to a third-party provider unless your deployment and provider policies permit it. Automated citation linking and lexical overlap checks can reject unsupported output but cannot prove legal entailment, completeness, or current legal force.

## Database Tables

Core application tables managed in `satya_db` via Flask-Migrate:

- `users` — user accounts, Werkzeug password hashes, roles, timestamps
- `conversations` — user chat sessions linked to `users`
- `messages` — user and assistant messages linked to `conversations`
- `documents` — uploaded PDF file metadata linked to `users`
- `audit_logs` — security and operational audit trail (`auth.*`, `profile.update`, `conversation.*`, `document.upload`, `admin.*`)
- `contact_messages` — contact form submissions
- `legal_source_document` & `evidence_chunk` — future verified legal source provenance tables (empty until dataset ingestion)

## Main routes

### Pages

- `/` landing page
- `/login`, `/register`, `/logout`
- `/dashboard`, `/chat`, `/profile` (signed-in users)
- `/knowledge`, `/documents`, `/about`, `/contact`
- `/admin` (administrators)

### JSON API

- `GET /api/health` (database connectivity health check)
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- `GET/PATCH /api/profile`
- `GET/POST /api/conversations`
- `GET/DELETE /api/conversations/<id>`
- `POST /api/chat`
- `GET/POST /api/documents`
- `GET /api/documents/<id>/file`
- `POST /api/contact`
- `GET /api/admin/stats`, `GET /api/admin/users`

State-changing requests are CSRF-protected. Browser clients should send the token from the `csrf-token` meta tag in the `X-CSRFToken` header. JSON endpoints return an `error` field with an appropriate HTTP status for expected failures.

## Project layout

```text
backend/                 Flask application, configuration, routes, services, and models
migrations/              Flask-Migrate (Alembic) schema migration scripts
frontend/templates/      Server-rendered, shared-layout pages
frontend/static/         CSS and browser JavaScript
instance/                Local SQLite fallback database (when SQLite is configured)
uploads/                 Administrator-uploaded source PDFs (not processed)
tests/                   Automated application and database tests
run.py                   Application entry point and Flask CLI commands
```

## Security and source handling

- Passwords are stored using Werkzeug password hashing (`generate_password_hash` / `check_password_hash`).
- Admin role is assigned through the interactive `flask --app run.py create-admin` command, not public registration.
- Only administrators can upload PDFs. The server checks the extension, PDF signature, and configured size limit; uploaded names are sanitized and stored under random filenames.
- The uploaded original is not altered or automatically processed. Metadata is stored in MySQL (`satya_db`).
- Do not treat an upload as proof of authenticity, currentness, commencement, or legal effect.
