# CLAUDE.md

Instructions for Claude Code when working with this repository.

> **Important:** Also read [AGENTS.md](AGENTS.md) for general AI agent
> instructions that apply to all AI coding tools, including development
> commands, code style, and commit message conventions.

## Claude-Specific Behavior

### Tool Usage Preferences

- Use Glob and Grep tools for file searches instead of shell commands
- Use Read tool instead of `cat`, `head`, or `tail`
- Use Edit tool for file modifications instead of `sed` or `awk`
- Prefer parallel tool calls when operations are independent

## Project-Specific Instructions

<!-- TODO: Add project-specific Claude instructions below -->

### Quick Reference

<!-- TODO: Add quick reference information for this specific project -->

- Key patterns and conventions
- Important file locations
- Common operations

### Code Generation Guidelines

<!-- TODO: Add code generation guidelines specific to this project -->

When creating new code in this repository:

1. Follow existing patterns in the same directory
2. Add resources to existing files rather than creating new ones
3. Keep implementations simple and focused

## Important Notes

- Use Conventional Commit format for commit messages
- Markdown lists must be separated from headings by empty line
- Use `shell` code fence language for shell scripts in Markdown
- Never commit sensitive data or API keys
