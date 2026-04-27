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

## API

- `load_from_xml(filepath: str) -> MaterialDatabase`
- `to_json(material_db, filepath: str)`
- `get_material(material_db, name: str) -> Optional[Material]`
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
