"""
search.py -- A simple alpha-beta search.

Negamax with alpha-beta pruning, iterative deepening, a quiescence search
to avoid the worst of the horizon effect, simple MVV-LVA move ordering for
captures, and a transposition table (keyed by the board's incrementally
maintained Zobrist hash) that caches search results across both branches
and iterative-deepening iterations. Still deliberately basic beyond that:
no null-move pruning, no late-move reductions, no killer/history
heuristics, no static-exchange evaluation.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from board import Board, Move, WHITE, piece_type, EMPTY
from movegen import generate_legal_moves, generate_pseudo_legal_moves, is_capture
from evaluate import evaluate, PIECE_VALUE

MATE_SCORE = 1_000_000
INF = 10_000_000

# Any |score| above this is a mate score rather than a normal eval, used to
# decide when TT-stored scores need mate-distance adjustment (see below).
MATE_THRESHOLD = MATE_SCORE - 1_000


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


def _ordered_moves(board: Board, moves: List[Move], tt_move: Optional[Move] = None) -> List[Move]:
    """MVV-LVA/promotion ordering, with the transposition table's
    remembered best move (if any) forced to the front -- it's usually the
    best move here too, and searching it first is what lets alpha-beta
    prune the rest of the list hardest."""
    def key(m: Move) -> int:
        if tt_move is not None and m == tt_move:
            return 1_000_000
        return _move_order_key(board, m)
    return sorted(moves, key=key, reverse=True)


class SearchTimeout(Exception):
    pass


@dataclass
class SearchStats:
    nodes: int = 0
    qnodes: int = 0


# -- Transposition table -----------------------------------------------

EXACT = 0        # score is the true value of the node
LOWER_BOUND = 1  # real score is >= stored score (a beta cutoff happened)
UPPER_BOUND = 2  # real score is <= stored score (no move raised alpha)


@dataclass
class TTEntry:
    depth: int
    score: int
    flag: int
    best_move: Optional[Move]


def _score_to_tt(score: int, ply: int) -> int:
    """Mate scores are naturally expressed as "distance from the root"
    (see MATE_SCORE - ply below), which is exactly wrong for caching: the
    same mate found at a different ply from a different path needs a
    different stored distance. Re-express as "distance from this node"
    before storing."""
    if score > MATE_THRESHOLD:
        return score + ply
    if score < -MATE_THRESHOLD:
        return score - ply
    return score


def _score_from_tt(score: int, ply: int) -> int:
    """Inverse of `_score_to_tt`: convert a stored "distance from this
    node" mate score back into "distance from the root" for the caller."""
    if score > MATE_THRESHOLD:
        return score - ply
    if score < -MATE_THRESHOLD:
        return score + ply
    return score


class Searcher:
    def __init__(self, deadline: Optional[float] = None, tt: Optional[Dict[int, TTEntry]] = None):
        self.deadline = deadline
        self.stats = SearchStats()
        # Shared across iterative-deepening depths (see find_best_move):
        # a shallower iteration's results still narrow the next, deeper
        # one's window and move ordering.
        self.tt: Dict[int, TTEntry] = tt if tt is not None else {}

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

        alpha_orig = alpha

        # Probe the transposition table before doing any move generation --
        # this is the main payoff of the TT: a sufficiently deep prior
        # result can resolve (or narrow) this node for free.
        #
        # Trade-off, shared by essentially every engine that does this:
        # probing before the repetition/50-move check below means a cached
        # score from one path can occasionally be reused on a different
        # path where this exact position is itself a repetition -- the
        # search may then slightly misjudge that one hypothetical line.
        # It never affects real game results: `board.is_repetition` in the
        # actual game (see game.py) always sees the true move history, not
        # the TT, so genuine draw claims are still reported correctly. To
        # keep the table itself clean, repetition/50-move draw scores are
        # never stored (see the early returns below, which skip the store
        # at the bottom of this function).
        tt_key = board.hash
        tt_entry = self.tt.get(tt_key)
        tt_move = tt_entry.best_move if tt_entry is not None else None
        if tt_entry is not None and tt_entry.depth >= depth:
            score = _score_from_tt(tt_entry.score, ply)
            if tt_entry.flag == EXACT:
                return score
            if tt_entry.flag == LOWER_BOUND:
                alpha = max(alpha, score)
            elif tt_entry.flag == UPPER_BOUND:
                beta = min(beta, score)
            if alpha >= beta:
                return score

        legal_moves = generate_legal_moves(board)
        if not legal_moves:
            if board.in_check():
                return -(MATE_SCORE - ply)
            return 0  # stalemate
        if board.halfmove_clock >= 100:
            return 0  # 50-move rule
        if board.is_repetition(3):
            return 0  # threefold repetition
        if depth == 0:
            return self.quiescence(board, alpha, beta)

        best = -INF
        best_move: Optional[Move] = None
        for move in _ordered_moves(board, legal_moves, tt_move):
            board.make_move(move)
            try:
                score = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                # The live game board is also used as the search workspace.
                # Always restore it, including when the search times out.
                board.unmake_move()
            if score > best:
                best = score
                best_move = move
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break  # beta cutoff

        if best <= alpha_orig:
            flag = UPPER_BOUND
        elif best >= beta:
            flag = LOWER_BOUND
        else:
            flag = EXACT
        self.tt[tt_key] = TTEntry(depth=depth, score=_score_to_tt(best, ply), flag=flag, best_move=best_move)

        return best

    def search_root(self, board: Board, depth: int) -> tuple[Optional[Move], int]:
        legal_moves = generate_legal_moves(board)
        if not legal_moves:
            return None, 0
        alpha, beta = -INF, INF
        tt_entry = self.tt.get(board.hash)
        tt_move = tt_entry.best_move if tt_entry is not None else None
        best_move = legal_moves[0]
        best_score = -INF
        for move in _ordered_moves(board, legal_moves, tt_move):
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
        self.tt[board.hash] = TTEntry(depth=depth, score=best_score, flag=EXACT, best_move=best_move)
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
    # One transposition table shared across all iterative-deepening depths
    # for this call: each shallower depth's results seed move ordering
    # (and sometimes outright cutoffs) for the next, deeper one.
    tt: Dict[int, TTEntry] = {}
    for depth in range(1, max_depth + 1):
        searcher = Searcher(deadline=deadline, tt=tt)
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