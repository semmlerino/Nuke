# Base64 Encoding/Pushing Hook System

This system automatically creates base64-encoded bundles of your application on each git commit and pushes them to a dedicated `encoded-releases` branch for easy deployment.

## Overview

**Workflow:**
1. Developer commits to `master` (or any branch)
2. Post-commit hook automatically creates encoded bundle
3. Background script pushes bundle to `encoded-releases` branch
4. Remote deployment pulls and decodes the bundle

## Files

### Core Scripts
- `bundle_app.py` - Collects application files and creates encoded bundle
- `decode_app.py` - Decodes base64 bundle and extracts files
- `transfer_cli.py` - Low-level CLI for base64 encoding folders
- `transfer_config.json` - Configuration for file inclusion/exclusion patterns

### Git Hooks
- `hooks/post-commit` - Main hook that runs on each commit
- `hooks/push_bundle_background.sh` - Background script for pushing to encoded-releases

## Setup Instructions

### 1. Copy Files to Your Project

```bash
# Copy the Python scripts to your project root
cp bundle_app.py /path/to/your/project/
cp decode_app.py /path/to/your/project/
cp transfer_cli.py /path/to/your/project/
cp transfer_config.json /path/to/your/project/

# Copy hooks to your .git/hooks directory
cp hooks/post-commit /path/to/your/project/.git/hooks/
cp hooks/push_bundle_background.sh /path/to/your/project/.git/hooks/

# Make hooks executable
chmod +x /path/to/your/project/.git/hooks/post-commit
chmod +x /path/to/your/project/.git/hooks/push_bundle_background.sh
```

### 2. Configure File Patterns

Edit `transfer_config.json` to customize which files to include/exclude:

```json
{
  "include_patterns": ["*.py", "*.json", "*.sh"],
  "exclude_patterns": ["test_*.py", "*.log"],
  "exclude_dirs": ["tests", "__pycache__", ".venv"]
}
```

### 3. Create the encoded-releases Branch

```bash
# Create orphan branch (no history from main branch)
git checkout --orphan encoded-releases

# Remove all files
git rm -rf .

# Create initial commit
echo "# Encoded Releases" > README.md
git add README.md
git commit -m "Initialize encoded-releases branch"

# Push to remote
git push -u origin encoded-releases

# Switch back to main branch
git checkout master
```

### 4. Customize Post-Commit Hook

Edit `hooks/post-commit` to match your project:

**Key paths to update:**
- Line 56: Python interpreter path (e.g., `$PROJECT_ROOT/.venv/bin/python3`)
- Lines 58-73: Critical import tests (update to your modules)

### 5. Create Output Directory

The hook creates `.post-commit-output/` for logs. This directory is auto-created but you may want to add it to `.gitignore`:

```bash
echo ".post-commit-output/" >> .gitignore
```

## Usage

### Automatic (On Commit)

After setup, every commit will:
1. Run linting (if `ruff` available)
2. Run type checking (if `basedpyright` available)
3. Test critical imports
4. Create encoded bundle
5. Push to `encoded-releases` branch

### Manual Bundle Creation

```bash
# Create bundle manually
python bundle_app.py -c transfer_config.json

# With verbose output
python bundle_app.py -c transfer_config.json -v

# List files that would be bundled
python bundle_app.py --list-files
```

### Decoding a Bundle

On the remote/deployment machine:

```bash
# Pull latest bundle
git checkout encoded-releases
git pull origin encoded-releases

# Decode and extract
python decode_app.py shotbot_latest.txt

# Extract to specific directory
python decode_app.py shotbot_latest.txt -o /path/to/deploy

# List contents without extracting
python decode_app.py shotbot_latest.txt --list-only
```

## Configuration Reference

### transfer_config.json Options

| Key | Description | Default |
|-----|-------------|---------|
| `include_patterns` | Glob patterns for files to include | `["*.py", "*.json", ...]` |
| `exclude_patterns` | Glob patterns for files to exclude | `["test_*.py", "*.log", ...]` |
| `exclude_dirs` | Directories to skip | `["tests", "__pycache__", ...]` |
| `max_file_size_mb` | Skip files larger than this | `10` |
| `chunk_size_kb` | Chunk size for encoding | `5120` |
| `output_dir` | Local output directory | `"encoded_releases"` |

## Log Files

Check `.post-commit-output/` for:
- `bundle.txt` - Bundle creation log
- `bundle-push.log` - Push to encoded-releases log
- `import-test.txt` - Import validation results
- `type-check.txt` - Type checking results (if enabled)
- `ruff-check.txt` - Linting results (if enabled)

## Troubleshooting

### Bundle Creation Fails

1. Check `.post-commit-output/bundle.txt` for errors
2. Verify `transfer_config.json` is valid JSON
3. Ensure Python environment has required dependencies

### Push Fails

1. Check `.post-commit-output/bundle-push.log`
2. Verify `encoded-releases` branch exists on remote
3. Check git remote permissions

### Import Tests Fail

1. Check `.post-commit-output/import-test.txt`
2. Ensure virtual environment path is correct in hook
3. Verify all dependencies are installed

## Dependencies

The encoding scripts require:
- Python 3.6+
- No external dependencies (uses stdlib only)

Optional tools for code quality checks:
- `ruff` - Linting
- `basedpyright` - Type checking

## Architecture

```
[Commit]
    → [post-commit hook]
        → Run quality checks (optional)
        → Test critical imports
        → Create bundle (bundle_app.py → transfer_cli.py)
        → Copy to encoded_releases/
        → Launch background push (push_bundle_background.sh)
            → Switch to encoded-releases branch
            → Copy bundle from temp
            → Commit with source info
            → Push to remote
            → Switch back to original branch
```

## Security Note

This system is designed for personal/internal deployment where:
- Single trusted user
- Private repositories
- Controlled deployment environments

For public/team use, consider:
- Restricting bundle contents
- Using CI/CD pipelines instead
- Adding authentication for deployment
