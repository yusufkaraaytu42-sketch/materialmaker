# ANSYS Material XML Bot (Any Materials)

This tool can now generate XML for **any materials** using two schemas:

1. **GENERIC** for structural/thermal/fluid-style properties (arbitrary property list)
2. **ELECTROMAGNETIC** for B-H curve materials with fixed `pr0..pr2` + `pa0..pa5`

## Run

### GUI

```bash
python3 ansys_material_xml_bot.py
```

### CLI

```bash
python3 ansys_material_xml_bot.py --from-file materials_input_example.txt --output materials.xml
```

## Text format

Use `materials_input_example.txt` as template.

### Generic material

```text
MATERIAL: Aluminum 6061-T6
TYPE: GENERIC
CLASS: Solids
SUBCLASS: Metals
DESCRIPTION: Optional
PROPERTY: Density|2700|kg m^-3|23
PROPERTY: Young's Modulus|6.89e10|Pa|23
END
```

### Electromagnetic material

```text
MATERIAL: Silicon Core Iron
TYPE: ELECTROMAGNETIC
CLASS: Electromagnetic
BH_B: 0,0.2,0.4,0.55
BH_H: 0,59.5,119,158.7
COLOR: 130,177,176
GUID: optional
END
```

## Rules

- `TYPE` can be `GENERIC` or `ELECTROMAGNETIC`.
- For `GENERIC`, add one or more `PROPERTY` lines (`Name|Value|Unit|TemperatureC`).
- For `ELECTROMAGNETIC`, `BH_B` and `BH_H` must have the same number of points.
- `GUID` is optional in electromagnetic mode (auto-generated if omitted).

## Output behavior

- Electromagnetic materials use the fixed ANSYS IDs/metadata (`pr0..pr2`, `pa0..pa5`).
- Generic materials are emitted with generated property/parameter IDs and corresponding metadata.
- Both material types can be mixed in the same exported XML file.
