import json
import math

FACE_MATCH_THRESHOLD = 0.45   # lower = stricter


def _is_descriptor(d):
    return (
        isinstance(d, (list, tuple))
        and len(d) == 128
        and all(isinstance(x, (int, float)) for x in d)
    )


def validate_face_descriptor(descriptor):
    """True if it is ONE valid descriptor (128 numbers)."""
    return _is_descriptor(descriptor)


def normalize_descriptors(stored):
    """Accepts None, a JSON string, one descriptor, or a list of descriptors.
    Always returns a list of valid descriptors (may be empty)."""
    if not stored:
        return []

    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except ValueError:
            return []

    if _is_descriptor(stored):
        return [list(stored)]

    if isinstance(stored, (list, tuple)):
        return [list(d) for d in stored if _is_descriptor(d)]

    return []


def verify_staff_face(stored, live):
    """Compare the live face with ALL saved faces and use the closest one.
    Returns (matched: bool, distance: float)."""
    descriptors = normalize_descriptors(stored)

    if not descriptors:
        raise ValueError("No registered face found.")

    if not _is_descriptor(live):
        raise ValueError("Invalid live face data.")

    best = min(
        math.sqrt(sum((a - b) ** 2 for a, b in zip(saved, live)))
        for saved in descriptors
    )

    return best < FACE_MATCH_THRESHOLD, best