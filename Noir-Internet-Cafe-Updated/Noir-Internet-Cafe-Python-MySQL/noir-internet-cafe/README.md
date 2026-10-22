# NOIR Internet Café

A monochrome café management application using separated HTML, CSS, JavaScript, a Python/Flask backend, and MySQL. Data is stored on the server. There are no default accounts, sample records, browser storage databases, or reset-demo controls.

**Updating an existing installation? Read `UPGRADE.md` first.**

## What is included

| Area | Functions |
| --- | --- |
| Authentication | Member registration, sign-in, sign-out, password changes, Administrator creation from the server console |
| Accounts | Administrator account creation, names/emails, Member or Administrator roles, enable/disable accounts |
| Stations | Add/edit computers and hourly rates, maintenance state, current occupancy, delete from the floor while retaining history |
| Bookings | Administrator-only creation, cancellation, and check-in |
| Sessions | Administrator-set duration, live remaining time, automatic billing cutoff, adjustable remaining time, saved rates |
| Billing | Unpaid invoices, cash/e-wallet/bank payment records, duplicate-payment protection, printable invoices and payment records |
| Dashboard | Actual station counts, active sessions, received revenue for the café’s current day, outstanding balance |
| Inventory | Admin-only hardware specs, IP/MAC, hostname, OS, costs, station links, security review evidence |
| Maintenance | Admin-only repair logs, dates, technician, actions, completion validation, costs |
| Reports | Admin-only CSV inventory, maintenance, sessions and payments |
| Backup | Server-console mysqldump wrapper and isolated restore runbook |
| Activity | Latest 100 account and café events |
| Member view | Read-only remaining time, available stations, and personal billing; no booking or management controls |

All new public registrations are **Members**. Administrator accounts are created from the server console or by an authenticated Administrator.

## Folder structure

```text
noir-internet-cafe/
  app.py                     Python entry point / Waitress server
  noir/
    __init__.py              Flask factory, configuration, CSRF, response headers
    api.py                   Account, booking, station, session, billing APIs
    db.py                    MySQL connections and transactions
    domain.py                Input validation and billing rules
    cli.py                   Setup, migrations, and password recovery commands
    migrations.py            Non-destructive upgrades for existing databases
  templates/index.html       HTML page
  static/css/styles.css      Black and white styling
  static/js/app.js            Browser UI and API calls
  database/schema.sql        MySQL tables, keys, and constraints
  scripts/configure.py        Creates a private .env with generated secrets
  tests/                     Unit and opt-in MySQL integration tests
  compose.yaml               Application + MySQL 8.4 containers
  Dockerfile                 Python application image
  requirements.txt           Python dependencies
  .env.example               Configuration reference
```

## Docker setup

Requirements: Docker Desktop or Docker Engine with Compose v2, and Python 3.11+ for generating configuration.

```sh
python scripts/configure.py
docker compose up --build -d
docker compose exec web python -m flask --app app create-admin
```

Choose your own Administrator name, email, and password when prompted. Open **http://localhost:8000**.

The configuration script generates a unique application secret and separate MySQL account/root passwords. The database has a persistent Docker volume and is not exposed on a host port. The web port is bound to localhost initially. `.env` is not copied into the image.

The database tables are initialized when the web container starts. `init-db` also runs the additive migrations for this version, and can be run again safely. Existing Python installations must run `python -m flask --app app migrate-db` before starting the updated app; see `UPGRADE.md`.

Do not change MySQL credentials in `.env` on an existing volume without also changing the credentials inside MySQL. The MySQL container’s initialization environment variables apply when the volume is first created.

## Without Docker: Python and an existing MySQL server

Requirements: Python 3.11+, MySQL 8.0.16+ (8.4 LTS preferred), and a terminal in this project folder.

### 1. Create configuration and install dependencies

Windows PowerShell:

```powershell
py scripts/configure.py
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux/macOS:

```sh
python3 scripts/configure.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Create the MySQL database and application user

Open the MySQL console as an account with database administration privileges. Copy the generated `DB_PASSWORD` from your local `.env` into the password position below.

