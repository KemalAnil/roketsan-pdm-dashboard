"""
rt_simulator.py — Real-time C-MAPSS synthetic engine degradation simulator

Trains the same classifier used in the PdM dashboard, generates a synthetic
engine degradation trajectory with seeded RNG, then runs model inference
cycle-by-cycle with a live matplotlib animation.

Usage (run from project root):
    python rt_simulator.py
    python rt_simulator.py --dataset FD002 --seed 7
    python rt_simulator.py --dataset FD001 --seed 42 --speed 30 --cycles 250

Arguments:
    --dataset   FD001 | FD002 | FD003 | FD004  (default: FD001)
    --seed      Integer RNG seed (default: random)
    --speed     Milliseconds per cycle in animation (default: 80)
    --cycles    Override total engine life in cycles (default: sampled from training distribution)
"""

import argparse
import sys
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import GroupShuffleSplit

# ── Config — identical to dashboard ───────────────────────────────────────────
RUL_THRESHOLD = 30
WINDOW_BEFORE = 15
WINDOW_AFTER  = 5

DS_CFG = {
    'FD001': {'T': 0.35, 'K': 1,  'smooth_w': 5, 'norm': 'minmax', 'model': 'mlp'},
    'FD002': {'T': 0.10, 'K': 5,  'smooth_w': 5, 'norm': 'zscore', 'model': 'rf'},
    'FD003': {'T': 0.40, 'K': 5,  'smooth_w': 5, 'norm': 'zscore', 'model': 'rf'},
    'FD004': {'T': 0.10, 'K': 5,  'smooth_w': 5, 'norm': 'zscore', 'model': 'rf'},
}

N_DISPLAY = 20      # max sensor traces — effectively "all" (C-MAPSS has ≤15)
EXTRACT_DIR = 'cmapss_extracted'

# ── Shared pipeline helpers ───────────────────────────────────────────────────

def smooth_trailing_ma(x, w):
    x = np.asarray(x, dtype=float)
    if w <= 1:
        return x
    c = np.cumsum(x)
    out = np.empty_like(x)
    for i in range(len(x)):
        j = i - w + 1
        out[i] = c[i] / (i + 1) if j <= 0 else (c[i] - c[j - 1]) / w
    return out


def load_cmapss(ds_name):
    cols = ['engine_id', 'cycle', 'os1', 'os2', 'os3'] + [f's{i}' for i in range(1, 22)]
    train = pd.read_csv(f'{EXTRACT_DIR}/train_{ds_name}.txt', sep=r'\s+', header=None)
    test  = pd.read_csv(f'{EXTRACT_DIR}/test_{ds_name}.txt',  sep=r'\s+', header=None)
    rul   = pd.read_csv(f'{EXTRACT_DIR}/RUL_{ds_name}.txt',   sep=r'\s+', header=None,
                        names=['add_rul'])
    train.columns = cols
    test.columns  = cols

    max_train_id = int(train['engine_id'].max())
    test = test.copy()
    test['engine_id'] = test['engine_id'] + max_train_id

    mc_train = train.groupby('engine_id')['cycle'].max().rename('max_cycle')
    train = train.join(mc_train, on='engine_id')
    train['RUL'] = train['max_cycle'] - train['cycle']

    mc_test  = test.groupby('engine_id')['cycle'].max().rename('max_cycle')
    test     = test.join(mc_test, on='engine_id')
    rul_map  = (test.groupby('engine_id')['cycle'].max()
                .reset_index().rename(columns={'cycle': 'last_cycle'}))
    rul_map['add_rul'] = rul['add_rul'].values
    test = test.merge(rul_map[['engine_id', 'add_rul']], on='engine_id')
    test['RUL'] = test['max_cycle'] - test['cycle'] + test['add_rul']

    df = pd.concat([train.drop(columns=['max_cycle']),
                    test.drop(columns=['max_cycle', 'add_rul'])], ignore_index=True)
    df['warning_flag'] = (df['RUL'] <= RUL_THRESHOLD).astype(int)

    first_warn = (df.groupby('engine_id')
                    .apply(lambda g: g.loc[g['warning_flag'] == 1, 'cycle'].min()
                           if g['warning_flag'].any() else np.nan)
                    .rename('true_alert_cycle'))
    df = df.join(first_warn, on='engine_id')
    df['target_window'] = (
        (df['cycle'] >= df['true_alert_cycle'] - WINDOW_BEFORE) &
        (df['cycle'] <= df['true_alert_cycle'] + WINDOW_AFTER) &
        df['true_alert_cycle'].notna()
    ).astype(int)

    sensor_cols = [c for c in cols if c.startswith('s')]
    return df, sensor_cols, max_train_id


