# Windows desktop preview

CellOnDesk includes a native Windows x64 desktop package. The current source
milestone is 0.12.0; it has not been released by this implementation task.

## Artifacts

The `Windows desktop package` GitHub Actions workflow produces:

- `CellOnDesk-<version>-Windows-x64-portable.zip`
- `CellOnDesk-<version>-Setup-x64.exe`
- packaged and installed diagnostics JSON files

The portable ZIP can be extracted and launched directly. The installer performs a per-user installation under `%LOCALAPPDATA%\\Programs\\CellOnDesk`, adds a Start menu shortcut, and optionally adds a desktop shortcut. Administrator rights are not required.

## Included capabilities

The current desktop includes:

- unified Discovery with common scientific filters, independent source progress,
  cached catalogs, normalized results and local sorting/filtering
- HuBMAP, CELLxGENE Discover and UCSC advanced source tabs
- HuBMAP manifest export
- portable offline HTML report export
- bundled Python runtime and GUI dependencies
- a headless diagnostics mode used for packaging verification

Local H5AD inspection and self-contained offline dashboards are included.
Optional CELLxGENE Census controls are retained but require a compatible Python
environment with the Census/SOMA dependency; it is not bundled on native Windows.
See [discovery architecture and validation](DISCOVERY_ARCHITECTURE.md).

## Automated validation

The Windows workflow:

1. installs the packaging dependencies on a clean Windows runner;
2. runs the source and offscreen Qt interaction/screenshot tests;
3. creates an on-directory PyInstaller application;
4. runs the packaged executable in diagnostics and real GUI smoke modes;
5. creates a portable ZIP;
6. compiles a per-user Inno Setup installer;
7. silently installs the application to a temporary directory;
8. runs the installed executable in diagnostics and GUI smoke modes;
9. silently uninstalls it;
10. uploads the installer, portable package, and diagnostics as workflow artifacts.

## Current release limitation

The installer is unsigned. Windows SmartScreen may therefore warn users until a code-signing certificate is configured. Signing and publication as a GitHub Release asset are required before calling the installer production-ready.
