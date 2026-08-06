# Windows desktop preview

CellOnDesk 0.9.0 adds an automatically built Windows x64 desktop package.

## Artifacts

The `Windows desktop package` GitHub Actions workflow produces:

- `CellOnDesk-0.9.0-Windows-x64-portable.zip`
- `CellOnDesk-Setup-x64.exe`
- packaged and installed diagnostics JSON files

The portable ZIP can be extracted and launched directly. The installer performs a per-user installation under `%LOCALAPPDATA%\\Programs\\CellOnDesk`, adds a Start menu shortcut, and optionally adds a desktop shortcut. Administrator rights are not required.

## Included capabilities

The first Windows package includes:

- the HuBMAP search desktop interface
- HuBMAP manifest export
- portable offline HTML report export
- bundled Python runtime and GUI dependencies
- a headless diagnostics mode used for packaging verification

The current GUI does not yet expose local H5AD inspection or CELLxGENE Census controls. Those remain available through the Python command-line installation while they are added to the desktop interface.

## Automated validation

The Windows workflow:

1. installs the packaging dependencies on a clean Windows runner;
2. runs the source test suite;
3. creates an on-directory PyInstaller application;
4. runs the packaged executable in diagnostics mode;
5. creates a portable ZIP;
6. compiles a per-user Inno Setup installer;
7. silently installs the application to a temporary directory;
8. runs the installed executable in diagnostics mode;
9. silently uninstalls it;
10. uploads the installer, portable package, and diagnostics as workflow artifacts.

## Current release limitation

The installer is unsigned. Windows SmartScreen may therefore warn users until a code-signing certificate is configured. Signing and publication as a GitHub Release asset are required before calling the installer production-ready.