def drop_constants(df, sensor_cols):
    return [c for c in sensor_cols if df[c].std() >= 1e-6 and df[c].nunique() > 1]


def make_scaler(norm):
    return MinMaxScaler() if norm == 'minmax' else StandardScaler()


def make_clf(model):
    if model == 'mlp':
        return MLPClassifier(hidden_layer_sizes=(100, 50), max_iter=500, random_state=42)
    if model == 'gb':
        return GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, random_state=42)
    return RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42)


def train_model(df, feat_cols, cfg):
    X      = df[feat_cols].values.astype(np.float32)
    y      = df['target_window'].values
    groups = df['engine_id'].values

    scaler = make_scaler(cfg['norm'])
    clf    = make_clf(cfg['model'])

    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    tr_idx, _ = next(gss.split(X, y, groups=groups))

    X_tr = scaler.fit_transform(X[tr_idx])
    clf.fit(X_tr, y[tr_idx])
    return scaler, clf


# ── Synthetic engine generator ────────────────────────────────────────────────

class SyntheticEngine:
    """
    Generates synthetic sensor readings that statistically match C-MAPSS training
    data, with a tunable degradation onset and RNG-controlled noise.

    Degradation model:
        sensor(t) = baseline_mean
                  + delta * deg_level(t)      ← learned drift direction from data
                  + noise(t)                  ← Gaussian, scaled to healthy std
    where deg_level(t) ramps from 0 at onset_cycle to 1 at total_cycles.
    """

    def __init__(self, df_train, feat_cols, rng, total_cycles=None):
        self.feat_cols = feat_cols
        self.rng       = rng

        # Use most common operating condition (relevant for FD002/FD004)
        if 'os1' in df_train.columns:
            main_cond = df_train.groupby('engine_id')['os1'].first().round(0).value_counts().index[0]
            df_cond   = df_train[df_train['os1'].round(0) == main_cond]
        else:
            df_cond = df_train

        df_healthy  = df_cond[df_cond['RUL'] > 100]
        df_critical = df_cond[df_cond['RUL'] <= RUL_THRESHOLD]

        if len(df_healthy) == 0:
            df_healthy = df_cond

        self.baseline_mean = df_healthy[feat_cols].mean().values
        self.baseline_std  = df_healthy[feat_cols].std().clip(lower=1e-6).values

        # Direction + magnitude of sensor drift from healthy→critical
        if len(df_critical) > 0:
            self.delta = df_critical[feat_cols].mean().values - self.baseline_mean
        else:
            self.delta = np.zeros(len(feat_cols))

        # --- Pick which sensors to display (most informative about degradation) ---
        # Relative drift = |delta| / healthy_std.  Higher → more informative.
        rel_drift = np.abs(self.delta) / (self.baseline_std + 1e-6)
        self.display_idx = np.argsort(rel_drift)[-N_DISPLAY:][::-1]

        # Flip sign so "visually upward = more degraded" for all displayed sensors
        self.display_flip = np.array([self.delta[i] < 0 for i in self.display_idx])

        # Display normalization ranges (baseline ± delta ± 3σ)
        self.display_ranges = []
        for i in self.display_idx:
            lo = min(self.baseline_mean[i],
                     self.baseline_mean[i] + self.delta[i]) - 3 * self.baseline_std[i]
            hi = max(self.baseline_mean[i],
                     self.baseline_mean[i] + self.delta[i]) + 3 * self.baseline_std[i]
            self.display_ranges.append((lo, hi))

        # --- Total life and onset ---
        life_dist = df_train.groupby('engine_id')['cycle'].max().values
        if total_cycles is None:
            # Sample from training distribution (clamp to 5th–95th percentile)
            lo_life = int(np.percentile(life_dist, 5))
            hi_life = int(np.percentile(life_dist, 95))
            total_cycles = int(rng.integers(lo_life, hi_life + 1))
        self.total_cycles = total_cycles

        # Degradation onset: between 20% and 55% of total life
        self.onset = int(rng.uniform(0.20, 0.55) * total_cycles)

        # Per-sensor noise: 15–40% of healthy std
        self.noise_scale = rng.uniform(0.15, 0.40, size=len(feat_cols)) * self.baseline_std

    @property
    def display_names(self):
        return [self.feat_cols[i] for i in self.display_idx]

    def step(self, cycle):
        """
        Returns (raw_sensor_array, degradation_level).
        degradation_level in [0, 1]: 0 = healthy, 1 = end-of-life.
        """
        if cycle <= self.onset:
            deg = 0.0
        else:
            deg = (cycle - self.onset) / max(1, self.total_cycles - self.onset)
        deg = float(np.clip(deg, 0.0, 1.05))

        noise  = self.rng.normal(0.0, self.noise_scale)
        values = self.baseline_mean + self.delta * deg + noise
        return values, deg

    def normalize_for_display(self, raw_vals):
        """Normalize displayed sensors to [0,1] with upward = more degraded."""
        normed = []
        for i_disp, (i_feat, (lo, hi), flip) in enumerate(
                zip(self.display_idx, self.display_ranges, self.display_flip)):
            v = raw_vals[i_feat]
            n = (v - lo) / max(hi - lo, 1e-6)
            normed.append(float(np.clip(1.0 - n if flip else n, -0.05, 1.10)))
        return normed


