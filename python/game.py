"""
game.py -- A friendly wrapper around Board/movegen/search meant to be easy
to drop behind a web API later (Flask/FastAPI endpoint, websocket, etc).

Everything here speaks plain Python types (strings, dicts, lists) so it's
simple to JSON-serialize for a frontend.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any

from board import Board, Move, START_FEN, WHITE, BLACK, square_from_name, has_insufficient_material
from movegen import generate_legal_moves
from search import find_best_move, SearchStats


class Game:
    def __init__(self, fen: str = START_FEN):
        self.board = Board(fen)
        self._move_history: List[str] = []

    # -- Queries -----------------------------------------------------

    def fen(self) -> str:
        return self.board.fen()

    def side_to_move(self) -> str:
        return "white" if self.board.to_move == WHITE else "black"

    def legal_moves(self) -> List[str]:
        return [m.uci() for m in generate_legal_moves(self.board)]

    def is_check(self) -> bool:
        return self.board.in_check()

    def is_checkmate(self) -> bool:
        return self.is_check() and not generate_legal_moves(self.board)

    def is_stalemate(self) -> bool:
        return (not self.is_check()) and not generate_legal_moves(self.board)

    def is_fifty_move_draw(self) -> bool:
        return self.board.halfmove_clock >= 100

    def is_threefold_repetition(self) -> bool:
        return self.board.is_repetition(3)

    def is_insufficient_material(self) -> bool:
        return has_insufficient_material(self.board)

    def is_game_over(self) -> bool:
        return (
            self.is_checkmate()
            or self.is_stalemate()
            or self.is_fifty_move_draw()
            or self.is_threefold_repetition()
            or self.is_insufficient_material()
        )

    def result(self) -> Optional[str]:
        """Returns '1-0', '0-1', '1/2-1/2', or None if the game isn't over."""
        if self.is_checkmate():
            # The side to move is mated, so the *other* side won.
            return "0-1" if self.board.to_move == WHITE else "1-0"
        if (
            self.is_stalemate()
            or self.is_fifty_move_draw()
            or self.is_threefold_repetition()
            or self.is_insufficient_material()
        ):
            return "1/2-1/2"
        return None

    def move_history(self) -> List[str]:
        return list(self._move_history)

    # -- Mutation ------------------------------------------------------

    def push_uci(self, uci: str) -> bool:
        """Play a move given in UCI form (e.g. 'e2e4', 'e7e8q'). Returns
        True if the move was legal and applied, False otherwise."""
        for move in generate_legal_moves(self.board):
            if move.uci() == uci:
                self.board.make_move(move)
                self._move_history.append(uci)
                return True
        return False

    def push(self, move: Move) -> None:
        self.board.make_move(move)
        self._move_history.append(move.uci())

    def undo(self) -> None:
        self.board.unmake_move()
        if self._move_history:
            self._move_history.pop()

    def reset(self, fen: str = START_FEN) -> None:
        self.board = Board(fen)
        self._move_history = []

    # -- Engine move -----------------------------------------------------

    def best_move(
        self, max_depth: int = 4, time_limit: Optional[float] = None
    ) -> Optional[str]:
        """Ask the simple search engine for its choice in this position."""
        move = find_best_move(self.board, max_depth=max_depth, time_limit=time_limit)
        return move.uci() if move is not None else None

    def play_engine_move(
        self, max_depth: int = 4, time_limit: Optional[float] = None
    ) -> Optional[str]:
        """Have the engine pick and actually play a move. Returns the UCI
        string played, or None if there were no legal moves."""
        uci = self.best_move(max_depth=max_depth, time_limit=time_limit)
        if uci is None:
            return None
        self.push_uci(uci)
        return uci

    # -- Serialization for a future web frontend --------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fen": self.fen(),
            "side_to_move": self.side_to_move(),
            "legal_moves": self.legal_moves(),
            "in_check": self.is_check(),
            "game_over": self.is_game_over(),
            "result": self.result(),
            "history": self.move_history(),
        }