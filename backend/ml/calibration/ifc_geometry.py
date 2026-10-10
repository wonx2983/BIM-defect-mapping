"""IFC geometry extraction — parse IFC files and extract triangulated meshes per element.

This module extracts the 3D geometry from an IFC (Industry Foundation Classes)
file and converts each structural element's shape into a triangulated mesh
suitable for ray-mesh intersection.

Each element is identified by its permanent GlobalId (GUID), and its
geometry is returned as a pair of numpy arrays: vertices (N×3) and
face indices (M×3).

Dependencies:
    - ``ifcopenshell``: For IFC parsing and shape extraction.
    - ``numpy``: For mesh data structures.

If ``ifcopenshell`` is not installed, a graceful ImportError is raised with
installation instructions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import of ifcopenshell — only needed when actually parsing IFC files.
_ifcopenshell = None
_ifcopenshell_geom = None


def _ensure_ifcopenshell():
    """Lazy-import ifcopenshell and its geometry module."""
    global _ifcopenshell, _ifcopenshell_geom
    if _ifcopenshell is None:
        try:
            import ifcopenshell
            import ifcopenshell.geom
            _ifcopenshell = ifcopenshell
            _ifcopenshell_geom = ifcopenshell.geom
        except ImportError as e:
            raise ImportError(
                "ifcopenshell is required for IFC geometry extraction. "
                "Install it with: pip install ifcopenshell"
            ) from e


# ── In-memory mesh cache ─────────────────────────────────────────────
# Keyed by (file_path, file_hash) to avoid re-parsing on every detection.
_mesh_cache: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}


def _file_hash(path: str | Path) -> str:
    """Compute a fast content hash for cache invalidation."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def extract_meshes_from_ifc(
    ifc_path: str | Path,
    element_types: list[str] | None = None,
    use_cache: bool = True,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Extract triangulated meshes from an IFC file, grouped by element GUID.

    Args:
        ifc_path: Path to the .ifc file.
        element_types: Optional filter — only extract elements of these IFC
            types (e.g. ``["IfcWall", "IfcColumn", "IfcSlab", "IfcBeam"]``).
            If ``None``, all structural elements are extracted.
        use_cache: Whether to use the in-memory cache.

    Returns:
        Dict mapping element GUID → ``(vertices, faces)`` where:
        - ``vertices``: (N, 3) float64 array of vertex positions in world coords.
        - ``faces``: (M, 3) int32 array of triangle vertex indices.
    """
    _ensure_ifcopenshell()

    ifc_path = Path(ifc_path)
    if not ifc_path.exists():
        raise FileNotFoundError(f"IFC file not found: {ifc_path}")

    # Cache lookup
    cache_key = str(ifc_path.resolve())
    if use_cache and cache_key in _mesh_cache:
        logger.info("Using cached meshes for %s (%d elements)",
                     ifc_path.name, len(_mesh_cache[cache_key]))
        return _mesh_cache[cache_key]

    logger.info("Parsing IFC file: %s", ifc_path)
    ifc_file = _ifcopenshell.open(str(ifc_path))

    # Default element types for concrete defect detection
    if element_types is None:
        element_types = [
            "IfcWall", "IfcWallStandardCase",
            "IfcColumn",
            "IfcSlab",
            "IfcBeam",
            "IfcFooting",
            "IfcPile",
            "IfcMember",
            "IfcPlate",
            "IfcCovering",
            "IfcBuildingElementProxy",
        ]

    # Configure geometry processing
    settings = _ifcopenshell_geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    settings.set(settings.WELD_VERTICES, True)

    meshes: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    total_elements = 0
    total_triangles = 0

    for element_type in element_types:
        try:
            elements = ifc_file.by_type(element_type)
        except Exception:
            continue

        for element in elements:
            guid = element.GlobalId
            if not guid:
                continue

            try:
                shape = _ifcopenshell_geom.create_shape(settings, element)
            except Exception as e:
                logger.debug("Cannot extract geometry for %s (%s): %s",
                             guid, element_type, e)
                continue

            # Extract vertices and faces from the shape
            geometry = shape.geometry
            verts_flat = geometry.verts
            faces_flat = geometry.faces

            if len(verts_flat) == 0 or len(faces_flat) == 0:
                continue

            vertices = np.array(verts_flat, dtype=np.float64).reshape(-1, 3)
            faces = np.array(faces_flat, dtype=np.int32).reshape(-1, 3)

            meshes[guid] = (vertices, faces)
            total_elements += 1
            total_triangles += len(faces)

    logger.info(
        "Extracted %d elements (%d triangles) from %s",
        total_elements, total_triangles, ifc_path.name,
    )

    # Cache the result
    if use_cache:
        _mesh_cache[cache_key] = meshes

    return meshes


def extract_element_properties(
    ifc_path: str | Path,
    guid: str,
) -> dict[str, Any]:
    """Extract property sets for a specific element by GUID.

    Returns a flat dict of property name → value.
    """
    _ensure_ifcopenshell()

    ifc_file = _ifcopenshell.open(str(ifc_path))

    element = None
    for el in ifc_file.by_type("IfcProduct"):
        if el.GlobalId == guid:
            element = el
            break

    if element is None:
        return {}

    props: dict[str, Any] = {
        "Name": getattr(element, "Name", None),
        "Type": element.is_a(),
        "GlobalId": guid,
    }

    # Extract property sets
    for definition in element.IsDefinedBy:
        if definition.is_a("IfcRelDefinesByProperties"):
            pset = definition.RelatingPropertyDefinition
            if pset.is_a("IfcPropertySet"):
                for prop in pset.HasProperties:
                    if prop.is_a("IfcPropertySingleValue") and prop.NominalValue:
                        props[prop.Name] = prop.NominalValue.wrappedValue

    return props


def get_element_guids(
    ifc_path: str | Path,
    element_types: list[str] | None = None,
) -> list[dict[str, str]]:
    """Get a list of all element GUIDs and their types from an IFC file.

    Useful for populating candidate sets and UI dropdowns.
    """
    _ensure_ifcopenshell()

    ifc_file = _ifcopenshell.open(str(ifc_path))

    if element_types is None:
        element_types = [
            "IfcWall", "IfcWallStandardCase", "IfcColumn", "IfcSlab",
            "IfcBeam", "IfcFooting", "IfcPile", "IfcMember", "IfcPlate",
        ]

    result = []
    for element_type in element_types:
        try:
            for element in ifc_file.by_type(element_type):
                result.append({
                    "guid": element.GlobalId,
                    "type": element.is_a(),
                    "name": getattr(element, "Name", None) or "",
                })
        except Exception:
            continue

    return result


def clear_mesh_cache(ifc_path: str | Path | None = None) -> None:
    """Clear the in-memory mesh cache.

    Args:
        ifc_path: If specified, clear only the cache for this file.
                  If ``None``, clear the entire cache.
    """
    global _mesh_cache
    if ifc_path is None:
        _mesh_cache.clear()
        logger.info("Cleared entire IFC mesh cache")
    else:
        key = str(Path(ifc_path).resolve())
        _mesh_cache.pop(key, None)
        logger.info("Cleared IFC mesh cache for %s", ifc_path)
