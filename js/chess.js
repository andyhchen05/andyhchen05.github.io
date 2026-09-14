// chess.js -- board UI + engine control for chess.html.
// The actual chess engine runs in chess-worker.js (Python via Pyodide);
// this file only draws the board and relays moves back and forth.

const PIECE_GLYPH = {
  P: "\u2659", N: "\u2658", B: "\u2657", R: "\u2656", Q: "\u2655", K: "\u2654",
  p: "\u265F", n: "\u265E", b: "\u265D", r: "\u265C", q: "\u265B", k: "\u265A",
};
const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];

class EngineClient {
  constructor(workerUrl) {
    this.worker = new Worker(workerUrl);
    this._nextId = 1;
    this._pending = new Map();
    this.worker.onmessage = (event) => {
      const { id, ok, result, error } = event.data;
      const resolver = this._pending.get(id);
      if (!resolver) return;
      this._pending.delete(id);
      ok ? resolver.resolve(result) : resolver.reject(new Error(error));
    };
  }

  _call(type, payload = {}) {
    const id = this._nextId++;
    return new Promise((resolve, reject) => {
      this._pending.set(id, { resolve, reject });
      this.worker.postMessage({ id, type, payload });
    });
  }

  init() { return this._call("init"); }
  reset() { return this._call("reset"); }
  pushMove(uci) { return this._call("push_move", { uci }); }
  engineMove(timeLimit, maxDepth) { return this._call("engine_move", { timeLimit, maxDepth }); }
}

class ChessUI {
  constructor(root, engine) {
    this.root = root;
    this.engine = engine;
    this.boardEl = root.querySelector("#board");
    this.boardShell = root.querySelector(".board-shell");
    this.statusEl = root.querySelector("#status");
    this.historyEl = root.querySelector("#move-history");
    this.newGameBtn = root.querySelector("#new-game");
    this.sideSelect = root.querySelector("#side-select");
    this.strengthSelect = root.querySelector("#strength-select");

    this.humanColor = "white";
    this.flipped = false;
    this.selected = null;
    this.state = null;
    this.locked = true; // locked while engine is thinking / not yet loaded

    this._buildSquares();
    this.newGameBtn.addEventListener("click", () => this.newGame());
    this.sideSelect.addEventListener("change", () => this.newGame());
  }

  _buildSquares() {
    this.boardEl.innerHTML = "";
    this.squareEls = {};
    for (let rank = 7; rank >= 0; rank--) {
      for (let file = 0; file < 8; file++) {
        const name = FILES[file] + (rank + 1);
        const sq = document.createElement("div");
        sq.className = "square " + ((file + rank) % 2 === 0 ? "dark" : "light");
        sq.dataset.square = name;
        sq.addEventListener("click", () => this.onSquareClick(name));
        sq.addEventListener("dragstart", (event) => this.onDragStart(event, name));
        sq.addEventListener("dragover", (event) => this.onDragOver(event, name));
        sq.addEventListener("drop", (event) => this.onDrop(event, name));
        sq.addEventListener("dragend", () => this.onDragEnd());
        this.boardEl.appendChild(sq);
        this.squareEls[name] = sq;
      }
    }
  }

  async start() {
    this.setStatus("Loading engine\u2026");
    this.state = (await this.engine.init()).state;
    this.locked = false;
    this.render();
    this.maybeLetEngineMove();
  }

  async newGame() {
    this.humanColor = this.sideSelect.value;
    this.flipped = this.humanColor === "black";
    this.selected = null;
    this.locked = true;
    this.setStatus("Starting new game\u2026");
    this._buildSquares();
    this.state = (await this.engine.reset()).state;
    this.locked = false;
    this.render();
    this.maybeLetEngineMove();
  }

  strengthConfig() {
    const v = this.strengthSelect.value;
    if (v === "fast") return { timeLimit: 0.6, maxDepth: 4 };
    if (v === "strong") return { timeLimit: 3.0, maxDepth: 6 };
    return { timeLimit: 1.5, maxDepth: 5 }; // "normal"
  }

  async maybeLetEngineMove() {
    if (!this.state || this.state.game_over) {
      this.showResult();
      return;
    }
    if (this.state.side_to_move === this.humanColor) return;

    this.locked = true;
    this.setStatus("Engine is thinking\u2026");
    const { timeLimit, maxDepth } = this.strengthConfig();
    const { played, state } = await this.engine.engineMove(timeLimit, maxDepth);
    this.state = state;
    this.locked = state.game_over;
    this.render();
    if (played) this.appendHistory(played);
    if (state.game_over) {
      this.showResult();
    } else {
      this.setStatus(`Your move (${this.humanColor}).`);
    }
  }

  async onSquareClick(square) {
    if (this.locked || !this.state || this.state.game_over) return;
    if (this.state.side_to_move !== this.humanColor) return;

    const piece = this.pieceAt(square);
    const isOwnPiece = piece && this.isHumanPiece(piece);

    if (this.selected === null) {
      if (isOwnPiece) {
        this.selected = square;
        this.render();
      }
      return;
    }

    if (square === this.selected) {
      this.selected = null;
      this.render();
      return;
    }

    if (this.selected) {
      await this.tryMove(this.selected, square);
    }
  }

