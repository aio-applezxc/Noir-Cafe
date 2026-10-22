# Update your existing NOIR installation

This update adds admin hardware/network inventory, maintenance logs, CSV exports, and console backup tooling. It also fixes the vertical centering on every workspace page, adds station deletion, restricts bookings to administrators, and gives members a read-only dashboard for remaining time, available PCs, and billing.

## Windows / your existing Python and MySQL installation

1. Stop the app with **Ctrl+C** in its terminal. Keep MySQL running.
2. Make a backup of your project folder and database.
3. Copy the files from the updated `noir-internet-cafe` folder into your existing `noir-internet-cafe` folder, replacing matching files. Keep your existing `.env` and `.venv`; the ZIP excludes those machine-specific files.
4. Open a terminal in that project folder and run:

```powershell
.\.venv\Scripts\python.exe -m flask --app app migrate-db
.\.venv\Scripts\python.exe app.py
```

5. Open **http://localhost:8000** and press **Ctrl+F5**.

The migration adds two nullable columns and creates the assets and maintenance_records tables if missing. It preserves accounts, stations, reservations, sessions, invoices, and payments. Run it before opening the updated app. Running it again is safe.

If you extracted into a NEW folder, copy your existing `.env` there, create a fresh virtual environment, install dependencies, then run the commands above:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Existing Docker installation

Keep your current `.env`, database volume, and project location. Replace the source files, then run:

```sh
docker compose up --build -d
```

The container startup runs `init-db`, which includes this update’s migrations. Do not delete the database volume.

## Using the updated features

- **Delete a broken PC:** Stations → Delete → confirm. End its session or cancel its booking first. Previous invoices and payments remain available.
- **Create bookings:** sign in as Administrator. Members have no booking page or booking actions; the server also rejects those requests.
- **Show a member’s countdown:** Start session → choose their Customer account → enter Session time (minutes). Walk-in sessions are not linked to a member login.
- **Change remaining time:** click the occupied station → Set remaining time. Enter the total minutes that should remain from now.
- **Sessions already running before this update:** their previous billing behavior is preserved. Use Set remaining time to give them a countdown.
- **Countdown reaches zero:** the web session ends and its invoice is finalized on the next dashboard refresh (normally within 15 seconds). Billing is capped at its saved deadline. This web app does not lock or shut down the physical PC.

The ZIP contains source code and setup files, not a database dump. Your records remain in your existing MySQL database.

## New platform tools

- **Inventory → Add device:** enter hardware, OS, IP/MAC, hostname, location, purchase cost, and review evidence. Link PCs to their station. IP fields are records; set DHCP reservations on your router separately.
- **Maintenance → Log maintenance:** choose an inventory device, issue, date, technician, and action. Completion requires an action, technician, and completion date.
- **Reports:** export inventory, repairs, usage, or payments as CSV. These exports are admin-only.
- **Backup:** read BACKUP-AND-RESTORE.md before running scripts/backup.py.
- **Windows helper:** Start-Noir.ps1 always works from its own folder and uses a local .venv. Run `./Start-Noir.ps1 -Mode setup` once if you extracted to a new folder.
