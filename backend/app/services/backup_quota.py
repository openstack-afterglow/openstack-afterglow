"""Global Cinder backup capacity derived from the global volume capacity."""


def derive_backup_gigabytes(limit: int) -> int:
    """Preserve native unlimited; otherwise reserve three times volume capacity."""
    if type(limit) is not int or limit < -1:
        raise ValueError("invalid volume gigabytes quota")
    return -1 if limit == -1 else 3 * limit
