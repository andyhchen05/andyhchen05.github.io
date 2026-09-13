"""
evaluate.py -- A simple static evaluation function.

Just material counting plus classic piece-square tables (values adapted
from GarboChess's tables, scaled down to centipawns). No mobility,
no pawn structure, no king-safety scoring -- those are the "exotic"
extras this simple port intentionally leaves out.

Evaluation is from White's perspective: positive means White is better.
"""

from __future__ import annotations

from board import Board, EMPTY, WHITE, BLACK, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, on_board, piece_color, piece_type

PIECE_VALUE = {
    PAWN: 100,
    KNIGHT: 320,
    BISHOP: 330,
    ROOK: 500,
    QUEEN: 950,
    KING: 0,
}

# Piece-square tables, indexed [rank 0..7][file 0..7] from White's side of
# the board (rank 0 = White's back rank). For Black we mirror the rank.
PAWN_TABLE = [
    [0,   0,   0,   0,   0,   0,   0,   0],
    [5,  10,  10, -20, -20,  10,  10,   5],
    [5,  -5, -10,   0,   0, -10,  -5,   5],
    [0,   0,   0,  20,  20,   0,   0,   0],
    [5,   5,  10,  25,  25,  10,   5,   5],
    [10, 10,  20,  30,  30,  20,  10,  10],
    [50, 50,  50,  50,  50,  50,  50,  50],
    [0,   0,   0,   0,   0,   0,   0,   0],
]

KNIGHT_TABLE = [
    [-50, -40, -30, -30, -30, -30, -40, -50],
    [-40, -20,   0,   5,   5,   0, -20, -40],
    [-30,   5,  10,  15,  15,  10,   5, -30],
    [-30,   0,  15,  20,  20,  15,   0, -30],
    [-30,   5,  15,  20,  20,  15,   5, -30],
    [-30,   0,  10,  15,  15,  10,   0, -30],
    [-40, -20,   0,   0,   0,   0, -20, -40],
    [-50, -40, -30, -30, -30, -30, -40, -50],
]

BISHOP_TABLE = [
    [-20, -10, -10, -10, -10, -10, -10, -20],
    [-10,   5,   0,   0,   0,   0,   5, -10],
    [-10,  10,  10,  10,  10,  10,  10, -10],
    [-10,   0,  10,  10,  10,  10,   0, -10],
    [-10,   5,   5,  10,  10,   5,   5, -10],
    [-10,   0,   5,  10,  10,   5,   0, -10],
    [-10,   0,   0,   0,   0,   0,   0, -10],
    [-20, -10, -10, -10, -10, -10, -10, -20],
]

ROOK_TABLE = [
    [0,  0,  0,  5,  5,  0,  0,  0],
    [-5,  0,  0,  0,  0,  0,  0, -5],
    [-5,  0,  0,  0,  0,  0,  0, -5],
    [-5,  0,  0,  0,  0,  0,  0, -5],
    [-5,  0,  0,  0,  0,  0,  0, -5],
    [-5,  0,  0,  0,  0,  0,  0, -5],
    [5, 10, 10, 10, 10, 10, 10,  5],
    [0,  0,  0,  0,  0,  0,  0,  0],
]

QUEEN_TABLE = [
    [-20, -10, -10, -5, -5, -10, -10, -20],
    [-10,   0,   5,  0,  0,   0,   0, -10],
    [-10,   5,   5,  5,  5,   5,   0, -10],
    [0,   0,   5,  5,  5,   5,   0,  -5],
    [-5,   0,   5,  5,  5,   5,   0,  -5],
    [-10,   0,   5,  5,  5,   5,   0, -10],
    [-10,   0,   0,  0,  0,   0,   0, -10],
    [-20, -10, -10, -5, -5, -10, -10, -20],
]

KING_TABLE_MIDDLEGAME = [
    [20,  30,  10,   0,   0,  10,  30,  20],
    [20,  20,   0,   0,   0,   0,  20,  20],
    [-10, -20, -20, -20, -20, -20, -20, -10],
    [-20, -30, -30, -40, -40, -30, -30, -20],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
]

PSQ_TABLE = {
    PAWN: PAWN_TABLE,
    KNIGHT: KNIGHT_TABLE,
    BISHOP: BISHOP_TABLE,
    ROOK: ROOK_TABLE,
    QUEEN: QUEEN_TABLE,
    KING: KING_TABLE_MIDDLEGAME,
}


def evaluate(board: Board) -> int:
    """Static evaluation from White's perspective, in centipawns."""
    score = 0
    for sq in range(128):
        if not on_board(sq):
            continue
        piece = board.squares[sq]
        if piece == EMPTY:
            continue
        color = piece_color(piece)
        ptype = piece_type(piece)
        rank = sq >> 4
        file = sq & 0x7
        table = PSQ_TABLE[ptype]
        psq = table[rank][file] if color == WHITE else table[7 - rank][file]
        value = PIECE_VALUE[ptype] + psq
        score += value if color == WHITE else -value
    return score