# ElementX backup and recovery

ElementX research data lives in **three places**. A backup is only complete if all three are covered.

| What | Where | Backed up by |
| --- | --- | --- |
| Samples, experiments, stored analysis results, ownership | SQLite file `DATABASE_URL` (e.g. `/var/data/elementx.db`) | `scripts.data_backup` (this document) |
| Original magnetometry / XRD uploads | `DATA_DIR/experiments/<uuid>/original.<ext>` | `scripts.data_backup` (this document) |
| User accounts (name, email, password hash, user IDs) | MongoDB (`MONGODB_URI`) | **Not covered here** – use MongoDB Atlas backups or `mongodump` |

> **Render disk snapshots are not a complete backup strategy.** Depending on your plan they may be
> unavailable, are tied to the same account/region, can capture a database mid-write, and know nothing
> about MongoDB. Treat them as an extra safety net, never as the only copy. The procedure below
> produces a verified, consistent, portable archive that you must also copy **off the server**.

Every research Sample is owned by a MongoDB user ID (`owner_user_id`). Research data restored without the
matching MongoDB accounts is orphaned (nobody can open it). Always keep a MongoDB backup taken at about the
same time as the research-data backup.

## What the backup tool guarantees

`python -m scripts.data_backup backup`:

1. Snapshots the database with SQLite's **online backup API** (`sqlite3.Connection.backup`). This is
   transactionally consistent even while the service is running in WAL mode. A plain `cp elementx.db` is
   **not** safe: recent committed data may still be in the `-wal` file, and a copy during a write can be torn.
2. Copies every original upload *after* the snapshot. The application writes an original file **before**
   committing its database row, so every row in the snapshot has its file. (A file uploaded in between is
   archived without a row and reported as an orphan – harmless.)
3. Writes one `elementx-backup-<UTC timestamp>.tar.gz` containing `manifest.json`, `elementx.db`, and
   `experiments/<uuid>/original.<ext>`, with SHA-256 checksums for everything.
4. **Verifies the archive it just wrote** (checksums, `PRAGMA integrity_check`, row counts, every experiment's
   original file present) before reporting success.
5. Never modifies or deletes live data. Archives are created with mode `0600` (they contain private research
   data) and are never overwritten.

Exit codes: `0` success; `1` error; `2` the archive was written but one or more experiments reference an
original file that is **missing on disk** (data loss that already happened – investigate immediately).

## Taking a backup

On Render, open a **Shell** for the `elementx-backend` service (shell access depends on your plan – verify
in the dashboard; otherwise use SSH). The environment already contains `DATA_DIR` and `DATABASE_URL`.

```bash
cd /opt/render/project/src/backend      # the service's backend directory; adjust if different
python -m scripts.data_backup backup    # writes to $DATA_DIR/backups/
```

Options:

* `--dest DIR` – write somewhere other than `$DATA_DIR/backups`.
* `--keep N` – afterwards delete the oldest `elementx-backup-*.tar.gz` beyond N (opt-in; nothing else is
  ever deleted).
* `--data-dir` / `--database-url` – override the environment (rarely needed).

`$DATA_DIR/backups` is on the **same disk** as the live data, so it protects against mistakes (a bad restore, an
accidental delete) but **not** against losing the disk. After each backup you must **copy the archive to a
different system** you control (for example `scp` through Render's SSH, or upload to object storage). Encrypt it
first if the destination is shared – the archive is plaintext research data.

Suggested schedule until automation exists: before every deploy, after any large upload session, and at least
daily while the lab is actively using the system. Automated off-site backup is **not implemented** yet (see the
outstanding items in the readiness report).

## Verifying a backup (do this regularly)

```bash
python -m scripts.data_backup verify /path/to/elementx-backup-20261008T120000123456Z.tar.gz
```

This re-checks checksums, SQLite integrity, row counts and original-file presence without touching live data. A
backup you have never verified (and ideally test-restored somewhere else) is a hope, not a backup. Do a **full
test restore into a scratch directory** at least once before going live and after any storage change:

```bash
python -m scripts.data_backup --data-dir /tmp/restore-test \
    --database-url sqlite:////tmp/restore-test/elementx.db restore /path/to/archive.tar.gz
```

## Restoring (metadata **and** original files together)

Both halves are restored in one step, from one archive, so the database and the files always match.

1. **Stop the backend service.** (Restoring under a running service can corrupt it.) On Render: suspend the
   service in the dashboard.
2. Make sure the archive is on the machine/disk (copy it back from your off-site location) and verify it:
   `python -m scripts.data_backup verify ARCHIVE`.
3. Restore. Run the command from a one-off shell with the service's `DATA_DIR`/`DATABASE_URL`:

   ```bash
   python -m scripts.data_backup restore ARCHIVE            # target is empty (new disk)
   python -m scripts.data_backup restore ARCHIVE --force    # target already has data
   ```

   Without `--force` the tool refuses to touch a location that already holds data. With `--force` the existing
   database (and its `-wal`/`-shm` files) and `experiments/` directory are **moved aside** to
   `$DATA_DIR/restore-previous-<UTC timestamp>/` – never deleted. Delete that folder yourself only once you are
   sure the restore is right.
4. The tool re-verifies the archive before changing anything, stages the restore inside `DATA_DIR` (so the
   switch-over is a rename on the same volume), swaps the files in, and runs `PRAGMA integrity_check` on the
   restored database.
5. Start the service. On boot the app opens the database, applies any additive schema upgrade, and re-enables WAL.
6. Check: `GET /health` shows `"researchStorage": true`; sign in and open a saved magnetometry experiment and a
   saved XRD experiment; confirm their plots and Hc/Mr values match what you expect.
7. Make sure the MongoDB accounts correspond to the restored research data (restore MongoDB to the matching time
   if accounts were lost).

### Disaster recovery on a brand-new disk or service

1. Create the service with its persistent disk mounted at `/var/data` (see `docs/PRODUCTION.md`).
2. Copy the archive onto the disk (for example into `/var/data/backups/`).
3. Run `python -m scripts.data_backup restore ARCHIVE` (target empty, so no `--force`).
4. Start the service and run the checks above.

## Restoring only part of the data

Don't. Restoring the database without its original files (or the reverse) produces experiments that cannot be
re-analysed or re-downloaded. The tool deliberately has no partial mode. To inspect a single file, extract it
from the archive (`tar -xzf ARCHIVE experiments/<uuid>/original.dat`) or restore into a scratch directory.

## What is *not* protected

* MongoDB accounts (back them up separately, see above).
* Data created after the last backup.
* Anything if the only archive copy lives on the disk that is lost.
* Secrets (`JWT_SECRET`, API keys): keep them in your password manager; they are never written to an archive.
