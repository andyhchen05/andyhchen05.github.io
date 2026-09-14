// chess-worker.js
//
// Runs the Python chess engine (board.py / movegen.py / evaluate.py /
// search.py / game.py -- unmodified, same files from the CLI version) in a
// Web Worker via Pyodide, so the UI thread never freezes while the engine
// is thinking. Talks to chess.js on the main thread via postMessage.

importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

const ENGINE_FILES = ["board.py", "movegen.py", "evaluate.py", "search.py", "game.py"];

let pyodideReadyPromise = init();

async function init() {
  const pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/",
  });

  // Fetch each engine source file (same folder as this worker script) and
  // write it into Pyodide's virtual filesystem so `import game` works
  // exactly like it does on the command line -- no code changes needed.
  for (const filename of ENGINE_FILES) {
    const response = await fetch(new URL(`../python/${filename}`, self.location));
    if (!response.ok) {
      throw new Error(`Failed to fetch ${filename}: ${response.status}`);
    }
    const source = await response.text();
    pyodide.FS.writeFile(`/${filename}`, source);
  }

  pyodide.runPython(`
import sys
if "/" not in sys.path:
    sys.path.insert(0, "/")
from game import Game
g = Game()
`);

  return pyodide;
}

function currentState(pyodide) {
  const dictProxy = pyodide.runPython("g.to_dict()");
  const state = dictProxy.toJs({ dict_converter: Object.fromEntries });
  dictProxy.destroy();
  return state;
}

self.onmessage = async (event) => {
  const { id, type, payload } = event.data;
  const pyodide = await pyodideReadyPromise;

  try {
    let result = {};

    switch (type) {
      case "init": {
        result = { state: currentState(pyodide) };
        break;
      }

      case "reset": {
        pyodide.runPython("g.reset()");
        result = { state: currentState(pyodide) };
        break;
      }

      case "push_move": {
        const uci = payload.uci;
        pyodide.globals.set("_uci", uci);
        const ok = pyodide.runPython("g.push_uci(_uci)");
        result = { ok, state: currentState(pyodide) };
        break;
      }

      case "engine_move": {
        const timeLimit = payload.timeLimit ?? 1.5;
        const maxDepth = payload.maxDepth ?? 5;
        pyodide.globals.set("_time_limit", timeLimit);
        pyodide.globals.set("_max_depth", maxDepth);
        const played = pyodide.runPython(
          "g.play_engine_move(max_depth=_max_depth, time_limit=_time_limit)"
        );
        result = { played, state: currentState(pyodide) };
        break;
      }

      default:
        throw new Error(`Unknown message type: ${type}`);
    }

    self.postMessage({ id, ok: true, result });
  } catch (err) {
    self.postMessage({ id, ok: false, error: String(err) });
  }
};