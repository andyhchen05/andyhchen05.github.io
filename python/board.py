"""
board.py -- Core board representation for the Python port of GarboChess.

Uses a classic 0x88 board: a 128-square array where the low nibble of a
square index is the file (0-7) and the high nibble is the rank (0-7).
Squares where (square & 0x88) != 0 are off the real 8x8 board and are used
as guard cells so that sliding/knight move generation can detect "off the
board" just by checking that bit.
"""

from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Optional, List

# ---------------------------------------------------------------------------
# Piece / color constants
# ---------------------------------------------------------------------------

EMPTY = 0
PAWN = 1
KNIGHT = 2
BISHOP = 3
ROOK = 4
QUEEN = 5
KING = 6

WHITE = 8
BLACK = 0

PIECE_TYPES = (PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING)

PIECE_CHAR = {PAWN: "p", KNIGHT: "n", BISHOP: "b", ROOK: "r", QUEEN: "q", KING: "k"}
CHAR_PIECE = {v: k for k, v in PIECE_CHAR.items()}

# Castling right bits, matching the original engine's convention.
CASTLE_WHITE_KING = 1
CASTLE_WHITE_QUEEN = 2
CASTLE_BLACK_KING = 4
CASTLE_BLACK_QUEEN = 8

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def piece_type(piece: int) -> int:
    return piece & 0x7


def piece_color(piece: int) -> int:
    return piece & WHITE


def make_piece(color: int, ptype: int) -> int:
    return color | ptype


# ---------------------------------------------------------------------------
# 0x88 square helpers
# ---------------------------------------------------------------------------

def square(file: int, rank: int) -> int:
    """file, rank in 0-7 (a1 = file 0, rank 0) -> 0x88 square index."""
    return (rank << 4) | file


def sq_file(sq: int) -> int:
    return sq & 0x7


def sq_rank(sq: int) -> int:
    return sq >> 4


def on_board(sq: int) -> bool:
    return (sq & 0x88) == 0


def square_name(sq: int) -> str:
    return "abcdefgh"[sq_file(sq)] + str(sq_rank(sq) + 1)


def square_from_name(name: str) -> int:
    file = "abcdefgh".index(name[0])
    rank = int(name[1]) - 1
    return square(file, rank)


# Knight jumps and king/queen/bishop/rook directions, expressed as 0x88 deltas.
KNIGHT_DELTAS = (-33, -31, -18, -14, 14, 18, 31, 33)
BISHOP_DELTAS = (-17, -15, 15, 17)
ROOK_DELTAS = (-16, -1, 1, 16)
KING_DELTAS = BISHOP_DELTAS + ROOK_DELTAS

PAWN_DIR = {WHITE: 16, BLACK: -16}
PAWN_START_RANK = {WHITE: 1, BLACK: 6}
PAWN_PROMOTE_RANK = {WHITE: 7, BLACK: 0}
PAWN_CAPTURE_DELTAS = {WHITE: (15, 17), BLACK: (-15, -17)}


# ---------------------------------------------------------------------------
# Zobrist hashing
# ---------------------------------------------------------------------------
# Used both for cheap repetition detection and as the transposition-table
# key (see search.py). A fixed seed keeps hashes reproducible from run to
# run -- handy for debugging -- while still being effectively random for
# the purpose of avoiding collisions.

_ZOBRIST_RNG = random.Random(0xC0FFEE)


def _rand64() -> int:
    return _ZOBRIST_RNG.getrandbits(64)


def _color_index(color: int) -> int:
    return 0 if color == WHITE else 1


# [color_index][piece_type][square] -- piece_type is 1..6 (PAWN..KING);
# index 0 is simply never touched. Sized to 128 so a square index can be
# used directly without remapping, even though only ~64 entries are ever
# read (off-board 0x88 squares never hold a piece).
ZOBRIST_PIECE = [[[_rand64() for _ in range(128)] for _ in range(7)] for _ in range(2)]
ZOBRIST_SIDE = _rand64()
ZOBRIST_CASTLE_BIT = {
    CASTLE_WHITE_KING: _rand64(),
    CASTLE_WHITE_QUEEN: _rand64(),
    CASTLE_BLACK_KING: _rand64(),
    CASTLE_BLACK_QUEEN: _rand64(),
}
ZOBRIST_EP_FILE = [_rand64() for _ in range(8)]


