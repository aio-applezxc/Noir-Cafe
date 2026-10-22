"""Verify backup command safety and failure cleanup without claiming a live dump."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('backup',Path(__file__).resolve().parent.parent/'scripts/backup.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class BackupTests(unittest.TestCase):
    def args(self,path):
        return argparse.Namespace(database='noir',login_path='noir-backup',output_dir=path,mysqldump='mysqldump',host='127.0.0.1',port=3306)

    def test_streamed_dump_and_manifest_without_password_arguments(self):
        def dump(command,stdout,check):
            self.assertIn('--single-transaction',command)
            self.assertNotIn('--databases',command)
            self.assertEqual(command[-1],'noir')
            self.assertFalse(any('password' in arg for arg in command))
            stdout.write(b'-- test fixture\nCREATE TABLE example(id INT);\n')
        with tempfile.TemporaryDirectory() as directory,patch.object(module.subprocess,'run',side_effect=dump):
            file=module.backup(self.args(directory))
            manifest=json.loads(file.with_suffix('.json').read_text())
            self.assertEqual(manifest['sha256'],hashlib.sha256(file.read_bytes()).hexdigest())
            self.assertEqual(manifest['restore_test'],'pending')
            self.assertFalse(list(Path(directory).glob('*.partial')))

    def test_failed_dump_leaves_no_completed_backup(self):
        def fail(command,stdout,check):
            stdout.write(b'partial')
            raise subprocess.CalledProcessError(1,command)
        with tempfile.TemporaryDirectory() as directory,patch.object(module.subprocess,'run',side_effect=fail):
            with self.assertRaises(subprocess.CalledProcessError):module.backup(self.args(directory))
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_invalid_database_rejected_before_starting_client(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(module.subprocess,'run') as run:
            args=self.args(directory);args.database='--all-databases'
            with self.assertRaises(ValueError):module.backup(args)
            run.assert_not_called()
