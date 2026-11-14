"""Deterministic security vulnerability and secret detection plugin."""

from __future__ import annotations

import math
import re
from typing import Annotated

from semantic_kernel.functions import kernel_function

from config.settings import Settings, get_settings
from core.models import Category, FileChange, Finding, Severity
from core.retrieval import KnowledgeBase, get_knowledge_base

_AWS_KEY_RE = re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16,20})\b")
_SLACK_TOKEN_RE = re.compile(r"\b(xox[baprs]-[0-9a-zA-Z-]{10,})\b")
_GITHUB_TOKEN_RE = re.compile(r"\b(gh[pousr]_[0-9a-zA-Z]{30,})\b")
_STRIPE_KEY_RE = re.compile(r"\b(sk_live_[0-9a-zA-Z]{20,})\b")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")
_PASSWORD_ASSIGN_RE = re.compile(r"""(?i)\b(?:password|passwd|pwd)\s*[:=]\s*['"]([^'"]{4,})['"]""")
_API_KEY_ASSIGN_RE = re.compile(r"""(?i)\b(?:api_key|secret_key|access_token|admin_token|auth_token)\s*[:=]\s*['"]([^'"]{12,})['"]""")

_SQLI_FSTRING_RE = re.compile(r"""(?i)f['"][^'"]*\b(select|insert\s+into|update|delete\s+from|drop\s+table)\b[^'"]*\{[^}]+\}""")
_SQLI_CONCAT_RE = re.compile(r"""(?i)['"][^'"]*\b(select|insert\s+into|update|delete\s+from)\b[^'"]*['"]\s*\+""")
_CMDI_SHELL_RE = re.compile(r"\bshell\s*=\s*True\b")
_CMDI_OS_SYSTEM_RE = re.compile(r"\bos\.system\s*\(")
_DESER_PICKLE_RE = re.compile(r"\bpickle\.(?:loads?|Unpickler)\b")
_DESER_YAML_RE = re.compile(r"\byaml\.load\s*\([^)]*(?!SafeLoader|safe_load)[^)]*\)")
_EVAL_EXEC_RE = re.compile(r"\b(eval|exec)\s*\(")
_XSS_INNER_HTML_RE = re.compile(r"(\.innerHTML\s*=|dangerouslySetInnerHTML|document\.write\s*\()")
_WEAK_HASH_RE = re.compile(r"\bhashlib\.(md5|sha1)\s*\(")
_TLS_DISABLED_RE = re.compile(r"\bverify\s*=\s*False\b")
_DEBUG_TRUE_RE = re.compile(r"\bDEBUG\s*=\s*True\b")
_CORS_WILDCARD_RE = re.compile(r"""(?i)(allow_origins:\s*['"]?\*['"]?|Access-Control-Allow-Origin['"]?\s*[:=]\s*['"]?\*)""")


def calculate_shannon_entropy(data: str) -> float:
    """Calculate the Shannon entropy of a string."""
    if not data:
        return 0.0
    entropy = 0.0
    length = float(len(data))
    for char in set(data):
        prob = data.count(char) / length
        if prob > 0.0:
            entropy -= prob * math.log2(prob)
    return entropy


def redact_secret_string(val: str) -> str:
    """Redact secret string to show only initial characters followed by asterisks."""
    clean = val.strip("'\"")
    if len(clean) <= 6:
        return "****"
    return clean[:4] + "****"


