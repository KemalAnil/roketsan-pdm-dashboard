# -*- coding: utf-8 -*-
"""
patch_sim_charts.py — Dark-theme fixes for System Test prob/RUL charts and
Engine Explorer RUL chart:
  1. Trace colors: navy #2c3e50 (invisible on dark) -> light; dim blues -> #58a6ff
  2. Playback Plotly.react calls get an explicit dark layout (no layout arg
     resets charts to Plotly's default white layout when simulation plays)
"""
import io

PATH = 'dashboard.html'
with io.open(PATH, encoding='utf-8') as f:
    html = f.read()

R = []

def rep(old, new, expect=1):
    global html
    n = html.count(old)
    R.append((n, expect, old[:64]))
    assert n == expect, f'expected {expect}, found {n}: {old[:80]}'
    html = html.replace(old, new)

# ── 1. Init traces (sim page) ─────────────────────────────────────────────────
rep("{x:[], y:[], mode:'lines', name:'Raw prob', line:{color:'#85c1e9', width:1}},",
    "{x:[], y:[], mode:'lines', name:'Raw prob', line:{color:'rgba(133,193,233,0.5)', width:1}},")
rep("{x:[], y:[], mode:'lines', name:'Smoothed prob', line:{color:'#1f77b4', width:2}},",
    "{x:[], y:[], mode:'lines', name:'Smoothed prob', line:{color:'#58a6ff', width:2.2}},")
rep("{x:[], y:[], mode:'lines', name:'True RUL', line:{color:'#2c3e50', width:2.5}},",
    "{x:[], y:[], mode:'lines', name:'True RUL', line:{color:'#e6edf3', width:2.5}},")
rep("{x:[], y:[], mode:'lines', name:'Predicted RUL', line:{color:'#2980b9', width:2, dash:'dash'}},",
    "{x:[], y:[], mode:'lines', name:'Predicted RUL', line:{color:'#58a6ff', width:2, dash:'dash'}},")

# ── 2. Engine Explorer RUL traces ─────────────────────────────────────────────
rep("""                x:e.c, y:e.rul_t, mode:'lines', name:'True RUL',
                line:{color:'#2c3e50', width:2.5}""",
    """                x:e.c, y:e.rul_t, mode:'lines', name:'True RUL',
                line:{color:'#e6edf3', width:2.5}""")
rep("""                x:e.c, y:e.rul_p, mode:'lines', name:'Predicted RUL',
                line:{color:'#2980b9', width:2, dash:'dash'}""",
    """                x:e.c, y:e.rul_p, mode:'lines', name:'Predicted RUL',
                line:{color:'#58a6ff', width:2, dash:'dash'}""")

# ── 3. Playback react calls: colors + explicit dark layout ────────────────────
DARK_BASE = ("{margin:{t:10,r:20,b:40,l:50}, paper_bgcolor:'rgba(0,0,0,0)', "
             "plot_bgcolor:'rgba(0,0,0,0)', "
             "font:{family:'Segoe UI,sans-serif', size:11, color:'#c9d1d9'}, "
             "legend:{orientation:'h', y:-0.22, x:0}, hovermode:'x unified', "
             "xaxis:{title:'Cycle', gridcolor:'#21262d', zeroline:false}, ")

rep("""        Plotly.react('sim-prob-chart', [
            {x:xs, y:simData.r.slice(0,i+1), mode:'lines', name:'Raw prob',
              line:{color:'#85c1e9', width:1}},
            {x:xs, y:simData.s.slice(0,i+1), mode:'lines', name:'Smoothed prob',
              line:{color:'#1f77b4', width:2}},
            {x:[simData.c[0], simData.c[simData.c.length-1]], y:[T,T],
              mode:'lines', name:'Threshold', line:{color:'#e74c3c', width:1.5, dash:'dot'}}
        ]);""",
    """        Plotly.react('sim-prob-chart', [
            {x:xs, y:simData.r.slice(0,i+1), mode:'lines', name:'Raw prob',
              line:{color:'rgba(133,193,233,0.5)', width:1}},
            {x:xs, y:simData.s.slice(0,i+1), mode:'lines', name:'Smoothed prob',
              line:{color:'#58a6ff', width:2.2}},
            {x:[simData.c[0], simData.c[simData.c.length-1]], y:[T,T],
              mode:'lines', name:'Threshold', line:{color:'#e74c3c', width:1.5, dash:'dot'}}
        ], """ + DARK_BASE + """yaxis:{title:'P(fault)', range:[-0.05,1.05], gridcolor:'#21262d'}});""")

rep("""        Plotly.react('sim-rul-chart', [
            {x:xs, y:simData.rul_t.slice(0,i+1), mode:'lines', name:'True RUL',
              line:{color:'#2c3e50', width:2.5}},
            {x:xs, y:simData.rul_p.slice(0,i+1), mode:'lines', name:'Predicted RUL',
              line:{color:'#2980b9', width:2, dash:'dash'}},
            {x:[simData.c[0], simData.c[simData.c.length-1]], y:[30,30],
              mode:'lines', name:'Warning (RUL=30)', line:{color:'#e74c3c', width:1.5, dash:'dot'}}
        ]);""",
    """        Plotly.react('sim-rul-chart', [
            {x:xs, y:simData.rul_t.slice(0,i+1), mode:'lines', name:'True RUL',
              line:{color:'#e6edf3', width:2.5}},
            {x:xs, y:simData.rul_p.slice(0,i+1), mode:'lines', name:'Predicted RUL',
              line:{color:'#58a6ff', width:2, dash:'dash'}},
            {x:[simData.c[0], simData.c[simData.c.length-1]], y:[30,30],
              mode:'lines', name:'Warning (RUL=30)', line:{color:'#e74c3c', width:1.5, dash:'dot'}}
        ], """ + DARK_BASE + """yaxis:{title:'RUL (cycles)', gridcolor:'#21262d', range:[-5, 130]}});""")

with io.open(PATH, 'w', encoding='utf-8') as f:
    f.write(html)

for n, e, s in R:
    print(f'  [{n}/{e}] {s}')
print('[OK] sim + EA charts patched')
