# AI Employee Vault – Platinum Tier
## Local Run Checklist

Run these three commands from the project root (each in its own terminal):

**Terminal 1 — Cloud Agent (daemon + auto)**
```bash
python cloud_agent.py --daemon --auto --interval 5
```

**Terminal 2 — Local Executor**
```bash
python local_executor.py --poll 2
```

**Terminal 3 — Generate Evidence Pack**
```bash
python scripts/generate_evidence_pack.py --n 20
```

Output: `Evidence/JUDGE_PROOF.md`
