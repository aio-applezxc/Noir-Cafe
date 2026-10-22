# Verification — 14 October 2026 platform update

## Completed

- Python compilation and JavaScript syntax checks passed.
- 12 billing/validation tests, 9 HTTP workflow tests, and 3 backup-wrapper tests passed (24 total).
- HTTP workflow tests use real Flask requests and a disposable SQLite adapter. They verify administrator-only writes; booking/check-in; personal invoice visibility; station deletion with history preserved; active/reserved station guards; duration validation; legacy sessions; and expiry without duplicate invoices or excess charges.
- JavaScript rendering checks passed for administrator and member navigation, hidden management controls, available-only member station cards, empty and legacy session states, countdown/charge calculations, delete controls, and the shared top-aligned container style. The reusable check is `node tests/check_ui.cjs`.

- Inventory checks cover admin-only access, IPv4/MAC validation, recorded security evidence, partial updates, maintenance completion rules, preserved repair history, and CSV formula neutralization.
- Backup-wrapper tests use mocked mysqldump execution: successful streaming/checksum, failed-dump cleanup, and unsafe database-name rejection. No live dump or restore was performed.
- PowerShell startup/evidence scripts and Linux deployment templates were reviewed but could not be executed on their target platforms.

## Environment limits

No MySQL server or Docker engine was available. Nine opt-in MySQL integration tests are included but were not executed here. The SQLite tests do not verify MySQL syntax, migrations on a real MySQL server, or concurrent row-lock behavior.

A browser was not installed, and its download was blocked by the environment. Browser rendering, screenshots, mobile layout, and interactive click-through verification were not performed. JavaScript rendering checks use a minimal DOM stub, not a real browser layout engine.

## Run locally

```sh
python -m unittest discover -s tests -v
node tests/check_ui.cjs
docker compose --profile test run --build --rm test
```

The Docker test profile uses an isolated `noir_test` database. It verifies full MySQL workflows, concurrency, authentication, timer expiry, station deletion, and repeated migration from the older schema.

## Installation check

1. Run the migration in `UPGRADE.md`, then start NOIR.
2. Check Overview, Stations, Bookings, Billing, Accounts, and Activity: all pages should start at the top with the same header position.
3. Start a timed session as Administrator, linked to a member account. In another browser window, sign in as that member. Confirm the countdown updates, and only My session, Available stations, and My billing appear in navigation.
4. Adjust remaining time as Administrator. Confirm the member sees the change after refresh.
5. Let a short session expire. Verify one invoice, the correct charge, and the released station.
6. Delete an unused or maintenance PC. Confirm it disappears from both dashboards while its earlier invoices and payments remain accessible.
7. Confirm a station with a running session or reservation cannot be deleted until released.
8. Check the mobile layout, keyboard navigation, invoice printing, and refresh after restarting the server.

## Additional platform acceptance checks

9. Admin → Inventory: create a device, enter its actual IP/MAC and specs, link a station, save and reload. Try a duplicate IP and verify rejection.
10. Admin → Maintenance: log a fault; verify completion requires a date, technician and action; export and review CSV.
11. Sign in as a member and verify Inventory, Maintenance and Reports are inaccessible, including direct API requests.
12. Follow PLATFORM-SETUP.md and BACKUP-AND-RESTORE.md to collect real OS, VLAN, HTTPS, backup and restore evidence. Update the project evidence checklist with actual dates/results.
