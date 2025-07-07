const { exec } = require('child_process');
const fs = require('fs').promises;
const path = require('path');
const crypto = require('crypto');

// Configuration
const VERSION_FILE = 'VERSION';
const CHANGELOG_FILE = 'CHANGELOG.md';

// Logging utility
function log(level, message, context = {}) {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${message}`, context);
}

// Run shell command utility with proper escaping
async function runCommand(command, options = {}) {
  log('debug', `Running command: ${command}`);
  return new Promise((resolve, reject) => {
    // Use shell: false when possible for security
    const execOptions = {
      maxBuffer: 10 * 1024 * 1024,
      ...options
    };
    
    exec(command, execOptions, (error, stdout, stderr) => {
      if (error) {
        log('error', `Command failed: ${command}`, { error: error.message, stderr });
        reject(new Error(`Command failed: ${command}\n${stderr}`));
        return;
      }
      if (stderr && !stderr.includes('warning')) {
        log('warn', `Command stderr: ${command}`, { stderr });
      }
      resolve(stdout.trim());
    });
  });
}

// Escape shell arguments
function escapeShellArg(arg) {
  return `'${arg.replace(/'/g, "'\\''")}'`;
}

// Parse semantic version
function parseVersion(version) {
  const match = version.match(/^v?(\d+)\.(\d+)\.(\d+)(-(.+))?(\+(.+))?$/);
  if (!match) {
    throw new Error(`Invalid version format: ${version}`);
  }
  return {
    major: parseInt(match[1]),
    minor: parseInt(match[2]),
    patch: parseInt(match[3]),
    prerelease: match[5] || null,
    build: match[7] || null,
    full: version
  };
}

// Compare semantic versions
function compareVersions(v1, v2) {
  const ver1 = typeof v1 === 'string' ? parseVersion(v1) : v1;
  const ver2 = typeof v2 === 'string' ? parseVersion(v2) : v2;
  
  if (ver1.major !== ver2.major) return ver1.major - ver2.major;
  if (ver1.minor !== ver2.minor) return ver1.minor - ver2.minor;
  if (ver1.patch !== ver2.patch) return ver1.patch - ver2.patch;
  
  // Pre-release versions have lower precedence
  if (ver1.prerelease && !ver2.prerelease) return -1;
  if (!ver1.prerelease && ver2.prerelease) return 1;
  
  return 0;
}

// Format version string
function formatVersion(major, minor, patch, prerelease = null) {
  let version = `${major}.${minor}.${patch}`;
  if (prerelease) {
    version += `-${prerelease}`;
  }
  return version;
}

// Get current version from VERSION file or git tags
async function getCurrentVersion() {
  try {
    // First try to read VERSION file
    const versionContent = await fs.readFile(VERSION_FILE, 'utf8');
    return versionContent.trim();
  } catch (error) {
    log('info', 'VERSION file not found, checking git tags...');
    
    // Fallback to git tags
    try {
      const tags = await runCommand('git tag -l "v*" --sort=-v:refname');
      if (tags) {
        const latestTag = tags.split('\n')[0];
        return latestTag.replace(/^v/, '');
      }
    } catch (gitError) {
      log('warn', 'No git tags found');
    }
    
    // Default to 0.0.0 if no version found
    log('info', 'No existing version found, starting at 0.0.0');
    return '0.0.0';
  }
}

