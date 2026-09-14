"""
search.py -- A simple alpha-beta search.
Deliberately basic, per spec: plain negamax with alpha-beta pruning,
iterative deepening, a quiescence search to avoid the worst of the
horizon effect, and simple MVV-LVA move ordering for captures. No
transposition table, no null-move pruning, no late-move reductions, no
killer/history heuristics, no static-exchange evaluation.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import List, Optional, Callable
from board import Board, Move, WHITE, piece_type, EMPTY
from movegen import generate_legal_moves, generate_pseudo_legal_moves, is_capture
from evaluate import evaluate, PIECE_VALUE
MATE_SCORE = 1_000_000
INF = 10_000_000
def _side_to_move_eval(board: Board) -> int:
    score = evaluate(board)
    return score if board.to_move == WHITE else -score
def _move_order_key(board: Board, move: Move) -> int:
    """Higher is searched first. MVV-LVA for captures, promotions boosted."""
    score = 0
    if is_capture(board, move):
        victim = board.squares[move.to_sq]
        attacker = board.squares[move.from_sq]
        victim_value = PIECE_VALUE[piece_type(victim)] if victim != EMPTY else PIECE_VALUE[1]  # EP capture: pawn
        attacker_value = PIECE_VALUE[piece_type(attacker)]
        score += 10_000 + victim_value * 10 - attacker_value
    if move.promotion:
        score += 5_000 + PIECE_VALUE[move.promotion]
    return score
def _ordered_moves(board: Board, moves: List[Move]) -> List[Move]:
    return sorted(moves, key=lambda m: _move_order_key(board, m), reverse=True)
class SearchTimeout(Exception):
    pass
@dataclass
class SearchStats:
    nodes: int = 0
    qnodes: int = 0
class Searcher:
    def __init__(self, deadline: Optional[float] = None):
        self.deadline = deadline
        self.stats = SearchStats()
    def _check_time(self) -> None:
        if self.deadline is not None and time.time() > self.deadline:
            raise SearchTimeout()
    def quiescence(self, board: Board, alpha: int, beta: int, depth_left: int = 6) -> int:
        self.stats.qnodes += 1
        if self.stats.qnodes % 2048 == 0:
            self._check_time()
        stand_pat = _side_to_move_eval(board)
        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat
        if depth_left == 0:
            return alpha
        captures = [m for m in generate_pseudo_legal_moves(board) if is_capture(board, m)]
        for move in _ordered_moves(board, captures):
            mover = board.to_move
            board.make_move(move)
            try:
                if board.in_check(mover):
                    # Illegal: that move left the mover's own king in check.
                    continue
                score = -self.quiescence(board, -beta, -alpha, depth_left - 1)
            finally:
                # SearchTimeout (and any other exception) must not leave the
                # caller's board in the position being searched.
                board.unmake_move()
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha
    def negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.stats.nodes += 1
        if self.stats.nodes % 1024 == 0:
            self._check_time()
        legal_moves = generate_legal_moves(board)
        if not legal_moves:
            if board.in_check():
                return -(MATE_SCORE - ply)
            return 0  # stalemate
        if board.halfmove_clock >= 100:
            return 0  # 50-move rule
        if depth == 0:
            return self.quiescence(board, alpha, beta)
        best = -INF
        for move in _ordered_moves(board, legal_moves):
            board.make_move(move)
            try:
                score = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                # The live game board is also used as the search workspace.
                # Always restore it, including when the search times out.
                board.unmake_move()
            if score > best:
                best = score
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break  # beta cutoff
        return best
    def search_root(self, board: Board, depth: int) -> tuple[Optional[Move], int]:
        legal_moves = generate_legal_moves(board)
        if not legal_moves:
            return None, 0
        alpha, beta = -INF, INF
        best_move = legal_moves[0]
        best_score = -INF
        for move in _ordered_moves(board, legal_moves):
            board.make_move(move)
            try:
                score = -self.negamax(board, depth - 1, -beta, -alpha, 1)
            finally:
                # Do not leak a partially searched line into the actual game.
                board.unmake_move()
            if score > best_score:
                best_score = score
                best_move = move
            if best_score > alpha:
                alpha = best_score
        return best_move, best_score
def find_best_move(
    board: Board,
    max_depth: int = 4,
    time_limit: Optional[float] = None,
    on_iteration: Optional[Callable[[int, Move, int, SearchStats], None]] = None,
) -> Optional[Move]:
    """Iterative deepening driver.
    Runs alpha-beta at increasing depth until `max_depth` is reached or
    `time_limit` seconds have elapsed, returning the best move found by the
    deepest fully-completed iteration.
    """
    deadline = (time.time() + time_limit) if time_limit is not None else None
    best_move: Optional[Move] = None
    stats = SearchStats()
    for depth in range(1, max_depth + 1):
        searcher = Searcher(deadline=deadline)
        try:
            move, score = searcher.search_root(board, depth)
        except SearchTimeout:
            break
        stats.nodes += searcher.stats.nodes
        stats.qnodes += searcher.stats.qnodes
        if move is not None:
            best_move = move
            if on_iteration is not None:
                on_iteration(depth, move, score, searcher.stats)
        if deadline is not None and time.time() > deadline:
            break
    return best_move