# Severity Policy & Merge Decision Specification

This document details the severity taxonomy, weighting algorithm, corroboration multipliers, and merge acceptance criteria defined in `config/severity_policy.yaml`.

---

## 1. Severity Taxonomy

| Severity | Numerical Rank | Definition | Examples | Blocks Merge? |
| :--- | :---: | :--- | :--- | :---: |
| **CRITICAL** | 5 | Exploitable vulnerability, leaked secret, remote code execution, or irreversible data loss. | SQL injection, hard-coded AWS key, command injection via `shell=True`. | **Yes (Always)** |
| **HIGH** | 4 | Severe functional defect, insecure API usage, or untested public business logic. | New public function with 0 tests, insecure deserialization, DOM XSS. | **Yes (Always)** |
| **MEDIUM** | 3 | Substantial code quality, reliability, or partial test adequacy concerns. | Missing assertions, bare `except:`, high cyclomatic complexity (>10), weak hash. | **Conditional** (If score >= 30) |
| **LOW** | 2 | Minor maintainability, style, or cosmetic divergence from project standards. | Line length (>100), naming convention violations, debug print statements. | **No** |
| **INFO** | 1 | Contextual observation or metadata regarding changeset composition. | Large changeset size, modified dependency manifests, sensitive areas touched. | **No** |

---

## 2. Risk Score Calculation

The Merge-Risk Score is calculated through a deterministic multi-stage algorithm:

### Step 1: Base Severity Weight Sum
Each deduplicated finding contributes points according to its assigned severity:
- `CRITICAL`: 40 points
- `HIGH`: 20 points
- `MEDIUM`: 8 points
- `LOW`: 2 points
- `INFO`: 0 points

$$\text{Base Score} = \min\left(100, \sum_{f \in \text{Findings}} \text{Weight}(f.\text{severity})\right)$$

### Step 2: Multi-Agent Corroboration Uplift
When independent specialist agents corroborate an issue in the same code region, the cumulative confidence increases. For every corroborated finding:

$$\text{Final Score} = \min\left(100, \text{round}\left(\text{Base Score} \times \left(1 + 0.10 \times N_{\text{corroborated}}\right)\right)\right)$$

---

## 3. Merge Decision Logic

The Reviewer Manager determines the merge recommendation based on the following deterministic rules:

1. **Rule 1 (Hard Blocker):**
   If any finding has a severity present in `blocking_severities` (`CRITICAL` or `HIGH`):
   $$\text{Decision} = \text{REQUEST\_CHANGES}$$
2. **Rule 2 (Cumulative Risk Threshold):**
   If the calculated $\text{Final Score} \ge \text{request\_changes\_score}$ (default threshold: 30):
   $$\text{Decision} = \text{REQUEST\_CHANGES}$$
3. **Rule 3 (Clean Approval):**
   If zero blocking issues exist and the risk score is below 30:
   $$\text{Decision} = \text{APPROVE}$$

---

## 4. Configuration Reference (`config/severity_policy.yaml`)

```yaml
weights:
  CRITICAL: 40
  HIGH: 20
  MEDIUM: 8
  LOW: 2
  INFO: 0

blocking_severities:
  - CRITICAL
  - HIGH

thresholds:
  request_changes_score: 30
  max_score: 100
  corroboration_multiplier: 0.10

category_priority:
  - security
  - test_coverage
  - style
  - diff

size_thresholds:
  XS: 20
  S: 100
  M: 300
  L: 800
  XL: 99999999
```