def _castle_zobrist(castle_rights: int) -> int:
    key = 0
    for bit, z in ZOBRIST_CASTLE_BIT.items():
        if castle_rights & bit:
            key ^= z
    return key


# ---------------------------------------------------------------------------
# Move representation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Move:
    from_sq: int
    to_sq: int
    promotion: Optional[int] = None  # KNIGHT/BISHOP/ROOK/QUEEN
    is_ep: bool = False
    is_castle_king: bool = False
    is_castle_queen: bool = False
    is_double_push: bool = False

    def uci(self) -> str:
        s = square_name(self.from_sq) + square_name(self.to_sq)
        if self.promotion:
            s += PIECE_CHAR[self.promotion]
        return s

    def __str__(self) -> str:
        return self.uci()


@dataclass
class _Undo:
    move: Move
    captured: int
    castle_rights: int
    ep_square: Optional[int]
    halfmove_clock: int
    hash_before: int


class Board:
    def __init__(self, fen: str = START_FEN):
        self.squares: List[int] = [EMPTY] * 128
        self.to_move: int = WHITE
        self.castle_rights: int = 0
        self.ep_square: Optional[int] = None
        self.halfmove_clock: int = 0
        self.fullmove_number: int = 1
        self._history: List[_Undo] = []
        self.hash: int = 0
        # Repetition tracking: a stack of position keys (one per position
        # reached, including the starting one) plus a running count per
        # key, so `is_repetition` is an O(1) lookup at every search node.
        self._position_key_history: List[int] = []
        self._position_counts: dict = {}
        self.set_fen(fen)

    # -- FEN -----------------------------------------------------------

    def set_fen(self, fen: str) -> None:
        parts = fen.split()
        placement = parts[0]
        side = parts[1] if len(parts) > 1 else "w"
        castling = parts[2] if len(parts) > 2 else "-"
        ep = parts[3] if len(parts) > 3 else "-"
        halfmove = int(parts[4]) if len(parts) > 4 else 0
        fullmove = int(parts[5]) if len(parts) > 5 else 1

        self.squares = [EMPTY] * 128
        rank = 7
        file = 0
        for ch in placement:
            if ch == "/":
                rank -= 1
                file = 0
            elif ch.isdigit():
                file += int(ch)
            else:
                color = WHITE if ch.isupper() else BLACK
                ptype = CHAR_PIECE[ch.lower()]
                self.squares[square(file, rank)] = make_piece(color, ptype)
                file += 1

        self.to_move = WHITE if side == "w" else BLACK

        self.castle_rights = 0
        if "K" in castling:
            self.castle_rights |= CASTLE_WHITE_KING
        if "Q" in castling:
            self.castle_rights |= CASTLE_WHITE_QUEEN
        if "k" in castling:
            self.castle_rights |= CASTLE_BLACK_KING
        if "q" in castling:
            self.castle_rights |= CASTLE_BLACK_QUEEN

        self.ep_square = None if ep == "-" else square_from_name(ep)
        self.halfmove_clock = halfmove
        self.fullmove_number = fullmove
        self._history = []

        self.hash = self._compute_hash()
        self._position_key_history = []
        self._position_counts = {}
        self._push_position_key()

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row = ""
            empty = 0
            for file in range(8):
                piece = self.squares[square(file, rank)]
                if piece == EMPTY:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    ch = PIECE_CHAR[piece_type(piece)]
                    row += ch.upper() if piece_color(piece) == WHITE else ch
            if empty:
                row += str(empty)
            rows.append(row)
        placement = "/".join(rows)

        side = "w" if self.to_move == WHITE else "b"

        castling = ""
        if self.castle_rights & CASTLE_WHITE_KING:
            castling += "K"
        if self.castle_rights & CASTLE_WHITE_QUEEN:
            castling += "Q"
        if self.castle_rights & CASTLE_BLACK_KING:
            castling += "k"
        if self.castle_rights & CASTLE_BLACK_QUEEN:
            castling += "q"
        if not castling:
            castling = "-"

        ep = "-" if self.ep_square is None else square_name(self.ep_square)

        return f"{placement} {side} {castling} {ep} {self.halfmove_clock} {self.fullmove_number}"

    # -- Repetition tracking -----------------------------------------------

    def _compute_hash(self) -> int:
        """Full from-scratch Zobrist hash. Only used on set_fen; make_move
        and unmake_move maintain self.hash incrementally from here on."""
        h = 0
        for sq in range(128):
            if not on_board(sq):
                continue
            piece = self.squares[sq]
            if piece == EMPTY:
                continue
            h ^= ZOBRIST_PIECE[_color_index(piece_color(piece))][piece_type(piece)][sq]
        if self.to_move == BLACK:
            h ^= ZOBRIST_SIDE
        h ^= _castle_zobrist(self.castle_rights)
        if self.ep_square is not None:
            h ^= ZOBRIST_EP_FILE[sq_file(self.ep_square)]
        return h

    def _toggle_piece_hash(self, piece: int, sq: int) -> None:
        if piece != EMPTY:
            self.hash ^= ZOBRIST_PIECE[_color_index(piece_color(piece))][piece_type(piece)][sq]

    def _position_key(self) -> int:
        """The Zobrist hash uniquely identifies the current position (piece
        placement, side to move, castling rights, en-passant file) for
        repetition purposes. (Strictly, FIDE rules only count the ep
        square when an ep capture is actually legal; treating any set ep
        square as significant is a common, slightly conservative
        simplification -- it can only under-count repetitions, never
        falsely report one.)"""
        return self.hash

    def _push_position_key(self) -> None:
        key = self._position_key()
        self._position_key_history.append(key)
        self._position_counts[key] = self._position_counts.get(key, 0) + 1

    def _pop_position_key(self) -> None:
        key = self._position_key_history.pop()
        remaining = self._position_counts[key] - 1
        if remaining <= 0:
            del self._position_counts[key]
        else:
            self._position_counts[key] = remaining

    def is_repetition(self, count: int = 3) -> bool:
        """True if the current position has occurred `count` or more times
        in this game (including right now) -- i.e. a threefold-repetition
        claim would be valid. Cheap: backed by an incrementally maintained
        count, not a scan."""
        return self._position_counts.get(self._position_key(), 0) >= count

    # -- Attacks ---------------------------------------------------------

    def is_square_attacked(self, sq: int, by_color: int) -> bool:
        """True if `sq` is attacked by any piece of `by_color`."""
        # Pawns: a pawn of `by_color` attacks diagonally forward, so we look
        # one square diagonally *backward* from `sq` for such a pawn.
        for delta in (15, 17):
            frm = sq - (delta if by_color == WHITE else -delta)
            if on_board(frm) and self.squares[frm] == make_piece(by_color, PAWN):
                return True

        # Knights
        for d in KNIGHT_DELTAS:
            frm = sq + d
            if on_board(frm) and self.squares[frm] == make_piece(by_color, KNIGHT):
                return True

        # King
        for d in KING_DELTAS:
            frm = sq + d
            if on_board(frm) and self.squares[frm] == make_piece(by_color, KING):
                return True

        # Bishops / Queens (diagonal sliders)
        for d in BISHOP_DELTAS:
            frm = sq + d
            while on_board(frm):
                p = self.squares[frm]
                if p != EMPTY:
                    if piece_color(p) == by_color and piece_type(p) in (BISHOP, QUEEN):
                        return True
                    break
                frm += d

        # Rooks / Queens (orthogonal sliders)
        for d in ROOK_DELTAS:
            frm = sq + d
            while on_board(frm):
                p = self.squares[frm]
                if p != EMPTY:
                    if piece_color(p) == by_color and piece_type(p) in (ROOK, QUEEN):
                        return True
                    break
                frm += d

        return False

    def king_square(self, color: int) -> int:
        target = make_piece(color, KING)
        for sq in range(128):
            if on_board(sq) and self.squares[sq] == target:
                return sq
        raise ValueError("no king on board for color")

    def in_check(self, color: Optional[int] = None) -> bool:
        color = self.to_move if color is None else color
        enemy = WHITE if color == BLACK else BLACK
        return self.is_square_attacked(self.king_square(color), enemy)

    # -- Make / Unmake -----------------------------------------------------

    def make_move(self, move: Move) -> None:
        piece = self.squares[move.from_sq]
        color = piece_color(piece)
        ptype = piece_type(piece)
        captured = self.squares[move.to_sq]

        undo = _Undo(
            move=move,
            captured=captured,
            castle_rights=self.castle_rights,
            ep_square=self.ep_square,
            halfmove_clock=self.halfmove_clock,
            hash_before=self.hash,
        )
        self._history.append(undo)

        # En-passant capture removes a pawn that is not on the destination square.
        if move.is_ep:
            captured_sq = move.to_sq - PAWN_DIR[color]
            self._toggle_piece_hash(self.squares[captured_sq], captured_sq)
            self.squares[captured_sq] = EMPTY

        # A normal capture removes whatever was standing on the destination
        # square before the hash reflects the mover arriving there.
        if captured != EMPTY:
            self._toggle_piece_hash(captured, move.to_sq)

        # Move the piece.
        self._toggle_piece_hash(piece, move.from_sq)
        self.squares[move.to_sq] = piece
        self.squares[move.from_sq] = EMPTY
        self._toggle_piece_hash(piece, move.to_sq)

        # Promotion: swap the pawn just placed on to_sq for the promoted piece.
        if move.promotion:
            self._toggle_piece_hash(piece, move.to_sq)
            promoted = make_piece(color, move.promotion)
            self.squares[move.to_sq] = promoted
            self._toggle_piece_hash(promoted, move.to_sq)

        # Castling: move the rook too.
        if move.is_castle_king:
            rank = sq_rank(move.from_sq)
            rook_from = square(7, rank)
            rook_to = square(5, rank)
            rook = self.squares[rook_from]
            self._toggle_piece_hash(rook, rook_from)
            self.squares[rook_to] = rook
            self.squares[rook_from] = EMPTY
            self._toggle_piece_hash(rook, rook_to)
        elif move.is_castle_queen:
            rank = sq_rank(move.from_sq)
            rook_from = square(0, rank)
            rook_to = square(3, rank)
            rook = self.squares[rook_from]
            self._toggle_piece_hash(rook, rook_from)
            self.squares[rook_to] = rook
            self.squares[rook_from] = EMPTY
            self._toggle_piece_hash(rook, rook_to)

        # Update castling rights.
        old_castle_rights = self.castle_rights
        if ptype == KING:
            if color == WHITE:
                self.castle_rights &= ~(CASTLE_WHITE_KING | CASTLE_WHITE_QUEEN)
            else:
                self.castle_rights &= ~(CASTLE_BLACK_KING | CASTLE_BLACK_QUEEN)
        self._clear_castle_right_for_square(move.from_sq)
        self._clear_castle_right_for_square(move.to_sq)
        if self.castle_rights != old_castle_rights:
            self.hash ^= _castle_zobrist(old_castle_rights) ^ _castle_zobrist(self.castle_rights)

        # Update en-passant target square.
        old_ep_square = self.ep_square
        if move.is_double_push:
            self.ep_square = (move.from_sq + move.to_sq) // 2
        else:
            self.ep_square = None
        if old_ep_square is not None:
            self.hash ^= ZOBRIST_EP_FILE[sq_file(old_ep_square)]
        if self.ep_square is not None:
            self.hash ^= ZOBRIST_EP_FILE[sq_file(self.ep_square)]

        # Halfmove clock (50-move rule).
        if ptype == PAWN or captured != EMPTY:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1

        if color == BLACK:
            self.fullmove_number += 1

        self.to_move = WHITE if color == BLACK else BLACK
        self.hash ^= ZOBRIST_SIDE

        self._push_position_key()

    def unmake_move(self) -> None:
        self._pop_position_key()

        undo = self._history.pop()
        move = undo.move

        color = WHITE if self.to_move == BLACK else BLACK
        self.to_move = color

        piece = self.squares[move.to_sq]
        if move.promotion:
            piece = make_piece(color, PAWN)

        self.squares[move.from_sq] = piece
        self.squares[move.to_sq] = undo.captured

        if move.is_ep:
            captured_sq = move.to_sq - PAWN_DIR[color]
            self.squares[move.to_sq] = EMPTY
            self.squares[captured_sq] = make_piece(WHITE if color == BLACK else BLACK, PAWN)

        if move.is_castle_king:
            rank = sq_rank(move.from_sq)
            rook_from = square(7, rank)
            rook_to = square(5, rank)
            self.squares[rook_from] = self.squares[rook_to]
            self.squares[rook_to] = EMPTY
        elif move.is_castle_queen:
            rank = sq_rank(move.from_sq)
            rook_from = square(0, rank)
            rook_to = square(3, rank)
            self.squares[rook_from] = self.squares[rook_to]
            self.squares[rook_to] = EMPTY

        self.castle_rights = undo.castle_rights
        self.ep_square = undo.ep_square
        self.halfmove_clock = undo.halfmove_clock
        # Restoring the saved pre-move hash directly, rather than reversing
        # each XOR above by hand, is both simpler and safer against bugs --
        # there's exactly one way for this to be wrong (the save on the way
        # in) instead of two (save and reverse).
        self.hash = undo.hash_before
        if color == BLACK:
            self.fullmove_number -= 1

    def _clear_castle_right_for_square(self, sq: int) -> None:
        if sq == square(0, 0):
            self.castle_rights &= ~CASTLE_WHITE_QUEEN
        elif sq == square(7, 0):
            self.castle_rights &= ~CASTLE_WHITE_KING
        elif sq == square(0, 7):
            self.castle_rights &= ~CASTLE_BLACK_QUEEN
        elif sq == square(7, 7):
            self.castle_rights &= ~CASTLE_BLACK_KING

    def copy(self) -> "Board":
        b = Board.__new__(Board)
        b.squares = list(self.squares)
        b.to_move = self.to_move
        b.castle_rights = self.castle_rights
        b.ep_square = self.ep_square
        b.halfmove_clock = self.halfmove_clock
        b.fullmove_number = self.fullmove_number
        b._history = []
        b.hash = self.hash
        b._position_key_history = list(self._position_key_history)
        b._position_counts = dict(self._position_counts)
        return b

    def __str__(self) -> str:
        lines = []
        for rank in range(7, -1, -1):
            row = []
            for file in range(8):
                piece = self.squares[square(file, rank)]
                if piece == EMPTY:
                    row.append(".")
                else:
                    ch = PIECE_CHAR[piece_type(piece)]
                    row.append(ch.upper() if piece_color(piece) == WHITE else ch)
            lines.append(f"{rank + 1}  " + " ".join(row))
        lines.append("   a b c d e f g h")
        return "\n".join(lines)


def has_insufficient_material(board: Board) -> bool:
    """True if neither side has enough material to checkmate, even with
    the worst possible play from the opponent.

    Covers the unambiguous, common cases -- king vs king, king+knight vs
    king, king+bishop vs king -- by requiring no pawns/rooks/queens on the
    board and at most one minor piece in total. Rarer "dead position"
    cases (e.g. bishops of the same color on both sides) are deliberately
    not detected: under-detecting a draw here is safe, wrongly declaring
    one is not.
    """
    minors = 0
    for sq in range(128):
        if not on_board(sq):
            continue
        piece = board.squares[sq]
        if piece == EMPTY:
            continue
        ptype = piece_type(piece)
        if ptype in (PAWN, ROOK, QUEEN):
            return False
        if ptype in (KNIGHT, BISHOP):
            minors += 1
            if minors > 1:
                return False
    return True