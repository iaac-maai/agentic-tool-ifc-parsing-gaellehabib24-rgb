#!/usr/bin/env python3
"""
IFC (Industry Foundation Classes) Parser Tool for Gemini API.
Parses IFC files and extracts structured building data.
"""

import google.generativeai as genai
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Helper routines for extracting semantic data from IFC models using
# ifcopenshell. These are used by the parser to build structured lists of
# spaces and windows so that downstream analysis (e.g. code compliance
# checks) can operate on them.
# ---------------------------------------------------------------------------

def _get_space_area(space) -> float | None:
    """Try to determine floor area of an IfcSpace from available data."""
    # direct attribute
    for attr in ("NetFloorArea", "GrossFloorArea", "Area"):  # common names
        if hasattr(space, attr):
            try:
                return float(getattr(space, attr))
            except Exception:
                pass

    # inspect related property sets and quantities
    for rel in getattr(space, "IsDefinedBy", []) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            pdef = rel.RelatingPropertyDefinition
            # quantities like IfcElementQuantity hold area measures
            if pdef and pdef.is_a("IfcElementQuantity"):
                for q in getattr(pdef, "Quantities", []):
                    # many quantity types exist; look for area values
                    if q.is_a("IfcQuantityArea"):
                        try:
                            return float(q.AreaValue)
                        except Exception:
                            pass
            elif pdef and pdef.is_a("IfcPropertySet"):
                for prop in getattr(pdef, "HasProperties", []):
                    name = getattr(prop, "Name", "").lower()
                    if "area" in name:
                        val = getattr(prop, "NominalValue", None)
                        if val is not None and hasattr(val, "wrappedValue"):
                            try:
                                return float(val.wrappedValue)
                            except Exception:
                                pass
    return None


def _get_space_height(space) -> float | None:
    """Extract a height value if available on the space or its properties."""
    for attr in ("Height", "UnboundedHeight", "Elevation"):
        if hasattr(space, attr):
            try:
                return float(getattr(space, attr))
            except Exception:
                pass

    # look for a property set containing height information
    for rel in getattr(space, "IsDefinedBy", []) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            pdef = rel.RelatingPropertyDefinition
            if pdef and pdef.is_a("IfcPropertySet"):
                for prop in getattr(pdef, "HasProperties", []):
                    name = getattr(prop, "Name", "").lower()
                    if "height" in name:
                        val = getattr(prop, "NominalValue", None)
                        if val is not None and hasattr(val, "wrappedValue"):
                            try:
                                return float(val.wrappedValue)
                            except Exception:
                                pass
    return None


def _extract_spaces(model) -> list[dict]:
    """Return a simplified dictionary for each IfcSpace in the model."""
    spaces = []
    for sp in model.by_type("IfcSpace"):
        spaces.append({
            "id": getattr(sp, "GlobalId", None),
            "name": getattr(sp, "Name", None),
            "long_name": getattr(sp, "LongName", None),
            "classification": getattr(sp, "PredefinedType", None) or getattr(sp, "Classification", None),
            "area": _get_space_area(sp),
            "height": _get_space_height(sp),
        })
    return spaces


def _get_window_area(window) -> float | None:
    """Compute rough area of a window from its overall dimensions."""
    w = getattr(window, "OverallWidth", None)
    h = getattr(window, "OverallHeight", None)
    try:
        if w is not None and h is not None:
            return float(w) * float(h)
    except Exception:
        pass
    return None


def _extract_windows(model) -> list[dict]:
    """Simplified representation for each IfcWindow in the model."""
    wins = []
    for w in model.by_type("IfcWindow"):
        wins.append({
            "id": getattr(w, "GlobalId", None),
            "name": getattr(w, "Name", None),
            "width": getattr(w, "OverallWidth", None),
            "height": getattr(w, "OverallHeight", None),
            "area": _get_window_area(w),
        })
    return wins


def _extract_evacuation_routes(model) -> list[dict]:
    """Gather spaces that appear to be part of a fire safety/evacuation route.

    For the purposes of the simple example we flag any space whose name
    contains keywords like 'stair', 'exit', 'corridor' or 'hall'.  A real
    implementation would follow explicit IfcRelFlowSegment or IsDefinedBy
    relationships.
    """
    keywords = ("stair", "exit", "corridor", "hallway", "hall")
    routes = []
    for sp in model.by_type("IfcSpace"):
        name = (getattr(sp, "Name", "") or "").lower()
        if any(k in name for k in keywords):
            routes.append({
                "id": getattr(sp, "GlobalId", None),
                "name": getattr(sp, "Name", None),
            })
    return routes