// Analyze changes to determine version bump type
async function analyzeChanges(lastCommitSha) {
  log('info', 'Analyzing changes to determine version bump...');
  
  try {
    // Get the diff for the last commit
    const changedFiles = await runCommand(`git show --name-status --oneline ${lastCommitSha}`);
    const commitMessage = await runCommand(`git log -1 --pretty=%B ${lastCommitSha}`);
    
    // Check what files were changed
    const hasPublishPyChanges = changedFiles.includes('publish.py');
    const hasInstallerChanges = changedFiles.match(/installer\.sh|setup.*\.sh/);
    const hasServiceChanges = changedFiles.includes('.service');
    const hasDocChanges = changedFiles.match(/README|\.md$/);
    const hasConfigChanges = changedFiles.match(/\.yml|\.yaml|\.json|\.toml/);
    
    // Check commit message for keywords
    const commitLower = commitMessage.toLowerCase();
    const isBreaking = commitLower.includes('breaking') || commitLower.includes('!:');
    const isFeat = commitLower.startsWith('feat') || commitLower.includes('feature');
    const isFix = commitLower.startsWith('fix');
    const isPerf = commitLower.includes('perf') || commitLower.includes('performance');
    const isRefactor = commitLower.includes('refactor');
    
    // Get detailed diff for publish.py if it changed
    let publishPyAnalysis = { major: false, minor: false, patch: false };
    if (hasPublishPyChanges) {
      try {
        const diff = await runCommand(`git show ${lastCommitSha} -- publish.py`);
        
        // Analyze the nature of changes in publish.py
        const addedLines = (diff.match(/^\+[^+]/gm) || []).length;
        const removedLines = (diff.match(/^-[^-]/gm) || []).length;
        const hasNewFunctions = diff.match(/^\+def\s+\w+/m);
        const hasNewClasses = diff.match(/^\+class\s+\w+/m);
        const hasApiChanges = diff.match(/websocket|rtmp|stream|publish|connect/i);
        const hasProtocolChanges = diff.match(/protocol|format|codec|encoding/i);
        
        // Determine impact
        if (isBreaking || hasProtocolChanges || removedLines > 50) {
          publishPyAnalysis.major = true;
        } else if (hasNewFunctions || hasNewClasses || hasApiChanges || addedLines > 30) {
          publishPyAnalysis.minor = true;
        } else {
          publishPyAnalysis.patch = true;
        }
        
        log('info', 'publish.py analysis', {
          addedLines,
          removedLines,
          hasNewFunctions: !!hasNewFunctions,
          hasNewClasses: !!hasNewClasses,
          hasApiChanges: !!hasApiChanges,
          hasProtocolChanges: !!hasProtocolChanges
        });
      } catch (error) {
        log('warn', 'Could not analyze publish.py diff in detail', { error: error.message });
        publishPyAnalysis.minor = true; // Default to minor for publish.py changes
      }
    }
    
    // Determine version bump
    let bumpType = 'patch'; // Default
    
    if (isBreaking || publishPyAnalysis.major) {
      bumpType = 'major';
    } else if (isFeat || publishPyAnalysis.minor || hasInstallerChanges || hasServiceChanges) {
      bumpType = 'minor';
    } else if (isFix || isPerf || isRefactor || publishPyAnalysis.patch || hasConfigChanges) {
      bumpType = 'patch';
    } else if (hasDocChanges && !hasPublishPyChanges) {
      bumpType = 'none'; // Don't bump for docs-only changes
    }
    
    log('info', 'Version bump analysis complete', {
      bumpType,
      hasPublishPyChanges,
      commitType: commitLower.split(':')[0],
      isBreaking
    });
    
    return {
      bumpType,
      hasPublishPyChanges,
      commitMessage,
      changedFiles
    };
  } catch (error) {
    log('error', 'Error analyzing changes', { error: error.message });
    throw error;
  }
}

