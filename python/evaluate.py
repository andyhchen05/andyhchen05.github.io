"""Static chess evaluation from White's perspective.

The evaluator intentionally stays inexpensive because it runs inside the
browser. It combines material and piece-square tables with lightweight
positional terms: mobility, pawn structure, passed pawns, rook activity,
the bishop pair, king safety, and endgame king activity.
"""

from __future__ import annotations

from board import (
    Board,
    EMPTY,
    WHITE,
    BLACK,
    PAWN,
    KNIGHT,
    BISHOP,
    ROOK,
    QUEEN,
    KING,
    BISHOP_DELTAS,
    KING_DELTAS,
    KNIGHT_DELTAS,
    ROOK_DELTAS,
    on_board,
    piece_color,
    piece_type,
    sq_file,
    sq_rank,
)

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

# In the endgame, the king becomes an active piece. These values are blended
# with KING_TABLE_MIDDLEGAME according to the remaining non-pawn material.
KING_TABLE_ENDGAME = [
    [-50, -30, -30, -30, -30, -30, -30, -50],
    [-30, -10,   0,   0,   0,   0, -10, -30],
    [-30,   0,  20,  30,  30,  20,   0, -30],
    [-30,  10,  30,  40,  40,  30,  10, -30],
    [-30,  10,  30,  40,  40,  30,  10, -30],
    [-30,   0,  20,  30,  30,  20,   0, -30],
    [-30, -10,   0,   0,   0,   0, -10, -30],
    [-50, -30, -30, -30, -30, -30, -30, -50],
]

PSQ_TABLE = {
    PAWN: PAWN_TABLE,
    KNIGHT: KNIGHT_TABLE,
    BISHOP: BISHOP_TABLE,
    ROOK: ROOK_TABLE,
    QUEEN: QUEEN_TABLE,
    KING: KING_TABLE_MIDDLEGAME,
}

# Phase is measured in standard "game phase" units. 24 represents a full
# complement of non-pawn material; lower values gradually activate the king.
MAX_PHASE = 24
PHASE_VALUE = {KNIGHT: 1, BISHOP: 1, ROOK: 2, QUEEN: 4}
MOBILITY_WEIGHT = {KNIGHT: 4, BISHOP: 4, ROOK: 3, QUEEN: 2, KING: 1}
PASSED_PAWN_BONUS = (0, 5, 10, 18, 30, 48, 75, 0)
EVALUATION_CACHE = {}
EVALUATION_CACHE_LIMIT = 100_000


def _color_sign(color: int) -> int:
    return 1 if color == WHITE else -1


def _collect_pieces(board: Board):
    pieces = {WHITE: [], BLACK: []}
    for sq in range(128):
        if on_board(sq) and board.squares[sq] != EMPTY:
            piece = board.squares[sq]
            pieces[piece_color(piece)].append((sq, piece_type(piece)))
    return pieces


def _phase(pieces) -> int:
    return min(
        MAX_PHASE,
        sum(
            PHASE_VALUE.get(ptype, 0)
            for color in (WHITE, BLACK)
            for _, ptype in pieces[color]
        ),
    )


def _piece_square_value(ptype: int, rank: int, file: int, endgame_ratio: float) -> int:
    table = PSQ_TABLE[ptype]
    middle = table[rank][file]
    if ptype != KING:
        return middle
    endgame = KING_TABLE_ENDGAME[rank][file]
    return round(middle * (1.0 - endgame_ratio) + endgame * endgame_ratio)


def _ray_mobility(board: Board, sq: int, deltas, color: int) -> int:
    """Count reachable squares for a sliding piece, stopping at blockers."""
    score = 0
    for delta in deltas:
        target = sq + delta
        while on_board(target):
            occupant = board.squares[target]
            if occupant == EMPTY:
                score += 1
            else:
                if piece_color(occupant) != color:
                    score += 1
                break
            target += delta
    return score


def _mobility(board: Board, color: int, pieces) -> int:
    """Return a weighted pseudo-legal mobility score for one side."""
    score = 0
    for sq, ptype in pieces[color]:
        if ptype == PAWN:
            continue
        if ptype == KNIGHT:
            targets = KNIGHT_DELTAS
        elif ptype == BISHOP:
            score += MOBILITY_WEIGHT[ptype] * _ray_mobility(board, sq, BISHOP_DELTAS, color)
            continue
        elif ptype == ROOK:
            score += MOBILITY_WEIGHT[ptype] * _ray_mobility(board, sq, ROOK_DELTAS, color)
            continue
        elif ptype == QUEEN:
            score += MOBILITY_WEIGHT[ptype] * (
                _ray_mobility(board, sq, BISHOP_DELTAS, color)
                + _ray_mobility(board, sq, ROOK_DELTAS, color)
            )
            continue
        else:
            targets = KING_DELTAS

        reachable = 0
        for delta in targets:
            target = sq + delta
            if on_board(target) and (
                board.squares[target] == EMPTY
                or piece_color(board.squares[target]) != color
            ):
                reachable += 1
        score += MOBILITY_WEIGHT[ptype] * reachable
    return score


