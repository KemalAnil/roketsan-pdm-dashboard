"""Replace only the SIM_DATA const in dashboard.html with updated trajectories."""
import json, re

with open('gen_imgs/sim_trajectories.json', encoding='utf-8') as f:
    sim_data = json.load(f)

new_sim_js = 'const SIM_DATA = ' + json.dumps(sim_data, separators=(',', ':')) + ';'

with open('dashboard.html', encoding='utf-8') as f:
    html = f.read()

pat   = r'const SIM_DATA = \{.*?\};'
match = re.search(pat, html, re.DOTALL)
assert match, 'SIM_DATA not found in dashboard.html'
html  = html[:match.start()] + new_sim_js + html[match.end():]

with open('dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

import os
print(f'[OK] SIM_DATA updated ({len(new_sim_js)//1024} KB)  dashboard.html = {os.path.getsize("dashboard.html")/1024/1024:.1f} MB')
