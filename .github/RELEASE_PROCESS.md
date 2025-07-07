# Raspberry Ninja Release Process

This document describes the automated release system for Raspberry Ninja.

## Overview

Raspberry Ninja uses an intelligent automated release system that:
- Automatically creates releases when significant files are modified
- Analyzes changes to determine appropriate version bumps (major/minor/patch)
- Generates comprehensive release notes
- Updates the changelog
- Creates GitHub releases with tags

## Automatic Releases

### Trigger Conditions

Releases are automatically triggered when changes are pushed to the `main` branch that modify:
- `publish.py` - The core streaming script
- `*/installer.sh` - Platform installation scripts
- `*.service` - System service files
- `raspberry_pi/Cargo.toml` - Rust configuration

### Version Bump Logic

The system analyzes changes to determine the appropriate version bump:

#### Major Version (X.0.0)
- Breaking changes in `publish.py`
- Protocol or format changes
- Large refactoring (>50 lines removed)
- Commit message contains "breaking" or "!:"

#### Minor Version (0.X.0)
- New features in `publish.py`
- New functions or classes added
- Installation script updates
- Service file changes
- API or streaming changes
- Commit message starts with "feat"

#### Patch Version (0.0.X)
- Bug fixes
- Performance improvements
- Small changes (<30 lines added)
- Configuration updates
- Commit message starts with "fix", contains "perf", or "refactor"

### Skipping Releases

To skip automatic release for a commit, include one of these in your commit message:
- `[skip-release]`
- `[release]` (already a release commit)
- `[auto-enhanced]` (from the commit enhancement system)

## Manual Releases

You can also trigger a release manually through GitHub Actions:

1. Go to Actions → "Manual Release" workflow
2. Click "Run workflow"
3. Select the version bump type (patch/minor/major)
4. Optionally add custom release notes
5. Click "Run workflow"

## Release Contents

Each release includes:

### Version File
- `VERSION` - Contains the current version number (e.g., "1.2.3")

### Changelog Entry
- Automatically added to `CHANGELOG.md`
- Includes release date, version, and changes
- Lists all commits since last release

### GitHub Release
- Created with tag `vX.Y.Z`
- Includes full release notes
- Links to platform-specific installation guides
- Shows recent commits

### Release Notes Format
```markdown
# Release X.Y.Z

**Release Date:** YYYY-MM-DD

## 🚀 Major Release / ✨ Minor Release / 🐛 Patch Release

[Description of changes]

### Core Changes (publish.py)
[If publish.py was modified]

### Commits
- Commit message (hash)
- Commit message (hash)

### Installation
[Links to platform guides]

### ⚠️ Upgrade Notes
[For major versions only]
```

## Best Practices

1. **Commit Messages**: Use conventional commits (feat:, fix:, chore:, etc.) for better automation
2. **Testing**: Ensure changes are tested before pushing to main
3. **Documentation**: Update relevant docs when adding features
4. **Breaking Changes**: Clearly mark breaking changes in commit messages

## Configuration

### Required Secrets
- `GITHUB_TOKEN` - Automatically provided by GitHub Actions
- `COMMIT_ENHANCER_PAT` - Personal Access Token for commit enhancement (optional)

### Files
- `.github/scripts/auto-release.js` - Main release automation script
- `.github/workflows/auto-release.yml` - Automatic release workflow
- `.github/workflows/manual-release.yml` - Manual release workflow
- `VERSION` - Current version number
- `CHANGELOG.md` - Version history

## Troubleshooting

### Release Not Triggering
- Check if the modified files are in the trigger list
- Ensure commit doesn't contain skip keywords
- Verify GitHub Actions are enabled

### Version Bump Incorrect
- Review the commit message format
- Check the analysis logic in `auto-release.js`
- Use manual release for specific version control

### GitHub Release Failed
- Ensure GitHub CLI is available
- Check permissions for the GitHub token
- Verify tag doesn't already exist

## Development

To test the release system locally:
```bash
# Set required environment variables
export GITHUB_TOKEN="your-token"

# Run the release script
node .github/scripts/auto-release.js
```

Note: Some features require GitHub Actions environment and won't work locally.