#!/usr/bin/env python3
"""Re-render platinum_overview.png at 200 DPI (2x) using same layout/colors."""
import os, struct
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams['font.family'] = ['Segoe UI Emoji', 'Segoe UI', 'DejaVu Sans']

OUT_PNG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'docs', 'architecture', 'platinum_overview.png')
os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)

DPI = 200          # 2x from original 100 DPI
FW  = 16.0         # -> 3200 px wide
FH  = 27.0         # -> 5400 px tall

fig = plt.figure(figsize=(FW, FH), dpi=DPI)
ax  = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, FW)
ax.set_ylim(0, FH)
ax.axis('off')
BG = '#0a0e1a'
ax.set_facecolor(BG)
fig.patch.set_facecolor(BG)

TITLE_C = '#ffd700'
SUB_C   = '#90caf9'
ARROW_C = '#4fc3f7'
WHITE   = '#ffffff'
PALE    = '#e3f2fd'

LAYERS = {
    'input' : {'header': '#0d47a1', 'inner': '#1565c0', 'border': '#64b5f6'},
    'cloud' : {'header': '#1a5c20', 'inner': '#2e7d32', 'border': '#81c784'},
    'hitl'  : {'header': '#4a148c', 'inner': '#6a1b9a', 'border': '#ce93d8'},
    'local' : {'header': '#004d40', 'inner': '#00695c', 'border': '#80cbc4'},
    'vault' : {'header': '#bf360c', 'inner': '#d84315', 'border': '#ff8a65'},
    'output': {'header': '#880e4f', 'inner': '#ad1457', 'border': '#f48fb1'},
    'svcs'  : {'header': '#1c313a', 'inner': '#37474f', 'border': '#90a4ae'},
}

def rbox(x, y, w, h, fc, ec, lw=2.0, alpha=0.92, pad=0.10):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f'round,pad={pad}',
        facecolor=fc, edgecolor=ec, linewidth=lw,
        alpha=alpha, zorder=2, clip_on=False))

def txt(x, y, s, sz=12, c=WHITE, bold=True, ha='center', va='center', ls=1.4):
    ax.text(x, y, s, fontsize=sz, color=c, ha=ha, va=va,
            fontweight='bold' if bold else 'normal',
            linespacing=ls, zorder=4,
            fontfamily=['Segoe UI Emoji', 'Segoe UI', 'DejaVu Sans'])

def down_arrow(cx, y_from, y_to):
    ax.annotate('', xy=(cx, y_to + 0.07), xytext=(cx, y_from - 0.07),
                arrowprops=dict(arrowstyle='-|>', color=ARROW_C,
                                lw=3.8, mutation_scale=34), zorder=5)

MARGIN = 0.30
LW     = FW - 2 * MARGIN
MX     = MARGIN + LW / 2

LHEADER = 0.78
LGAP    = 0.16
LCOMP_H = 1.46
LFOOTER = 0.14
LTOTAL  = LHEADER + LGAP + LCOMP_H + LFOOTER
ARROW_H = 0.72

y_cur = FH - 1.45
y_bottoms = []
for _ in range(7):
    y_cur -= LTOTAL
    y_bottoms.append(y_cur)
    y_cur -= ARROW_H
Y_INPUT, Y_CLOUD, Y_HITL, Y_LOCAL, Y_VAULT, Y_OUTPUT, Y_SVCS = y_bottoms

def draw_layer(y_bot, key, title, components):
    p = LAYERS[key]
    rbox(MARGIN, y_bot, LW, LTOTAL, fc=p['header'], ec=p['border'], lw=2.5, alpha=0.18, pad=0.12)
    h_y = y_bot + LFOOTER + LCOMP_H + LGAP
    rbox(MARGIN, h_y, LW, LHEADER, fc=p['header'], ec=p['border'], lw=2.2, alpha=0.97, pad=0.10)
    txt(MX, h_y + LHEADER / 2, title, sz=14.5, c=WHITE, bold=True)
    n = len(components)
    c_pad = 0.20
    c_w = (LW - (n + 1) * c_pad) / n
    c_y = y_bot + LFOOTER
    for i, (ico, label) in enumerate(components):
        cx = MARGIN + c_pad + i * (c_w + c_pad)
        rbox(cx, c_y, c_w, LCOMP_H, fc=p['inner'], ec=p['border'], lw=1.8, alpha=0.90, pad=0.08)
        txt(cx + c_w / 2, c_y + LCOMP_H / 2, f'{ico}\n{label}', sz=10.5, c=PALE, bold=False, ls=1.45)

def flow_label(y_mid, label):
    txt(MX + 0.8, y_mid, label, sz=8.5, c='#4dd0e1', bold=False)

# Title
TITLE_Y = FH - 0.58
txt(MX, TITLE_Y, '🏆  AI Employee Vault – Platinum Tier', sz=22, c=TITLE_C, bold=True)
txt(MX, TITLE_Y - 0.65,
    'Distributed AI Task Management  |  v1.4.0  |  Oracle OCI (me-dubai-1) + HuggingFace Spaces',
    sz=11.5, c=SUB_C, bold=False)
