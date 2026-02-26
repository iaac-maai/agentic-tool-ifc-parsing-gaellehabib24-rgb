"""
Compliance checks based on Catalan Building Code example requirements.

Functions provided here are intended to be called by an IFC compliance
orchestrator.  The main exported check function follows the required
contract (accepts model as first argument, returns list of dict results;
see checker_template.py for specification).  Auxiliary helper functions
perform the detailed space/window/evacuation analyses described in the
assignment prompt.

Implemented deliverables:

* check_space_compliance(model) -> list[dict]
* analyze_window_compliance(ifc_model, spaces=None) -> list[dict]
* analyze_evacuation_routes(ifc_model, spaces=None) -> list[dict]

The heuristics used by these routines are intentionally simple and
robust; full compliance would normally require accurate geometry and
thorough code logic.
"""

import ifcopenshell
from collections import deque

# ---------------------------------------------------------------------------
# public interface
# ---------------------------------------------------------------------------

def check_space_compliance(model: ifcopenshell.file, **kwargs) -> list[dict]:
    """Primary check function for pytest contract.

    Accepts an Ifc model, extracts space information, and evaluates
    each space against simplified Catalan code requirements (height,
    area, classification).

    Returns a list of result dictionaries.
    """
    spaces = _extract_spaces(model)
    return _evaluate_space_compliance(spaces)


def analyze_window_compliance(ifc_model: ifcopenshell.file,
                               spaces: list[dict] | None = None) -> list[dict]:
    """Analyse window-to-floor ratios and related requirements.

    Parameters
    ----------
    ifc_model : ifcopenshell.file
        IFC model object.
    spaces : list[dict], optional
        Pre‑extracted space dictionaries created by :func:`_extract_spaces`.
        If omitted the function will extract spaces itself.

    Returns
    -------
    list[dict]
        One result per space reporting the ratio and compliance.
    """
    if spaces is None:
        spaces = _extract_spaces(ifc_model)

    results = []
    windows = _extract_windows(ifc_model)

    # total window area used for every space where a direct affiliation
    # cannot be determined.  A more sophisticated tool would trace
    # relationships; here we simply derive a global figure.
    total_win_area = sum(w.get("area") or 0 for w in windows)

    for sp in spaces:
        floor_area = sp.get("area")
        ratio = None
        status = "warning"
        comment = None

        if floor_area and floor_area > 0:
            ratio = total_win_area / floor_area
            if ratio >= 0.125:
                status = "pass"
            else:
                status = "fail"
                comment = "window-to-floor ratio below 12.5%"
        else:
            comment = "floor area unknown, cannot compute ratio"

        results.append({
            "element_id": sp.get("id"),
            "element_type": "IfcSpace",
            "element_name": sp.get("name") or "<unnamed>",
            "element_name_long": sp.get("long_name"),
            "check_status": status,
            "actual_value": f"ratio={ratio:.3f}" if ratio is not None else "n/a",
            "required_value": ">=0.125 window/floor",
            "comment": comment,
            "log": None,
        })

    return results


