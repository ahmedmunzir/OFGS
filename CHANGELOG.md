# Changelog

<details open>
<summary><strong>v2.3.0</strong></summary>

### Added

- Added signed APT repository support for Debian-family package installation.
- Added signed DNF/RPM repository support for EL9, acceptance-tested on Rocky Linux 9.
- Added cryptographic verification of package and repository metadata signatures.
- Added automated package acceptance testing in clean Debian 12 and Rocky Linux 9 environments.
- Added release-tag-only automation for publishing package artifacts and signed APT and EL9 RPM repositories.

</details>
<details>
<summary><strong>Previous Releases</strong></summary><br>
<details>
<summary><strong>v2.2.1</strong></summary>

### Improved

- Improved GNUPlot detection by locating it through the system `PATH` instead of relying on a fixed installation path.
- Renamed the internal generator from `gnuplot_generate.py` to `ofgs_generate.py` for consistent OFGS naming.
- Improved upgrade handling to safely remove the obsolete generator entrypoint.

### Fixed

- Fixed `ofgs generate` incorrectly returning a successful exit status when run outside a valid OpenFOAM case.
- Improved exit-status propagation so OFGS failures behave correctly in shell scripts and automated workflows.
- Added clearer handling when GNUPlot is unavailable.


</details>
<details>
<summary><strong>v2.2.0</strong></summary>

### Improved

- Improved graph generation reliability during active OpenFOAM simulations.
  - Prevents incomplete or unstable post-processing data from replacing valid generated graphs.
  - Preserves the previous valid dashboard and graph set when generation cannot safely complete.
  - Prevents graphs from temporarily disappearing while OpenFOAM is writing new post-processing output.

- Improved concurrent OFGS generation.
  - Added per-case generation locking.
  - Prevents multiple OFGS generation processes from interfering with each other.
  - Generated graph scripts, the dashboard and graph index are now published safely as a consistent set.

- Improved generation safety.
  - New output is prepared before replacing existing generated files.
  - Failed generation preserves the previous valid output.
  - Inaccessible abandoned OFGS staging directories no longer prevent otherwise valid generation.

- Improved `ofgs generate` output.
  - Removed verbose development and dataset diagnostics.
  - Added concise case, graph-count and generation summaries.
  - Added clearer errors when OpenFOAM post-processing data is incomplete or unstable.

- Improved built-in help output.
  - Interactive terminal formatting is preserved.
  - Redirected and piped help output no longer contains ANSI escape sequences.

### Fixed

- Fixed an intermittent race where `ofgs graph <id>` could report that an existing graph did not exist during concurrent generation.
- Fixed generation being able to publish a reduced graph set when OFGS read a newly created OpenFOAM timestep before it had finished being written.
- Fixed abandoned inaccessible OFGS staging directories being able to block later generation.
- Fixed ANSI colour sequences appearing in captured or redirected help output.

</details>
<details>
<summary><strong>v2.1.0</strong></summary>

### Added

- Added `ofgs doctor` to diagnose the current OFGS installation and OpenFOAM case.
  - Verifies OFGS installation.
  - Checks GNUPlot and Python availability.
  - Detects whether the current directory is a valid OpenFOAM case.
  - Reports dashboard status, supported datasets and generated graph count.
  - Provides clear PASS, WARN and FAIL diagnostics.
  - Performs all checks in read-only mode.

- Added `ofgs clean` to safely remove OFGS-generated files from the current case.
  - Removes `monitor.gp` and `graphs/`.
  - Never removes OpenFOAM simulation data.
  - Includes confirmation prompts and `--force` support.
  - Reports exactly which files were removed.

### Improved

- Completely redesigned the built-in help system.
  - Cleaner command layout.
  - Command-specific help pages.
  - Better usage examples.
  - Automatic bold headings for interactive terminals.
  - Plain text output when redirected or piped.

- Improved `ofgs doctor` output.
  - Colour-coded PASS, WARN and FAIL status indicators.
  - Easier to read diagnostic summaries.

- Improved `ofgs clean` output.
  - Displays exactly which generated files were removed.
  - More informative completion messages.

</details>

<details>
<summary><strong>v2.0.0</strong></summary>

### Added
- Standalone `ofgs` command-line interface.
- Automatic migration from legacy gnuplot-wrapper installations.
- Improved installer with safe update workflow.

### Changed
- OFGS no longer replaces the system `gnuplot` executable.
- Installation now uses:
  - `/usr/local/bin/ofgs`
  - `/usr/local/share/ofgs`
- Documentation updated to use the new OFGS commands.

### Improved
- Cleaner installation architecture.
- Safer coexistence with system gnuplot.
- Updated help text and README.

</details>

<details>
<summary><strong>v1.4.0</strong></summary>

### Added
- Installation and uninstallation scripts.
- Safe upgrade support.
- Update confirmation and `--force` installation.
- Compatibility with Windows Subsystem for Linux (WSL).

### Improved
- More robust installation process.
- Better installation messaging.

</details>

<details>
<summary><strong>v1.3.0</strong></summary>

### Added
- Multi-graph viewing.
- Graph index (`ofgs list`).
- Support for opening multiple graphs simultaneously.

### Improved
- Graph numbering.
- Graph selection.
- General usability improvements.

</details>

<details>
<summary><strong>v1.2.0</strong></summary>

### Added
- Live monitoring for dashboards.
- Live monitoring for individual graphs.

### Improved
- Automatic graph regeneration during live sessions.

</details>

<details>
<summary><strong>v1.1.0</strong></summary>

### Added
- Command-line interface.
- Dashboard viewer.
- Individual graph viewer.
- Built-in help.

</details>

<details>
<summary><strong>v1.0.0</strong></summary>

### Initial Release

- Automatic detection of supported OpenFOAM datasets.
- Automatic generation of gnuplot scripts.
- Interactive monitoring dashboard.
- Standalone graph generation.

</details>

</details>