```sql
CREATE DATABASE noir CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'noir_app'@'localhost' IDENTIFIED BY 'PASTE_DB_PASSWORD_FROM_YOUR_ENV_FILE';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
ON noir.* TO 'noir_app'@'localhost';
```

Edit `.env` so `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` match your MySQL installation. Keep the generated `SECRET_KEY` private. `MYSQL_ROOT_PASSWORD` is used only by the Docker configuration.

### 3. Initialize tables, create your Administrator, and run

Windows PowerShell:

```powershell
.venv\Scripts\python.exe -m flask --app app init-db
.venv\Scripts\python.exe -m flask --app app create-admin
.venv\Scripts\python.exe app.py
```

Linux/macOS:

```sh
.venv/bin/python -m flask --app app init-db
.venv/bin/python -m flask --app app create-admin
.venv/bin/python app.py
```

Open **http://localhost:8000**. Waitress serves the app with debugging disabled.

## First use

1. Sign in as your Administrator.
2. **Stations → Add station:** create each actual PC and set its hourly rate.
3. Create customer accounts under **Accounts**, or let customers self-register.
4. **Start session:** choose a customer account, or enter a walk-in guest name. Choose a duration in minutes (60 by default). Link the session to the customer’s account so they can see their remaining time and billing. Time starts at the server when you confirm.
5. Select an occupied station to **Set remaining time** or **End and create invoice** early. Timed sessions finish at their scheduled end.
6. Receive the customer’s payment, choose its method, and click **Record payment**.
7. Use **Billing** to find unpaid invoices and print billing records.

For a reservation, the Administrator uses **New booking**, then checks the customer in from the Bookings page or reserved station card. Members cannot create, cancel, or check in bookings.

## Operating rules

- An available PC can be reserved up to 30 days ahead. A reservation **holds the station immediately**, until it is checked in or cancelled. It does not schedule multiple future slots on one PC. The interface explains this before confirmation.
- Only Administrators can create or cancel bookings for accounts or guests. Members have three workspace views: My session, Available stations, and My billing.
- New sessions have a duration of 1–1,440 minutes (default 60). The deadline is saved in MySQL, so refreshing or signing out does not reset it. The browser countdown updates each second. Dashboard refreshes and station actions settle expired sessions, create one invoice, and release the station. If no browser is open, settlement occurs on the next request and billing still stops at the saved deadline.
- Existing sessions from before this update keep their open-ended behavior until an Administrator selects the occupied PC, clicks **Set remaining time**, and supplies a time limit. Members see an explicit “Not set” label for these legacy sessions.
- **Set remaining time** replaces the remaining minutes from now; it does not add minutes. It retains the original start time and hourly rate. Completed sessions require a new session.
- **Stations → Delete** removes a PC from all floor/availability views. End any active session and cancel any reservation first. Historical station records remain for invoices and payments; removed station names remain reserved to preserve identity.
- The session stores the rate in effect when it starts. Later station rate changes apply to new sessions.
- Billing uses elapsed server time rounded up to a whole minute, with a one-minute minimum. The amount is computed with Python `Decimal` and rounded to two decimals. Example: 61 seconds at ₱60/hour is two minutes, or ₱2.00.
- Ending a session creates an unpaid invoice and frees the station. Recording full payment clears that invoice. This version does not implement partial payments, refunds, discounts, tax invoicing, or an online payment gateway.
- Cash, e-wallet, and bank entries are records of funds actually received by the cashier. E-wallet and bank entries require a reference. The application does not transfer funds or independently verify outside payment providers.
- Café dates and totals use `CAFE_TIMEZONE`, defaulting to `Asia/Manila`. Database timestamps use UTC. Booking input uses the Administrator’s device timezone, converts to UTC, and displays in the café timezone afterward.
- Account deactivation revokes its logins. It preserves bookings, running café sessions, and billing records for the Administrator to resolve.
- Station occupancy is managed by the Administrator. Automatic PC discovery, operating-system locking, shutdown, and remote control require a separate station agent and are not part of this web application.

## Authentication and data handling

