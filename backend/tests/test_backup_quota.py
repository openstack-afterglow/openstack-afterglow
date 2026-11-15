"""The global backup-capacity rule never applies to backup counts or typed quotas."""

import pytest

from app.services.backup_quota import derive_backup_gigabytes


@pytest.mark.parametrize("limit,expected", [(-1, -1), (0, 0), (1, 3), (1024, 3072)])
def test_derive_backup_gigabytes(limit, expected):
    assert derive_backup_gigabytes(limit) == expected


@pytest.mark.parametrize("limit", [True, False, -2, 1.0, "1", None])
def test_derive_backup_gigabytes_rejects_invalid_native_limits(limit):
    with pytest.raises(ValueError, match="invalid volume gigabytes quota"):
        derive_backup_gigabytes(limit)
