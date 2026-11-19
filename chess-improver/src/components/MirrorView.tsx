import React, { useEffect, useMemo, useState } from 'react';
import { Chess } from 'chess.js';
import type { PlayerColor } from '../../shared/types';
import { api, ApiError } from '../lib/api';
import { ChessBoard } from './ChessBoard';

export function MirrorView() {
  const [side, setSide] = useState<PlayerColor>('w');
  const [moves, setMoves] = useState<string[]>([]);
  const [profile, setProfile] = useState<{ indexed: number; games: number; skipped: number } | null>(null);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [profileError, setProfileError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [lastReply, setLastReply] = useState<{ source: 'archive' | 'stockfish'; occurrences: number; samples: number } | null>(null);
  const game = useMemo(() => {
    const chess = new Chess();
    for (const uci of moves) chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
    return chess;
  }, [moves]);

  useEffect(() => {
    let active = true;
    api.mirrorProfile().then(p => { if (active) setProfile(p); }).catch(() => { if (active) setProfileError(true); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (game.isGameOver() || game.turn() === side) return;
    let active = true;
    setThinking(true);
    setError(null);
    api.mirrorMove(moves).then(reply => {
      if (!active) return;
      setLastReply(reply);
      setThinking(false);
      setMoves(previous => [...previous, reply.move]);
    }).catch(err => { if (active) { setBlocked(err instanceof ApiError && err.status === 409); setError(err instanceof Error ? err.message : 'Could not get a reply.'); } })
      .finally(() => { if (active) setThinking(false); });
    return () => { active = false; };
  }, [moves, side, game, retry]);

  function restart(color = side) {
    setSide(color);
    setMoves([]);
    setError(null);
    setBlocked(false);
    setThinking(false);
    setLastReply(null);
    setRetry(n => n + 1);
  }

  const over = game.isGameOver();
  const status = game.isCheckmate() ? `Checkmate — ${game.turn() === side ? 'the mirror wins' : 'you win'}.`
    : game.isDraw() ? 'Game drawn.' : game.isGameOver() ? 'Game over.'
    : thinking ? 'Choosing a reply…' : game.turn() === side ? 'Your move' : 'Waiting for a reply';
  const history = game.history();
  const last = moves.at(-1);
  return (
    <div className="mirror-layout view-shell">
      <header className="mirror-heading">
        <span className="eyebrow">Play your patterns</span>
        <h1>Meet your <em>mirror.</em></h1>
        <p>Play against an opponent built from your own recorded moves. It picks your most frequent move in a matching position; when there is no match, local Stockfish plays instead. This is an approximation, not a prediction of what you would always play. To protect blind drills, a game pauses if it reaches a known drill position.</p>
      </header>
      <div className="mirror-grid">
        <section className="mirror-board" aria-label="Play against your mirror">
          <div className="mirror-status" role="status"><span className="dot" /> {status}</div>
          <ChessBoard fen={game.fen()} orientation={side} interactive={!thinking && !error && !over && game.turn() === side} allowedTurnColor={side}
            lastMove={last ? { from: last.slice(0, 2), to: last.slice(2, 4) } : null}
            onMoveAttempt={uci => { if (!thinking && !over && game.turn() === side) setMoves(prev => [...prev, uci]); }} />
          {error && <div className="mirror-error" role="alert">{error} {!blocked && game.turn() !== side && <button type="button" onClick={() => setRetry(n => n + 1)}>Retry reply</button>}</div>}
        </section>
        <aside className="mirror-panel">
          <h2>New game</h2>
          <p>Choose your side. Changing sides starts a new game.</p>
          <div className="mirror-controls" aria-label="Choose your side">
            <button type="button" className={side === 'w' ? 'selected' : ''} aria-pressed={side === 'w'} onClick={() => restart('w')}>Play White</button>
            <button type="button" className={side === 'b' ? 'selected' : ''} aria-pressed={side === 'b'} onClick={() => restart('b')}>Play Black</button>
          </div>
          <button type="button" className="mirror-reset" onClick={() => restart()}>Start over</button>
          <div className="mirror-divider" />
          <h2>Your playing profile</h2>
          <p>{profile ? `${profile.games.toLocaleString()} games used from ${profile.indexed.toLocaleString()} indexed games. ${profile.skipped} unsupported or unreadable games excluded.` : profileError ? 'Profile unavailable. Try reopening this page.' : 'Preparing your local game history…'}</p>
          {lastReply && <p className="mirror-source">{lastReply.source === 'archive' ? `Last reply: played ${lastReply.occurrences} of ${lastReply.samples} times in this exact position.` : 'Last reply: Stockfish (no recorded match for this position).'}</p>}
          <div className="mirror-divider" />
          <h2>Moves</h2>
          <div className="mirror-moves" aria-label="Game moves">{history.length ? history.map((san, i) => <span key={i}>{i % 2 === 0 && <b>{Math.floor(i / 2) + 1}. </b>}{san}</span>) : <span>Your game will appear here.</span>}</div>
        </aside>
      </div>
    </div>
  );
}
