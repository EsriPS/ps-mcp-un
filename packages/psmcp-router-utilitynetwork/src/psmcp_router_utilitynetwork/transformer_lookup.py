"""Metadata-driven, complete nearest-transformer queries without map effects."""

import json
import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

_TRANSFORMER = re.compile(r"\btransformers?\b", re.IGNORECASE)
_MOUNTED_QUALIFIER = re.compile(r"\b(?:pad|vault)[\s-]+mounted\b", re.IGNORECASE)
_AMBIGUOUS = re.compile(r"\b(?:or|and|not|non|pad|vault|foundation|inspection)\b|/", re.IGNORECASE)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_NUMERIC_TYPES = {
    "esriFieldTypeSmallInteger",
    "esriFieldTypeInteger",
    "esriFieldTypeBigInteger",
    "esriFieldTypeSingle",
    "esriFieldTypeDouble",
    "esriFieldTypeOID",
}


@dataclass(frozen=True)
class TransformerLayer:
    """Verified layer identity and OR-of-AND classification predicates."""

    layer_id: int
    url: str
    object_id_field: str
    global_id_field: str
    clauses: tuple[tuple[tuple[str, Any], ...], ...]
    where: str
    batch_size: int
    supports_pagination: bool


def validate_search(
    latitude: float, longitude: float, radius_meters: float, limit: int, service_url: str | None
) -> str:
    """Validate inputs without clamping and return a normalized FeatureServer URL."""
    for name, value, minimum, maximum in (
        ("latitude", latitude, -90, 90),
        ("longitude", longitude, -180, 180),
        ("radius_meters", radius_meters, 25, 25000),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not minimum <= value <= maximum
        ):
            raise ValueError(f"{name} must be finite and between {minimum} and {maximum}")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 25:
        raise ValueError("limit must be an integer between 1 and 25")
    if not isinstance(service_url, str) or not service_url:
        raise ValueError("Provide network_service_url or set UTILITY_NETWORK_URL.")
    parsed = urlsplit(service_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.rstrip("/").endswith("/FeatureServer")
    ):
        raise ValueError(
            "network_service_url must be a FeatureServer URL without credentials/query"
        )
    return service_url.rstrip("/")


def _is_transformer(label: Any) -> bool:
    if not isinstance(label, str) or not label.strip():
        raise ValueError("Missing classification label in layer metadata")
    if not _TRANSFORMER.search(label):
        return False
    # Pad/vault mounting describes equipment, unlike a transformer pad or vault.
    if _AMBIGUOUS.search(_MOUNTED_QUALIFIER.sub("", label)):
        raise ValueError(f"Ambiguous transformer classification label: {label!r}")
    return True


def _classification_field(field: dict) -> bool:
    if field.get("domain") is not None and not isinstance(field["domain"], dict):
        raise ValueError("Malformed field domain metadata")
    labels = (field["name"], field.get("alias", ""), (field.get("domain") or {}).get("name", ""))
    return any(
        re.search(
            r"(asset|device|equipment).*(type|group|class)|^(type|class|kind)(code)?$",
            re.sub(r"[^a-z0-9]", "", str(label).lower()),
        )
        for label in labels
    )


def _literal(field: dict, value: Any) -> str:
    if field.get("type") == "esriFieldTypeString" and isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if (
        field.get("type") in _NUMERIC_TYPES
        and not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    ):
        if (
            field["type"] not in {"esriFieldTypeSingle", "esriFieldTypeDouble"}
            and type(value) is not int
        ):
            raise ValueError(f"Expected an integer classification code for {field['name']!r}")
        return str(value)
    raise ValueError(f"Invalid classification code for field {field['name']!r}")


def _domain_codes(field: dict, domain: Any) -> list[Any]:
    if domain is None:
        return []
    if not isinstance(domain, dict):
        raise ValueError("Malformed classification domain")
    if domain.get("type") != "codedValue":
        return []
    values = domain.get("codedValues")
    if not isinstance(values, list) or not values:
        raise ValueError("Missing coded classification values")
    seen = set()
    matching = []
    for value in values:
        if not isinstance(value, dict) or "code" not in value:
            raise ValueError("Malformed coded classification value")
        _literal(field, value["code"])
        if value["code"] in seen:
            raise ValueError("Ambiguous duplicate classification code")
        seen.add(value["code"])
        if _is_transformer(value.get("name")):
            matching.append(value["code"])
    return matching


