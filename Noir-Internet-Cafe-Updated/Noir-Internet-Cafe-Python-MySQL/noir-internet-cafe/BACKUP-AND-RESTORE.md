# Backup and isolated restore drill

The backup helper uses official MySQL client tools and a saved login path. Install MySQL 8.x client tools and put their `bin` folder on PATH, or pass the full mysqldump executable path with `--mysqldump`. The script does not encrypt the output or perform a restore. CSV exports cannot replace this backup.

## Configure once on the trusted server

Create a separate backup account through your MySQL administrator. Choose your own strong password locally; do not put it in a submitted document.

```sql
CREATE USER 'noir_backup'@'localhost' IDENTIFIED BY 'CHOOSE_A_UNIQUE_PASSWORD';
GRANT SELECT, SHOW VIEW, TRIGGER ON noir.* TO 'noir_backup'@'localhost';
```

Then run this command in the server terminal. It prompts for the backup account password:

```sh
mysql_config_editor set --login-path=noir-backup --host=127.0.0.1 --user=noir_backup --password
```

The login file is obfuscated, not strong encryption. Restrict it to the server account. On Windows, use folder Security settings to allow only the operator and Administrators to read the login file and backup folder. On Linux, keep the login file mode 600 and backup directory mode 700.

## Create a backup

Stop schema changes and migrations while a dump is running. Normal InnoDB reads/writes may continue. Run with the project's Python executable:

```powershell
& ".\.venv\Scripts\python.exe" scripts/backup.py --output-dir "C:\NOIR-Backups" --database noir
```

Linux equivalent:

```sh
.venv/bin/python scripts/backup.py --output-dir /var/backups/noir --database noir
```

Each successful run writes a timestamped SQL file and a JSON file containing its SHA-256 checksum, size, and UTC timestamp. A failed dump removes its partial output and exits nonzero. Save the exit status/log and inspect the checksum; success is not proof that restoration works. This backup covers application database tables; separately protect `.env`, application source, server configuration, and the MySQL account/grant setup.

For Docker, run the helper where a matching MySQL client can connect to the database. Do not expose MySQL to the public Internet just to run a backup. The bundled Compose database has no host port. An alternative on a Linux Docker host is `docker compose exec -T db mysqldump ...`, using a login path configured inside that container; redirect the output in a trusted shell and check its exit status before treating it as a backup.

## Schedule and retention policy (proposed)

Use the server account that owns the MySQL login path. In Windows Task Scheduler, schedule the full Python executable and full script path with arguments; set Start in to the project folder. On Linux, schedule the equivalent command through a systemd timer or cron. Test the task interactively and after a reboot.

- Daily database backup at closing time; retain 7 daily copies.
- Weekly encrypted offline copy; retain 4 weekly copies.
- Monthly archive; retain 3 monthly copies.
- Rotate two external backup drives, with one disconnected and held securely off-site. Encrypt the drives using an organization-approved tool and keep recovery keys separately.
- Check the job result daily. Perform an isolated restore every month and before major changes.
- Target recovery point: at most 24 hours of lost records. Target recovery time: under 4 hours. These are targets to measure, not achieved results.

## Restore drill - isolated VM only

1. Create an isolated Ubuntu VM using the VM plan in the project report. Give it a separate network with no production connection. Install the same MySQL major version as the source. Copy only a trusted SQL backup and its matching manifest into it.
2. Calculate the SQL file's SHA-256 and compare it with the JSON manifest. A mismatch fails the drill. Use `Get-FileHash -Algorithm SHA256` on Windows or `sha256sum` on Linux.
3. On that isolated VM, create a fresh database named `noir_restore_test`. Configure a `noir-restore` MySQL login path for an account authorized to create and load tables there. Do not use the production database or credentials.
4. Open the MySQL client connected to the test database:

```sh
mysql --login-path=noir-restore noir_restore_test
```

5. Inside the MySQL prompt, load your actual file path (forward slashes also work on Windows):

```sql
SOURCE /path/to/trusted-backup.sql;
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM stations;
SELECT COUNT(*) FROM assets;
SELECT COUNT(*) FROM cafe_sessions;
SELECT COUNT(*) FROM invoices;
SELECT COUNT(*) FROM payments;
SELECT COUNT(*) FROM maintenance_records;
```

6. Compare row counts and payment totals against a source snapshot taken at the backup time. Install a separate NOIR copy in the isolated VM. Configure it for `noir_restore_test`, a new SECRET_KEY, and no public access. Invalidate copied login tokens using `DELETE FROM auth_sessions;` in this isolated database before testing login. Check sample invoices, maintenance history, and account permissions.
7. Record backup age, restore duration, software versions, results, and screenshots without private records. Do not mark the drill successful unless checks pass. Delete the isolated VM when the approved retention period ends. Never restore a test dump over the live database.

Sources: MySQL 8.4 Reference Manual, “mysqldump” and “mysql_config_editor”; CISA, #StopRansomware Guide. URLs and APA references are in the project report.
