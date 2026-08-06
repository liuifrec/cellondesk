# CellOnDesk release checklist

Use this checklist before tagging an archived public release.

## Code and packaging

- [ ] Ruff and pytest pass on Python 3.10 and 3.12 across Linux, Windows, and macOS.
- [ ] Source distribution and wheel build successfully.
- [ ] `twine check dist/*` passes.
- [ ] The wheel installs into a clean environment.
- [ ] `cellondesk doctor` reports the expected components and version.
- [ ] Package and `CITATION.cff` versions agree.

## Real-data validation

- [ ] HuBMAP search produces JSON, manifest, and offline HTML outputs.
- [ ] A modern AnnData H5AD passes structural inspection and gene preview.
- [ ] A legacy/compound-layout H5AD passes structural inspection and gene preview.
- [ ] Dense, CSR, and CSC expression paths have validated fixtures.
- [ ] A dated CELLxGENE Census release produces a bounded gene preview.
- [ ] Census JSON and HTML contain the resolved release, query provenance, and source dataset IDs.
- [ ] Available Census dataset citation strings appear in the report.
- [ ] All generated HTML reports open without network access.

## Coworker usability

- [ ] Installation is tested from the wheel, not only a source checkout.
- [ ] A new user can complete the README examples without developer intervention.
- [ ] Common missing-extra errors provide actionable installation instructions.
- [ ] Windows and macOS path handling is confirmed with real files.
- [ ] Example reports are attached to a release or documentation page.

## Archival and citation

- [ ] Create an immutable semantic-version tag.
- [ ] Create a GitHub Release with changelog and known limitations.
- [ ] Archive the release through Zenodo or another DOI provider.
- [ ] Add the version DOI to `CITATION.cff` and README.
- [ ] Cite CellOnDesk separately from all underlying datasets and portals.

## Software-paper threshold

- [ ] Define the user problem and comparison tools clearly.
- [ ] Include a reproducible benchmark of memory use and runtime.
- [ ] Include at least one realistic scientific review workflow.
- [ ] Document supported file layouts, source APIs, and known failure modes.
- [ ] Archive code, validation inputs, expected outputs, and manuscript figures.