def _pawn_structure(board: Board, color: int, pieces, pawn_files) -> int:
    """Score doubled, isolated, connected, and passed pawns for one side."""
    pawns = [
        (sq_file(sq), sq_rank(sq))
        for sq, ptype in pieces[color]
        if ptype == PAWN
    ]
    if not pawns:
        return 0

    files = pawn_files[color]
    score = 0
    for file in files:
        count = sum(1 for pawn_file, _ in pawns if pawn_file == file)
        score -= 12 * max(0, count - 1)

    enemy = BLACK if color == WHITE else WHITE
    enemy_pawns = [
        (sq_file(sq), sq_rank(sq))
        for sq, ptype in pieces[enemy]
        if ptype == PAWN
    ]
    enemy_by_file = {}
    for file, rank in enemy_pawns:
        enemy_by_file.setdefault(file, []).append(rank)

    direction = 1 if color == WHITE else -1
    for file, rank in pawns:
        if file - 1 not in files and file + 1 not in files:
            score -= 12

        connected = any(
            abs(other_file - file) == 1 and abs(other_rank - rank) <= 1
            for other_file, other_rank in pawns
            if (other_file, other_rank) != (file, rank)
        )
        if connected:
            score += 6

        blocked_by_enemy = any(
            enemy_rank * direction > rank * direction
            for enemy_file in (file - 1, file, file + 1)
            for enemy_rank in enemy_by_file.get(enemy_file, ())
        )
        if not blocked_by_enemy:
            advancement = rank if color == WHITE else 7 - rank
            score += PASSED_PAWN_BONUS[advancement]

    return score


def _rook_activity(board: Board, color: int, pieces, all_pawn_files) -> int:
    own_pawn_files = pawn_files = all_pawn_files[color]
    enemy = BLACK if color == WHITE else WHITE
    pawn_files = pawn_files | all_pawn_files[enemy]
    score = 0
    for sq, ptype in pieces[color]:
        if ptype != ROOK:
            continue
        file = sq_file(sq)
        if file not in pawn_files:
            score += 18
        elif file not in own_pawn_files:
            score += 8
        advanced_rank = sq_rank(sq) if color == WHITE else 7 - sq_rank(sq)
        if advanced_rank == 6:
            score += 16
    return score


def _king_safety(board: Board, color: int, all_pawn_files) -> int:
    """Use pawn shield, nearby open files, and direct check pressure."""
    king_sq = board.king_square(color)
    king_file = sq_file(king_sq)
    king_rank = sq_rank(king_sq)
    direction = 1 if color == WHITE else -1
    score = 0

    shield_rank = king_rank + direction
    if 0 <= shield_rank < 8:
        for file in range(max(0, king_file - 1), min(8, king_file + 2)):
            shield_sq = (shield_rank << 4) | file
            if board.squares[shield_sq] == color | PAWN:
                score += 10

    pawn_files = all_pawn_files[WHITE] | all_pawn_files[BLACK]
    for file in range(max(0, king_file - 1), min(8, king_file + 2)):
        if file not in pawn_files:
            score -= 8

    enemy = BLACK if color == WHITE else WHITE
    if board.is_square_attacked(king_sq, enemy):
        score -= 70
    return score


def _bishop_pair(pieces, color: int) -> int:
    bishops = sum(1 for _, ptype in pieces[color] if ptype == BISHOP)
    return 30 if bishops >= 2 else 0


def evaluate(board: Board) -> int:
    """Static evaluation from White's perspective, in centipawns."""
    cached = EVALUATION_CACHE.get(board.hash)
    if cached is not None:
        return cached

    pieces = _collect_pieces(board)
    pawn_files = {
        color: {sq_file(sq) for sq, ptype in pieces[color] if ptype == PAWN}
        for color in (WHITE, BLACK)
    }
    endgame_ratio = 1.0 - (_phase(pieces) / MAX_PHASE)
    score = 0
    for color in (WHITE, BLACK):
        for sq, ptype in pieces[color]:
            rank = sq_rank(sq)
            file = sq_file(sq)
            table_rank = rank if color == WHITE else 7 - rank
            value = PIECE_VALUE[ptype] + _piece_square_value(
                ptype, table_rank, file, endgame_ratio
            )
            score += _color_sign(color) * value

    score += 4 * (
        _mobility(board, WHITE, pieces) - _mobility(board, BLACK, pieces)
    )
    score += _pawn_structure(board, WHITE, pieces, pawn_files)
    score -= _pawn_structure(board, BLACK, pieces, pawn_files)
    score += _rook_activity(board, WHITE, pieces, pawn_files)
    score -= _rook_activity(board, BLACK, pieces, pawn_files)
    score += _bishop_pair(pieces, WHITE) - _bishop_pair(pieces, BLACK)
    score += round(
        (1.0 - endgame_ratio)
        * (
            _king_safety(board, WHITE, pawn_files)
            - _king_safety(board, BLACK, pawn_files)
        )
    )
    if len(EVALUATION_CACHE) >= EVALUATION_CACHE_LIMIT:
        EVALUATION_CACHE.clear()
    EVALUATION_CACHE[board.hash] = score
    return score