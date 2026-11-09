# Security

This is an early-stage local tool. Only the current main branch is maintained;
there is no security-response SLA.

For a sensitive vulnerability, use GitHub's **Report a vulnerability** feature:
https://github.com/R-Koda/splittrace/security/advisories/new

Do not put credentials, patient information or sensitive sample manifests in
public issues. Include a synthetic reproducer and the affected commit where
possible. Non-sensitive correctness bugs can be reported in ordinary issues.

The core does not upload data or execute manifest content. Reports may contain
identifiers supplied by the caller. Review them before sharing. Large manifests
or deeply connected provenance graphs can consume substantial CPU and memory;
the prototype is intended for small, locally trusted inputs.
