"""
export_sim_data.py — Batch-generate synthetic engine trajectories for dashboard embedding.

For each C-MAPSS dataset, trains the model once then generates N_SEEDS synthetic
engines, saving cycle-by-cycle sensor traces and model probabilities to JSON.

Output: gen_imgs/sim_trajectories.json
"""

import json, os, sys
import numpy as np

# Reuse everything from rt_simulator
sys.path.insert(0, os.path.dirname(__file__))
import rt_simulator as sim

N_SEEDS    = 10                              # engines per dataset
SEEDS      = list(range(10, 10 + N_SEEDS))  # seeds 10–19 (different from demo seed 42)
DATASETS   = ['FD001', 'FD002', 'FD003', 'FD004']
ROUND_DP   = 3                              # decimal places to save (keeps JSON compact)

os.makedirs('gen_imgs', exist_ok=True)

out = {}

for ds in DATASETS:
    cfg = sim.DS_CFG[ds]
    print(f'\n{"="*55}')
    print(f'  {ds}  (model={cfg["model"].upper()})')
    print(f'{"="*55}')

    # Train model once per dataset
    print('  Loading data ...')
    df, sensor_cols, max_train_id = sim.load_cmapss(ds)
    feat_cols = sim.drop_constants(df, sensor_cols)
    print(f'  Training {cfg["model"].upper()} ...')
    scaler, clf = sim.train_model(df, feat_cols, cfg)
    df_train = df[df['engine_id'] <= max_train_id]
    print(f'  Model ready. Generating {N_SEEDS} engines ...')

    engines = []
    for seed in SEEDS:
        rng    = np.random.default_rng(seed)
        engine = sim.SyntheticEngine(df_train, feat_cols, rng)
        T      = engine.total_cycles
        ta     = max(1, T - sim.RUL_THRESHOLD + 1)

        cycles_list = []
        raw_p_list  = []
        sm_p_list   = []
        sens_hist   = [[] for _ in range(sim.N_DISPLAY)]
        k_run       = 0
        alert_at    = None

        for cycle in range(1, T + 1):
            raw_vals, _ = engine.step(cycle)
            row  = np.array([raw_vals], dtype='float32')
            Xs   = scaler.transform(row)
            p    = float(clf.predict_proba(Xs)[0, 1])

            cycles_list.append(cycle)
            raw_p_list.append(round(p, ROUND_DP))

            n  = len(raw_p_list)
            w  = cfg['smooth_w']
            sm = float(np.mean(raw_p_list[max(0, n - w):n]))
            sm_p_list.append(round(sm, ROUND_DP))

            if sm >= cfg['T']:
                k_run += 1
            else:
                k_run = 0
            if alert_at is None and k_run >= cfg['K']:
                alert_at = cycle - cfg['K'] + 1

            normed = engine.normalize_for_display(raw_vals)
            for i, v in enumerate(normed):
                sens_hist[i].append(round(v, ROUND_DP))

        engines.append({
            'seed':       seed,
            'total':      T,
            'onset':      engine.onset,
            'sensors':    engine.display_names,
            'sensor_hist': sens_hist,
            'raw_p':      raw_p_list,
            'sm_p':       sm_p_list,
            'alert_at':   alert_at,
            'true_alert': ta,
        })

        delta = (alert_at - ta) if alert_at else None
        sign  = ('+' if delta and delta >= 0 else '')
        print(f'    seed={seed}  life={T}  alert@{alert_at}  '
              f'true@{ta}  delta={sign}{delta}')

    out[ds] = {
        'cfg': {
            'T': cfg['T'], 'K': cfg['K'],
            'smooth_w': cfg['smooth_w'], 'model': cfg['model']
        },
        'engines': engines,
    }
    print(f'  Done — {len(engines)} engines saved.')

out_path = 'gen_imgs/sim_trajectories.json'
with open(out_path, 'w') as f:
    json.dump(out, f, separators=(',', ':'))

size_kb = os.path.getsize(out_path) / 1024
print(f'\n{"="*55}')
print(f'[OK] Saved {out_path}  ({size_kb:.1f} KB)')
for ds, v in out.items():
    print(f'     {ds}: {len(v["engines"])} engines')
print('\nNext step: run embed_sim.py to inject into dashboard.html')
