#!/bin/bash
set -e  # Exit on error

echo "🔄 Starting dependency update process..."
echo ""

# Step 1: Upgrade lock file
echo "📦 Step 1/5: Upgrading uv.lock with latest versions..."
uv lock --upgrade
echo "✅ Lock file updated"
echo ""

# Step 2: Sync dependencies
echo "📥 Step 2/5: Installing updated dependencies..."
uv sync --all-extras
echo "✅ Dependencies installed"
echo ""

# Step 3: Update pyproject.toml
echo "✏️  Step 3/5: Updating pyproject.toml with current versions..."
uv run --with tomli --with tomli-w python3 - << 'PYTHON_SCRIPT'
import tomli
import tomli_w
import re

# Read current pyproject.toml
with open('pyproject.toml', 'rb') as f:
    pyproject = tomli.load(f)

# Read uv.lock to get current versions
with open('uv.lock', 'r') as f:
    lock_content = f.read()

# Extract package versions from lock file
def get_version_from_lock(package_name):
    pattern = rf'name = "{package_name}"\nversion = "([^"]+)"'
    match = re.search(pattern, lock_content)
    return match.group(1) if match else None

# Update dependencies
updated_deps = []
for dep in pyproject['project']['dependencies']:
    # Extract package name (handle extras and version specs)
    pkg_match = re.match(r'^([a-zA-Z0-9_-]+)(?:\[([^\]]+)\])?', dep)
    if pkg_match:
        pkg_name = pkg_match.group(1)
        extras = pkg_match.group(2)
        
        version = get_version_from_lock(pkg_name)
        if version:
            # Keep extras if present
            if extras:
                updated_deps.append(f"{pkg_name}[{extras}]>={version}")
            else:
                updated_deps.append(f"{pkg_name}>={version}")
        else:
            updated_deps.append(dep)
    else:
        updated_deps.append(dep)

# Sort for consistency
pyproject['project']['dependencies'] = sorted(updated_deps)

# Update test dependencies
if 'test' in pyproject['project'].get('optional-dependencies', {}):
    updated_test_deps = []
    for dep in pyproject['project']['optional-dependencies']['test']:
        pkg_match = re.match(r'^([a-zA-Z0-9_-]+)(?:\[([^\]]+)\])?', dep)
        if pkg_match:
            pkg_name = pkg_match.group(1)
            extras = pkg_match.group(2)
            
            version = get_version_from_lock(pkg_name)
            if version:
                if extras:
                    updated_test_deps.append(f"{pkg_name}[{extras}]>={version}")
                else:
                    updated_test_deps.append(f"{pkg_name}>={version}")
            else:
                updated_test_deps.append(dep)
        else:
            updated_test_deps.append(dep)
    
    pyproject['project']['optional-dependencies']['test'] = sorted(updated_test_deps)

# Update dev dependencies
if 'dev' in pyproject['project'].get('optional-dependencies', {}):
    updated_dev_deps = []
    for dep in pyproject['project']['optional-dependencies']['dev']:
        pkg_match = re.match(r'^([a-zA-Z0-9_-]+)(?:\[([^\]]+)\])?', dep)
        if pkg_match:
            pkg_name = pkg_match.group(1)
            extras = pkg_match.group(2)
            
            version = get_version_from_lock(pkg_name)
            if version:
                if extras:
                    updated_dev_deps.append(f"{pkg_name}[{extras}]>={version}")
                else:
                    updated_dev_deps.append(f"{pkg_name}>={version}")
            else:
                updated_dev_deps.append(dep)
        else:
            updated_dev_deps.append(dep)
    
    pyproject['project']['optional-dependencies']['dev'] = sorted(updated_dev_deps)

# Write back
with open('pyproject.toml', 'wb') as f:
    tomli_w.dump(pyproject, f)

print("✅ Updated pyproject.toml with current versions")
PYTHON_SCRIPT
echo ""

# Step 4: Show summary
echo "📊 Step 4/4: Generating update summary..."
echo ""
echo "═══════════════════════════════════════════════════════"
echo "                  UPDATE SUMMARY                        "
echo "═══════════════════════════════════════════════════════"

# Show git diff of changed versions
if command -v git &> /dev/null; then
    if git diff --quiet pyproject.toml 2>/dev/null; then
        echo "ℹ️  No version changes in pyproject.toml"
    else
        echo ""
        echo "📝 Changed versions in pyproject.toml:"
        echo ""
        git diff pyproject.toml | grep -E "^\+.*>=" | sed 's/^+/  ✅ /' || echo "  (none)"
    fi
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo ""
echo "🎉 Dependency update complete!"
echo ""
echo "Next steps:"
echo "  1. Review changes: git diff pyproject.toml uv.lock"
echo "  2. Commit changes: git add pyproject.toml uv.lock"
echo "  3. Push to remote: git commit -m 'chore: update dependencies' && git push"
echo ""
