# NOIR Internet Café

**Already using NOIR? Follow `UPGRADE.md` to keep your existing database and settings.**

This is a Python application. Open it through the running server; do not double-click the HTML file.


## VS Code on Windows (your existing MySQL setup)

1. Extract the ZIP. In VS Code use **File → Open Folder** and select the inner `noir-internet-cafe` folder containing `app.py` and `requirements.txt`.
2. If upgrading, copy your original `.env` into this folder. Keep your MySQL database. Do not copy `.venv` to a new location.
3. Open **Terminal → New Terminal**. Run:

```powershell
py -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

4. Only if there is no `.env`, run the command below, then edit `.env` to match your actual MySQL database/user/password. The script creates a unique SECRET_KEY; do not replace it with a placeholder.

```powershell
& ".\.venv\Scripts\python.exe" scripts/configure.py
```

5. For your EXISTING database:

```powershell
& ".\.venv\Scripts\python.exe" -m flask --app app migrate-db
& ".\.venv\Scripts\python.exe" app.py
```

6. Open **http://localhost:8000**. Press Ctrl+F5 after upgrading.

For a NEW database, first follow README.md to create the MySQL database and user, then use `init-db` instead of `migrate-db`, followed by `create-admin`, and finally `app.py`.

Optional helper: `.\Start-Noir.ps1 -Mode setup`, then `-Mode migrate`, then `.\Start-Noir.ps1`. If PowerShell blocks local scripts, use the explicit Python commands above; no activation is required.

**Common errors:** A folder path with spaces needs `cd "FULL PATH"`; a path alone is not a command. Missing requirements.txt means the terminal is in the wrong folder. A pip update notice is informational. Missing SECRET_KEY means `.env` is missing or invalid. Do not send anyone your .env or password.

## Quick start with Docker Desktop

Install Docker Desktop (including Docker Compose) and Python 3.11 or newer. Start Docker Desktop, extract this folder, and open a terminal in the extracted folder.

```sh
python scripts/configure.py
docker compose up --build -d
docker compose exec web python -m flask --app app create-admin
```

The last command asks for **your Administrator name, email, and password**. There is no preset account or password. Use at least 12 characters for the password.

Open **http://localhost:8000** and sign in with the Administrator credentials you just created.

1. Open **Stations → Add station**, enter a name, and set your actual hourly rate.
2. Repeat for each computer in your café.
3. Open **Accounts → Create account** to add accounts, or let customers use **Create account** on the sign-in screen.
4. Start sessions, create or check in bookings, and manage billing.

MySQL stores every account, reservation, session, invoice, and payment record. The first launch contains no sample customers, stations, or payments.

**If you already have Python and MySQL installed:** follow the “Without Docker” section in `README.md`.

**Keep `.env` and your MySQL data volume.** `docker compose down` stops the app and preserves its database. Avoid deleting the data volume unless you intentionally want to erase the café’s records.

## Check the installation

```sh
docker compose ps
docker compose logs --tail=80 web
```

MySQL may take a minute to initialize on the first start. Wait for `web` and `db` to be healthy before signing in.

More details: `README.md`. Included verification: `VERIFICATION.md`.