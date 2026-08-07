# Security Policy

## Status

QuantForge is an early-stage, foundational project with no released
functionality. This policy establishes the reporting process from the start.

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report privately using GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
("Report a vulnerability" under the repository's **Security** tab).

When reporting, please include:

- a description of the issue and its potential impact,
- steps to reproduce, and
- any relevant versions or configuration.

We will acknowledge the report and work with you on a resolution and
coordinated disclosure timeline.

## Secrets

Never commit secrets, credentials, API keys, or `.env` files. If you discover a
secret committed to the repository, report it privately as above so it can be
rotated and removed from history.
