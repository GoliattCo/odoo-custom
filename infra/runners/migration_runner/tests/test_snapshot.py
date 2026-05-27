"""Unit tests for migration_runner.snapshot — specifically the
``_parse_backup_label`` parser which decodes pgbackrest stdout.

Discovered during Tier 5 Item 3 validation that pgbackrest 2.50+
emits a different label-announcement format than the parser
recognized. Real production stdout from pgbackrest 2.57 was
parsed as None → snapshot job failed even though the backup
itself succeeded. Both formats now coexist."""

from __future__ import annotations

from migration_runner.snapshot import _parse_backup_label


class TestParseBackupLabelNewFormat:
    """pgbackrest 2.50+ format: 'INFO: new backup label = <label>'."""

    def test_parses_incremental_label_from_real_257_output(self) -> None:
        # Real stdout captured from the migration-runner daemon on
        # 2026-05-27 during the Tier 5 Item 3 drill against acmesas2.
        stdout = (
            '2026-05-27 06:53:22.191 P00   INFO: last backup label = '
            '20260524-065900F_20260526-065247D, version = 2.57.0\n'
            '2026-05-27 06:53:22.191 P00   INFO: execute non-exclusive backup start\n'
            '2026-05-27 06:53:24.639 P00   INFO: '
            'new backup label = 20260524-065900F_20260527-065322I\n'
            '2026-05-27 06:53:25.504 P00   INFO: incr backup size = 2.5MB\n'
        )
        assert _parse_backup_label(stdout) == '20260524-065900F_20260527-065322I'

    def test_parses_full_backup_label(self) -> None:
        stdout = '2026-05-27 INFO: new backup label = 20260527-120000F\n'
        assert _parse_backup_label(stdout) == '20260527-120000F'


class TestParseBackupLabelLegacyFormat:
    """pre-2.50 format: 'INFO: <type> backup: label = <label>' — kept
    so we can re-deploy older Postgres images without breaking the
    parser."""

    def test_parses_legacy_full_backup_format(self) -> None:
        stdout = 'INFO: full backup: label = 20260523-220000F\n'
        assert _parse_backup_label(stdout) == '20260523-220000F'

    def test_parses_legacy_incr_backup_format(self) -> None:
        stdout = 'INFO: incr backup: label = 20260523-220000F_20260524-100000I\n'
        assert _parse_backup_label(stdout) == '20260523-220000F_20260524-100000I'


class TestParseBackupLabelSelectivity:
    """The parser must NOT return the 'last backup label' line — that's
    the prior backup, not this run's. Returning it would write a stale
    snapshot_id that rollback's `pgbackrest info` lookup wouldn't
    associate with the just-completed job."""

    def test_prefers_new_over_last_when_both_present(self) -> None:
        stdout = (
            'INFO: last backup label = OLD-LABEL\n'
            'INFO: new backup label = NEW-LABEL\n'
        )
        assert _parse_backup_label(stdout) == 'NEW-LABEL'

    def test_returns_none_when_only_last_present(self) -> None:
        # 'last backup label = ...' alone (no 'new' line) means the
        # backup didn't actually run — never claim it as ours.
        # The current parser intentionally matches only 'new backup
        # label = ' and 'backup: label = ', not 'last backup label = '.
        stdout = 'INFO: last backup label = SOMEONE-ELSES-LABEL\n'
        assert _parse_backup_label(stdout) is None


class TestParseBackupLabelEmptyOrMissing:
    def test_returns_none_on_empty_stdout(self) -> None:
        assert _parse_backup_label('') is None

    def test_returns_none_when_no_label_line(self) -> None:
        stdout = 'INFO: backup command begin\nINFO: backup command end\n'
        assert _parse_backup_label(stdout) is None