# ── Main simulation ───────────────────────────────────────────────────────────

def run_simulation(dataset, seed, speed_ms, override_cycles):
    rng = np.random.default_rng(seed)
    cfg = DS_CFG[dataset]

    # 1. Load and train
    print(f'\n{"="*55}')
    print(f'  C-MAPSS Real-Time Simulator  |  {dataset}  |  seed={seed}')
    print(f'{"="*55}')
    print(f'  [1/3] Loading {dataset} data ...')
    df, sensor_cols, max_train_id = load_cmapss(dataset)
    feat_cols = drop_constants(df, sensor_cols)
    print(f'        {len(feat_cols)} active sensor features: {feat_cols}')

    print(f'  [2/3] Training {cfg["model"].upper()} classifier ...')
    scaler, clf = train_model(df, feat_cols, cfg)
    print(f'        Model ready.')

    # 2. Synthetic engine
    print(f'  [3/3] Generating synthetic engine ...')
    df_train = df[df['engine_id'] <= max_train_id]
    engine   = SyntheticEngine(df_train, feat_cols, rng, total_cycles=override_cycles)
    T        = engine.total_cycles
    ta       = max(1, T - RUL_THRESHOLD + 1)   # true alert cycle (when RUL first hits threshold)

    print(f'        Total life   : {T} cycles')
    print(f'        True alert @ : cycle {ta}  (RUL ≤ {RUL_THRESHOLD})')
    print(f'        Onset        : cycle {engine.onset}')
    print(f'        Display sens : {engine.display_names}')
    print(f'\n  Starting animation — close the window to exit.\n')

    # 3. Build figure
    DARK   = '#0d1117'
    PANEL  = '#161b22'
    BORDER = '#30363d'
    FG     = '#c9d1d9'
    DIM    = '#8b949e'
    SENSOR_COLORS = ['#58a6ff', '#ff7b72', '#3fb950', '#d2a8ff']
    ALERT_COL     = '#f85149'
    SAFE_COL      = '#3fb950'
    WARN_COL      = '#d29922'

    matplotlib.rcParams.update({
        'figure.facecolor': DARK,
        'axes.facecolor':   PANEL,
        'axes.edgecolor':   BORDER,
        'axes.labelcolor':  DIM,
        'xtick.color':      DIM,
        'ytick.color':      DIM,
        'text.color':       FG,
        'grid.color':       BORDER,
        'grid.linewidth':   0.6,
    })

    fig = plt.figure(figsize=(13, 7.5))
    fig.canvas.manager.set_window_title(
        f'PdM Real-Time Sim  —  {dataset}  seed={seed}')

    gs = GridSpec(3, 1, figure=fig, hspace=0.40,
                  left=0.07, right=0.97, top=0.91, bottom=0.07)

    ax_s = fig.add_subplot(gs[0])   # sensors
    ax_p = fig.add_subplot(gs[1])   # probability
    ax_h = fig.add_subplot(gs[2])   # health bar

    fig.suptitle(
        f'C-MAPSS Real-Time Simulator  ·  Dataset: {dataset}  ·  '
        f'Model: {cfg["model"].upper()}  ·  Seed: {seed}  ·  Life: {T} cycles',
        fontsize=11, color=FG, y=0.97)

    # --- Sensor panel ---
    ax_s.set_title('Key Sensor Readings  (normalized, ↑ = more degraded)',
                   fontsize=9, color=DIM, pad=5)
    ax_s.set_xlim(0, T)
    ax_s.set_ylim(-0.08, 1.18)
    ax_s.set_ylabel('Norm. value', fontsize=9)
    ax_s.axhline(0, color=BORDER, lw=0.8)
    ax_s.axhline(1, color=BORDER, lw=0.8)
    ax_s.axvline(ta, color=ALERT_COL, lw=1.2, ls=':', alpha=0.5)
    ax_s.axvspan(ta, T, color=ALERT_COL, alpha=0.06)
    ax_s.grid(True, axis='x')

    sensor_lines = []
    for name, color in zip(engine.display_names, SENSOR_COLORS):
        ln, = ax_s.plot([], [], color=color, lw=1.6, label=name)
        sensor_lines.append(ln)
    ax_s.legend(loc='upper left', fontsize=8, ncol=2,
                facecolor=DARK, edgecolor=BORDER,
                labelcolor=FG, framealpha=0.9)

    # --- Probability panel ---
    ax_p.set_title('Alert Probability', fontsize=9, color=DIM, pad=5)
    ax_p.set_xlim(0, T)
    ax_p.set_ylim(-0.05, 1.15)
    ax_p.set_ylabel('P(alert)', fontsize=9)
    ax_p.set_xlabel('Cycle', fontsize=9)
    ax_p.axhline(cfg['T'], color=ALERT_COL, lw=1.5, ls='--', alpha=0.85,
                 label=f'Threshold  T={cfg["T"]}')
    ax_p.axvline(ta, color=ALERT_COL, lw=1.2, ls=':', alpha=0.5)
    ax_p.axvspan(ta, T, color=ALERT_COL, alpha=0.06,
                 label=f'True danger zone (RUL ≤ {RUL_THRESHOLD})')
    ax_p.grid(True)

    raw_ln,  = ax_p.plot([], [], color='#58a6ff', lw=1.0, alpha=0.45, label='Raw P')
    sm_ln,   = ax_p.plot([], [], color='#ffa657', lw=2.2,
                         label=f'Smoothed (MA w={cfg["smooth_w"]})')
    ax_p.legend(loc='upper left', fontsize=8, ncol=2,
                facecolor=DARK, edgecolor=BORDER,
                labelcolor=FG, framealpha=0.9)

    alert_vl = ax_p.axvline(x=-999, color=ALERT_COL, lw=2.0, alpha=0.0)
    alert_tx = ax_p.text(0.50, 0.88, '', transform=ax_p.transAxes,
                         ha='center', fontsize=9, color=ALERT_COL,
                         fontweight='bold', zorder=10)

    # --- Health bar panel ---
    ax_h.set_xlim(0, 1)
    ax_h.set_ylim(0, 1)
    ax_h.axis('off')

    # Background trough
    ax_h.add_patch(mpatches.FancyBboxPatch(
        (0.04, 0.20), 0.92, 0.42,
        boxstyle='round,pad=0.01', facecolor=DARK,
        edgecolor=BORDER, lw=1.5, zorder=1))

    health_bar = mpatches.FancyBboxPatch(
        (0.04, 0.20), 0.92, 0.42,
        boxstyle='round,pad=0.01', facecolor=SAFE_COL,
        edgecolor='none', zorder=2)
    ax_h.add_patch(health_bar)

    status_tx = ax_h.text(0.50, 0.72, 'HEALTHY',
                           ha='center', va='bottom', fontsize=12,
                           color=SAFE_COL, fontweight='bold',
                           transform=ax_h.transAxes, zorder=3)
    cycle_tx  = ax_h.text(0.03, 0.04, f'Cycle: 0 / {T}',
                           ha='left', va='bottom', fontsize=9,
                           color=DIM, transform=ax_h.transAxes)
    rul_tx    = ax_h.text(0.97, 0.04, f'True RUL: {T}',
                           ha='right', va='bottom', fontsize=9,
                           color=DIM, transform=ax_h.transAxes)

    # 4. Simulation state
    st = {
        'cycles':    [],
        'raw_p':     [],
        'sm_p':      [],
        'sens_hist': [[] for _ in range(N_DISPLAY)],
        'k_run':     0,
        'alert_at':  None,
    }

    def _update(_frame):
        cycle = _frame + 1
        if cycle > T:
            return []

        # --- Sensor step ---
        raw_vals, deg = engine.step(cycle)

        # --- Inference ---
        row = np.array([raw_vals], dtype=np.float32)
        X_s = scaler.transform(row)
        p   = float(clf.predict_proba(X_s)[0, 1])

        st['cycles'].append(cycle)
        st['raw_p'].append(p)

        # Trailing moving-average smoothing
        n  = len(st['raw_p'])
        w  = cfg['smooth_w']
        sm = float(np.mean(st['raw_p'][max(0, n - w):n]))
        st['sm_p'].append(sm)

        # K-consecutive alert detection
        if sm >= cfg['T']:
            st['k_run'] += 1
        else:
            st['k_run'] = 0

        if st['alert_at'] is None and st['k_run'] >= cfg['K']:
            st['alert_at'] = cycle - cfg['K'] + 1

        # --- Sensor history ---
        normed = engine.normalize_for_display(raw_vals)
        for i, v in enumerate(normed):
            st['sens_hist'][i].append(v)

        cs = st['cycles']

        # Update sensor lines
        for i, ln in enumerate(sensor_lines):
            ln.set_data(cs, st['sens_hist'][i])

        # Update prob lines
        raw_ln.set_data(cs, st['raw_p'])
        sm_ln.set_data(cs, st['sm_p'])

        # Alert annotation
        if st['alert_at'] is not None:
            ac = st['alert_at']
            alert_vl.set_xdata([ac, ac])
            alert_vl.set_alpha(0.9)
            true_rul = max(0, T - ac)
            delta    = ac - ta
            sign     = ('+' if delta >= 0 else '')
            alert_tx.set_text(
                f'⚡ ALERT @ cycle {ac}   |   True RUL: {true_rul}   |   '
                f'Δ: {sign}{delta} cycles vs true')

        # Health bar
        health = max(0.0, 1.0 - deg)
        health_bar.set_width(0.92 * health)

        if st['alert_at'] is not None:
            hcol   = ALERT_COL
            status = 'ALERT FIRED'
        elif health > 0.60:
            hcol   = SAFE_COL
            status = 'HEALTHY'
        elif health > 0.30:
            hcol   = WARN_COL
            status = 'DEGRADING'
        else:
            hcol   = ALERT_COL
            status = 'CRITICAL'

        health_bar.set_facecolor(hcol)
        status_tx.set_color(hcol)
        status_tx.set_text(status)
        cycle_tx.set_text(f'Cycle: {cycle} / {T}')
        rul_tx.set_text(f'True RUL: {max(0, T - cycle)}')

        return []

    ani = animation.FuncAnimation(
        fig, _update, frames=T,
        interval=speed_ms, blit=False, repeat=False)

    plt.show()

    # 5. Post-run summary
    print(f'\n{"="*55}')
    print(f'  Simulation complete  —  {dataset}  seed={seed}')
    print(f'  Total life    : {T} cycles')
    print(f'  Degradation   : onset @ cycle {engine.onset}')
    print(f'  True alert @  : cycle {ta}  (RUL ≤ {RUL_THRESHOLD})')
    if st['alert_at']:
        ac  = st['alert_at']
        rul = max(0, T - ac)
        d   = ac - ta
        print(f'  Model alert @ : cycle {ac}')
        print(f'  True RUL      : {rul} cycles at alert')
        print(f'  Delta         : {d:+d} cycles  '
              f'({"early" if d < 0 else "late" if d > 0 else "exact"})')
        tol = 26  # FD003-style tolerance placeholder
        print(f'  Within ±{tol}    : {"YES" if abs(d) <= tol else "NO"}')
    else:
        print('  Model never fired an alert for this engine.')
    print(f'{"="*55}\n')


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Real-time C-MAPSS synthetic engine degradation simulator')
    parser.add_argument('--dataset', default='FD001',
                        choices=list(DS_CFG.keys()),
                        help='C-MAPSS dataset to use (default: FD001)')
    parser.add_argument('--seed', type=int, default=None,
                        help='RNG seed (default: random)')
    parser.add_argument('--speed', type=int, default=80,
                        help='Milliseconds per cycle in animation (default: 80)')
    parser.add_argument('--cycles', type=int, default=None,
                        help='Override total engine life in cycles')
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else int(np.random.randint(0, 99999))
    run_simulation(args.dataset, seed, args.speed, args.cycles)


if __name__ == '__main__':
    main()