  onDragStart(event, square) {
    if (
      this.locked ||
      !this.state ||
      this.state.game_over ||
      this.state.side_to_move !== this.humanColor ||
      !this.pieceAt(square) ||
      !this.isHumanPiece(this.pieceAt(square))
    ) {
      event.preventDefault();
      return;
    }

    this.selected = square;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", square);
    this.render();
  }

  onDragOver(event, square) {
    if (!this.selected || !this.isLegalTarget(square)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }

  onDrop(event, square) {
    event.preventDefault();
    const source = event.dataTransfer.getData("text/plain") || this.selected;
    if (source) this.tryMove(source, square);
  }

  onDragEnd() {
    if (!this.locked) {
      this.selected = null;
      this.render();
    }
  }

  isLegalTarget(square) {
    return Boolean(
      this.selected &&
      this.state &&
      this.state.legal_moves.some(
        (move) => move.startsWith(this.selected) && move.slice(2, 4) === square
      )
    );
  }

  async tryMove(source, square) {
    if (this.locked || !this.state || this.state.game_over) return;
    if (this.state.side_to_move !== this.humanColor) return;

    const sourcePiece = this.pieceAt(source);
    const targetPiece = this.pieceAt(square);
    const isOwnTarget = targetPiece && this.isHumanPiece(targetPiece);
    const candidates = this.state.legal_moves.filter(
      (m) => m.startsWith(source) && m.slice(2, 4) === square
    );

    if (candidates.length === 0) {
      this.selected = isOwnTarget ? square : null;
      this.render();
      return;
    }

    let uci = candidates[0];
    if (candidates.length > 1) {
      // Multiple candidates only happens for promotion choices.
      uci = await this.choosePromotion(candidates);
      if (!uci) {
        this.selected = null;
        this.render();
        return;
      }
    }

    this.selected = null;
    this.locked = true;
    const { ok, state } = await this.engine.pushMove(uci);
    if (ok) {
      this.state = state;
      this.appendHistory(uci);
    }
    this.locked = false;
    this.render();
    this.maybeLetEngineMove();
  }

  choosePromotion(candidates) {
    return new Promise((resolve) => {
      const labels = { q: "Queen", r: "Rook", b: "Bishop", n: "Knight" };
      const choice = window.prompt(
        "Promote to: " +
          candidates.map((c) => labels[c[4]] || c[4]).join(", ") +
          "\nType one of: q, r, b, n"
      );
      const match = candidates.find((c) => c.endsWith((choice || "").trim().toLowerCase()));
      resolve(match || null);
    });
  }

  pieceAt(square) {
    const placement = this.state.fen.split(" ")[0];
    const rows = placement.split("/"); // rows[0] = rank 8 ... rows[7] = rank 1
    const file = FILES.indexOf(square[0]);
    const rank = parseInt(square[1], 10) - 1;
    const row = rows[7 - rank];
    let col = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) {
        col += parseInt(ch, 10);
      } else {
        if (col === file) return ch;
        col += 1;
      }
    }
    return null;
  }

  isHumanPiece(fenChar) {
    if (!fenChar) return false;
    const isWhite = fenChar === fenChar.toUpperCase();
    return (isWhite && this.humanColor === "white") || (!isWhite && this.humanColor === "black");
  }

  render() {
    if (!this.state) return;
    const legalTargets = this.selected
      ? new Set(
          this.state.legal_moves
            .filter((m) => m.startsWith(this.selected))
            .map((m) => m.slice(2, 4))
        )
      : new Set();

    for (const [name, el] of Object.entries(this.squareEls)) {
      const piece = this.pieceAt(name);
      el.replaceChildren();
      if (piece) {
        const glyph = document.createElement("span");
        glyph.className = "piece-glyph";
        glyph.textContent = PIECE_GLYPH[piece];
        el.appendChild(glyph);
      }
      el.draggable = Boolean(
        piece &&
        this.isHumanPiece(piece) &&
        !this.locked &&
        this.state.side_to_move === this.humanColor
      );
      el.classList.toggle("selected", name === this.selected);
      el.classList.toggle("legal-target", legalTargets.has(name));
      el.classList.toggle("white-piece", !!piece && piece === piece.toUpperCase());
      el.classList.toggle("black-piece", !!piece && piece === piece.toLowerCase());
    }

    this.boardEl.classList.toggle("flipped", this.flipped);
    this.boardShell.classList.toggle("flipped", this.flipped);
  }

  appendHistory(uci) {
    const li = document.createElement("li");
    li.textContent = uci;
    this.historyEl.appendChild(li);
  }

  setStatus(text) {
    this.statusEl.textContent = text;
  }

  showResult() {
    const result = this.state.result;
    if (!result) {
      this.setStatus("Game over.");
      return;
    }
    if (result === "1/2-1/2") {
      this.setStatus("Draw.");
    } else if ((result === "1-0" && this.humanColor === "white") ||
               (result === "0-1" && this.humanColor === "black")) {
      this.setStatus("You win!");
    } else {
      this.setStatus("Engine wins.");
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const engine = new EngineClient("js/chess-worker.js");
  const ui = new ChessUI(document, engine);
  ui.start();
});