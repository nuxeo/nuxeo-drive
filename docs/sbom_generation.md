# SBOM Generation

How to generate a Software Bill of Materials (SBOM) for Nuxeo Drive locally, covering
only the dependencies that are actually shipped to end users.

Nuxeo Drive is distributed as a **desktop application**, so the relevant approval column
is _"Including in Hyland's Products and Deliverables"_. See
[Approved open source licenses](#approved-open-source-licenses) below.

## Scope: shipped dependencies only

`tools/deps/requirements.txt` is generated with `pip-compile`, so it already contains the
**complete runtime closure** (direct dependencies *and* their transitive dependencies).
That file alone defines what ships.

Everything else is out of scope and must not be reported:

| File | Contents | In the SBOM? |
| --- | --- | --- |
| `tools/deps/requirements.txt` | Application runtime modules | **Yes** |
| `tools/deps/requirements-pip.txt` | `pip`, `setuptools`, `wheel`, build backends | No |
| `tools/deps/requirements-tests.txt` | `pytest`, `black`, `flake8`, `mypy`, … | No |
| `tools/deps/requirements-tox.txt` | `tox` and its dependencies | No |
| `tools/deps/requirements-dev.txt` | Developer conveniences | No |
| `tools/deps/requirements-bench.txt` | Benchmark tooling | No |

Scanning a `tox` environment or a full development virtualenv pulls in build and test
packages, which inflates the report with components that are never distributed.

## 1. Install Syft

[Syft](https://github.com/anchore/syft) is the SBOM generator.

### macOS

    brew install syft

### GNU/Linux

    curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

### Windows (PowerShell)

    winget install Anchore.Syft

Verify the installation:

    syft version

## 2. Create a runtime-only virtual environment

Install **only** `tools/deps/requirements.txt` into a dedicated, empty environment. Do not
reuse `.tox/` or an existing development virtualenv.

### GNU/Linux, macOS

    python3 -m venv /tmp/nxdrive-sbom
    /tmp/nxdrive-sbom/bin/python -m pip install --upgrade pip
    /tmp/nxdrive-sbom/bin/python -m pip install -r tools/deps/requirements.txt

### Windows (PowerShell)

    python -m venv $env:TEMP\nxdrive-sbom
    & $env:TEMP\nxdrive-sbom\Scripts\python.exe -m pip install --upgrade pip
    & $env:TEMP\nxdrive-sbom\Scripts\python.exe -m pip install -r tools\deps\requirements.txt

> **Note**
> `requirements.txt` contains platform-specific modules: `pywin32` (Windows only) and
> `distro` (GNU/Linux only). A single machine can therefore never produce a complete
> SBOM. Generate one SBOM per target platform, or state the scanned platform in the
> report.

## 3. Generate the SBOM

Point Syft at the environment's `site-packages`, not at the repository root. Package
metadata (`*.dist-info/METADATA`) lives there, and it is what carries the license
information.

`--enrich python` lets Syft query PyPI for licenses that are missing from the local
metadata. It requires network access; drop the flag when working offline, at the cost of
more unresolved licenses.

### GNU/Linux, macOS

    syft scan dir:/tmp/nxdrive-sbom/lib/python3.13/site-packages \
        --enrich python \
        --source-name nuxeo-drive \
        --source-version "$(git describe --tags --always)" \
        -o spdx-json=sbom.spdx.json \
        -o spdx-tag-value=sbom.spdx.txt

### Windows (PowerShell)

    syft scan dir:$env:TEMP\nxdrive-sbom\Lib\site-packages `
        --enrich python `
        --source-name nuxeo-drive `
        --source-version (git describe --tags --always) `
        -o spdx-json=sbom.spdx.json `
        -o spdx-tag-value=sbom.spdx.txt

`sbom.spdx.json` is the machine-readable deliverable; `sbom.spdx.txt` holds the same data
in a human-readable form and is used for the review below. Use
`-o cyclonedx-json=sbom.cdx.json` instead if CycloneDX is required.

## 4. Review the licenses

List every component and its license.

### GNU/Linux, macOS

    grep -E '^(PackageName|PackageVersion|PackageLicenseDeclared):' sbom.spdx.txt

### Windows (PowerShell)

    Select-String -Path sbom.spdx.txt -Pattern '^(PackageName|PackageVersion|PackageLicenseDeclared):'

Then check each license against the approved list.

### Components reported without a license

Syft reports `NOASSERTION` when it cannot determine a license. Resolve every occurrence
before the SBOM is considered complete, since each one is an unassessed compliance risk.

Common causes:

- **The license is declared only through a trove classifier.** Some wheels ship no
  `License` or `License-Expression` field and only a
  `Classifier: License :: OSI Approved :: …` line, which Syft does not map to an SPDX
  identifier. Read the classifier from
  `site-packages/<name>-<version>.dist-info/METADATA`.
- **The license text is in a PEP 639 `licenses/` subdirectory** of the `.dist-info`
  directory rather than in the metadata itself.
- **Vendored native libraries.** For example, the PySide6 wheel bundles FFmpeg under
  `PySide6/Qt/lib/libav*`. Its license depends on the build flags, which are embedded in
  the binary:

      strings <library> | grep -- '--enable'

  An FFmpeg build without `--enable-gpl` and without `--enable-version3` is LGPL v2.1 or
  later, not GPL.

Record the determination and the evidence for it, so the conclusion can be audited later.

### Multi-license components

- `A OR B` — you may elect either license. Pick the one that is approved and state which.
- `A AND B` — every listed license applies simultaneously. The most restrictive one
  governs.

## Approved open source licenses

Check every license against the Hyland approved license table:

<https://hyland.atlassian.net/wiki/spaces/OGC/pages/2347174146/Open+Source+Software>

Use the **"Including in Hyland's Products and Deliverables"** column: Nuxeo Drive is a
desktop application, so the _"Deploying within Hyland-managed Cloud Environments"_ column
does not apply.

The table marks each license as approved, requiring additional evaluation, under ongoing
review, or not approved. Anything that is not approved must be escalated to Legal before
release.
