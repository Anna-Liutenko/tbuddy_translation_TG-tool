# GitHub Code Status Checker

A comprehensive tool for checking GitHub repository status, comparing local and remote repositories, and generating actionable reports. This feature integrates seamlessly with the tbuddy translation tool to provide Git workflow insights.

## Features

- **Local Repository Analysis**: Scan uncommitted changes, staged files, and repository state
- **Remote GitHub Integration**: Compare with remote repository using GitHub API
- **Comprehensive Reporting**: Multiple output formats (summary, detailed, table, JSON)
- **Actionable Recommendations**: Get specific commands to synchronize your repository
- **CLI and API Access**: Use via command line or REST API endpoint
- **Flexible Configuration**: Works with or without GitHub API authentication

## Quick Start

### Prerequisites

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **GitHub Token** (Optional but recommended):
   - Visit [GitHub Settings > Personal Access Tokens](https://github.com/settings/tokens)
   - Create a token with `repo` scope (for private repos) or `public_repo` (for public repos)
   - Set environment variable: `export GITHUB_TOKEN=your_token_here`

### Command Line Usage

#### Basic Status Check
```bash
python git_status_checker.py
```

#### Detailed Status with File Information
```bash
python git_status_checker.py --detailed
```

#### JSON Output for Scripts
```bash
python git_status_checker.py --format json
```

#### Check Specific Repository Path
```bash
python git_status_checker.py --path /path/to/repo
```

#### Show Recommended Actions
```bash
python git_status_checker.py --actions
```

### API Usage

#### Basic Status Check
```bash
GET /status/github
```

#### With Parameters
```bash
GET /status/github?path=/path/to/repo&format=summary&github=true
```

#### Example Response
```json
{
  \"success\": true,\n  \"repository\": {\n    \"name\": \"tbuddy_translation_TG-tool\",\n    \"remote_url\": \"https://github.com/user/repo.git\",\n    \"current_branch\": \"main\"\n  },\n  \"local_status\": {\n    \"uncommitted_changes\": 3,\n    \"staged_files\": 1,\n    \"untracked_files\": 2,\n    \"modified_files\": [\"app.py\", \"requirements.txt\"],\n    \"last_commit\": {\n      \"sha\": \"abc123\",\n      \"message\": \"Update deployment configuration\",\n      \"timestamp\": \"2024-01-15T10:30:00Z\",\n      \"author\": \"Developer Name\"\n    }\n  },\n  \"remote_status\": {\n    \"latest_commit\": {\n      \"sha\": \"def456\",\n      \"message\": \"Fix authentication bug\",\n      \"timestamp\": \"2024-01-15T09:15:00Z\",\n      \"author\": \"Another Developer\"\n    },\n    \"ahead_count\": 2,\n    \"behind_count\": 1\n  },\n  \"sync_status\": {\n    \"is_synchronized\": false,\n    \"needs_pull\": true,\n    \"needs_push\": true,\n    \"status_text\": \"Diverged: 2 ahead, 1 behind\",\n    \"has_local_changes\": true,\n    \"recommendations\": [\n      \"Commit local changes\",\n      \"Pull latest changes from remote (after committing)\",\n      \"Push commits to remote repository\",\n      \"Consider rebasing before pushing\"\n    ]\n  },\n  \"timestamp\": \"2024-01-15T10:45:00Z\"\n}\n```\n\n## Configuration\n\n### Environment Variables\n\n| Variable | Description | Required | Default |\n|----------|-------------|----------|---------|\n| `GITHUB_TOKEN` | GitHub Personal Access Token | No | None |\n| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | No | INFO |\n\n### GitHub Token Setup\n\n1. **Create Token**:\n   - Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)\n   - Click \"Generate new token (classic)\"\n   - Select scopes:\n     - `public_repo` for public repositories only\n     - `repo` for private repositories access\n\n2. **Set Environment Variable**:\n   ```bash\n   # Linux/macOS\n   export GITHUB_TOKEN=your_token_here\n   \n   # Windows PowerShell\n   $env:GITHUB_TOKEN=\"your_token_here\"\n   \n   # Windows Command Prompt\n   set GITHUB_TOKEN=your_token_here\n   ```\n\n3. **Add to .env file**:\n   ```bash\n   GITHUB_TOKEN=your_token_here\n   ```\n\n## Command Line Options\n\n### Required Arguments\nNone - all arguments are optional.\n\n### Optional Arguments\n\n| Option | Short | Description | Default |\n|--------|-------|-------------|----------|\n| `--path` | `-p` | Path to git repository | Current directory (`.`) |\n| `--format` | `-f` | Output format: `summary`, `detailed`, `table`, `json` | `summary` |\n| `--branch` | `-b` | Specific branch to check | Current branch |\n| `--detailed` | | Show detailed file-by-file information | False |\n| `--remote-only` | | Check only remote status without local comparison | False |\n| `--no-github` | | Skip GitHub API calls (local git only) | False |\n| `--actions` | | Show recommended actions | False |\n| `--github-token` | | GitHub API token (overrides environment) | None |\n| `--verbose` | `-v` | Enable verbose logging | False |\n| `--version` | | Show version information | |\n| `--help` | `-h` | Show help message | |\n\n### Output Formats\n\n#### Summary Format (Default)\n```\n📁 Repository: tbuddy_translation_TG-tool\n🌿 Branch: main\n⚠️  Status: Diverged: 2 ahead, 1 behind\n📝 Local changes: 3 files\n   • 1 staged\n   • 2 modified\n   • 0 untracked\n🔄 Remote comparison:\n   • 2 commits ahead\n   • 1 commits behind\n💾 Last local commit: abc123 - Update deployment configuration\n🌐 Last remote commit: def456 - Fix authentication bug\n\n💡 Recommended actions:\n   • Commit local changes\n   • Pull latest changes from remote (after committing)\n   • Push commits to remote repository\n   • Consider rebasing before pushing\n```\n\n#### Table Format\n```\n+-------------------+--------------------------------+\n| Repository        | tbuddy_translation_TG-tool     |\n| Branch            | main                           |\n| Status            | Diverged: 2 ahead, 1 behind   |\n| Local Changes     | 3 files                        |\n| Staged Files      | 1                              |\n| Modified Files    | 2                              |\n| Untracked Files   | 0                              |\n| Ahead by          | 2 commits                      |\n| Behind by         | 1 commits                      |\n| Synchronized      | ❌                              |\n+-------------------+--------------------------------+\n```\n\n#### JSON Format\nStructured JSON output suitable for programmatic processing (see API example above).\n\n## API Endpoints\n\n### GET /status/github\n\nReturns comprehensive GitHub repository status information.\n\n#### Query Parameters\n\n| Parameter | Type | Description | Default |\n|-----------|------|-------------|----------|\n| `path` | string | Repository path | Current directory |\n| `format` | string | Response format: `json`, `summary`, `table`, `actions` | `json` |\n| `github` | boolean | Include GitHub API data | `true` |\n\n#### Request Headers\n\n| Header | Description | Required |\n|--------|-------------|----------|\n| `X-GitHub-Token` | GitHub API token | No (uses environment variable if not provided) |\n\n#### Response Codes\n\n| Code | Description |\n|------|-------------|\n| 200 | Success |\n| 400 | Bad request (invalid repository path, etc.) |\n| 500 | Server error |\n\n#### Error Response Format\n```json\n{\n  \"success\": false,\n  \"error\": \"Error message description\",\n  \"timestamp\": \"2024-01-15T10:45:00Z\"\n}\n```\n\n## Use Cases\n\n### Daily Development Workflow\n```bash\n# Quick status check\npython git_status_checker.py\n\n# Before pushing changes\npython git_status_checker.py --actions\n\n# Check if pull is needed\npython git_status_checker.py --format json | jq '.sync_status.needs_pull'\n```\n\n### CI/CD Integration\n```bash\n# Check if repository is clean before deployment\nif python git_status_checker.py --format json | jq -e '.sync_status.is_synchronized and (.local_status.uncommitted_changes == 0)'; then\n    echo \"Repository is clean, proceeding with deployment\"\nelse\n    echo \"Repository has uncommitted changes or is not synchronized\"\n    exit 1\nfi\n```\n\n### Monitoring Script\n```python\nimport requests\nimport json\n\nresponse = requests.get('http://localhost:8080/status/github')\nstatus = response.json()\n\nif not status['sync_status']['is_synchronized']:\n    print(f\"⚠️ Repository not synchronized: {status['sync_status']['status_text']}\")\n    for recommendation in status['sync_status']['recommendations']:\n        print(f\"  • {recommendation}\")\n```\n\n## Troubleshooting\n\n### Common Issues\n\n#### \"Not a git repository\"\n**Cause**: Running the command outside a git repository.\n**Solution**: Navigate to a git repository directory or specify path with `--path`.\n\n#### \"GitHub API rate limit exceeded\"\n**Cause**: Too many API requests without authentication.\n**Solution**: Set up a GitHub token to increase rate limits.\n\n#### \"Remote connection failed\"\n**Cause**: Network issues or invalid remote URL.\n**Solution**: Check internet connection and verify remote URL with `git remote -v`.\n\n#### \"Permission denied\" for GitHub API\n**Cause**: Invalid or expired GitHub token, or insufficient permissions.\n**Solution**: \n- Verify token is correct\n- Ensure token has appropriate scopes (`repo` or `public_repo`)\n- Check if token has expired\n\n### Debug Mode\n\nEnable verbose logging for troubleshooting:\n```bash\npython git_status_checker.py --verbose\n```\n\nOr set environment variable:\n```bash\nexport LOG_LEVEL=DEBUG\npython git_status_checker.py\n```\n\n### API Debugging\n\nTest API endpoint:\n```bash\n# Basic test\ncurl -X GET \"http://localhost:8080/status/github\"\n\n# With authentication\ncurl -X GET \"http://localhost:8080/status/github\" \\\n     -H \"X-GitHub-Token: your_token_here\"\n\n# With parameters\ncurl -X GET \"http://localhost:8080/status/github?format=summary&github=true\"\n```\n\n## Architecture\n\n### Components\n\n1. **Models** (`models.py`): Data structures for repository status and file changes\n2. **Git Analyzer** (`git_analyzer.py`): Local git repository analysis\n3. **GitHub Client** (`github_client.py`): GitHub API integration\n4. **Status Reporter** (`status_reporter.py`): Report generation and formatting\n5. **CLI Interface** (`git_status_checker.py`): Command-line interface\n6. **Flask Integration** (`app.py`): REST API endpoint\n\n### Data Flow\n\n```\n[CLI Input] → [Status Reporter] → [Git Analyzer] → [Local Git Status]\n                     ↓\n[GitHub Client] → [GitHub API] → [Remote Status]\n                     ↓\n[Report Generation] → [Output Formatting] → [User Output]\n```\n\n### Security Considerations\n\n1. **Token Security**: GitHub tokens are sensitive and should be stored securely\n2. **Environment Variables**: Use environment variables instead of hardcoding tokens\n3. **API Rate Limits**: Respect GitHub API rate limits to avoid blocking\n4. **Repository Access**: Ensure tokens have minimal required permissions\n\n## Development\n\n### Running Tests\n\n```bash\n# Run all tests\npython -m pytest tests/test_git_status_checker.py -v\n\n# Run specific test class\npython -m pytest tests/test_git_status_checker.py::TestModels -v\n\n# Run with coverage\npython -m pytest tests/test_git_status_checker.py --cov=. --cov-report=html\n```\n\n### Contributing\n\n1. **Code Style**: Follow PEP 8 guidelines\n2. **Testing**: Add tests for new functionality\n3. **Documentation**: Update this README for new features\n4. **Error Handling**: Include proper error handling and logging\n\n### Adding New Features\n\n1. **Extend Models**: Add new data structures in `models.py`\n2. **Update Analyzer**: Enhance git analysis in `git_analyzer.py`\n3. **Enhance Client**: Add GitHub API functionality in `github_client.py`\n4. **Improve Reporting**: Add new output formats in `status_reporter.py`\n5. **Update CLI**: Add command-line options in `git_status_checker.py`\n6. **Extend API**: Add new endpoints or parameters in `app.py`\n\n## Performance\n\n### Optimization Tips\n\n1. **Token Usage**: Use GitHub tokens to avoid rate limiting\n2. **Caching**: Consider caching GitHub API responses for frequently accessed repositories\n3. **Async Operations**: For multiple repositories, consider async processing\n4. **Minimal Scopes**: Use minimal GitHub token scopes for security\n\n### Rate Limits\n\n| Authentication | Requests per hour |\n|----------------|-------------------|\n| No token | 60 |\n| With token | 5,000 |\n\n## License\n\nThis feature is part of the tbuddy translation tool and follows the same license terms.\n\n## Support\n\nFor issues and questions:\n1. Check this documentation\n2. Review the troubleshooting section\n3. Enable debug logging for more details\n4. Check GitHub API status at [status.github.com](https://status.github.com/)\n\n---\n\n*Last updated: January 2024*"