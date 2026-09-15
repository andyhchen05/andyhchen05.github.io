import unittest

from board import Board
from evaluate import evaluate
from game import Game
from movegen import generate_legal_moves
from search import find_best_move


START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class EngineBenchmarkTests(unittest.TestCase):
    def test_start_position_is_symmetric_and_unchanged(self):
        board = Board(START_FEN)
        before = (board.fen(), board.hash, len(board._history))
        self.assertEqual(evaluate(board), 0)
        self.assertEqual(before, (board.fen(), board.hash, len(board._history)))

    def test_book_returns_principled_opening_sequence(self):
        game = Game()
        self.assertEqual(game.best_move(max_depth=1), "e2e4")
        self.assertTrue(game.push_uci("e2e4"))
        self.assertEqual(game.best_move(max_depth=1), "c7c5")
        self.assertTrue(game.push_uci("c7c5"))
        self.assertEqual(game.best_move(max_depth=1), "g1f3")

    def test_engine_takes_hanging_queen(self):
        board = Board("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1")
        move = find_best_move(board, max_depth=4, time_limit=1.0)
        self.assertIsNotNone(move)
        self.assertEqual(move.uci(), "e4d5")

    def test_engine_finds_mate(self):
        board = Board("7k/5Q2/6K1/8/8/8/8/8 w - - 0 1")
        move = find_best_move(board, max_depth=4, time_limit=1.0)
        self.assertIsNotNone(move)
        board.make_move(move)
        self.assertTrue(board.in_check())
        self.assertEqual(generate_legal_moves(board), [])

    def test_search_restores_board_state(self):
        board = Board(START_FEN)
        before = (board.fen(), board.hash, len(board._history))
        find_best_move(board, max_depth=4, time_limit=1.0)
        self.assertEqual(before, (board.fen(), board.hash, len(board._history)))


if __name__ == "__main__":
    unittest.main()