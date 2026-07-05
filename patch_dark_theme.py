# -*- coding: utf-8 -*-
"""
patch_dark_theme.py — Convert light-themed pages (Dashboard, Engine Analysis,
System Test, Fleet Overview) to Live Sim's GitHub-dark palette.
  bg #0d1117 · cards #161b22 · raised #21262d · borders #30363d
  text #c9d1d9 · muted #8b949e
Live Sim page already uses these values and is untouched.
"""
import io

PATH = 'dashboard.html'
with io.open(PATH, encoding='utf-8') as f:
    html = f.read()

orig_len = len(html)

# Ordered (old, new, min_expected) replacements.
REPLACEMENTS = [
    # ── Page + card surfaces ──────────────────────────────────────────────
    ('background: #f0f2f5', 'background: #0d1117', 1),      # body
    ('background:white',    'background:#161b22', 10),      # JS-built cards
    ('background: white',   'background: #161b22', 5),      # CSS cards
    ('background: #fafafa', 'background: #21262d', 1),
    ('background:#f8f9fa',  'background:#1c2128', 0),
    ('background: #f8f9fa', 'background: #1c2128', 1),      # table stripes
    ('background:#f5f5f5',  'background:#21262d', 1),
    ('background: #eaf0fb', 'background: #1f2a3a', 1),      # tr:hover
    ('background:#eaf4fb',  'background:#1c2733', 1),       # fleet legend bar
    ('#e8f5e9', '#16281c', 2),                              # green tint (bar, tr, ea-card)
    ('#fdf2f2', '#2d1a1c', 1),                              # sim alert tint
    ('#fef9ec', '#2b2415', 1),                              # sim warn tint

    # ── Text ──────────────────────────────────────────────────────────────
    ('color:#2c3e50',  'color:#c9d1d9', 5),
    ('color: #2c3e50', 'color: #c9d1d9', 5),
    ("color: '#2c3e50'", "color: '#c9d1d9'", 1),            # Plotly textfont
    ('color:#7f8c8d',  'color:#8b949e', 3),
    ('color: #7f8c8d', 'color: #8b949e', 1),
    ('color: #555',    'color: #8b949e', 1),
    ('color:#555',     'color:#8b949e', 0),
    ('color: #888',    'color: #8b949e', 1),
    ('color:#333',     'color:#c9d1d9', 0),
    ('color: #333',    'color: #c9d1d9', 0),

    # ── Borders ───────────────────────────────────────────────────────────
    ('1px solid #ddd',    '1px solid #30363d', 5),
    ('1px solid #f0f0f0', '1px solid #30363d', 3),
    ('1px solid #e9ecef', '1px solid #30363d', 1),
    ('1px solid #c8e6c9', '1px solid #238636', 1),
    ('1.5px solid #bdc3c7', '1.5px solid #30363d', 1),
    ('2px solid #2c3e50', '2px solid #30363d', 1),          # h2 underline

    # ── Shadows → hairline outlines (shadows invisible on dark) ──────────
    ('box-shadow: 0 2px 8px rgba(0,0,0,.07)', 'box-shadow: 0 0 0 1px #30363d', 3),
    ('box-shadow:0 2px 8px rgba(0,0,0,.07)',  'box-shadow:0 0 0 1px #30363d', 3),

    # ── Plotly layouts ────────────────────────────────────────────────────
    # Engine Analysis sharedLayout
    ("paper_bgcolor:'white', plot_bgcolor:'#fafafa',",
     "paper_bgcolor:'#161b22', plot_bgcolor:'#0d1117', font:{color:'#c9d1d9'},", 1),
    # SHAP chart
    ("plot_bgcolor: 'white',",  "plot_bgcolor: '#161b22',", 1),
    ("paper_bgcolor: 'white'",  "paper_bgcolor: '#161b22'", 1),
    ("gridcolor: '#f0f0f0'",    "gridcolor: '#21262d'", 1),
    ("margin: { l: 100, r: 80, t: 16, b: 44 },",
     "margin: { l: 100, r: 80, t: 16, b: 44 }, font: { color: '#c9d1d9' },", 1),
    # Sim page charts (transparent bg — just grids + font)
    ("gridcolor:'#eee'", "gridcolor:'#21262d'", 4),
    ("font:{family:'Segoe UI,sans-serif', size:11},",
     "font:{family:'Segoe UI,sans-serif', size:11, color:'#c9d1d9'},", 1),
]

problems = []
for old, new, min_n in REPLACEMENTS:
    n = html.count(old)
    if n < min_n:
        problems.append(f'  !! "{old}" found {n}x (expected >= {min_n})')
    html = html.replace(old, new)
    print(f'  [{n:2d}x] {old[:58]}')

# ── CSS extras appended before the responsive block ──────────────────────────
CSS_ANCHOR = '/* ── Responsive / Mobile ─'
assert CSS_ANCHOR in html, 'responsive CSS anchor not found'
DARK_EXTRAS = '''/* ── Dark theme extras ───────────────────────────────────────────────────── */
body { color: #c9d1d9; }
select, input[type="text"], input[type="number"] {
  background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
}
::placeholder { color: #6e7681; }
.section img { background: #fff; border-radius: 8px; }
tr:nth-child(even) td { color: #c9d1d9; }
td { color: #c9d1d9; }

'''
html = html.replace(CSS_ANCHOR, DARK_EXTRAS + CSS_ANCHOR, 1)
print('  [OK] dark CSS extras appended')

with io.open(PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'\n[OK] dashboard.html patched ({orig_len} -> {len(html)} chars)')
if problems:
    print('WARNINGS:')
    print('\n'.join(problems))
