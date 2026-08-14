# Home media backup to Google Drive

This helper installs the HDZ-style upload job for generated media metadata under
`/home`.

It copies:

- `/home/symedia_gd` to `REMOTE:/media/symedia_gd`
- `/home/symedia_jav` to `REMOTE:/media/symedia_jav`

Install:

```bash
sudo ./scripts/install-home-media-backup.sh snake_zhangtianlong321:/media
```

Or through the post-auth entry:

```bash
sudo ./post-auth.sh home-media-backup snake_zhangtianlong321:/media
```

Run once immediately:

```bash
sudo /root/scripts/rclone-home-backup.sh
```

Check progress:

```bash
tail -f /var/log/rclone-home-backup/backup-$(date +%F).log
rclone lsf snake_zhangtianlong321:/media/symedia_jav --files-only -R --max-depth 5 | head
```

Why this script does not use `--create-empty-src-dirs`:

For a large Google Drive team drive, `--create-empty-src-dirs` can make rclone
spend a long time creating directory objects first. The drive then appears to
contain the show folders but no `.strm`, `.nfo`, or image files yet. This script
uses file-first `rclone copy` so real files begin appearing before empty
directory metadata is finished.

Notes:

- The job uses `copy`, not `sync`, on the upload side. It will not delete files
  from the team drive just because a local source disappears.
- Duplicate Google Drive objects can still produce
  `Duplicate object found in source - ignoring` during download scans. That is a
  drive-side duplicate-name warning, not proof that new files were uploaded.
