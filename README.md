# ANSYS Electromagnetic Material XML Bot

This tool generates ANSYS `EngineeringData` XML in the same structure you shared:

- `PropertyData property="pr0"` = **B-H Curve** (`pa0` dependent B list, `pa1` independent H list)
- `PropertyData property="pr1"` = **Material Unique Id** (`guid`, `Display=False`)
- `PropertyData property="pr2"` = **Color** (`pa2`, `pa3`, `pa4`, and `pa5=Appearance`)
- Global `<Metadata>` with `pa0..pa5` and `pr0..pr2` definitions

## Run (GUI)

```bash
python3 ansys_material_xml_bot.py
```

## Run (CLI)

```bash
python3 ansys_material_xml_bot.py --from-file materials_input_example.txt --output materials.xml
```

## Text Input Format

Use `materials_input_example.txt` as template:

```text
MATERIAL: Material name
CLASS: Electromagnetic
BH_B: 0,0.86,1.12
BH_H: 0,317.4,476.2
COLOR: 181,168,168
GUID: optional-guid
END
```

Rules:
- `BH_B` and `BH_H` must have the same number of comma-separated points.
- `COLOR` is `R,G,B`.
- `GUID` is optional (auto-generated if missing).
- `CLASS` defaults to `Electromagnetic`.

## Why this fixes your issue

Your provided XML format uses fixed property/parameter IDs (`pr0..pr2`, `pa0..pa5`) and metadata.
This bot now emits that exact structure instead of a generic property schema.
