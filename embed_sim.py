"""
embed_sim.py — Inject sim_trajectories.json + Live Sim tab into dashboard.html

Adds:
  1. "Live Sim" nav tab
  2. #page-live-sim div with dark-theme animated panels
  3. SIM_DATA const and liveSim JS in the script block
  4. showPage() extended to handle 'live-sim'
"""

import json, re, os

# ── Load trajectory data ──────────────────────────────────────────────────────
with open('gen_imgs/sim_trajectories.json', encoding='utf-8') as f:
    sim_data = json.load(f)

sim_data_js = 'const SIM_DATA = ' + json.dumps(sim_data, separators=(',', ':')) + ';'

# ── Read dashboard ────────────────────────────────────────────────────────────
with open('dashboard.html', encoding='utf-8') as f:
    html = f.read()

# ── 1. Nav tab ────────────────────────────────────────────────────────────────
NAV_OLD = "  <a href=\"#\" onclick=\"showPage('fleet'); return false;\">Fleet Overview</a>"
NAV_NEW = (NAV_OLD + "\n"
           "  <a href=\"#\" onclick=\"showPage('live-sim'); return false;\">&#9889; Live Sim</a>")
assert NAV_OLD in html, 'NAV anchor not found'
html = html.replace(NAV_OLD, NAV_NEW, 1)

# ── 2. Live Sim page div (insert after </div> that closes page-fleet) ─────────
FLEET_END = '</div>\n\n<script>'
assert FLEET_END in html, 'Fleet closing marker not found'

LIVE_SIM_PAGE = """
<!-- ══════════════════════════ LIVE SIM PAGE ══════════════════════════════ -->
<div id="page-live-sim" style="display:none; background:#0d1117; min-height:100vh; padding:20px 24px; box-sizing:border-box;">

  <!-- Header -->
  <div style="margin-bottom:18px;">
    <h2 style="margin:0 0 4px; color:#c9d1d9; font-size:20px;">&#9889; Live Simulation &mdash; Synthetic Engine</h2>
    <p style="margin:0; color:#8b949e; font-size:13px;">Synthetic engines generated from C-MAPSS training statistics &mdash; same model, new random degradation trajectories</p>
  </div>

  <!-- Controls -->
  <div style="display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; margin-bottom:16px; background:#161b22; border:1px solid #30363d; border-radius:8px; padding:12px 16px;">
    <div>
      <label style="display:block; font-size:11px; color:#8b949e; margin-bottom:4px;">DATASET</label>
      <select id="ls-ds-sel" onchange="lsDsChange()" style="background:#0d1117; color:#c9d1d9; border:1px solid #30363d; border-radius:6px; padding:6px 10px; font-size:13px;">
        <option value="FD001">FD001 (MLP)</option>
        <option value="FD002">FD002 (RF)</option>
        <option value="FD003">FD003 (RF)</option>
        <option value="FD004">FD004 (RF)</option>
      </select>
    </div>
    <div>
      <label style="display:block; font-size:11px; color:#8b949e; margin-bottom:4px;">ENGINE SEED</label>
      <select id="ls-eng-sel" onchange="lsEngChange()" style="background:#0d1117; color:#c9d1d9; border:1px solid #30363d; border-radius:6px; padding:6px 10px; font-size:13px;"></select>
    </div>
    <div>
      <label style="display:block; font-size:11px; color:#8b949e; margin-bottom:4px;">SPEED</label>
      <div style="display:flex; gap:4px;">
        <button onclick="lsSetSpeed(80,this)"  class="ls-spd active" id="ls-spd-1">1&times;</button>
        <button onclick="lsSetSpeed(30,this)"  class="ls-spd" id="ls-spd-2">3&times;</button>
        <button onclick="lsSetSpeed(10,this)"  class="ls-spd" id="ls-spd-3">10&times;</button>
      </div>
    </div>
    <div style="display:flex; gap:8px; margin-top:4px;">
      <button id="ls-play-btn" onclick="lsTogglePlay()" style="background:#238636; color:#fff; border:none; border-radius:6px; padding:8px 18px; font-size:13px; font-weight:600; cursor:pointer;">&#9654; Play</button>
      <button onclick="lsReset()" style="background:#21262d; color:#c9d1d9; border:1px solid #30363d; border-radius:6px; padding:8px 14px; font-size:13px; cursor:pointer;">&#9632; Reset</button>
      <button onclick="lsRandom()" style="background:#1f6feb; color:#fff; border:none; border-radius:6px; padding:8px 14px; font-size:13px; cursor:pointer;">&#8635; Random</button>
    </div>
    <div id="ls-meta" style="font-size:12px; color:#8b949e; align-self:center; margin-left:auto;"></div>
  </div>

  <!-- Alert banner (hidden until alert fires) -->
  <div id="ls-alert-banner" style="display:none; background:#3d1f1f; border:1px solid #f85149; border-radius:6px; padding:10px 16px; margin-bottom:14px; color:#f85149; font-size:13px; font-weight:600;"></div>

  <!-- Charts row -->
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:14px;">
    <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:12px;">
      <div style="font-size:12px; color:#8b949e; margin-bottom:6px;">KEY SENSOR READINGS &nbsp;<span style="font-size:11px;">(normalized &bull; &#8593; = more degraded)</span></div>
      <div id="ls-sensor-chart" style="width:100%; height:280px;"></div>
    </div>
    <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:12px;">
      <div style="font-size:12px; color:#8b949e; margin-bottom:6px;">ALERT PROBABILITY</div>
      <div id="ls-prob-chart" style="width:100%; height:280px;"></div>
    </div>
  </div>

  <!-- Health bar -->
  <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:14px 16px;">
    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
      <span id="ls-status" style="font-size:14px; font-weight:700; color:#3fb950;">HEALTHY</span>
      <div style="font-size:12px; color:#8b949e; display:flex; gap:20px;">
        <span id="ls-cycle">Cycle: 0</span>
        <span id="ls-rul">True RUL: —</span>
      </div>
    </div>
    <div style="background:#0d1117; border-radius:6px; height:22px; overflow:hidden; border:1px solid #30363d;">
      <div id="ls-health-fill" style="height:100%; width:100%; background:#3fb950; border-radius:6px; transition:width 0.1s, background 0.3s;"></div>
    </div>
  </div>

  <a href="#" onclick="showPage('dashboard'); return false;"
     style="display:block; text-align:center; color:#58a6ff; text-decoration:none; font-size:13px; padding:14px 8px 4px;">
    &larr; Back to Dashboard
  </a>
</div>

<style>
.ls-spd {
  background:#21262d; color:#8b949e; border:1px solid #30363d;
  border-radius:5px; padding:5px 11px; font-size:12px; cursor:pointer;
}
.ls-spd.active { background:#1f6feb; color:#fff; border-color:#1f6feb; }
</style>

"""