def parse_ifc_file(file_path: str) -> dict:
    """
    Parse an IFC file and extract key information.
    
    Args:
        file_path: Path to the IFC file to parse
        
    Returns:
        Dictionary containing parsed IFC data
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        return {"error": f"File not found: {file_path}"}
    
    if not file_path.suffix.lower() == '.ifc':
        return {"error": f"File must be an IFC file, got: {file_path.suffix}"}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse header section
        header_section = {}
        if 'HEADER;' in content and 'ENDSEC;' in content:
            header_start = content.find('HEADER;') + 7
            header_end = content.find('ENDSEC;', header_start)
            header_content = content[header_start:header_end]
            
            # Extract key header information
            if 'FILE_NAME' in header_content:
                file_name_match = header_content.split('FILE_NAME')[1].split(';')[0]
                header_section['file_name'] = file_name_match.strip()
            
            if 'FILE_SCHEMA' in header_content:
                schema_match = header_content.split('FILE_SCHEMA')[1].split(';')[0]
                header_section['file_schema'] = schema_match.strip()
        
        # Count key entities in data section
        entity_counts = {}
        data_start = content.find('DATA;') + 5
        data_end = content.find('ENDSEC;', data_start)
        data_content = content[data_start:data_end]
        
        # Extract entity types
        import re
        entity_pattern = r'#\d+\s*=\s*(\w+)'
        entities = re.findall(entity_pattern, data_content)
        
        for entity in entities:
            entity_counts[entity] = entity_counts.get(entity, 0) + 1
        
        # Extract specific geometric and structural elements
        ifcbuilding_count = entities.count('IFCBUILDING')
        ifcstory_count = entities.count('IFCBUILDINGSTOREY')
        ifcwall_count = entities.count('IFCWALL')
        ifcdoor_count = entities.count('IFCDOOR')
        ifcwindow_count = entities.count('IFCWINDOW')
        ifcslab_count = entities.count('IFCSLAB')
        ifccolumn_count = entities.count('IFCCOLUMN')
        ifcbeam_count = entities.count('IFCBEAM')
        
        # also attempt to open the file with ifcopenshell so we can extract
        # more semantic information about spaces, windows, and evacuation
        # routes.  Predefine variables so that failures do not leave them
        # undefined.
        spaces = []
        windows = []
        evacuation_routes = []
        try:
            import ifcopenshell
            model = ifcopenshell.open(str(file_path))
            spaces = _extract_spaces(model)
            windows = _extract_windows(model)
            evacuation_routes = _extract_evacuation_routes(model)
        except Exception:
            # if ifcopenshell is not available or parsing fails we simply ignore
            spaces = []
            windows = []
            evacuation_routes = []

        return {
            "file": str(file_path),
            "status": "success",
            "header": header_section,
            "summary": {
                "total_entities": len(entities),
                "buildings": ifcbuilding_count,
                "storeys": ifcstory_count,
                "walls": ifcwall_count,
                "doors": ifcdoor_count,
                "windows": ifcwindow_count,
                "slabs": ifcslab_count,
                "columns": ifccolumn_count,
                "beams": ifcbeam_count,
            },
            "entity_types": entity_counts,
            "spaces": spaces,
            "windows": windows,
            "evacuation_routes": evacuation_routes,
        }
    
    except Exception as e:
        return {"error": f"Failed to parse IFC file: {str(e)}"}


# Define the IFC Parser Tool schema for Gemini
ifc_parse_tool = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name="parse_ifc",
            description="Parse an IFC (Industry Foundation Classes) file and extract structured building information including entities, geometry, and metadata. IFC is a standard format for Building Information Modeling (BIM).",
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    "file_path": genai.protos.Schema(
                        type=genai.protos.Type.STRING,
                        description="Path to the IFC file to parse (e.g., 'building.ifc' or '/path/to/model.ifc')"
                    )
                },
                required=["file_path"]
            )
        )
    ]
)
