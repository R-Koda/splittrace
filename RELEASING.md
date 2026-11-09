# Publishing splittrace

The PyPI Trusted Publisher is configured for the repository and environment below. Run the workflow manually from main after checking a release.

- PyPI project: `splittrace`
- GitHub owner: `R-Koda`
- GitHub repository: `splittrace`
- Workflow filename: `publish.yml`
- GitHub environment: `pypi`

The workflow is manual-only and restricted to the main branch. The build job tests the installed wheel before passing artifacts to a separate publish job; only the latter has OIDC permission. No long-lived PyPI token is stored.

After a successful upload, verify installation from PyPI in a new virtual environment and check the metadata points to this repository. PyPI versions are immutable: bump the version for subsequent uploads.
