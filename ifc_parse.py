#!/usr/bin/env python3
"""
IFC (Industry Foundation Classes) Parser Tool for Gemini API.
Parses IFC files and extracts structured building data.
"""

import google.generativeai as genai
import os
from pathlib import Path


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
            "entity_types": entity_counts
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
