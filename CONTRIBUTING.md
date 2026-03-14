# Contributing to Data Eyes
Thank you for your interest in contributing to Data Eyes! We welcome contributions from the community.

## How to Contribute

### Reporting Bugs
If you find a bug, please open an issue on GitHub with:
- A clear description of the problem
- Steps to reproduce the issue
- Expected vs actual behavior
- Your environment (OS, Python version, SQL Server version)

### Suggesting Enhancements
We welcome feature requests! Please open an issue with:
- A clear description of the proposed feature
- Use cases and benefits
- Any implementation ideas you have

### Pull Requests
1. **Fork the repository** and create your branch from `dev`
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make your changes**
   - Write clear, readable code
   - Follow the existing code style
   - Add tests for new functionality
   - Update documentation as needed

3. **Commit your changes**
   ```bash
   git commit -m "feat: add new feature"
   ```

   We follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` - New features
   - `fix:` - Bug fixes
   - `docs:` - Documentation changes
   - `test:` - Test updates
   - `refactor:` - Code refactoring
   - `chore:` - Maintenance tasks

4. **Push to your fork** and submit a pull request to the `dev` branch
   ```bash
   git push origin feature/my-new-feature
   ```

5. **Wait for review** - A maintainer will review your PR and may request changes

## Testing
- Write tests for new features and bug fixes
- Ensure all tests pass before submitting a PR
- Aim for good test coverage

## Security
- Never commit sensitive data (passwords, API keys, etc.)
- Review the [Security Policy](SECURITY.md) for reporting vulnerabilities
- Follow security best practices in your code

## Questions?
Feel free to open an issue for any questions about contributing!

## License
By contributing, you agree that your contributions will be licensed under the same license as the project (see [LICENSE](LICENSE) file).