- Passwords use Werkzeug’s salted scrypt password hashing.
- Random login tokens are stored as hashes in MySQL; signed HttpOnly cookies hold the browser login. Logins expire after 12 hours. Sign-out and password changes revoke stored tokens.
- State-changing API requests require a CSRF token. Permission and ownership checks run on the server.
- Login and registration attempt limits are stored in MySQL. Database queries use parameters.
- Booking/session transitions use transactions and row locks. Unique constraints prevent two active sessions or two pending reservations on a station, and prevent duplicate invoices/payments.
- Station rates and invoice amounts are calculated or retrieved by the backend; customer-supplied amounts are ignored.
- The last active Administrator and your own Administrator role cannot be disabled through account management.
- A Member cannot access another customer’s session or invoice details. Booking details and management actions are restricted to Administrators.

The browser refreshes dashboard data every 15 seconds while the page is visible and no form is being edited. A connection failure leaves an explicit stale-data notice.

## Password recovery and maintenance

Reset a forgotten password from the trusted server console:

```sh
docker compose exec web python -m flask --app app reset-password
```

For a non-Docker setup, replace `docker compose exec web python` with your virtual environment’s Python executable.

Remove expired login/rate-limit records periodically:

```sh
docker compose exec web python -m flask --app app cleanup-auth
```

Public registration can be disabled by setting `ALLOW_REGISTRATION=false` and restarting the web application. Administrators can still create accounts.

## Hosting and backups

For public hosting, put the application behind an HTTPS reverse proxy, set `COOKIE_SECURE=true`, and set `TRUSTED_HOSTS` to your domain plus `localhost,127.0.0.1` for health checks. Retain the default localhost binding when the proxy is on the same machine. Restart the web service after configuration changes.

The application does not trust client-supplied forwarding headers. IP attempt limits will see the proxy’s address unless you deliberately configure a trusted proxy arrangement. Email-based sign-in limits continue to apply. Verify your proxy and authentication behavior before allowing public registrations at scale.

Use a MySQL user scoped to this database. After initialization, your deployment may remove schema-changing privileges and apply future migrations with a separate administrative credential.

Back up the MySQL database regularly with your normal MySQL backup tooling and test restoration. Store `.env` separately and privately. `docker compose down` preserves the data volume; deleting the volume removes its records.

The supplied containers and files are an installable application. They have not been connected to your computers, payment providers, public domain, or existing MySQL server by this delivery.

## Tests

Pure validation and billing tests, with no installed dependencies needed:

```sh
python -m unittest discover -s tests -v
```

Real MySQL integration tests in an isolated, temporary database:

```sh
docker compose --profile test run --build --rm test
docker compose --profile test stop testdb
```

The test profile uses a distinct `testdb` service with a memory-backed database. The tests require `DB_NAME=noir_test` and `RUN_MYSQL_TESTS=1`; they never run automatically against the application database. Never repoint this test database configuration at business data.

Coverage includes registration persistence and hashing, role checks, CSRF, account deactivation, login revocation, reservation ownership, concurrent station starts, rate snapshots, billing, and repeat-payment protection.

## Troubleshooting

| Problem | Action |
| --- | --- |
| `Set a unique SECRET_KEY` | Run `python scripts/configure.py`, or put a generated secret with at least 40 characters in `.env`. |
| Database unavailable | Start MySQL, check DB settings, and run `init-db`. For Docker, inspect `docker compose logs db web`. |
| MySQL access denied after changing `.env` | Restore the matching credential or update the MySQL account itself. Changing container variables does not update an existing database user. |
| Cannot sign in on localhost HTTP | Use `COOKIE_SECURE=false` locally; secure cookies require HTTPS. |
| Session changed | Refresh the page so it receives a fresh CSRF token. |
| Too many attempts | Wait for the attempt-limit window to expire: 15 minutes for sign-in, one hour for registration. |
| Reserved PC will not start for a walk-in | Check in the reservation or cancel it first. |
| A booking holds a PC before arrival | This version uses immediate holds; cancel the reservation to release the station. |
| Forgot a password | Run the `reset-password` console command. |

## Technical references

- [Flask security considerations](https://flask.palletsprojects.com/en/stable/web-security/)
- [Flask configuration](https://flask.palletsprojects.com/en/stable/config/)
- [MySQL locking reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html)