def _fields(metadata: dict) -> dict[str, dict]:
    fields = metadata.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("Point layer is missing fields/classification metadata")
    result = {}
    for field in fields:
        if not isinstance(field, dict) or not isinstance(field.get("name"), str):
            raise ValueError("Malformed layer field metadata")
        name = field["name"]
        if not _IDENTIFIER.fullmatch(name) or name.casefold() in result:
            raise ValueError("Unsupported or ambiguous layer field name")
        result[name.casefold()] = field
    return result


def classify_layer(
    layer_id: int, url: str, metadata: dict, service: dict
) -> TransformerLayer | None:
    """Resolve subtype or equipment-domain predicates; never classify all devices.

    Returns None for a classified non-transformer point layer or a non-point layer.
    Missing/ambiguous classification on a point layer fails the entire search.
    """
    geometry_type = metadata.get("geometryType")
    if not isinstance(geometry_type, str):
        raise ValueError(f"Layer {layer_id} is missing geometryType metadata")
    if geometry_type != "esriGeometryPoint":
        return None
    fields = _fields(metadata)
    subtype_name = metadata.get("typeIdField") or metadata.get("subtypeField")
    subtypes = metadata.get("types", [])
    if not isinstance(subtypes, list):
        raise ValueError("Malformed layer subtype metadata")
    clauses: list[tuple[tuple[str, Any], ...]] = []
    classification_known = False

    def domains(overrides: dict | None = None) -> list[tuple[str, list[Any]]]:
        nonlocal classification_known
        matches = []
        normalized = {name.casefold(): domain for name, domain in (overrides or {}).items()}
        for key, field in fields.items():
            if key == str(subtype_name).casefold() or not _classification_field(field):
                continue
            domain = normalized.get(key, field.get("domain"))
            if isinstance(domain, dict) and domain.get("type") == "inherited":
                domain = field.get("domain")
            codes = _domain_codes(field, domain)
            if isinstance(domain, dict) and domain.get("type") == "codedValue":
                classification_known = True
            if codes:
                matches.append((field["name"], codes))
        if len(matches) > 1:
            raise ValueError("Ambiguous transformer classification across multiple fields")
        return matches

    if subtypes:
        field = fields.get(str(subtype_name).casefold())
        if field is None:
            raise ValueError("Subtype classification field is missing")
        seen_subtypes = set()
        for subtype in subtypes:
            if not isinstance(subtype, dict) or "id" not in subtype:
                raise ValueError("Malformed subtype classification")
            _literal(field, subtype["id"])
            if subtype["id"] in seen_subtypes:
                raise ValueError("Ambiguous duplicate subtype code")
            seen_subtypes.add(subtype["id"])
            classification_known = True
            prefix = ((field["name"], subtype["id"]),)
            if _is_transformer(subtype.get("name")):
                clauses.append(prefix)
                continue
            overrides = subtype.get("domains", {})
            if not isinstance(overrides, dict):
                raise ValueError("Malformed subtype domain overrides")
            for name, codes in domains(overrides):
                clauses.extend((*prefix, (name, code)) for code in codes)
    else:
        if subtype_name:
            raise ValueError("Declared subtype field has no subtype metadata")
        for name, codes in domains():
            clauses.extend(((name, code),) for code in codes)
    if not classification_known:
        raise ValueError(f"Unknown transformer classification for point layer {layer_id}")
    if not clauses:
        return None

    def identity_field(property_name: str, field_type: str) -> str:
        declared = metadata.get(property_name)
        typed = [field["name"] for field in fields.values() if field.get("type") == field_type]
        if len(typed) != 1 or (
            declared is not None
            and (not isinstance(declared, str) or declared.casefold() != typed[0].casefold())
        ):
            raise ValueError(f"Missing or ambiguous {property_name} metadata")
        return typed[0]

    batch_size = metadata.get("maxRecordCount", service.get("maxRecordCount"))
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("Missing or invalid maxRecordCount for transformer layer")
    capabilities = metadata.get("advancedQueryCapabilities", {})
    if not isinstance(capabilities, dict):
        raise ValueError("Malformed query capabilities")
    if capabilities.get("supportsQueryWithDistance") is False:
        raise ValueError("Transformer layer does not support distance queries")
    where = " OR ".join(
        "("
        + " AND ".join(
            f"{name} = {_literal(fields[name.casefold()], code)}" for name, code in clause
        )
        + ")"
        for clause in clauses
    )
    return TransformerLayer(
        layer_id,
        url,
        identity_field("objectIdField", "esriFieldTypeOID"),
        identity_field("globalIdField", "esriFieldTypeGlobalID"),
        tuple(clauses),
        where,
        batch_size,
        capabilities.get("supportsPagination") is True
        and capabilities.get("supportsOrderBy") is True,
    )


