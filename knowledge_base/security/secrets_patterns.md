# Secret Detection and Credential Protection Standards

## SEC-SECRET-001: AWS Access Keys
Hard-coded AWS access key IDs (starting with `AKIA` followed by 16 alphanumeric characters) expose cloud infrastructure to total compromise. Never commit AWS access keys or secrets to repositories. Retrieve credentials through AWS IAM roles, instance profiles, or environment variables (`AWS_ACCESS_KEY_ID`).

## SEC-SECRET-002: Generic API Keys and Bearer Tokens
Hard-coded bearer tokens, service account credentials, Slack tokens (`xoxb-`, `xoxp-`), Stripe keys (`sk_live_`), and GitHub personal access tokens (`ghp_`) must not be committed. Access keys must be retrieved from runtime secret stores (e.g., Vault, AWS Secrets Manager, Kubernetes Secrets) or environment variables.

## SEC-SECRET-003: High-Entropy String Literals
Strings exhibiting Shannon entropy higher than 4.3 in source code frequently represent cryptographic keys, HMAC secrets, or authorization tokens. High-entropy literals should be externalized to environment configurations.

## SEC-SECRET-004: Hard-Coded Passwords
Hard-coded passwords in connection strings, configuration files, or variable assignments (e.g., `password = "admin123"`) present immediate security hazards. Externalize database passwords using environment variables or encrypted credential vaults.

## SEC-SECRET-005: Asymmetric Private Keys
Committing PEM-encoded private keys (e.g., `-----BEGIN RSA PRIVATE KEY-----`, `-----BEGIN OPENSSH PRIVATE KEY-----`) compromises the underlying public key infrastructure. Store private keys exclusively in hardware security modules (HSM) or secure key vaults.
