# AI Employee Vault – Platinum Tier: Security Model

**Document Version:** 1.0.0
**Classification:** Internal Engineering Reference — Security Sensitive
**Last Updated:** 2026-02-27
**Status:** Authoritative

---

## 1. Security Philosophy

The Platinum Tier security model is built on the principle of **defense in depth** — multiple independent security controls such that the failure of any single control does not compromise system integrity. The model assumes adversarial conditions: untrusted inputs, compromised networks, and the possibility of insider threats.

Core tenets:

1. **Least Privilege:** Every component operates with the minimum permissions required for its defined function.
2. **Zero Trust Between Components:** The Cloud Agent and Local Executor do not trust each other's outputs without independent verification.
3. **Immutable Audit:** Security events cannot be deleted or modified — the audit trail is the last line of accountability.
4. **Secrets Never in Vault:** No credentials, API keys, or secrets are ever written to Vault artifacts.
5. **Human in the Critical Path:** No task transitions to execution without explicit human authorization — no AI system can bypass this gate.

---

## 2. Threat Model

### 2.1 Assets to Protect

| Asset | Sensitivity | Description |
|---|---|---|
| Task Manifests | HIGH | Contain prompts, parameters, and potential business logic |
| Prompt Log | HIGH | Historical record of all AI interactions |
| Execution Environment | CRITICAL | Local machine — must not be compromised by task content |
| Approval Workflow | CRITICAL | Bypassing this gate is the primary attack surface |
| Cloud Agent Credentials | CRITICAL | HuggingFace tokens, API keys |
| Vault Access | HIGH | Unauthorized write access could inject malicious tasks |

### 2.2 Threat Actors

| Actor | Type | Motivation | Capability |
|---|---|---|---|
| External Attacker | Adversarial | Inject malicious tasks, exfiltrate data | Network access, social engineering |
| Malicious Task Content | Automated | Prompt injection, command injection via task parameters | Content within approved tasks |
| Compromised Cloud Agent | Adversarial | Write malicious manifests to Vault | Write access to Pending_Approval/ |
| Insider Threat | Adversarial | Bypass approval, manipulate logs | Physical/logical access |
| Accidental Misconfiguration | Non-adversarial | Unintended data exposure | System access |

### 2.3 Attack Vectors

| Attack Vector | Target | Mitigation |
|---|---|---|
| Prompt injection via task content | Local Executor | Schema validation, sandboxed execution |
| Command injection via parameters | Local Executor | Parameter sanitization, allowlist validation |
| Direct Vault write (malicious task) | Approval gate | File system ACLs, approval gate enforcement |
| Log tampering | Audit trail | Append-only logs, hash chaining |
| Cloud Agent compromise | Vault | Vault access controls, Local Executor schema validation |
| Man-in-the-middle (Vault sync) | Data integrity | Prompt hash verification |
| Replay attack (re-execution) | Local Executor | Task ID uniqueness enforcement, execution history |
| Approval forgery | Approval gate | Approver identity verification (implementation-level) |

---

## 3. Access Control Model

### 3.1 Vault Directory Permissions

| Directory | Cloud Agent | Local Executor | Human Approver | Read-Only Users |
|---|---|---|---|---|
| `vault/Pending_Approval/` | READ + WRITE | READ | READ + WRITE (move) | READ |
| `vault/Approved/` | READ | READ + WRITE (move) | READ + WRITE (move) | READ |
| `vault/Done/` | READ | WRITE | READ | READ |
| `vault/Logs/` | READ + WRITE | READ + WRITE | READ | READ |

### 3.2 File System ACL Recommendations

On Linux/macOS:
```bash
# Vault owned by vault-service group
chown -R vault-user:vault-group /path/to/vault
chmod 2750 /path/to/vault
chmod 2770 /path/to/vault/Pending_Approval
chmod 2770 /path/to/vault/Approved
chmod 2770 /path/to/vault/Done
chmod 2770 /path/to/vault/Logs

# Cloud Agent user: member of vault-group, NOT executor-group
# Local Executor user: member of vault-group, NOT cloud-agent-group
# Human Approver: member of vault-group with sudo-level move rights
```

### 3.3 API Authentication (Cloud Agent)

The Cloud Agent API requires authentication on all endpoints except `/health`:

- **Authentication Method:** Bearer token (HuggingFace Spaces built-in auth or custom JWT)
- **Authorization:** Role-based — `submitter`, `viewer`, `admin`
- **Rate Limiting:** Applied per authenticated identity to prevent abuse
- **API Keys:** Rotated minimum every 90 days

---

## 4. Data Protection

### 4.1 Prompt Integrity

Every prompt artifact includes a SHA-256 hash computed over the concatenation of the `system` and `user` prompt fields. The Local Executor **must** recompute and verify this hash before execution. A hash mismatch is treated as a critical security event:

```python
import hashlib

def verify_prompt_hash(prompt_obj: dict) -> bool:
    content = prompt_obj["system"] + prompt_obj["user"]
    computed = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return computed == prompt_obj["hash"]
```

A hash mismatch indicates:
- Manifest tampering during Vault sync
- Storage corruption
- Active attack

**Response:** Task is immediately moved to `vault/Logs/`, security event logged, operator alerted.

### 4.2 Secrets Management

| Secret Type | Storage Location | Access Method |
|---|---|---|
| HuggingFace API Token | Environment variable / HF Secrets | `os.environ["HF_TOKEN"]` |
| Executor Identity Key | `.env` file (not in Vault) | `os.environ["EXECUTOR_SECRET"]` |
| Cloud Agent API Key | HuggingFace Secrets | Injected at runtime |
| Vault Sync Credentials | OS credential store | Platform keychain API |

**Prohibited locations for secrets:**
- Any file in `vault/`
- Task manifest files
- `history/prompt_log.json`
- Any version-controlled file

### 4.3 Data Classification

| Data Type | Classification | Handling |
|---|---|---|
| Task descriptions | INTERNAL | Standard Vault handling |
| System prompts | CONFIDENTIAL | Never logged in plaintext if marked sensitive |
| Execution results | INTERNAL | Stored in vault/Done/ |
| Error messages | INTERNAL | Sanitized before logging (strip PII) |
| API tokens | SECRET | Environment variables only |
| User identifiers | PII-SENSITIVE | Pseudonymized in logs |

---

## 5. Execution Sandboxing

The Local Executor must implement execution isolation to prevent task content from accessing the host system beyond its authorized scope:

### 5.1 Sandboxing Levels (in order of preference)

1. **Container Isolation (Recommended):** Execute each task in an ephemeral Docker/Podman container with no network access and read-only filesystem mounts.
2. **Process Isolation:** Execute in a subprocess with reduced privileges (drop capabilities, `setuid`/`setgid`).
3. **Virtual Environment Isolation:** Minimum — Python venv isolation for code execution tasks.

### 5.2 Resource Limits

| Resource | Limit | Enforcement |
|---|---|---|
| CPU | 2 cores per task | `cgroups` / Docker `--cpus` |
| Memory | 512MB per task | `cgroups` / Docker `--memory` |
| Disk write | 100MB per task | Disk quota / container volume limits |
| Network | No access (default) | `--network=none` / firewall rules |
| Execution time | Task-type specific (default: 5min) | Timeout via subprocess |
| File descriptors | 64 per process | `ulimit -n` |

---

## 6. Audit Trail Security

### 6.1 Log Integrity

The prompt log implements hash chaining to detect tampering:

- Each log entry includes the SHA-256 hash of the previous entry (`prev_hash`)
- The first entry references a known genesis hash
- Any gap or hash mismatch indicates log manipulation

```json
{
  "log_id": "...",
  "prev_hash": "sha256-of-previous-entry",
  "entry_hash": "sha256-of-this-entry-content",
  ...
}
```

### 6.2 Log Access Controls

- `history/prompt_log.json` — READ access for all system components, WRITE (append) for logger only
- Log files are never opened with write modes that allow overwrite
- Log file ownership: dedicated `logger-user` service account

### 6.3 Log Backup

- Real-time replication to secondary storage recommended
- Minimum: daily backup of `history/` directory
- Backup integrity verified via SHA-256 checksum of archived log files

---

## 7. Incident Response

### 7.1 Security Event Classification

| Event | Severity | Response |
|---|---|---|
| Prompt hash mismatch | CRITICAL | Block task, alert operator, preserve evidence |
| Unknown task_id in Approved/ | HIGH | Quarantine task, investigate provenance |
| Log hash chain break | HIGH | Preserve log, alert operator, audit from last valid entry |
| Execution timeout exceeded | MEDIUM | Terminate process, log forensic data |
| Schema validation failure | MEDIUM | Reject task, log detailed failure report |
| Repeated approval of same task | HIGH | Block, alert — possible replay attack |
| Secrets found in manifest | CRITICAL | Purge manifest, rotate secrets, full audit |

### 7.2 Incident Containment Steps

1. **Isolate:** Immediately pause Local Executor if active attack suspected.
2. **Preserve:** Do not modify or delete any Vault contents or logs.
3. **Document:** Record all observations with timestamps.
4. **Investigate:** Trace task lineage through prompt log and Vault history.
5. **Remediate:** Address root cause before resuming operations.
6. **Review:** Post-incident review within 48 hours.

---

## 8. Compliance Considerations

This security model is designed to support compliance with the following frameworks (full compliance requires additional controls beyond this document):

- **SOC 2 Type II:** Audit trail, access controls, incident response
- **ISO 27001:** Information security management, risk assessment
- **GDPR:** PII pseudonymization in logs, data minimization
- **OWASP AI Security:** Prompt injection defenses, model input/output validation

---

*End of Security Model — AI Employee Vault Platinum Tier v1.0.0*