// Generate release notes
async function generateReleaseNotes(currentVersion, newVersion, lastCommitSha, analysis) {
  log('info', 'Generating release notes...');
  
  try {
    // Get recent commits since last tag/version
    let commitsSinceLastRelease = '';
    try {
      const lastTag = await runCommand('git describe --tags --abbrev=0 HEAD~1 2>/dev/null || echo ""');
      if (lastTag) {
        commitsSinceLastRelease = await runCommand(`git log ${lastTag}..HEAD --pretty=format:"- %s (%h)" --no-merges`);
      } else {
        // If no previous tag, get last 10 commits
        commitsSinceLastRelease = await runCommand('git log -10 --pretty=format:"- %s (%h)" --no-merges');
      }
    } catch (error) {
      log('warn', 'Could not get commits for release notes', { error: error.message });
    }
    
    // Build release notes
    const releaseDate = new Date().toISOString().split('T')[0];
    let releaseNotes = `# Release ${newVersion}\n\n`;
    releaseNotes += `**Release Date:** ${releaseDate}\n\n`;
    
    // Add summary based on bump type
    if (analysis.bumpType === 'major') {
      releaseNotes += `## 🚀 Major Release\n\n`;
      releaseNotes += `This release includes breaking changes or significant new features.\n\n`;
    } else if (analysis.bumpType === 'minor') {
      releaseNotes += `## ✨ Minor Release\n\n`;
      releaseNotes += `This release includes new features and improvements.\n\n`;
    } else {
      releaseNotes += `## 🐛 Patch Release\n\n`;
      releaseNotes += `This release includes bug fixes and minor improvements.\n\n`;
    }
    
    // Add specific changes for publish.py
    if (analysis.hasPublishPyChanges) {
      releaseNotes += `### Core Changes (publish.py)\n\n`;
      releaseNotes += `The main streaming script has been updated. `;
      
      if (analysis.bumpType === 'major') {
        releaseNotes += `This includes significant changes that may affect compatibility.\n\n`;
      } else if (analysis.bumpType === 'minor') {
        releaseNotes += `New features or improvements have been added.\n\n`;
      } else {
        releaseNotes += `Bug fixes or minor improvements have been applied.\n\n`;
      }
    }
    
    // Add commit list
    if (commitsSinceLastRelease) {
      releaseNotes += `### Commits\n\n`;
      releaseNotes += commitsSinceLastRelease + '\n\n';
    }
    
    // Add installation reminder
    releaseNotes += `### Installation\n\n`;
    releaseNotes += `For installation instructions, please refer to the platform-specific guides:\n`;
    releaseNotes += `- [Raspberry Pi](./raspberry_pi/README.md)\n`;
    releaseNotes += `- [NVIDIA Jetson](./nvidia_jetson/README.md)\n`;
    releaseNotes += `- [Orange Pi](./orangepi/README.md)\n`;
    releaseNotes += `- [Ubuntu](./ubuntu/README.md)\n\n`;
    
    // Add upgrade notes if major version
    if (analysis.bumpType === 'major') {
      releaseNotes += `### ⚠️ Upgrade Notes\n\n`;
      releaseNotes += `This is a major version upgrade. Please review the changes carefully before updating.\n`;
      releaseNotes += `It's recommended to backup your configuration before upgrading.\n\n`;
    }
    
    return releaseNotes;
  } catch (error) {
    log('error', 'Error generating release notes', { error: error.message });
    throw error;
  }
}