html = html.replace(FLEET_END, LIVE_SIM_PAGE + '\n\n<script>', 1)

# ── 3. showPage() — add 'live-sim' ───────────────────────────────────────────
OLD_SHOW = (
    "    document.getElementById('page-fleet').style.display = page === 'fleet' ? 'block' : 'none';\n"
    "    if (page === 'fleet') renderFleet();"
)
NEW_SHOW = (
    "    document.getElementById('page-fleet').style.display = page === 'fleet' ? 'block' : 'none';\n"
    "    document.getElementById('page-live-sim').style.display = page === 'live-sim' ? 'block' : 'none';\n"
    "    if (page === 'fleet') renderFleet();\n"
    "    if (page === 'live-sim' && !lsInited) { lsInited = true; lsInit(); }"
)
assert OLD_SHOW in html, 'showPage fleet block not found'
html = html.replace(OLD_SHOW, NEW_SHOW, 1)

OLD_SIM_PAUSE = "    if (page !== 'simulation') simPause();"
NEW_SIM_PAUSE = (
    "    if (page !== 'simulation') simPause();\n"
    "    if (page !== 'live-sim') lsPause();"
)
assert OLD_SIM_PAUSE in html, 'simPause line not found'
html = html.replace(OLD_SIM_PAUSE, NEW_SIM_PAUSE, 1)

