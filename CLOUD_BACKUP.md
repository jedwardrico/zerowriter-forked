# Cloud backup

Press **Ctrl+E** on the typewriter to copy your saved documents to a cloud service.
It uses [rclone](https://rclone.org), which supports Google Drive, Dropbox, OneDrive,
Nextcloud/WebDAV, S3 and many more, so you pick the service.

- It is a one-way copy. New and changed `.md` files are uploaded; nothing is ever deleted
  or overwritten with an older version. Deleting a file on the typewriter does **not**
  delete its backup.
- Typing keeps working while it uploads. The corner of the screen shows `[Syncing]`, then
  `[Synced]`, or `[Failed]` / `[Timeout]` / `[Setup?]` / `[No tool]`.
- The open document is saved first. Text that has never been saved (no file name yet) is
  not uploaded: press Ctrl+S first.
- The Pi needs a wifi connection when you press Ctrl+E. Your SD card files are unaffected.
- Details of any failure are written to `data/cloud.log` next to `main.py`.

## One-time setup (over SSH)

1. Install rclone: `sudo apt install rclone`
2. The typewriter runs as root (`sudo python main.py`), so configure rclone as root too:
   `sudo rclone config`
   Choose `n` (new remote), give it a name such as `gdrive`, pick your service, and follow
   the prompts. For Google Drive / Dropbox / OneDrive, the Pi has no browser: when asked
   "Use web browser to automatically authenticate?" answer `n`, then run the
   `rclone authorize "drive"` command it shows on a computer that has a browser and paste
   the result back. See https://rclone.org/remote_setup/
3. Check it works: `sudo rclone lsd gdrive:`
4. Tell ZeroWriter where to send files, in the `examples` folder (use any folder name):
   `echo "gdrive:ZeroWriter" | sudo tee data/cloud_remote.txt`
   (or set the `ZW_CLOUD_REMOTE` environment variable instead)
5. Restart the typewriter, write something, Ctrl+S, then Ctrl+E.

Credentials live in rclone's config (`/root/.config/rclone/rclone.conf`), not in this
repository. For a Google Drive account you care about, consider rclone's `drive.file`
scope, which lets it see only the files it created.

## Possible follow-ups

- **Back up on idle:** run the backup automatically after a stretch with no typing (e.g. a few
  minutes), only if something changed since the last successful sync. Should stay silent if
  the Pi is offline rather than showing `[Failed]` over and over.
- **Back up on power-down:** run the backup on Ctrl+Esc before `poweroff`. Needs a short
  timeout so a missing wifi connection can't delay shutdown, and an on-screen "Backing up..."
  note instead of the usual power-down message while it runs.