// Update CHANGELOG.md
async function updateChangelog(releaseNotes) {
  log('info', 'Updating CHANGELOG.md...');
  
  try {
    let existingChangelog = '';
    try {
      existingChangelog = await fs.readFile(CHANGELOG_FILE, 'utf8');
    } catch (error) {
      log('info', 'CHANGELOG.md not found, creating new one');
      existingChangelog = '# Changelog\n\nAll notable changes to Raspberry Ninja will be documented in this file.\n\n';
    }
    
    // Insert new release notes after the header
    const headerMatch = existingChangelog.match(/^#\s+Changelog.*?\n+/m);
    if (headerMatch) {
      const insertPosition = headerMatch.index + headerMatch[0].length;
      const updatedChangelog = 
        existingChangelog.slice(0, insertPosition) +
        releaseNotes + '\n---\n\n' +
        existingChangelog.slice(insertPosition);
      
      await fs.writeFile(CHANGELOG_FILE, updatedChangelog);
      log('info', 'CHANGELOG.md updated successfully');
    } else {
      // No header found, prepend
      await fs.writeFile(CHANGELOG_FILE, existingChangelog + '\n\n' + releaseNotes);
      log('info', 'CHANGELOG.md updated (appended)');
    }
  } catch (error) {
    log('error', 'Error updating CHANGELOG.md', { error: error.message });
    throw error;
  }
}

// Create GitHub release
async function createGitHubRelease(version, releaseNotes) {
  log('info', `Creating GitHub release for v${version}...`);
  
  const tagName = `v${version}`;
  
  try {
    // Create and push tag
    await runCommand(`git tag -a ${tagName} -m "Release ${version}"`);
    await runCommand(`git push origin ${tagName}`);
    
    // Create release using GitHub CLI if available
    try {
      await runCommand('gh --version');
      
      // Write release notes to temp file
      const tempFile = `.release-notes-${Date.now()}.tmp`;
      await fs.writeFile(tempFile, releaseNotes);
      
      // Create release
      await runCommand(`gh release create ${tagName} --title "Release ${version}" --notes-file ${tempFile}`);
      
      // Cleanup
      await fs.unlink(tempFile);
      
      log('info', `GitHub release created successfully: ${tagName}`);
    } catch (ghError) {
      log('warn', 'GitHub CLI not available, tag pushed but release must be created manually', { error: ghError.message });
    }
  } catch (error) {
    log('error', 'Error creating GitHub release', { error: error.message });
    throw error;
  }
}

// Main function
async function main() {
  log('info', 'Starting auto-release process...');
  
  try {
    // Get last commit info
    const lastCommitSha = await runCommand('git log -1 --pretty=%H');
    const lastCommitMessage = await runCommand('git log -1 --pretty=%B');
    
    // Skip if commit is already a release commit
    if (lastCommitMessage.includes('[release]') || lastCommitMessage.includes('[skip-release]')) {
      log('info', 'Skipping release for release-related commit');
      process.exit(0);
    }
    
    // Analyze changes
    const analysis = await analyzeChanges(lastCommitSha);
    
    if (analysis.bumpType === 'none') {
      log('info', 'No version bump needed for this commit');
      process.exit(0);
    }
    
    // Get current version
    const currentVersion = await getCurrentVersion();
    const version = parseVersion(currentVersion);
    
    // Calculate new version
    let newMajor = version.major;
    let newMinor = version.minor;
    let newPatch = version.patch;
    
    switch (analysis.bumpType) {
      case 'major':
        newMajor++;
        newMinor = 0;
        newPatch = 0;
        break;
      case 'minor':
        newMinor++;
        newPatch = 0;
        break;
      case 'patch':
        newPatch++;
        break;
    }
    
    const newVersion = formatVersion(newMajor, newMinor, newPatch);
    log('info', `Version bump: ${currentVersion} → ${newVersion} (${analysis.bumpType})`);
    
    // Validate version is actually higher
    if (compareVersions(newVersion, currentVersion) <= 0) {
      log('error', `New version ${newVersion} is not higher than current version ${currentVersion}`);
      throw new Error('Version validation failed: new version must be higher than current version');
    }
    
    // Update VERSION file
    await fs.writeFile(VERSION_FILE, newVersion);
    log('info', 'VERSION file updated');
    
    // Generate release notes
    const releaseNotes = await generateReleaseNotes(currentVersion, newVersion, lastCommitSha, analysis);
    
    // Update CHANGELOG
    await updateChangelog(releaseNotes);
    
    // Commit version bump and changelog
    await runCommand('git add VERSION CHANGELOG.md');
    await runCommand(`git commit -m "chore: release v${newVersion} [release]"`);
    await runCommand('git push');
    
    // Create GitHub release
    await createGitHubRelease(newVersion, releaseNotes);
    
    log('info', `Release v${newVersion} completed successfully!`);
    process.exit(0);
  } catch (error) {
    log('error', 'Auto-release failed', { error: error.message, stack: error.stack });
    process.exit(1);
  }
}

// Run main function
main().catch(error => {
  log('error', 'Unhandled error in main', { error: error.message, stack: error.stack });
  process.exit(1);
});