async def _request(
    client: httpx.AsyncClient, url: str, token: str | None, parameters: dict | None = None
) -> dict:
    parameters = {"f": "json", **(parameters or {})}
    headers = {"X-Esri-Authorization": f"Bearer {token}"} if token else {}
    try:
        response = (
            await client.post(url, data=parameters, headers=headers)
            if url.endswith("/query")
            else await client.get(url, params=parameters, headers=headers)
        )
        response.raise_for_status()
    except httpx.HTTPError:
        # Keep HTTP internals and authentication details out of MCP error messages.
        raise ValueError("Transformer service HTTP request failed") from None
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("Transformer service returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Transformer service returned a non-object response")
    if data.get("error") is not None:
        code = data["error"].get("code") if isinstance(data["error"], dict) else None
        code = code if type(code) is int else "unknown"
        raise ValueError(f"Transformer service returned an ArcGIS error (code {code})")
    return data


def _object_ids(values: Any) -> list[int]:
    if not isinstance(values, list) or any(type(value) is not int or value < 0 for value in values):
        raise ValueError("Malformed object IDs in transformer query")
    if len(values) != len(set(values)):
        raise ValueError("Duplicate object IDs in transformer query")
    return values


def _attribute(attributes: dict, name: str) -> Any:
    if not isinstance(attributes, dict):
        raise ValueError("Missing or malformed feature attributes")
    matches = [value for key, value in attributes.items() if key.casefold() == name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Missing or ambiguous returned attribute {name!r}")
    return matches[0]


def _code_matches(attributes: dict, name: str, code: Any) -> bool:
    value = _attribute(attributes, name)
    return not isinstance(value, bool) and value == code


async def _all_ids(
    client: httpx.AsyncClient, layer: TransformerLayer, token: str | None, spatial: dict
) -> list[int]:
    query = {"where": layer.where, **spatial}
    count_data = await _request(
        client, layer.url + "/query", token, {**query, "returnCountOnly": "true"}
    )
    count = count_data.get("count")
    if type(count) is not int or count < 0:
        raise ValueError("Missing or invalid transformer count")
    data = await _request(client, layer.url + "/query", token, {**query, "returnIdsOnly": "true"})
    if "objectIds" not in data:
        raise ValueError("Missing object IDs in transformer query")
    ids = _object_ids(data.get("objectIds") if count else data.get("objectIds") or [])
    if (
        str(data.get("objectIdFieldName", layer.object_id_field)).casefold()
        != layer.object_id_field.casefold()
    ):
        raise ValueError("Object ID field changed during transformer query")
    if not data.get("exceededTransferLimit") and len(ids) == count:
        return sorted(ids)
    if not layer.supports_pagination:
        raise ValueError("Incomplete transformer ID query; ordered pagination is unavailable")

    ids = []
    while len(ids) < count:
        data = await _request(
            client,
            layer.url + "/query",
            token,
            {
                **query,
                "outFields": layer.object_id_field,
                "returnGeometry": "false",
                "orderByFields": layer.object_id_field + " ASC",
                "resultOffset": len(ids),
                "resultRecordCount": layer.batch_size,
            },
        )
        features = data.get("features")
        if not isinstance(features, list) or not features:
            raise ValueError("Missing transformer ID page")
        try:
            page = _object_ids(
                [_attribute(feature["attributes"], layer.object_id_field) for feature in features]
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed transformer ID page") from exc
        if page != sorted(page) or (ids and page[0] <= ids[-1]):
            raise ValueError("Duplicate or unordered transformer ID page")
        ids.extend(page)
        if len(ids) > count or (len(ids) < count and not data.get("exceededTransferLimit")):
            raise ValueError("Transformer ID pages disagree with the total count")
        if len(ids) == count and data.get("exceededTransferLimit"):
            raise ValueError("Transformer ID pagination remains truncated")
    if count == 0:
        raise ValueError("Transformer ID query disagrees with an empty count")
    return ids


async def _batch(
    client: httpx.AsyncClient, layer: TransformerLayer, token: str | None, ids: list[int]
) -> list[tuple[dict, dict | None]]:
    data = await _request(
        client,
        layer.url + "/query",
        token,
        {
            "objectIds": ",".join(str(value) for value in ids),
            "where": layer.where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
        },
    )
    if data.get("exceededTransferLimit"):
        if len(ids) == 1:
            raise ValueError("Transformer feature page remains truncated")
        middle = len(ids) // 2
        return await _batch(client, layer, token, ids[:middle]) + await _batch(
            client, layer, token, ids[middle:]
        )
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError("Missing transformer feature page")
    try:
        returned = _object_ids(
            [_attribute(feature["attributes"], layer.object_id_field) for feature in features]
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed transformer feature page") from exc
    if set(returned) != set(ids):
        raise ValueError("Missing or unexpected IDs in transformer feature page")
    return [(feature, data.get("spatialReference")) for feature in features]


def _coordinates(geometry: Any, spatial_reference: Any) -> tuple[float, float]:
    if not isinstance(geometry, dict):
        raise ValueError("Missing transformer point geometry")
    references = [
        reference
        for reference in (spatial_reference, geometry.get("spatialReference"))
        if reference is not None
    ]
    if not references or any(
        not isinstance(reference, dict)
        or reference.get("latestWkid", reference.get("wkid")) != 4326
        for reference in references
    ):
        raise ValueError("Transformer query must return WGS84 (outSR=4326) geometry")
    latitude, longitude = geometry.get("y"), geometry.get("x")
    for value, bound in ((latitude, 90), (longitude, 180)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or abs(value) > bound
        ):
            raise ValueError("Invalid WGS84 transformer point geometry")
    return latitude, longitude


def geodesic_distance(
    latitude: float, longitude: float, other_latitude: float, other_longitude: float
) -> float:
    """Compute WGS84 ellipsoid distance in meters using the Vincenty inverse.

    Searches are limited to 25 km; a non-convergent inverse fails explicitly
    instead of silently substituting a different ranking metric.
    """
    a, flattening = 6378137.0, 1 / 298.257223563
    b = a * (1 - flattening)
    first, second = (
        math.atan((1 - flattening) * math.tan(math.radians(value)))
        for value in (latitude, other_latitude)
    )
    sin_first, cos_first = math.sin(first), math.cos(first)
    sin_second, cos_second = math.sin(second), math.cos(second)
    difference = math.radians((other_longitude - longitude + 180) % 360 - 180)
    lam = difference
    for _ in range(100):
        sin_lam, cos_lam = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(
            cos_second * sin_lam, cos_first * sin_second - sin_first * cos_second * cos_lam
        )
        if sin_sigma == 0:
            return 0.0
        cos_sigma = sin_first * sin_second + cos_first * cos_second * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_first * cos_second * sin_lam / sin_sigma
        cos_sq_alpha = max(0.0, 1 - sin_alpha * sin_alpha)
        cos_two_sigma = (
            cos_sigma - 2 * sin_first * sin_second / cos_sq_alpha if cos_sq_alpha > 1e-15 else 0.0
        )
        c = flattening / 16 * cos_sq_alpha * (4 + flattening * (4 - 3 * cos_sq_alpha))
        updated = difference + (1 - c) * flattening * sin_alpha * (
            sigma + c * sin_sigma * (cos_two_sigma + c * cos_sigma * (-1 + 2 * cos_two_sigma**2))
        )
        if abs(updated - lam) <= 1e-12:
            break
        lam = updated
    else:
        raise ValueError("WGS84 distance did not converge for returned transformer geometry")
    u_sq = cos_sq_alpha * (a * a - b * b) / (b * b)
    coefficient_a = 1 + u_sq / 16384 * (4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq)))
    coefficient_b = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))
    delta_sigma = (
        coefficient_b
        * sin_sigma
        * (
            cos_two_sigma
            + coefficient_b
            / 4
            * (
                cos_sigma * (-1 + 2 * cos_two_sigma**2)
                - coefficient_b
                / 6
                * cos_two_sigma
                * (-3 + 4 * sin_sigma**2)
                * (-3 + 4 * cos_two_sigma**2)
            )
        )
    )
    return b * coefficient_a * (sigma - delta_sigma)


