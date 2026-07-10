<svg viewBox="0 0 1200 260" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="nodeGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1f2937"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L6,3 L0,6 Z" fill="#2dd4bf"/>
    </marker>
  </defs>

  <rect width="1200" height="260" fill="url(#bg)"/>

  <!-- subtle hex accents -->
  <polygon points="60,20 80,32 80,56 60,68 40,56 40,32" fill="none" stroke="#2dd4bf" stroke-opacity="0.25" stroke-width="2"/>
  <polygon points="1140,190 1160,202 1160,226 1140,238 1120,226 1120,202" fill="none" stroke="#a78bfa" stroke-opacity="0.25" stroke-width="2"/>

  <!-- Title -->
  <text x="600" y="45" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="30" font-weight="700" fill="#f0f6fc" text-anchor="middle">⬡ RepoGraph</text>
  <text x="600" y="70" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="14" fill="#8b949e" text-anchor="middle">Dependency-aware context selection for LLMs</text>

  <!-- Pipeline -->
  <g font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="15" font-weight="600">

    <!-- Repository -->
    <rect x="30" y="140" width="180" height="60" rx="10" fill="url(#nodeGrad)" stroke="#30363d" stroke-width="1.5"/>
    <text x="120" y="165" fill="#58a6ff" text-anchor="middle" font-size="20">📦</text>
    <text x="120" y="188" fill="#e6edf3" text-anchor="middle">Repository</text>

    <line x1="210" y1="170" x2="248" y2="170" stroke="#2dd4bf" stroke-width="2.5" marker-end="url(#arrow)"/>

    <!-- AST Parser -->
    <rect x="250" y="140" width="180" height="60" rx="10" fill="url(#nodeGrad)" stroke="#30363d" stroke-width="1.5"/>
    <text x="340" y="165" fill="#2dd4bf" text-anchor="middle" font-size="20">🌳</text>
    <text x="340" y="188" fill="#e6edf3" text-anchor="middle">AST Parser</text>

    <line x1="430" y1="170" x2="468" y2="170" stroke="#2dd4bf" stroke-width="2.5" marker-end="url(#arrow)"/>

    <!-- Dependency Graph -->
    <rect x="470" y="140" width="200" height="60" rx="10" fill="url(#nodeGrad)" stroke="#30363d" stroke-width="1.5"/>
    <text x="570" y="165" fill="#f2cc60" text-anchor="middle" font-size="20">🕸️</text>
    <text x="570" y="188" fill="#e6edf3" text-anchor="middle">Dependency Graph</text>

    <line x1="670" y1="170" x2="708" y2="170" stroke="#2dd4bf" stroke-width="2.5" marker-end="url(#arrow)"/>

    <!-- Context Selection -->
    <rect x="710" y="140" width="210" height="60" rx="10" fill="url(#nodeGrad)" stroke="#30363d" stroke-width="1.5"/>
    <text x="815" y="165" fill="#a78bfa" text-anchor="middle" font-size="20">🎯</text>
    <text x="815" y="188" fill="#e6edf3" text-anchor="middle">Context Selection</text>

    <line x1="920" y1="170" x2="958" y2="170" stroke="#2dd4bf" stroke-width="2.5" marker-end="url(#arrow)"/>

    <!-- LLM -->
    <rect x="960" y="140" width="180" height="60" rx="10" fill="url(#nodeGrad)" stroke="#30363d" stroke-width="1.5"/>
    <text x="1050" y="165" fill="#f87171" text-anchor="middle" font-size="20">🤖</text>
    <text x="1050" y="188" fill="#e6edf3" text-anchor="middle">LLM</text>
  </g>

  <text x="600" y="235" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="13" fill="#6e7681" text-anchor="middle">~180,000 tokens  →  ~8,000 tokens of precisely relevant context</text>
</svg>
