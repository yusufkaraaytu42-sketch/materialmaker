# Material XML Builder

`material_xml_gui.py` is a Tkinter GUI that builds the custom `EngineeringData` XML format.

## Features
- Add material data manually in the GUI.
- Add properties with dependent/independent values.
- Import one or more materials from a plain text list file.
- Export XML with:
  - `EngineeringData > item > MatML_Doc`
  - `Material/BulkDetails/PropertyData`
  - Metadata (`ParameterDetails`, `PropertyDetails`) and ID linking (`paX`, `prX`).

## Run

```bash
python3 material_xml_gui.py
```

## Text import format
Use blocks like this:

```text
MATERIAL: Air, gas
DESCRIPTION: Optional
CLASS: Fluids
SUBCLASS: Gases

PROPERTY: Density
DEPENDENT: Density|kg m^-3|1.16,1.00
INDEPENDENT: Temperature|C|23,100
QUALIFIER: Behavior=Isotropic
INTERPOLATION: Linear Multivariate (Qhull)
EXTRAPOLATION: Projection to the Bounding Box
ENDPROPERTY
ENDMATERIAL
```

- `DEPENDENT` and `INDEPENDENT` use `name|unit|comma,separated,values`.
- You can add multiple `INDEPENDENT` lines per property for multivariate tables.
- Add multiple `QUALIFIER` lines as `key=value`.

See `example_materials.txt` for a complete sample.
