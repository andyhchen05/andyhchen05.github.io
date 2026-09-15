"""A compact, deterministic opening book for the browser engine.

The book deliberately contains common principles rather than thousands of
positions. It saves search time in the opening while still handing control
back to the evaluator as soon as a player leaves one of these lines.
"""

from typing import Iterable, Optional, Sequence


# Keys are the complete move history in UCI notation. Values are ordered
# alternatives; the first legal move keeps games reproducible.
OPENING_BOOK = {
    (): ("e2e4", "d2d4", "c2c4", "g1f3"),
    ("e2e4",): ("c7c5", "e7e5", "e7e6", "c7c6"),
    ("e2e4", "c7c5"): ("g1f3", "c2c3", "d2d4"),
    ("e2e4", "c7c5", "g1f3"): ("d7d6", "b8c6", "e7e6"),
    ("e2e4", "c7c5", "g1f3", "d7d6"): ("d2d4", "f1b5", "c2c3"),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4"): ("c5d4", "g8f6"),
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4"): ("f3d4", "d1d4"),
    ("e2e4", "e7e5"): ("g1f3", "f1c4", "d2d4"),
    ("e2e4", "e7e5", "g1f3"): ("b8c6", "g8f6", "d7d6"),
    ("e2e4", "e7e5", "g1f3", "b8c6"): ("f1b5", "f1c4", "d2d4"),
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5"): ("a7a6", "g8f6"),
    ("d2d4",): ("d7d5", "g8f6", "e7e6"),
    ("d2d4", "d7d5"): ("c2c4", "g1f3", "c1f4"),
    ("d2d4", "d7d5", "c2c4"): ("e7e6", "c7c6", "g8f6"),
    ("d2d4", "d7d5", "c2c4", "e7e6"): ("b1c3", "g1f3", "c4d5"),
    ("c2c4",): ("e7e5", "g8f6", "c7c5"),
    ("g1f3",): ("d7d5", "g8f6", "c7c5"),
}


def opening_book_move(
    history: Sequence[str], legal_moves: Iterable[str]
) -> Optional[str]:
    """Return the first legal book move for this exact opening sequence."""
    candidates = OPENING_BOOK.get(tuple(history), ())
    legal = set(legal_moves)
    return next((move for move in candidates if move in legal), None)