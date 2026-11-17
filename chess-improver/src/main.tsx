import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root container #root was not found in index.html');
}

// StrictMode is intentionally omitted: the initial Stockfish SSE analysis stream
// is a side effect that should be opened exactly once per page load.
createRoot(container).render(<App />);
