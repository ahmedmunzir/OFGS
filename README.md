# OFGS (OpenFOAM Gnuplot Suite) v2.1.0

OFGS (OpenFOAM Gnuplot Suite) is a standalone command-line tool built around gnuplot for visualising OpenFOAM simulation data. It automatically detects supported datasets and provides commands for generating, viewing and live-monitoring simulation graphs.

## Prerequisites

OFGS requires:

- GNUPlot 5.4 or later
- Python 3
- An OpenFOAM case containing supported post-processing data

Tested on:
- HPC Environments
- Windows Subsystem for Linux (WSL)

## Installation

Download or clone the repository and change into the OFGS directory:

```bash
cd /path-to/ofgs
```

Install OFGS system-wide:

```bash
sudo ./install.sh
```

Rerunning the installer updates an existing OFGS installation after confirmation. Use `--force` to skip the prompt.

To remove OFGS:

```bash
sudo ./uninstall.sh
```

## Usage

Generate all gnuplot scripts for the current OpenFOAM case:

```bash
ofgs generate
```

Open the interactive monitoring dashboard:

```bash
ofgs monitor
```

Open the monitoring dashboard with automatic updates every two seconds:

```bash
ofgs monitor --live
```

List all available graphs:

```bash
ofgs list
```

Open a specific graph by ID:

**(Separate multiple graph id's with commas)**

```bash
ofgs graph <id>
ofgs graph <id1,id2,...>
```

Open a graph with automatic updates:
```bash
ofgs graph <id> --live
```

Display the built-in help message:

```bash
ofgs help
ofgs help <command>
```

Remove the generated dashboard and standalone graph files from the current directory:

```bash
ofgs clean
```

This removes only `monitor.gp` and `graphs/`, after confirmation. Use `--force` to skip the prompt. OpenFOAM case data is never removed.

Diagnose the OFGS installation, system dependencies, current OpenFOAM case, generated dashboard and supported datasets:

```bash
ofgs doctor
```

Doctor is read-only and never generates graphs or modifies files.

## Recommended Usage

OFGS is built on top of gnuplot and therefore inherits some of its display and formatting limitations.

For cases with a large number of available graphs, `ofgs monitor` provides a useful overview of the simulation. However, displaying many graphs in a single window can make individual plots difficult to read. This all depends on the amount of graphs generated and the size of your monitor.

For a more detailed view, use `ofgs list` to see the available graph IDs and select only the graphs you are interested in viewing.

`ofgs monitor --live` is best suited to getting an overview of the entire simulation while it is running, while viewing selected graphs individually or in smaller groups is recommended for a clearer and more focused view of specific results and trends.

## Notes

- Run commands from the root directory of an OpenFOAM case.
- All viewing commands automatically regenerate the required graph scripts before opening them, ensuring the latest simulation data is displayed.
- `ofgs generate` can be used when you only want to regenerate the dashboard and graph scripts without opening a window.
- Live mode refreshes graphs automatically every two seconds while a simulation is running.

# Changelog

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
<summary><strong>Previous Releases</strong></summary><br>
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