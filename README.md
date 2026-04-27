# Material XML Parser (Ansys Granta / EngineeringData)

This repository now includes `material_xml_parser.py`, a Python module that parses the Ansys Granta MatML/EngineeringData XML structure into Python dataclasses and JSON-serializable objects.

## What it parses

Supported wrappers:
- `<merged><item><EngineeringData>...`
- direct `<EngineeringData>` files
- direct `<MatML_Doc>` files

Supported sections:
- `Material/BulkDetails` (`Name`, `Description`, `Class`, `Subclass`)
- `PropertyData` with linked `PropertyDetails` IDs (`prX`)
- `ParameterValue` with linked `ParameterDetails` IDs (`paY`)
- metadata units (`<Units>/<Unit power="...">`, `<Unitless/>`)
- qualifiers at property and parameter level
- interpolation/extrapolation options from `pa6`
- `pa6` values used as normal data (e.g., `Appearance`) are not treated as interpolation nodes unless interpolation qualifiers are present

## API

- `load_from_xml(filepath: str) -> MaterialDatabase`
- `to_json(material_db, filepath: str)`
- `get_material(material_db, name: str) -> Optional[Material]`
- `validate_for_mechanical(material_db) -> dict` (heuristic report for missing core properties + duplicates)
- `evaluate_property(material, prop_name, **field_vars) -> float` (basic helper)

## Quick usage

```python
from material_xml_parser import load_from_xml, get_material

db = load_from_xml("example_engineering_data.xml")
air = get_material(db, "Air, gas")
print(air.properties["Density"].unit)
print(db.to_json())
```

## Notes

- Dependent and independent comma-separated lists are aligned by index.
- If a property has no independent variable, points are stored with an empty `independent` list.
- For one independent variable, `evaluate_property` performs linear interpolation.
- For multi-dimensional properties, `evaluate_property` currently does exact-match lookup.

## Example files

- `example_engineering_data.xml`: sample XML for smoke testing.
- `example_hyperelastic.xml`: sample matching real hyperelastic-style structure with multi-independent data and multiple dependent scalar parameters.
- `example_materials.txt`: sample import file for the reworked GUI builder.

## Reworked GUI builder

Run:

```bash
python3 material_xml_gui.py
```

The GUI now builds XML in the same structural style as your real files:

- root `<EngineeringData version=\"...\" versiondate=\"...\">`
- `<Notes/>`
- `<Materials><MatML_Doc>...`
- material blocks with `<BulkDetails>` and repeated `<PropertyData>`
- generated `<Metadata>` with `ParameterDetails` / `PropertyDetails` IDs (`pa0...`, `pr0...`)
- export-time validation for duplicate material names and warnings for materials missing Density / Young's Modulus / Poisson's Ratio

Property editor supports:

- multiple dependent series (e.g. Red/Green/Blue or orthotropic constants)
- multiple independent series
- property qualifiers
- interpolation/extrapolation option qualifiers
- optional blank/unitless fields

TXT import format uses:

- `DEP: name|unit|v1,v2,...`
- `IND: name|unit|v1,v2,...`
- `PQUAL: key=value`
- `OPTION_NAME`, `INTERPOLATION`, `EXTRAPOLATION`
