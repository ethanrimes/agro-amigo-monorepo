# Documentation

Public documentation describes AgroAmigo's functionality, data semantics,
architecture and main implementation components.

- [Architecture and user journeys](ARCHITECTURE.md)
- [Code navigation](CODE_NAVIGATION.md)
- [Data sources and interpretation](DATA_SOURCES.md)
- [Mi finca](MI_FINCA_DATA.md)
- [Colombian price references](OFFICIAL_COLOMBIA_SOURCES.md)
- [International price references](OFFICIAL_INTERNATIONAL_SOURCES.md)

Internal audits, QA checklists, release evidence, research and operational notes
belong in `docs/private/`. That folder is local and gitignored. Generated test
artifacts remain in the separately ignored `artifacts/` folder. Public guides
must stand on their own without links to private documents.

The public documentation paths are explicitly listed in `.gitignore`; add a
new public guide to that list when it meets these criteria.
