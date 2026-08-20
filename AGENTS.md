# AGENTS.md

Instructions for AI coding agents working with this repository.

## Repository Overview

<!-- TODO: Update with repository-specific description -->

This is a LetsMOD repository. Update this section with specific details about
what this repository contains and its purpose.

## Directory Structure

<!-- TODO: Update with actual directory structure -->

```plaintext
src/              # Source code
tests/            # Test files
docs/             # Documentation
```

## Development Guidelines

### Code Style

- Follow existing patterns in the codebase
- Use consistent naming conventions
- Keep code organized and readable
- Add comments only where logic is not self-evident
- Do not add unnecessary complexity

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

- `feat:` - New features
- `fix:` - Bugfixes
- `refactor:` - Code changes that neither fix bugs nor add features
- `docs:` - Documentation changes
- `style:` - Formatting, linting fixes (no code change)
- `test:` - Adding or modifying tests
- `ci:` - CI/CD configuration changes
- `chore:` - Maintenance tasks

### Pull Requests

- Create feature branches from `develop`
- Use descriptive PR titles following Conventional Commits format
- Reference Linear tickets in PR titles: `feat: description (PROJ-xxx)`
- Keep PRs focused and reasonably sized
- Ensure CI checks pass before requesting review

## Development Commands

<!-- TODO: Update with actual commands for this repository -->

```shell
# Install dependencies
npm install

# Run tests
npm test

# Build
npm run build

# Lint
npm run lint
```

## Testing Guidelines

- Write tests for new functionality
- Maintain existing test coverage
- Run tests before committing

## Security Guidelines

- Never commit secrets, credentials, or API keys
- Use environment variables for sensitive configuration
- Follow principle of least privilege
- Report security issues privately

## Additional Resources

<!-- TODO: Add links to relevant documentation, wikis, or external resources -->

- [LetsMOD Documentation](https://docs.letsmod.com)
- [Linear](https://linear.app/letsmod)