# ── 4. Inject SIM_DATA + liveSim JS before closing </script> ─────────────────
LS_JS = r"""

// ═══════════════════════ LIVE SIM ═══════════════════════════════════════════

""" + sim_data_js + r"""

const LS_SENSOR_COLORS = ['#58a6ff','#ff7b72','#3fb950','#d2a8ff'];
let lsInited = false;
let ls = {
    ds: 'FD001', idx: 0, frame: 0,
    playing: false, timer: null, speed: 80,
    chartsReady: false
};

function lsInit() {
    _lsBuildEngSel();
    _lsInitCharts();
    lsLoadEngine();
}

function _lsBuildEngSel() {
    const sel = document.getElementById('ls-eng-sel');
    sel.innerHTML = '';
    const engs = SIM_DATA[ls.ds].engines;
    engs.forEach(function(e, i) {
        const opt = document.createElement('option');
        opt.value = i;
        opt.textContent = 'Seed ' + e.seed + '  (' + e.total + ' cycles)';
        sel.appendChild(opt);
    });
}

function _lsInitCharts() {
    const darkLayout = {
        paper_bgcolor:'#161b22', plot_bgcolor:'#0d1117',
        font:{color:'#c9d1d9', size:11},
        margin:{l:48,r:16,t:10,b:36},
        xaxis:{color:'#8b949e', gridcolor:'#21262d', zerolinecolor:'#30363d', title:{text:'Cycle',font:{size:11}}},
        yaxis:{color:'#8b949e', gridcolor:'#21262d', zerolinecolor:'#30363d'},
        legend:{bgcolor:'#161b22', bordercolor:'#30363d', font:{color:'#c9d1d9',size:10}},
        showlegend:true
    };

    // Sensor chart — 4 empty traces
    var sTraces = LS_SENSOR_COLORS.map(function(c,i) {
        return {x:[], y:[], mode:'lines', name:'s?',
                line:{color:c, width:1.6}, type:'scatter'};
    });
    Plotly.newPlot('ls-sensor-chart', sTraces,
        Object.assign({}, darkLayout, {
            yaxis: Object.assign({}, darkLayout.yaxis, {title:{text:'Norm.',font:{size:10}}, range:[-0.08,1.15]})
        }),
        {responsive:true, displayModeBar:false});

    // Prob chart — raw + smoothed
    var pTraces = [
        {x:[], y:[], mode:'lines', name:'Raw P',
         line:{color:'#58a6ff', width:1}, opacity:0.45, type:'scatter'},
        {x:[], y:[], mode:'lines', name:'Smoothed',
         line:{color:'#ffa657', width:2.2}, type:'scatter'},
    ];
    Plotly.newPlot('ls-prob-chart', pTraces,
        Object.assign({}, darkLayout, {
            yaxis: Object.assign({}, darkLayout.yaxis, {range:[-0.05,1.15]})
        }),
        {responsive:true, displayModeBar:false});

    ls.chartsReady = true;
}

function lsLoadEngine() {
    lsPause();
    ls.frame = 0;
    var eng = SIM_DATA[ls.ds].engines[ls.idx];
    var cfg = SIM_DATA[ls.ds].cfg;

    // Update sensor legend names
    Plotly.restyle('ls-sensor-chart', {name: eng.sensors});

    // Meta info
    document.getElementById('ls-meta').textContent =
        'Life: ' + eng.total + ' cycles  ·  Onset: ~' + eng.onset +
        '  ·  True alert: cycle ' + eng.true_alert +
        '  ·  T=' + cfg.T + '  K=' + cfg.K;

    // Static shapes: threshold + danger zone
    var shapes = [
        {type:'line', x0:0, x1:eng.total, y0:cfg.T, y1:cfg.T,
         line:{color:'#f85149', width:1.5, dash:'dash'}},
        {type:'rect', x0:eng.true_alert, x1:eng.total, y0:0, y1:1.1,
         fillcolor:'rgba(248,81,73,0.08)', line:{width:0}},
    ];
    Plotly.relayout('ls-prob-chart', {
        shapes: shapes,
        'xaxis.range': [0, eng.total],
        'yaxis.range': [-0.05, 1.15]
    });
    Plotly.relayout('ls-sensor-chart', {'xaxis.range':[0, eng.total]});

    // Clear alert banner
    document.getElementById('ls-alert-banner').style.display = 'none';

    // Reset health bar
    _lsDrawFrame(0);
    document.getElementById('ls-play-btn').textContent = '▶ Play';
}

function _lsDrawFrame(n) {
    var eng = SIM_DATA[ls.ds].engines[ls.idx];
    var cfg = SIM_DATA[ls.ds].cfg;
    var cs  = [];
    for (var i = 0; i < n; i++) cs.push(i + 1);

    // Sensor traces
    var sx = [cs, cs, cs, cs];
    var sy = [
        eng.sensor_hist[0].slice(0, n),
        eng.sensor_hist[1].slice(0, n),
        eng.sensor_hist[2].slice(0, n),
        eng.sensor_hist[3].slice(0, n)
    ];
    Plotly.restyle('ls-sensor-chart', {x: sx, y: sy});

    // Prob traces
    Plotly.restyle('ls-prob-chart', {
        x: [cs, cs],
        y: [eng.raw_p.slice(0, n), eng.sm_p.slice(0, n)]
    });

    // Alert line
    var alertFired = eng.alert_at && n >= eng.alert_at;
    if (alertFired) {
        var shapes = [
            {type:'line', x0:0, x1:eng.total, y0:cfg.T, y1:cfg.T,
             line:{color:'#f85149', width:1.5, dash:'dash'}},
            {type:'rect', x0:eng.true_alert, x1:eng.total, y0:0, y1:1.1,
             fillcolor:'rgba(248,81,73,0.08)', line:{width:0}},
            {type:'line', x0:eng.alert_at, x1:eng.alert_at, y0:0, y1:1.1,
             line:{color:'#f85149', width:2}}
        ];
        Plotly.relayout('ls-prob-chart', {shapes: shapes});

        var banner = document.getElementById('ls-alert-banner');
        if (banner.style.display === 'none') {
            var delta = eng.alert_at - eng.true_alert;
            var sign  = delta >= 0 ? '+' : '';
            banner.textContent = '⚡ ALERT FIRED @ cycle ' + eng.alert_at +
                '   |   True RUL at alert: ' + (eng.total - eng.alert_at) +
                '   |   Δ: ' + sign + delta + ' cycles vs true threshold';
            banner.style.display = 'block';
        }
    }

    // Health bar
    var cycle = n;
    var deg   = (cycle > eng.onset) ? (cycle - eng.onset) / Math.max(1, eng.total - eng.onset) : 0;
    var health = Math.max(0, 1 - deg);
    var pct   = Math.round(health * 100);
    var bar   = document.getElementById('ls-health-fill');
    var st    = document.getElementById('ls-status');

    var color, label;
    if (alertFired)      { color = '#f85149'; label = '⚡ ALERT FIRED'; }
    else if (health > 0.6){ color = '#3fb950'; label = 'HEALTHY'; }
    else if (health > 0.3){ color = '#d29922'; label = 'DEGRADING'; }
    else                  { color = '#f85149'; label = 'CRITICAL'; }

    bar.style.width = pct + '%';
    bar.style.background = color;
    st.textContent = label;
    st.style.color = color;

    document.getElementById('ls-cycle').textContent = 'Cycle: ' + cycle + ' / ' + eng.total;
    document.getElementById('ls-rul').textContent   = 'True RUL: ' + Math.max(0, eng.total - cycle);
}

function lsTogglePlay() {
    if (ls.playing) { lsPause(); }
    else            { lsPlay();  }
}

function lsPlay() {
    if (ls.playing) return;
    var eng = SIM_DATA[ls.ds].engines[ls.idx];
    if (ls.frame >= eng.total) ls.frame = 0;
    ls.playing = true;
    document.getElementById('ls-play-btn').textContent = '⏸ Pause';
    ls.timer = setInterval(function() {
        if (ls.frame >= eng.total) {
            lsPause();
            document.getElementById('ls-play-btn').textContent = '▶ Play';
            return;
        }
        _lsDrawFrame(ls.frame);
        ls.frame++;
    }, ls.speed);
}

function lsPause() {
    ls.playing = false;
    clearInterval(ls.timer);
    ls.timer = null;
    var btn = document.getElementById('ls-play-btn');
    if (btn) btn.textContent = '▶ Play';
}

function lsReset() {
    lsPause();
    ls.frame = 0;
    lsLoadEngine();
}

function lsRandom() {
    lsPause();
    var engs = SIM_DATA[ls.ds].engines;
    ls.idx = Math.floor(Math.random() * engs.length);
    document.getElementById('ls-eng-sel').value = ls.idx;
    lsLoadEngine();
    lsPlay();
}

function lsSetSpeed(ms, btn) {
    ls.speed = ms;
    document.querySelectorAll('.ls-spd').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    if (ls.playing) { lsPause(); lsPlay(); }
}

function lsDsChange() {
    lsPause();
    ls.ds = document.getElementById('ls-ds-sel').value;
    ls.idx = 0;
    _lsBuildEngSel();
    lsLoadEngine();
}

function lsEngChange() {
    lsPause();
    ls.idx = parseInt(document.getElementById('ls-eng-sel').value);
    lsLoadEngine();
}

// ════════════════════════════════════════════════════════════════════════════
"""

# Find closing </script> tag (last one)
close_script = html.rfind('</script>')
assert close_script != -1, 'Closing </script> not found'
html = html[:close_script] + LS_JS + '\n</script>' + html[close_script + len('</script>'):]

# ── Write output ──────────────────────────────────────────────────────────────
with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

size_mb = os.path.getsize('dashboard.html') / 1024 / 1024
print(f'[OK] dashboard.html updated  ({size_mb:.1f} MB)')
print('     - Added "Live Sim" nav tab')
print('     - Added #page-live-sim with dark-theme panels')
print('     - Injected SIM_DATA + liveSim JS')
print(f'     - SIM_DATA: {sum(len(v["engines"]) for v in sim_data.values())} engines across {len(sim_data)} datasets')
