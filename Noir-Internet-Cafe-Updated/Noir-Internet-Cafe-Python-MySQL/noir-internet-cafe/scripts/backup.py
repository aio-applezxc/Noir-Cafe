"""Consistent InnoDB backup using a preconfigured MySQL client login path.

Requires MySQL client tools. Configure credentials with mysql_config_editor;
the password is never passed as a command argument or stored by this script.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid


def backup(args):
    if not re.fullmatch(r'[A-Za-z0-9_]+', args.database):
        raise ValueError('Database name must contain letters, digits or underscores.')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.login_path):
        raise ValueError('Invalid login path name.')
    destination = Path(args.output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = destination / f'{args.database}-{stamp}-{uuid.uuid4().hex[:8]}.sql'
    partial = output.with_suffix('.sql.partial')
    command = [args.mysqldump, f'--login-path={args.login_path}', '--protocol=TCP',
               f'--host={args.host}', f'--port={args.port}', '--single-transaction',
               '--quick', '--no-tablespaces', '--set-gtid-purged=OFF',
               '--column-statistics=0', '--skip-lock-tables', args.database]
    try:
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            # Inherit stderr so native MySQL connection errors remain actionable.
            subprocess.run(command, stdout=handle, check=True)
        if not partial.stat().st_size:
            raise RuntimeError('mysqldump produced an empty file.')
        partial.rename(output)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256()
    with output.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    manifest = {'file':output.name, 'sha256':digest.hexdigest(), 'database':args.database,
                'created_utc':stamp, 'bytes':output.stat().st_size,
                'restore_test':'pending', 'encrypted':False}
    descriptor = os.open(output.with_suffix('.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(manifest, handle, indent=2)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--database', default='noir')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=3306)
    parser.add_argument('--login-path', default='noir-backup')
    parser.add_argument('--mysqldump', default='mysqldump')
    args = parser.parse_args()
    try:
        output = backup(args)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Backup failed: {error}\n')
    print(f'Backup saved: {output}')
    print('SQL contains private records. Encrypt/copy it offline and test a restore in an isolated VM.')


if __name__ == '__main__':
    main()