async def find_nearest_transformers(
    latitude: float,
    longitude: float,
    radius_meters: float,
    limit: int,
    service_url: str | None,
    token: str | None,
    verify_ssl: bool,
) -> dict:
    """Discover classified point layers, fetch every candidate, and rank globally.

    Any uncertain classification, incomplete query, or malformed geometry aborts
    the request. Results never represent a silently truncated sample.
    """
    service_url = validate_search(latitude, longitude, radius_meters, limit, service_url)
    spatial = {
        "geometry": json.dumps({"x": longitude, "y": latitude, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "distance": radius_meters,
        "units": "esriSRUnit_Meter",
        "spatialRel": "esriSpatialRelIntersects",
    }
    candidates = []
    async with httpx.AsyncClient(timeout=30.0, verify=verify_ssl) as client:
        service = await _request(client, service_url, token)
        layers = service.get("layers")
        if not isinstance(layers, list) or not layers:
            raise ValueError("FeatureServer has no discoverable layer metadata")
        classified = []
        seen = set()
        for entry in layers:
            if not isinstance(entry, dict) or type(entry.get("id")) is not int or entry["id"] < 0:
                raise ValueError("Malformed FeatureServer layer identity")
            layer_id = entry["id"]
            if layer_id in seen:
                raise ValueError("Ambiguous duplicate FeatureServer layer ID")
            seen.add(layer_id)
            url = f"{service_url}/{layer_id}"
            metadata = await _request(client, url, token)
            layer = classify_layer(layer_id, url, metadata, service)
            if layer is not None:
                classified.append(layer)
        if not classified:
            raise ValueError("No transformer classification found in point-layer metadata")
        for layer in classified:
            ids = await _all_ids(client, layer, token, spatial)
            for offset in range(0, len(ids), layer.batch_size):
                for feature, reference in await _batch(
                    client, layer, token, ids[offset : offset + layer.batch_size]
                ):
                    attributes = feature["attributes"]
                    if not any(
                        all(_code_matches(attributes, name, code) for name, code in clause)
                        for clause in layer.clauses
                    ):
                        raise ValueError("Transformer classification changed during retrieval")
                    global_id = _attribute(attributes, layer.global_id_field)
                    if not isinstance(global_id, str) or not global_id.strip():
                        raise ValueError("Missing transformer GlobalID")
                    y, x = _coordinates(feature.get("geometry"), reference)
                    distance = geodesic_distance(latitude, longitude, y, x)
                    if distance <= radius_meters:
                        candidates.append(
                            {
                                "layerId": layer.layer_id,
                                "layerUrl": layer.url,
                                "objectId": _attribute(attributes, layer.object_id_field),
                                "globalId": global_id,
                                "distanceMeters": distance,
                                "coordinates": {"latitude": y, "longitude": x},
                                "attributes": attributes,
                            }
                        )
    candidates.sort(key=lambda item: (item["distanceMeters"], item["layerId"], item["objectId"]))
    nearest = candidates[:limit]
    return {
        "featureServiceUrl": service_url,
        "searchPoint": {"latitude": latitude, "longitude": longitude},
        "radiusMeters": radius_meters,
        "count": len(nearest),
        "nearest": nearest,
    }