class SecurityPlugin:
    """Deterministic security analyzer for secrets, unsafe APIs, and injection flaws."""

    def __init__(
        self,
        settings: Settings | None = None,
        kb: KnowledgeBase | None = None,
    ):
        self.settings = settings or get_settings()
        self.kb = kb or get_knowledge_base()

    def _get_citation(self, rule_id: str) -> str | None:
        """Resolve evidence source citation from knowledge base."""
        chunk = self.kb.lookup_rule(rule_id)
        if chunk:
            return chunk.citation
        results = self.kb.search(rule_id, top_k=1, category_filter="security")
        if results:
            return results[0][0].citation
        return None

    @kernel_function(
        name="check_security",
        description="Scan added lines for secrets, credentials, and dangerous programming patterns",
    )
    def check_security(
        self,
        files: Annotated[list[FileChange], "List of parsed FileChange objects"],
        risk_areas: Annotated[list[str], "Detected risk domains from Diff Agent"] | None = None,
    ) -> list[Finding]:
        """Perform comprehensive deterministic security analysis."""
        findings: list[Finding] = []
        active_risk_areas = set(risk_areas or [])

        for f in files:
            if f.is_binary or f.role == "docs":
                continue

            # Special check for dependency manifest files
            if f.role == "dependency":
                dep_findings = self._check_dependency_file(f)
                findings.extend(dep_findings)
                continue

            for hunk in f.hunks:
                for line in hunk.added_lines:
                    text = line.content
                    line_no = line.line_number

                    # 1. Secret Detection
                    secret_finding = self._check_secrets(text, f.path, line_no)
                    if secret_finding:
                        findings.append(secret_finding)
                        # Avoid double-flagging same line with pattern rules
                        continue

                    # 2. Unsafe Pattern Detection
                    pattern_findings = self._check_unsafe_patterns(
                        text, f.path, line_no, f.language, active_risk_areas
                    )
                    findings.extend(pattern_findings)

        return findings

    def _check_secrets(self, text: str, file_path: str, line_no: int) -> Finding | None:
        """Inspect text for hard-coded tokens, keys, and high-entropy secrets."""
        # AWS Key
        m_aws = _AWS_KEY_RE.search(text)
        if m_aws:
            raw = m_aws.group(1)
            citation = self._get_citation("SEC-SECRET-001")
            return Finding(
                id=Finding.generate_id(Category.SECURITY, "SEC-SECRET-001", file_path, line_no),
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                title="Hard-Coded AWS Access Key Detected",
                description=f"Line {line_no} contains hard-coded AWS access credentials ({redact_secret_string(raw)}).",
                file_path=file_path,
                line_start=line_no,
                line_end=line_no,
                code_snippet=text.replace(raw, redact_secret_string(raw)),
                rule_id="SEC-SECRET-001",
                evidence_source=citation,
                recommendation="Externalize credentials to environment variables or IAM instance profiles. Revoke the exposed key immediately.",
                confidence=1.0,
                reported_by=["security_agent"],
            )

        # Slack Token
        m_slack = _SLACK_TOKEN_RE.search(text)
        if m_slack:
            raw = m_slack.group(1)
            citation = self._get_citation("SEC-SECRET-002")
            return Finding(
                id=Finding.generate_id(Category.SECURITY, "SEC-SECRET-002", file_path, line_no),
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                title="Hard-Coded Slack Token Detected",
                description=f"Line {line_no} contains hard-coded Slack token ({redact_secret_string(raw)}).",
                file_path=file_path,
                line_start=line_no,
                line_end=line_no,
                code_snippet=text.replace(raw, redact_secret_string(raw)),
                rule_id="SEC-SECRET-002",
                evidence_source=citation,
                recommendation="Externalize tokens to secure secret stores and rotate immediately.",
                confidence=1.0,
                reported_by=["security_agent"],
            )

        # GitHub Token
        m_gh = _GITHUB_TOKEN_RE.search(text)
        if m_gh:
            raw = m_gh.group(1)
            citation = self._get_citation("SEC-SECRET-002")
            return Finding(
                id=Finding.generate_id(Category.SECURITY, "SEC-SECRET-002", file_path, line_no),
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                title="Hard-Coded GitHub Token Detected",
                description=f"Line {line_no} contains hard-coded GitHub personal access token ({redact_secret_string(raw)}).",
                file_path=file_path,
                line_start=line_no,
                line_end=line_no,
                code_snippet=text.replace(raw, redact_secret_string(raw)),
                rule_id="SEC-SECRET-002",
                evidence_source=citation,
                recommendation="Externalize token and revoke immediately from GitHub account settings.",
                confidence=1.0,
                reported_by=["security_agent"],
            )

        # Stripe Key
        m_stripe = _STRIPE_KEY_RE.search(text)
        if m_stripe:
            raw = m_stripe.group(1)
            citation = self._get_citation("SEC-SECRET-002")
            return Finding(
                id=Finding.generate_id(Category.SECURITY, "SEC-SECRET-002", file_path, line_no),
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                title="Hard-Coded Stripe Live Secret Key",
                description=f"Line {line_no} contains live payment gateway secret ({redact_secret_string(raw)}).",
                file_path=file_path,
                line_start=line_no,
                line_end=line_no,
                code_snippet=text.replace(raw, redact_secret_string(raw)),
                rule_id="SEC-SECRET-002",
                evidence_source=citation,
                recommendation="Rotate compromised Stripe key immediately and inject via environment variables.",
                confidence=1.0,
                reported_by=["security_agent"],
            )

        # Private Key Block
        if _PRIVATE_KEY_RE.search(text):
            citation = self._get_citation("SEC-SECRET-005")
            return Finding(
                id=Finding.generate_id(Category.SECURITY, "SEC-SECRET-005", file_path, line_no),
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                title="Committed Asymmetric Private Key Block",
                description=f"Line {line_no} contains PEM private key header.",
                file_path=file_path,
                line_start=line_no,
                line_end=line_no,
                code_snippet="-----BEGIN PRIVATE KEY----- [REDACTED]",
                rule_id="SEC-SECRET-005",
                evidence_source=citation,
                recommendation="Remove private key from source control and generate a new key pair.",
                confidence=1.0,
                reported_by=["security_agent"],
            )

        # Password Assignment
        m_pwd = _PASSWORD_ASSIGN_RE.search(text)
        if m_pwd:
            raw = m_pwd.group(1)
            citation = self._get_citation("SEC-SECRET-004")
            return Finding(
                id=Finding.generate_id(Category.SECURITY, "SEC-SECRET-004", file_path, line_no),
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                title="Hard-Coded Password Assignment",
                description=f"Line {line_no} contains plaintext password assignment.",
                file_path=file_path,
                line_start=line_no,
                line_end=line_no,
                code_snippet=text.replace(raw, redact_secret_string(raw)),
                rule_id="SEC-SECRET-004",
                evidence_source=citation,
                recommendation="Retrieve passwords securely from environment variables or encrypted secrets management.",
                confidence=1.0,
                reported_by=["security_agent"],
            )

        # Generic API Key Assignment
        m_api = _API_KEY_ASSIGN_RE.search(text)
        if m_api:
            raw = m_api.group(1)
            citation = self._get_citation("SEC-SECRET-002")
            return Finding(
                id=Finding.generate_id(Category.SECURITY, "SEC-SECRET-002", file_path, line_no),
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                title="Hard-Coded API Key or Token Assignment",
                description=f"Line {line_no} contains hard-coded API key or token ({redact_secret_string(raw)}).",
                file_path=file_path,
                line_start=line_no,
                line_end=line_no,
                code_snippet=text.replace(raw, redact_secret_string(raw)),
                rule_id="SEC-SECRET-002",
                evidence_source=citation,
                recommendation="Externalize API keys to environment variables and rotate exposed keys.",
                confidence=1.0,
                reported_by=["security_agent"],
            )

        # Shannon Entropy Check for Unclassified String Literals
        str_literals = re.findall(r"""['"]([a-zA-Z0-9_\-+/=]{16,})['"]""", text)
        for literal in str_literals:
            entropy = calculate_shannon_entropy(literal)
            if entropy >= self.settings.entropy_threshold and not literal.startswith(("http://", "https://", "schemas.")):
                citation = self._get_citation("SEC-SECRET-003")
                return Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-SECRET-003", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.CRITICAL,
                    title="High-Entropy String Literal (Probable Secret)",
                    description=f"Line {line_no} contains a high-entropy string ({entropy:.2f} bits) resembling a credential.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text.replace(literal, redact_secret_string(literal)),
                    rule_id="SEC-SECRET-003",
                    evidence_source=citation,
                    recommendation="Confirm if this value is an authentication credential and externalize to secret storage.",
                    confidence=0.90,
                    reported_by=["security_agent"],
                )

        return None

    def _check_unsafe_patterns(
        self,
        text: str,
        file_path: str,
        line_no: int,
        language: str,
        risk_areas: set[str],
    ) -> list[Finding]:
        """Check for dangerous function calls, injections, and insecure configurations."""
        findings: list[Finding] = []

        # Rule SEC-SQLI-001: SQL Injection
        if _SQLI_FSTRING_RE.search(text) or _SQLI_CONCAT_RE.search(text):
            citation = self._get_citation("SEC-SQLI-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-SQLI-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.CRITICAL,
                    title="SQL Injection Vulnerability via String Formatting",
                    description=f"Line {line_no} dynamically constructs a SQL statement using string interpolation.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-SQLI-001",
                    evidence_source=citation,
                    recommendation="Use parameterized queries (prepared statements) with placeholders (e.g. %s or ?) provided by DB-API.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        # Rule SEC-CMDI-001: Command Injection
        if _CMDI_SHELL_RE.search(text) or _CMDI_OS_SYSTEM_RE.search(text):
            citation = self._get_citation("SEC-CMDI-001")
            # Upgrade to CRITICAL if touching auth/payments risk areas
            sev = Severity.CRITICAL if ("auth" in risk_areas or "payments" in risk_areas) else Severity.HIGH
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-CMDI-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=sev,
                    title="Command Injection Risk via Subprocess Shell",
                    description=f"Line {line_no} invokes subprocess with shell=True or uses os.system(), allowing command chaining.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-CMDI-001",
                    evidence_source=citation,
                    recommendation="Pass command arguments as a list with shell=False to prevent shell metacharacter execution.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        # Rule SEC-DESER-001: Insecure Deserialization
        if _DESER_PICKLE_RE.search(text) or _DESER_YAML_RE.search(text):
            citation = self._get_citation("SEC-DESER-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-DESER-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.HIGH,
                    title="Insecure Object Deserialization",
                    description=f"Line {line_no} deserializes untrusted payload using pickle or unsafe yaml.load.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-DESER-001",
                    evidence_source=citation,
                    recommendation="Use yaml.safe_load or json.loads to prevent arbitrary object instantiation.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        # Rule SEC-EVAL-001: Dynamic Code Execution
        if _EVAL_EXEC_RE.search(text):
            citation = self._get_citation("SEC-EVAL-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-EVAL-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.HIGH,
                    title="Dynamic Code Execution via eval() or exec()",
                    description=f"Line {line_no} evaluates dynamic code strings.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-EVAL-001",
                    evidence_source=citation,
                    recommendation="Avoid eval/exec. Parse inputs using ast.literal_eval() or structured schemas.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        # Rule SEC-XSS-001: DOM Manipulation / XSS
        if _XSS_INNER_HTML_RE.search(text):
            citation = self._get_citation("SEC-XSS-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-XSS-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.HIGH,
                    title="Cross-Site Scripting (XSS) via Direct DOM Assignment",
                    description=f"Line {line_no} modifies DOM directly using innerHTML or dangerouslySetInnerHTML.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-XSS-001",
                    evidence_source=citation,
                    recommendation="Use textContent or framework sanitizers to encode user-supplied text safely.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        # Rule SEC-CRYPTO-001: Weak Cryptographic Hash
        if _WEAK_HASH_RE.search(text):
            citation = self._get_citation("SEC-CRYPTO-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-CRYPTO-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.MEDIUM,
                    title="Use of Broken Cryptographic Hash Algorithm",
                    description=f"Line {line_no} uses MD5 or SHA1 for hashing.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-CRYPTO-001",
                    evidence_source=citation,
                    recommendation="Use SHA-256 (hashlib.sha256) for data integrity or Argon2id/bcrypt for password hashing.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        # Rule SEC-TLS-001: Disabled TLS Certificate Validation
        if _TLS_DISABLED_RE.search(text):
            citation = self._get_citation("SEC-TLS-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-TLS-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.HIGH,
                    title="TLS Certificate Verification Disabled (verify=False)",
                    description=f"Line {line_no} disables SSL/TLS validation, enabling MitM attacks.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-TLS-001",
                    evidence_source=citation,
                    recommendation="Remove verify=False and ensure valid certificate trust chains are configured.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        # Rule SEC-DEBUG-001: Insecure Debug Flag
        if _DEBUG_TRUE_RE.search(text):
            citation = self._get_citation("SEC-DEBUG-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-DEBUG-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.MEDIUM,
                    title="Production Debug Mode Enabled",
                    description=f"Line {line_no} sets DEBUG=True.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-DEBUG-001",
                    evidence_source=citation,
                    recommendation="Ensure debug flags are disabled or read strictly from environment configuration.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        # Rule SEC-CORS-001: Permissive CORS Header
        if _CORS_WILDCARD_RE.search(text):
            citation = self._get_citation("SEC-CORS-001")
            findings.append(
                Finding(
                    id=Finding.generate_id(Category.SECURITY, "SEC-CORS-001", file_path, line_no),
                    category=Category.SECURITY,
                    severity=Severity.MEDIUM,
                    title="Overly Permissive CORS Header (Wildcard '*')",
                    description=f"Line {line_no} configures wildcard Access-Control-Allow-Origin.",
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    code_snippet=text,
                    rule_id="SEC-CORS-001",
                    evidence_source=citation,
                    recommendation="Explicitly enumerate trusted frontend domains in CORS policy.",
                    confidence=1.0,
                    reported_by=["security_agent"],
                )
            )

        return findings

    def _check_dependency_file(self, file_change: FileChange) -> list[Finding]:
        """Detect unpinned dependency specifications in package manifests."""
        findings: list[Finding] = []
        citation = self._get_citation("SEC-DEP-001")

        for hunk in file_change.hunks:
            for line in hunk.added_lines:
                text = line.content.strip()
                if not text or text.startswith("#"):
                    continue

                # In requirements.txt: bare package name without version constraint
                if "requirements" in file_change.path:
                    if not re.search(r"[=><~]", text):
                        findings.append(
                            Finding(
                                id=Finding.generate_id(Category.SECURITY, "SEC-DEP-001", file_change.path, line.line_number),
                                category=Category.SECURITY,
                                severity=Severity.LOW,
                                title=f"Unpinned Dependency '{text}'",
                                description=f"Dependency '{text}' added without pinned version constraints on line {line.line_number}.",
                                file_path=file_change.path,
                                line_start=line.line_number,
                                line_end=line.line_number,
                                code_snippet=text,
                                rule_id="SEC-DEP-001",
                                evidence_source=citation,
                                recommendation="Pin package to an exact or minimum verified version (e.g. package>=1.2.0).",
                                confidence=1.0,
                                reported_by=["security_agent"],
                            )
                        )

        return findings
