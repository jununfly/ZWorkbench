def normalize_label(value: str) -> str:
    """Normalize a human label for a stable local identifier."""
    return "_".join(value.strip().split())
