"""
movegen.py -- Move generation for the Python GarboChess port.

Generates pseudo-legal moves piece by piece (simple, readable -- no
piece-list bookkeeping like the original engine), then filters out any
move that would leave the mover's own king in check to get legal moves.
"""

from __future__ import annotations
from typing import List

from board import (
    Board, Move, EMPTY, WHITE, BLACK, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING,
    KNIGHT_DELTAS, BISHOP_DELTAS, ROOK_DELTAS, KING_DELTAS,
    PAWN_DIR, PAWN_START_RANK, PAWN_PROMOTE_RANK, PAWN_CAPTURE_DELTAS,
    on_board, sq_rank, square, piece_color, piece_type,
    CASTLE_WHITE_KING, CASTLE_WHITE_QUEEN, CASTLE_BLACK_KING, CASTLE_BLACK_QUEEN,
)

PROMOTION_PIECES = (QUEEN, ROOK, BISHOP, KNIGHT)


def _add_pawn_moves(board: Board, frm: int, to: int, moves: List[Move], is_ep: bool = False) -> None:
    if sq_rank(to) == PAWN_PROMOTE_RANK[board.to_move]:
        for promo in PROMOTION_PIECES:
            moves.append(Move(frm, to, promotion=promo))
    else:
        moves.append(Move(frm, to, is_ep=is_ep))


def generate_pseudo_legal_moves(board: Board) -> List[Move]:
    moves: List[Move] = []
    color = board.to_move
    enemy = WHITE if color == BLACK else BLACK

    for frm in range(128):
        if not on_board(frm):
            continue
        piece = board.squares[frm]
        if piece == EMPTY or piece_color(piece) != color:
            continue
        ptype = piece_type(piece)

        if ptype == PAWN:
            direction = PAWN_DIR[color]

            # Single push
            to = frm + direction
            if on_board(to) and board.squares[to] == EMPTY:
                _add_pawn_moves(board, frm, to, moves)

                # Double push from the start rank
                if sq_rank(frm) == PAWN_START_RANK[color]:
                    to2 = frm + 2 * direction
                    if board.squares[to2] == EMPTY:
                        moves.append(Move(frm, to2, is_double_push=True))

            # Captures (including en-passant)
            for delta in PAWN_CAPTURE_DELTAS[color]:
                to = frm + delta
                if not on_board(to):
                    continue
                target = board.squares[to]
                if target != EMPTY and piece_color(target) == enemy:
                    _add_pawn_moves(board, frm, to, moves)
                elif board.ep_square is not None and to == board.ep_square:
                    _add_pawn_moves(board, frm, to, moves, is_ep=True)

        elif ptype == KNIGHT:
            for d in KNIGHT_DELTAS:
                to = frm + d
                if not on_board(to):
                    continue
                target = board.squares[to]
                if target == EMPTY or piece_color(target) == enemy:
                    moves.append(Move(frm, to))

        elif ptype == KING:
            for d in KING_DELTAS:
                to = frm + d
                if not on_board(to):
                    continue
                target = board.squares[to]
                if target == EMPTY or piece_color(target) == enemy:
                    moves.append(Move(frm, to))
            _generate_castle_moves(board, frm, moves)

        else:  # sliding pieces: bishop, rook, queen
            deltas = {
                BISHOP: BISHOP_DELTAS,
                ROOK: ROOK_DELTAS,
                QUEEN: BISHOP_DELTAS + ROOK_DELTAS,
            }[ptype]
            for d in deltas:
                to = frm + d
                while on_board(to):
                    target = board.squares[to]
                    if target == EMPTY:
                        moves.append(Move(frm, to))
                    else:
                        if piece_color(target) == enemy:
                            moves.append(Move(frm, to))
                        break
                    to += d

    return moves


def _generate_castle_moves(board: Board, king_sq: int, moves: List[Move]) -> None:
    color = board.to_move
    enemy = WHITE if color == BLACK else BLACK
    rank = 0 if color == WHITE else 7
    if king_sq != square(4, rank):
        return

    king_right = CASTLE_WHITE_KING if color == WHITE else CASTLE_BLACK_KING
    queen_right = CASTLE_WHITE_QUEEN if color == WHITE else CASTLE_BLACK_QUEEN

    if board.in_check(color):
        return

    if board.castle_rights & king_right:
        f_sq, g_sq, h_sq = square(5, rank), square(6, rank), square(7, rank)
        if (board.squares[f_sq] == EMPTY and board.squares[g_sq] == EMPTY
                and board.squares[h_sq] == (ROOK | color)
                and not board.is_square_attacked(f_sq, enemy)
                and not board.is_square_attacked(g_sq, enemy)):
            moves.append(Move(king_sq, g_sq, is_castle_king=True))

    if board.castle_rights & queen_right:
        b_sq, c_sq, d_sq, a_sq = (square(1, rank), square(2, rank),
                                   square(3, rank), square(0, rank))
        if (board.squares[b_sq] == EMPTY and board.squares[c_sq] == EMPTY
                and board.squares[d_sq] == EMPTY
                and board.squares[a_sq] == (ROOK | color)
                and not board.is_square_attacked(d_sq, enemy)
                and not board.is_square_attacked(c_sq, enemy)):
            moves.append(Move(king_sq, c_sq, is_castle_queen=True))


def generate_legal_moves(board: Board) -> List[Move]:
    color = board.to_move
    legal: List[Move] = []
    for move in generate_pseudo_legal_moves(board):
        board.make_move(move)
        if not board.in_check(color):
            legal.append(move)
        board.unmake_move()
    return legal


def is_capture(board: Board, move: Move) -> bool:
    return board.squares[move.to_sq] != EMPTY or move.is_ep