# Contributing to CamoFox

Thank you for your interest in contributing to CamoFox! This project helps people maintain their privacy and use their cellular data without carrier interference.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How to Contribute

### Reporting Bugs

Use the [Bug Report](https://github.com/ilovekyrinathemost-maker/CamoFox/issues/new?template=bug_report.md) template.

### Reporting Detection Changes

If T-Mobile (or another carrier) changes their detection methods, use the [Detection Report](https://github.com/ilovekyrinathemost-maker/CamoFox/issues/new?template=detection_report.md) template. These are high-priority issues.

### Suggesting Features

Use the [Feature Request](https://github.com/ilovekyrinathemost-maker/CamoFox/issues/new?template=feature_request.md) template.

### Submitting Code

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Test thoroughly (see [Testing](#testing))
5. Commit with clear messages: `git commit -m "feat: add UDP relay support"`
6. Push to your fork: `git push origin feature/my-feature`
7. Open a Pull Request using the PR template

## Development Setup

### Router Plugin (`camofox-router/`)

**Requirements:**
- GL-iNet Opal (GL-SFT1200) or compatible OpenWrt router
- SSH access to the router
- `shellcheck` installed locally for linting

**Setup:**
```bash
# Clone the repo
git clone https://github.com/ilovekyrinathemost-maker/CamoFox.git
cd CamoFox

# Copy router files to your router for testing
scp -r camofox-router/ root@192.168.8.1:/tmp/

# Install on router
ssh root@192.168.8.1 'cd /tmp/camofox-router && sh scripts/install.sh'
```

### iPhone App (`camofox-ios/`)

**Requirements:**
- iPhone with cellular data
- [Pythonista 3](https://apps.apple.com/us/app/pythonista-3/id1085978097) ($9.99)
- Python 3.6+ locally for development/testing

**Setup:**
1. Copy `camofox-ios/`, `lib/`, and `dns/` to Pythonista's iCloud directory
2. Open `camofox_start.py` and run to verify basic functionality
3. For local development, use any Python 3.6+ environment

## Code Style Guidelines

### Router Scripts (POSIX Shell)

- **POSIX sh only** — no bashisms. The router runs BusyBox ash.
- Use `#!/bin/sh` shebang
- Pass `shellcheck --shell=sh` with no warnings
- Use snake_case for function and variable names
- Quote all variable expansions: `"$var"` not `$var`
- Use `$(command)` not backticks
- Add comments for non-obvious logic
- Keep functions focused and short

```sh
# Good
get_proxy_status() {
    local pid_file="/var/run/redsocks.pid"
    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "running"
    else
        echo "stopped"
    fi
}
```

### Python (iPhone App & Library)

- **Python 3.6+** compatible (Pythonista constraint)
- Follow PEP 8 style
- Use type hints where practical
- All files must pass `python -m py_compile`
- Use descriptive variable names
- Add docstrings to functions and classes
- Handle exceptions gracefully — the proxy must not crash silently

```python
# Good
def start_proxy(host: str, port: int, timeout: int = 30) -> bool:
    """Start the SOCKS5 proxy server.

    Args:
        host: Bind address for the proxy.
        port: Bind port for the proxy.
        timeout: Connection timeout in seconds.

    Returns:
        True if the proxy started successfully.
    """
```

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `refactor:` — Code refactoring
- `test:` — Adding or updating tests
- `chore:` — Maintenance tasks
- `security:` — Security fixes

Examples:
```
feat: add UDP relay support via SOCKS5
fix: prevent redsocks crash on iPhone disconnect
docs: add troubleshooting section for iOS 18
security: sanitize proxy auth credentials in logs
```

## Testing

### Automated Checks

Before submitting a PR, run these locally:

```bash
# Python syntax check (excludes dns/ third-party library)
find camofox-ios/ lib/ -name '*.py' -exec python -m py_compile {} \;
python -m py_compile socks5.py

# Shell script linting
find camofox-router/ -name '*.sh' -exec shellcheck --shell=sh {} \;
shellcheck --shell=sh camofox-router/files/usr/bin/camofox
shellcheck --shell=sh camofox-router/files/etc/init.d/camofox
```

### Manual Testing

For router changes:
1. Install on a test router
2. Run `camofox test` — all checks should pass
3. Verify the kill switch activates when the proxy is stopped
4. Confirm TTL is set correctly: `camofox status`
5. Test with real traffic to verify no leaks

For iPhone changes:
1. Run the proxy in Pythonista
2. Verify connections from the router succeed
3. Test keepalive functionality
4. Run `diagnostics.py` for a full check

### What NOT to Modify

- `dns/` — This is a bundled third-party library (dnspython). Do not modify or lint it.
- Do not commit carrier-specific credentials or account information.

## Pull Request Process

1. Ensure your code passes all automated checks (CI will verify)
2. Fill out the PR template completely
3. Ensure the PR targets the `main` branch
4. Request review from maintainers
5. Address any review feedback
6. Squash commits if requested

### PR Review Criteria

- [ ] Code follows style guidelines
- [ ] All CI checks pass
- [ ] Changes are tested on real hardware (where applicable)
- [ ] Documentation is updated
- [ ] No secrets or credentials committed
- [ ] Kill switch functionality is preserved
- [ ] Changes don't break existing bypass layers

## Security

If you discover a security vulnerability, **do not** open a public issue. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

## Questions?

Open a [Discussion](https://github.com/ilovekyrinathemost-maker/CamoFox/discussions) or file an issue. We're happy to help new contributors get started.

---

Thank you for helping make CamoFox better! 🦊
