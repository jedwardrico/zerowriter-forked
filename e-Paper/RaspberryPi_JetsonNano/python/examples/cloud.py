#
# Cloud backup for ZeroWriter documents, using rclone (https://rclone.org).
#
# rclone talks to Google Drive, Dropbox, OneDrive, S3, WebDAV/Nextcloud, ...
# so this module doesn't care which one you use. Set it up once over SSH
# (see CLOUD_BACKUP.md), then press Ctrl+E on the typewriter.
#
# It is a one-way *copy*: new and changed documents are uploaded, nothing is
# ever deleted or overwritten with older data on either side. Deleting a file
# on the typewriter does not delete its backup.
#
import os
import shutil
import subprocess
import threading
import time

TIMEOUT_S = int(os.environ.get('ZW_CLOUD_TIMEOUT', 120))

_lock = threading.Lock()


def configured_remote(data_dir):
    """The rclone destination, e.g. 'gdrive:ZeroWriter', or None if not set up.

    Taken from $ZW_CLOUD_REMOTE, else the first line of data/cloud_remote.txt.
    """
    remote = os.environ.get('ZW_CLOUD_REMOTE', '').strip()
    if not remote:
        try:
            with open(os.path.join(data_dir, 'cloud_remote.txt')) as f:
                remote = f.readline().strip()
        except OSError:
            remote = ''
    return remote or None


def _log(data_dir, text):
    try:
        with open(os.path.join(data_dir, 'cloud.log'), 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text.strip()}\n")
    except OSError:
        pass


def backup(docs_dir, data_dir):
    """Upload new/changed documents. Returns (ok, short_message).

    The message is short enough to show in the on-screen status corner.
    Details (rclone's own error text) go to data/cloud.log.
    """
    remote = configured_remote(data_dir)
    if not remote:
        return False, "[Setup?]"
    if shutil.which('rclone') is None:
        _log(data_dir, "rclone is not installed")
        return False, "[No tool]"
    if not _lock.acquire(blocking=False):
        return False, "[Busy]"
    try:
        cmd = ['rclone', 'copy', docs_dir, remote, '--update',
               '--include', '*.md', '--contimeout', '15s', '--low-level-retries', '2']
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            _log(data_dir, f"timed out after {TIMEOUT_S}s: {remote}")
            return False, "[Timeout]"
        if result.returncode != 0:
            _log(data_dir, f"rclone exit {result.returncode}: {result.stderr}")
            return False, "[Failed]"
        return True, "[Synced]"
    finally:
        _lock.release()