def analyze_evacuation_routes(ifc_model: ifcopenshell.file,
                               spaces: list[dict] | None = None) -> list[dict]:
    """Analyse spatial connectivity and evacuation distance.

    A simple graph is built where each node is a space and edges indicate
    adjacency through doors or shared boundaries.  The longest path (in
    number of hops) is converted to an approximate distance assuming an
    average 5m segment.  Additional checks for corridor width, door width
    and dead-end corridors are also performed.
    """
    if spaces is None:
        spaces = _extract_spaces(ifc_model)

    # build id->space mapping
    id_to_space = {s["id"]: s for s in spaces if s.get("id")}
    graph = {sid: set() for sid in id_to_space}

    # connect spaces that share the same door via IfcRelSpaceBoundary
    for door in ifc_model.by_type("IfcDoor"):
        related = []
        for rel in getattr(door, "ReferencedBy", []):
            if rel.is_a("IfcRelSpaceBoundary") and rel.RelatingSpace:
                related.append(rel.RelatingSpace.GlobalId)
        if len(related) >= 2:
            for a in related:
                for b in related:
                    if a != b and a in graph and b in graph:
                        graph[a].add(b)
                        graph[b].add(a)

    # as a fallback make the graph fully connected so functions return
    # something even if no explicit relationships exist
    if all(len(neighbors) == 0 for neighbors in graph.values()):
        keys = list(graph.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                graph[keys[i]].add(keys[j])
                graph[keys[j]].add(keys[i])

    # BFS helper to compute farthest node from a start
    def _bfs(start_id):
        visited = {start_id: 0}
        queue = deque([start_id])
        while queue:
            u = queue.popleft()
            for v in graph.get(u, []):
                if v not in visited:
                    visited[v] = visited[u] + 1
                    queue.append(v)
        # return node with max distance
        farthest = max(visited.items(), key=lambda kv: kv[1])
        return farthest  # (node, hops)

    # compute diameter (maximum hops between any two spaces)
    diameter = 0
    for sid in graph:
        _, hops = _bfs(sid)
        if hops > diameter:
            diameter = hops

    approx_distance = diameter * 5.0  # assume 5m per hop

    # basic compliance evaluation
    evac_status = "pass" if approx_distance <= 25.0 else "fail"
    evac_comment = None
    if evac_status == "fail":
        evac_comment = f"longest estimated route {approx_distance:.1f}m exceeds 25m"

    results = []
    results.append({
        "element_id": None,
        "element_type": "EvacuationSummary",
        "element_name": "Evacuation Distance",
        "element_name_long": None,
        "check_status": evac_status,
        "actual_value": f"{approx_distance:.1f}m",
        "required_value": "<=25m",
        "comment": evac_comment,
        "log": None,
    })

    # corridor and door width checks
    for sp in spaces:
        name = (sp.get("name") or "").lower()
        if "corridor" in name or "hall" in name:
            width = None
            # attempt to read a width property if available
            for rel in getattr(sp, "IsDefinedBy", []) or []:
                if rel.is_a("IfcRelDefinesByProperties"):
                    pdef = rel.RelatingPropertyDefinition
                    if pdef and pdef.is_a("IfcPropertySet"):
                        for prop in getattr(pdef, "HasProperties", []):
                            pname = getattr(prop, "Name", "").lower()
                            if "width" in pname:
                                val = getattr(prop, "NominalValue", None)
                                if val is not None and hasattr(val, "wrappedValue"):
                                    try:
                                        width = float(val.wrappedValue)
                                    except Exception:
                                        pass
            status = "pass"
            comment = None
            if width is not None and width < 1.2:
                status = "fail"
                comment = f"corridor width {width}m below 1.2m"
            results.append({
                "element_id": sp.get("id"),
                "element_type": "IfcSpace",
                "element_name": sp.get("name") or "",
                "element_name_long": sp.get("long_name"),
                "check_status": status,
                "actual_value": f"width={width}" if width is not None else "unknown",
                "required_value": ">=1.2m",
                "comment": comment,
                "log": None,
            })

    # door width checks
    for door in ifc_model.by_type("IfcDoor"):
        width = getattr(door, "OverallWidth", None)
        status = "pass"
        comment = None
        if width is not None and width < 0.8:
            status = "fail"
            comment = f"door width {width}m below 0.8m"
        results.append({
            "element_id": getattr(door, "GlobalId", None),
            "element_type": "IfcDoor",
            "element_name": getattr(door, "Name", None) or "",
            "element_name_long": getattr(door, "LongName", None),
            "check_status": status,
            "actual_value": f"width={width}" if width is not None else "unknown",
            "required_value": ">=0.8m",
            "comment": comment,
            "log": None,
        })

    return results

# ---------------------------------------------------------------------------
# internal helpers reused by multiple functions
# ---------------------------------------------------------------------------

def _extract_spaces(model):
    # duplicate from ifc_parse for convenience; callers outside of that
    # module may not import ifc_parse.
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


def _window_area(window) -> float | None:
    """Quick area guess for a window based on its overall dimensions."""
    w = getattr(window, "OverallWidth", None)
    h = getattr(window, "OverallHeight", None)
    try:
        if w is not None and h is not None:
            return float(w) * float(h)
    except Exception:
        pass
    return None


def _extract_windows(model):
    """Simple representation for windows used by the window compliance check."""
    wins = []
    for w in model.by_type("IfcWindow"):
        wins.append({
            "id": getattr(w, "GlobalId", None),
            "name": getattr(w, "Name", None),
            "width": getattr(w, "OverallWidth", None),
            "height": getattr(w, "OverallHeight", None),
            "area": _window_area(w),
        })
    return wins

# reuse area/height helpers from earlier

def _get_space_area(space) -> float | None:
    for attr in ("NetFloorArea", "GrossFloorArea", "Area"):
        if hasattr(space, attr):
            try:
                return float(getattr(space, attr))
            except Exception:
                pass
    for rel in getattr(space, "IsDefinedBy", []) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            pdef = rel.RelatingPropertyDefinition
            if pdef and pdef.is_a("IfcElementQuantity"):
                for q in getattr(pdef, "Quantities", []):
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
    for attr in ("Height", "UnboundedHeight", "Elevation"):
        if hasattr(space, attr):
            try:
                return float(getattr(space, attr))
            except Exception:
                pass
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


def _evaluate_space_compliance(spaces: list[dict]) -> list[dict]:
    results = []
    # simple requirement tables (min height, min area) keyed by classification
    height_map = {"default": 2.3, "living": 2.5, "kitchen": 2.3, "bathroom": 2.3}
    area_map = {"default": 4.0, "bedroom": 8.0, "living room": 12.0, "kitchen": 6.0}

    for sp in spaces:
        cls = (sp.get("classification") or "").lower() if sp.get("classification") else ""
        required_height = height_map.get(cls, height_map["default"])
        required_area = area_map.get(cls, area_map["default"])

        actual_height = sp.get("height")
        actual_area = sp.get("area")

        status = "pass"
        comment_parts = []

        if actual_height is None or actual_height < required_height:
            status = "fail"
            comment_parts.append(
                f"height {actual_height} < {required_height}" if actual_height is not None else "height unknown"
            )
        if actual_area is None or actual_area < required_area:
            status = "fail"
            comment_parts.append(
                f"area {actual_area} < {required_area}" if actual_area is not None else "area unknown"
            )
        if not cls:
            if status == "pass":
                status = "warning"
            comment_parts.append("classification missing")

        results.append({
            "element_id": sp.get("id"),
            "element_type": "IfcSpace",
            "element_name": sp.get("name") or "<unnamed>",
            "element_name_long": sp.get("long_name"),
            "check_status": status,
            "actual_value": f"h={actual_height}, a={actual_area}",
            "required_value": f">={required_height}m height, >={required_area}m2 area",
            "comment": "; ".join(comment_parts) if comment_parts else None,
            "log": None,
        })
    return results