ax.axhline(TITLE_Y - 1.05, xmin=MARGIN/FW, xmax=(FW-MARGIN)/FW,
           color=TITLE_C, lw=1.4, alpha=0.40, zorder=1)

draw_layer(Y_INPUT, 'input', '[ IN ]  INPUT LAYER',
           [('[ GMAIL ]', 'Gmail\nWatcher'), ('[ DROP ]', 'Manual\nDrop'),
            ('[ INBOX ]', 'Inbox\nFolder'), ('[ QUEUE ]', 'Needs_Action\nQueue')])
down_arrow(MX, Y_INPUT, Y_CLOUD + LTOTAL)
flow_label(Y_INPUT - ARROW_H/2, 'atomic rename  ->  vault/Needs_Action/')

draw_layer(Y_CLOUD, 'cloud', '[ AI ]  CLOUD AI LAYER  (HuggingFace Spaces — Always-On 24/7)',
           [('[ AGENT ]', 'Cloud Agent\nv1.4.0'), ('[ PLAN ]', 'Task\nPlanning'),
            ('[ PROMPT ]', 'Prompt\nGeneration')])
down_arrow(MX, Y_CLOUD, Y_HITL + LTOTAL)
flow_label(Y_CLOUD - ARROW_H/2, 'task manifest  ->  vault/Pending_Approval/')

draw_layer(Y_HITL, 'hitl', '[ HUMAN ]  HUMAN-IN-THE-LOOP GATE',
           [('[ GATE ]', 'HITL Gate\nhitl.py'), ('[ HUMAN ]', 'Human\nApproval'),
            ('[ REJECT ]', 'Rejection\nHandling')])
down_arrow(MX, Y_HITL, Y_LOCAL + LTOTAL)
flow_label(Y_HITL - ARROW_H/2, 'human moves  ->  vault/Approved/')

draw_layer(Y_LOCAL, 'local', '[ RUN ]  LOCAL EXECUTION + MCP TOOL LAYER',
           [('[ EXEC ]', 'Local\nExecutor'), ('[ EMAIL ]', 'Email\nMCP'),
            ('[ CAL ]', 'Calendar\nMCP'), ('[ FILE ]', 'File\nMCP'),
            ('[ SOCIAL ]', 'Social\nMCP'), ('[ ODOO ]', 'Odoo\nClient')])
down_arrow(MX, Y_LOCAL, Y_VAULT + LTOTAL)
flow_label(Y_LOCAL - ARROW_H/2, 'claim-by-move  ->  Done / Retry_Queue/')

draw_layer(Y_VAULT, 'vault', '[ VAULT ]  VAULT STATE MACHINE  (File-System Communication Bus)',
           [('[ PENDING ]', 'Pending_\nApproval'), ('[ APPRVD ]', 'Approved'),
            ('[ DONE ]', 'Done'), ('[ RETRY ]', 'Retry_\nQueue'), ('[ LOGS ]', 'Logs')])
down_arrow(MX, Y_VAULT, Y_OUTPUT + LTOTAL)
flow_label(Y_VAULT - ARROW_H/2, 'JSONL records  ->  execution_log.json')

draw_layer(Y_OUTPUT, 'output', '[ OUT ]  OUTPUT & REPORTING',
           [('[ EXEC ]', 'Execution\nLogs'), ('[ PROOF ]', 'Evidence\nPack'),
            ('[ BRIEF ]', 'CEO\nBriefing'), ('[ HLTH ]', 'Health\nLogs')])
down_arrow(MX, Y_OUTPUT, Y_SVCS + LTOTAL)
flow_label(Y_OUTPUT - ARROW_H/2, 'Watchdog + Rate Limiter supervise all layers')

draw_layer(Y_SVCS, 'svcs', '[ SVC ]  SYSTEM SERVICES',
           [('[ WATCH ]', 'Watchdog\nSupervisor'), ('[ RATE ]', 'Rate\nLimiter'),
            ('[ RETRY ]', 'Retry\nLogic'), ('[ LOG ]', 'Prompt Logger\nSHA-256 Chain')])

foot_y = Y_SVCS - 0.48
ax.axhline(foot_y + 0.22, xmin=MARGIN/FW, xmax=(FW-MARGIN)/FW,
           color=TITLE_C, lw=1.0, alpha=0.28, zorder=1)
txt(MX, foot_y,
    'AI Employee Vault – Platinum Tier  |  Claim-by-Move Protocol  |  SHA-256 Audit Chain  |  Oracle Cloud (me-dubai-1)',
    sz=9, c='#546e7a', bold=False)

plt.savefig(OUT_PNG, dpi=DPI, bbox_inches='tight', facecolor=BG, pad_inches=0.12)
plt.close(fig)

with open(OUT_PNG, 'rb') as f:
    f.read(16)
    w = struct.unpack('>I', f.read(4))[0]
    h = struct.unpack('>I', f.read(4))[0]
print(f'[OK] {OUT_PNG}  {w}x{h} px  {os.path.getsize(OUT_PNG)//1024} KB')
