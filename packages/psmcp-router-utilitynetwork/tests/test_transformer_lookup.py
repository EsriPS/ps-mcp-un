"""Deterministic nearest-transformer contract tests; no live ArcGIS calls."""

import copy
import json
import math
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
import pytest
from fastmcp import Client, FastMCP
from psmcp_router_developer_tools import service as developer
from psmcp_router_utilitynetwork import transformer_lookup as lookup
from psmcp_router_utilitynetwork import utility_network_service as service

from psmcp import server

URL = "https://client-b.invalid/FeatureServer"
GLOBAL_ID = "{00000000-0000-0000-0000-000000000009}"


def layer_metadata(code=42, batch_size=2):
    """A projected native layer with a discovered, non-demo transformer subtype."""
    return {
        "geometryType": "esriGeometryPoint",
        "extent": {"spatialReference": {"wkid": 3857}},
        "objectIdField": "OBJECTID",
        "globalIdField": "GlobalID",
        "typeIdField": "ASSETGROUP",
        "maxRecordCount": batch_size,
        "advancedQueryCapabilities": {
            "supportsPagination": True,
            "supportsOrderBy": True,
            "supportsQueryWithDistance": True,
        },
        "fields": [
            {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            {"name": "GlobalID", "type": "esriFieldTypeGlobalID"},
            {"name": "ASSETGROUP", "type": "esriFieldTypeInteger"},
            {"name": "EquipmentKind", "alias": "Equipment Type", "type": "esriFieldTypeInteger"},
        ],
        "types": [{"id": code, "name": "Distribution Transformer", "domains": {}}],
    }


def feature(object_id=9, latitude=34.0001, longitude=-117, code=42):
    return {
        "attributes": {
            "OBJECTID": object_id,
            "GlobalID": GLOBAL_ID if object_id == 9 else f"{{gid-{object_id}}}",
            "ASSETGROUP": code,
        },
        "geometry": {"x": longitude, "y": latitude},
    }


class FixtureServer:
    """ArcGIS-shaped metadata/count/ID/page responses with inspectable requests."""

    def __init__(self, respx_mock, url=URL, layer_id=27, metadata=None, features=None):
        self.url, self.layer_id = url, layer_id
        self.metadata = metadata if metadata is not None else layer_metadata()
        self.features = features if features is not None else [feature()]
        self.requests = []
        self.id_response = None
        self.page_hook = None
        self.spatial_reference = {"wkid": 4326}
        self.count_override = None
        self.service_route = respx_mock.get(url).mock(
            return_value=httpx.Response(
                200, json={"layers": [{"id": layer_id, "name": "Equipment"}]}
            )
        )
        self.layer_route = respx_mock.get(f"{url}/{layer_id}").mock(
            side_effect=lambda _: httpx.Response(200, json=self.metadata)
        )
        self.query_route = respx_mock.post(f"{url}/{layer_id}/query").mock(side_effect=self.query)

    def query(self, request):
        parameters = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        self.requests.append(parameters)
        if parameters.get("returnCountOnly") == "true":
            data = {
                "count": self.count_override
                if self.count_override is not None
                else len(self.features)
            }
        elif parameters.get("returnIdsOnly") == "true":
            data = (
                self.id_response
                if self.id_response is not None
                else {
                    "objectIdFieldName": "OBJECTID",
                    "objectIds": [item["attributes"]["OBJECTID"] for item in self.features],
                }
            )
        elif "objectIds" in parameters:
            ids = {int(value) for value in parameters["objectIds"].split(",")}
            data = {
                "features": [
                    copy.deepcopy(item)
                    for item in self.features
                    if item["attributes"]["OBJECTID"] in ids
                ],
                "spatialReference": self.spatial_reference,
            }
        else:
            offset, count = int(parameters["resultOffset"]), int(parameters["resultRecordCount"])
            selected = sorted(self.features, key=lambda item: item["attributes"]["OBJECTID"])[
                offset : offset + count
            ]
            data = {
                "features": [
                    {"attributes": {"OBJECTID": item["attributes"]["OBJECTID"]}}
                    for item in selected
                ],
                "exceededTransferLimit": offset + len(selected) < len(self.features),
            }
        if self.page_hook:
            data = self.page_hook(parameters, data)
        return httpx.Response(200, json=data)

    async def run(self, **arguments):
        return await lookup.find_nearest_transformers(
            **{
                "latitude": 34,
                "longitude": -117,
                "radius_meters": 1609.344,
                "limit": 5,
                "service_url": self.url,
                "token": None,
                "verify_ssl": True,
                **arguments,
            }
        )


async def test_golden_output_and_wgs84_request_contract(respx_mock):
    fixture = FixtureServer(respx_mock)
    result = await fixture.run()
    assert result == {
        "featureServiceUrl": URL,
        "searchPoint": {"latitude": 34, "longitude": -117},
        "radiusMeters": 1609.344,
        "count": 1,
        "nearest": [
            {
                "layerId": 27,
                "layerUrl": f"{URL}/27",
                "objectId": 9,
                "globalId": GLOBAL_ID,
                "distanceMeters": pytest.approx(11.092239, abs=0.00001),
                "coordinates": {"latitude": 34.0001, "longitude": -117},
                "attributes": feature()["attributes"],
            }
        ],
    }
    for parameters in fixture.requests[:2]:
        assert parameters["where"] == "(ASSETGROUP = 42)"
        assert parameters["inSR"] == "4326"
        assert parameters["distance"] == "1609.344"
        assert parameters["units"] == "esriSRUnit_Meter"
        assert json.loads(parameters["geometry"]) == {
            "x": -117,
            "y": 34,
            "spatialReference": {"wkid": 4326},
        }
    assert fixture.requests[-1]["outSR"] == "4326"
    assert fixture.requests[-1]["objectIds"] == "9"


async def test_other_service_and_subtype_specific_asset_type_codes(respx_mock):
    metadata = layer_metadata(code=8)
    metadata["types"] = [
        {
            "id": 8,
            "name": "Network Equipment",
            "domains": {
                "EquipmentKind": {
                    "type": "codedValue",
                    "codedValues": [
                        {"code": 71, "name": "Switch"},
                        {"code": 913, "name": "Power Transformer"},
                    ],
                }
            },
        },
        {
            "id": 9,
            "name": "Switch Equipment",
            "domains": {
                "EquipmentKind": {
                    "type": "codedValue",
                    "codedValues": [{"code": 913, "name": "Switch"}],
                }
            },
        },
    ]
    item = feature(code=8)
    item["attributes"]["EquipmentKind"] = 913
    fixture = FixtureServer(
        respx_mock, "https://client-a.invalid/network/FeatureServer", 83, metadata, [item]
    )
    result = await fixture.run()
    assert result["nearest"][0]["layerId"] == 83
    assert fixture.requests[0]["where"] == "(ASSETGROUP = 8 AND EquipmentKind = 913)"


async def test_coded_domain_without_subtypes_and_safe_string_literal(respx_mock):
    metadata = layer_metadata()
    metadata.pop("typeIdField")
    metadata["types"] = []
    field = metadata["fields"][-1]
    field.update(
        type="esriFieldTypeString",
        domain={"type": "codedValue", "codedValues": [{"code": "T'R", "name": "Transformer"}]},
    )
    item = feature()
    item["attributes"]["EquipmentKind"] = "T'R"
    fixture = FixtureServer(respx_mock, metadata=metadata, features=[item])
    assert (await fixture.run())["count"] == 1
    assert fixture.requests[0]["where"] == "(EquipmentKind = 'T''R')"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", float("nan")),
        ("latitude", float("inf")),
        ("latitude", 90.1),
        ("latitude", -90.1),
        ("longitude", 180.1),
        ("longitude", -180.1),
        ("longitude", -float("inf")),
        ("radius_meters", 24.9),
        ("radius_meters", 25000.1),
        ("radius_meters", float("nan")),
        ("limit", 0),
        ("limit", 26),
        ("limit", 1.5),
        ("limit", True),
        ("latitude", True),
        ("radius_meters", "50"),
        ("service_url", ""),
        ("service_url", "https://example.invalid/FeatureServer/3"),
        ("service_url", "https://example.invalid/FeatureServer?token=bad"),
        ("service_url", "https://user:password@example.invalid/FeatureServer"),
    ],
)
async def test_invalid_inputs_fail_before_http(respx_mock, field, value):
    fixture = FixtureServer(respx_mock)
    with pytest.raises(ValueError):
        await fixture.run(**{field: value})
    assert not fixture.service_route.called


@pytest.mark.parametrize(
    ("latitude", "longitude", "radius", "limit"),
    [
        (-90, -180, 25, 1),
        (90, 180, 25000, 25),
    ],
)
def test_inclusive_input_boundaries(latitude, longitude, radius, limit):
    assert lookup.validate_search(latitude, longitude, radius, limit, URL + "/") == URL


@pytest.mark.parametrize(
    "mutation",
    [
        lambda metadata: metadata.pop("fields"),
        lambda metadata: metadata.update(types=[], typeIdField="ASSETGROUP"),
        lambda metadata: metadata["types"][0].update(name="Transformer or Switch"),
        lambda metadata: metadata["types"].append(copy.deepcopy(metadata["types"][0])),
        lambda metadata: metadata.update(typeIdField="MissingField"),
        lambda metadata: metadata.update(maxRecordCount=0),
        lambda metadata: metadata["fields"].pop(1),
        lambda metadata: metadata["fields"].append(
            {"name": "SecondGlobalID", "type": "esriFieldTypeGlobalID"}
        ),
        lambda metadata: metadata["fields"][2].update(name="ASSETGROUP; DROP TABLE"),
        lambda metadata: metadata["advancedQueryCapabilities"].update(
            supportsQueryWithDistance=False
        ),
    ],
)
async def test_invalid_or_ambiguous_metadata_fails_before_candidate_queries(respx_mock, mutation):
    metadata = layer_metadata()
    mutation(metadata)
    fixture = FixtureServer(respx_mock, metadata=metadata)
    with pytest.raises(ValueError):
        await fixture.run()
    assert not fixture.query_route.called


async def test_missing_classification_never_uses_layer_name_or_all_devices(respx_mock):
    metadata = layer_metadata()
    metadata.pop("typeIdField")
    metadata["types"] = []
    metadata["name"] = "Transformers"
    fixture = FixtureServer(respx_mock, metadata=metadata)
    with pytest.raises(ValueError, match="Unknown transformer classification"):
        await fixture.run()
    assert not fixture.query_route.called


async def test_known_non_transformer_metadata_is_not_a_match(respx_mock):
    metadata = layer_metadata()
    metadata["types"][0]["name"] = "Switch"
    fixture = FixtureServer(respx_mock, metadata=metadata)
    with pytest.raises(ValueError, match="No transformer classification"):
        await fixture.run()


@pytest.mark.parametrize(
    "label",
    [
        "Pad Mounted Transformer",
        "Pad-Mounted Transformer",
        "Vault Mounted Transformer",
        "Vault-Mounted Transformer",
    ],
)
@pytest.mark.parametrize("classification", ["subtype", "domain"])
async def test_mounted_transformer_equipment_qualifiers_are_supported(
    respx_mock, label, classification
):
    metadata = layer_metadata()
    if classification == "subtype":
        metadata["types"][0]["name"] = label
    else:
        metadata.pop("typeIdField")
        metadata["types"] = []
        metadata["fields"][2]["domain"] = {
            "type": "codedValue",
            "codedValues": [{"code": 42, "name": label}],
        }
    fixture = FixtureServer(respx_mock, metadata=metadata)
    result = await fixture.run()
    assert result["count"] == 1
    assert result["nearest"][0]["globalId"] == GLOBAL_ID
    assert fixture.requests[0]["where"] == "(ASSETGROUP = 42)"


@pytest.mark.parametrize(
    "label",
    [
        "Transformer Pad",
        "Transformer Vault",
        "Transformer Foundation",
        "Non-Transformer",
        "Pad-Mounted Transformer Pad",
        "Vault Mounted Transformer Vault",
        "Pad Mounted Transformer Inspection",
        "Pad Mounted Transformer or Switch",
    ],
)
async def test_transformer_related_structure_labels_are_not_transformer_equipment(
    respx_mock, label
):
    metadata = layer_metadata()
    metadata["types"][0]["name"] = label
    with pytest.raises(ValueError, match="Ambiguous transformer classification"):
        await FixtureServer(respx_mock, metadata=metadata).run()


async def test_subtype_domain_overrides_field_wide_codes(respx_mock):
    metadata = layer_metadata()
    metadata["types"] = [
        {
            "id": 42,
            "name": "Equipment",
            "domains": {
                "EquipmentKind": {
                    "type": "codedValue",
                    "codedValues": [{"code": 80, "name": "Transformer"}],
                }
            },
        }
    ]
    metadata["fields"][-1]["domain"] = {
        "type": "codedValue",
        "codedValues": [{"code": 1, "name": "Transformer"}],
    }
    item = feature()
    item["attributes"]["EquipmentKind"] = 80
    fixture = FixtureServer(respx_mock, metadata=metadata, features=[item])
    await fixture.run()
    assert fixture.requests[0]["where"] == "(ASSETGROUP = 42 AND EquipmentKind = 80)"


async def test_explicit_inherited_subtype_domain_uses_layer_domain(respx_mock):
    metadata = layer_metadata()
    metadata["types"] = [
        {"id": 42, "name": "Equipment", "domains": {"EquipmentKind": {"type": "inherited"}}}
    ]
    metadata["fields"][-1]["domain"] = {
        "type": "codedValue",
        "codedValues": [{"code": 80, "name": "Transformer"}],
    }
    item = feature()
    item["attributes"]["EquipmentKind"] = 80
    fixture = FixtureServer(respx_mock, metadata=metadata, features=[item])
    await fixture.run()
    assert fixture.requests[0]["where"] == "(ASSETGROUP = 42 AND EquipmentKind = 80)"


@pytest.mark.parametrize(
    "values",
    [
        [{"code": 1, "name": "Transformer"}, {"code": 1, "name": "Switch"}],
        [{"code": "one", "name": "Transformer"}],
        [{"code": 1.5, "name": "Transformer"}],
        [{"code": 1, "name": None}],
        [],
    ],
)
async def test_ambiguous_or_malformed_classification_domains_fail(respx_mock, values):
    metadata = layer_metadata()
    metadata.pop("typeIdField")
    metadata["types"] = []
    metadata["fields"][-1]["domain"] = {"type": "codedValue", "codedValues": values}
    with pytest.raises(ValueError):
        await FixtureServer(respx_mock, metadata=metadata).run()


async def test_ambiguous_domain_fields_are_rejected(respx_mock):
    metadata = layer_metadata()
    metadata.pop("typeIdField")
    metadata["types"] = []
    for field in metadata["fields"][2:]:
        field["domain"] = {
            "type": "codedValue",
            "codedValues": [{"code": 42, "name": "Transformer"}],
        }
    with pytest.raises(ValueError, match="multiple fields"):
        await FixtureServer(respx_mock, metadata=metadata).run()


async def test_all_batches_rank_nearest_beyond_first_batch(respx_mock):
    features = [feature(index, latitude=34 + (6 - index) * 0.001) for index in range(1, 6)]
    fixture = FixtureServer(respx_mock, features=features)
    result = await fixture.run(limit=1)
    assert result["nearest"][0]["objectId"] == 5
    assert [request["objectIds"] for request in fixture.requests if "objectIds" in request] == [
        "1,2",
        "3,4",
        "5",
    ]


async def test_truncated_id_response_uses_complete_ordered_id_pages(respx_mock):
    fixture = FixtureServer(respx_mock, features=[feature(index) for index in range(1, 6)])
    fixture.id_response = {"objectIds": [1, 2], "exceededTransferLimit": True}
    result = await fixture.run()
    assert result["count"] == 5
    pages = [request for request in fixture.requests if "resultOffset" in request]
    assert [request["resultOffset"] for request in pages] == ["0", "2", "4"]
    assert all(
        request["outFields"] == "OBJECTID" and request["orderByFields"] == "OBJECTID ASC"
        for request in pages
    )


async def test_short_ids_without_flag_still_require_complete_retrieval(respx_mock):
    fixture = FixtureServer(respx_mock, features=[feature(1), feature(2), feature(3)])
    fixture.id_response = {"objectIds": [1]}
    assert (await fixture.run())["count"] == 3
    assert any("resultOffset" in request for request in fixture.requests)


async def test_truncated_ids_without_pagination_fail(respx_mock):
    metadata = layer_metadata()
    metadata["advancedQueryCapabilities"]["supportsPagination"] = False
    fixture = FixtureServer(respx_mock, metadata=metadata)
    fixture.id_response = {"objectIds": [], "exceededTransferLimit": True}
    with pytest.raises(ValueError, match="pagination"):
        await fixture.run()


@pytest.mark.parametrize("mode", ["empty", "repeat", "early_end", "still_truncated"])
async def test_invalid_id_pages_fail_instead_of_partial_success(respx_mock, mode):
    fixture = FixtureServer(respx_mock, features=[feature(1), feature(2), feature(3)])
    fixture.id_response = {"objectIds": [], "exceededTransferLimit": True}

    def hook(parameters, data):
        if parameters.get("resultOffset") == "2":
            if mode == "empty":
                data["features"] = []
            elif mode == "repeat":
                data["features"] = [{"attributes": {"OBJECTID": 1}}]
            elif mode == "still_truncated":
                data["exceededTransferLimit"] = True
        if mode == "early_end" and parameters.get("resultOffset") == "0":
            data["exceededTransferLimit"] = False
        return data

    fixture.page_hook = hook
    with pytest.raises(ValueError):
        await fixture.run()
    assert not any("objectIds" in request for request in fixture.requests)


async def test_truncated_feature_batches_are_split_and_fully_verified(respx_mock):
    fixture = FixtureServer(respx_mock, features=[feature(1), feature(2)])
    fixture.page_hook = lambda parameters, data: (
        {**data, "exceededTransferLimit": True} if parameters.get("objectIds") == "1,2" else data
    )
    assert (await fixture.run())["count"] == 2
    assert [request["objectIds"] for request in fixture.requests if "objectIds" in request] == [
        "1,2",
        "1",
        "2",
    ]


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unexpected", "truncated"])
async def test_invalid_feature_batches_abort_all_results(respx_mock, mode):
    fixture = FixtureServer(respx_mock, features=[feature(1), feature(2), feature(3)])

    def hook(parameters, data):
        if parameters.get("objectIds") == "3":
            if mode == "missing":
                data["features"] = []
            elif mode == "duplicate":
                data["features"] *= 2
            elif mode == "unexpected":
                data["features"][0]["attributes"]["OBJECTID"] = 99
            else:
                data["exceededTransferLimit"] = True
        return data

    fixture.page_hook = hook
    with pytest.raises(ValueError):
        await fixture.run()


@pytest.mark.parametrize(
    "mode",
    [
        "missing_geometry",
        "missing_sr",
        "projected_sr",
        "invalid_coordinate",
        "nan",
        "missing_globalid",
        "wrong_class",
    ],
)
async def test_invalid_geometry_identity_or_classification_fails(respx_mock, mode):
    fixture = FixtureServer(respx_mock)
    if mode == "missing_geometry":
        fixture.features[0].pop("geometry")
    elif mode == "missing_sr":
        fixture.spatial_reference = None
    elif mode == "projected_sr":
        fixture.spatial_reference = {"wkid": 3857}
    elif mode == "invalid_coordinate":
        fixture.features[0]["geometry"]["x"] = 2000000
    elif mode == "nan":
        # JSON cannot encode NaN through httpx; use a nonnumeric coordinate.
        fixture.features[0]["geometry"]["y"] = "NaN"
    elif mode == "missing_globalid":
        fixture.features[0]["attributes"].pop("GlobalID")
    else:
        fixture.features[0]["attributes"]["ASSETGROUP"] = 1
    with pytest.raises(ValueError):
        await fixture.run()


async def test_geometry_level_wgs84_and_outside_radius_filter(respx_mock):
    fixture = FixtureServer(respx_mock, features=[feature(1), feature(2, latitude=35)])
    fixture.spatial_reference = None
    for item in fixture.features:
        item["geometry"]["spatialReference"] = {"wkid": 4326}
    result = await fixture.run()
    assert result["count"] == 1 and result["nearest"][0]["objectId"] == 1


async def test_empty_search_is_valid(respx_mock):
    fixture = FixtureServer(respx_mock, features=[])
    result = await fixture.run()
    assert result["count"] == 0 and result["nearest"] == []
    assert len(fixture.requests) == 2


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"objectIds": None},
        {"objectIds": [9, 9]},
        {"objectIds": ["9"]},
        {"objectIds": [9], "objectIdFieldName": "wrong"},
    ],
)
async def test_invalid_id_response_is_not_silent_empty(respx_mock, response):
    fixture = FixtureServer(respx_mock)
    fixture.id_response = response
    with pytest.raises(ValueError):
        await fixture.run()


async def test_empty_arcgis_null_ids_are_valid_when_count_is_zero(respx_mock):
    fixture = FixtureServer(respx_mock, features=[])
    fixture.id_response = {"objectIds": None}
    assert (await fixture.run())["nearest"] == []


async def test_unknown_point_layer_prevents_partial_global_ranking(respx_mock):
    fixture = FixtureServer(respx_mock)
    fixture.service_route.mock(
        return_value=httpx.Response(200, json={"layers": [{"id": 27}, {"id": 90}]})
    )
    unknown = layer_metadata()
    unknown.pop("typeIdField")
    unknown["types"] = []
    respx_mock.get(f"{URL}/90").mock(return_value=httpx.Response(200, json=unknown))
    with pytest.raises(ValueError, match="Unknown transformer classification"):
        await fixture.run()
    assert not fixture.query_route.called


async def test_arcgis_error_after_first_batch_does_not_return_partial_success(respx_mock):
    fixture = FixtureServer(respx_mock, features=[feature(1), feature(2), feature(3)])
    fixture.page_hook = lambda parameters, data: (
        {"error": {"code": 498}} if parameters.get("objectIds") == "3" else data
    )
    with pytest.raises(ValueError, match="498"):
        await fixture.run()


async def test_conflicting_geometry_spatial_reference_is_rejected(respx_mock):
    fixture = FixtureServer(respx_mock)
    fixture.features[0]["geometry"]["spatialReference"] = {"wkid": 3857}
    with pytest.raises(ValueError, match="outSR=4326"):
        await fixture.run()


async def test_multiple_layers_stable_distance_layer_object_id_ties(respx_mock):
    first = FixtureServer(respx_mock, layer_id=83, features=[feature(4), feature(2)])
    FixtureServer(respx_mock, layer_id=27, features=[feature(9)])
    first.service_route.mock(
        return_value=httpx.Response(200, json={"layers": [{"id": 83}, {"id": 27}, {"id": 60}]})
    )
    respx_mock.get(f"{URL}/60").mock(
        return_value=httpx.Response(200, json={"geometryType": "esriGeometryPolyline"})
    )
    result = await first.run()
    assert [(item["layerId"], item["objectId"]) for item in result["nearest"]] == [
        (27, 9),
        (83, 2),
        (83, 4),
    ]


@pytest.mark.parametrize(
    ("status", "body"),
    [(401, {}), (500, {}), (200, {"error": {"code": 498, "message": "sensitive server detail"}})],
)
async def test_auth_http_and_arcgis_errors_are_visible_and_redacted(respx_mock, status, body):
    fixture = FixtureServer(respx_mock)
    fixture.layer_route.mock(return_value=httpx.Response(status, json=body))
    with pytest.raises(ValueError) as error:
        await fixture.run(token="fixture-secret")
    assert "fixture-secret" not in str(error.value)
    assert "sensitive server detail" not in str(error.value)
    assert not fixture.query_route.called


async def test_http_timeout_fails_without_returning_partial_candidates(respx_mock):
    fixture = FixtureServer(respx_mock)
    fixture.query_route.mock(side_effect=httpx.ReadTimeout("fixture timeout"))
    with pytest.raises(ValueError, match="HTTP request failed"):
        await fixture.run()


async def test_tool_resolves_token_environment_and_ssl(monkeypatch):
    mocked = AsyncMock(return_value={"count": 0})
    monkeypatch.setenv("UTILITY_NETWORK_URL", URL)
    monkeypatch.setattr(service, "resolve_token", lambda token: "resolved-fixture-token")
    monkeypatch.setattr(service, "VERIFY_SSL", False)
    monkeypatch.setattr(service, "find_nearest_transformers", mocked)
    assert await service.network_find_nearest_transformers(34, -117) == {"count": 0}
    mocked.assert_awaited_once_with(34, -117, 1609.344, 5, URL, "resolved-fixture-token", False)


async def test_authentication_header_never_puts_token_in_query_urls(respx_mock):
    fixture = FixtureServer(respx_mock)
    await fixture.run(token="fixture-token")
    for call in respx_mock.calls:
        assert call.request.headers["X-Esri-Authorization"] == "Bearer fixture-token"
        assert "token" not in call.request.url.params
        assert "fixture-token" not in str(call.request.url)


async def test_actual_root_schema_wire_result_and_skill_publication(respx_mock, monkeypatch):
    FixtureServer(respx_mock)
    monkeypatch.setattr(developer, "_skill_registry", None)
    monkeypatch.setenv("ENABLED_ROUTERS", "developer_tools,utilitynetwork")
    monkeypatch.setenv("UTILITY_NETWORK_URL", URL)
    monkeypatch.setattr(service, "resolve_token", lambda token: None)
    monkeypatch.setenv(
        "DEVTOOLS_SKILL_SOURCES",
        json.dumps(
            [{"type": "package", "package": "psmcp_router_utilitynetwork", "path": "skills"}]
        ),
    )
    root = FastMCP("transformer-contract")
    server._load_and_mount_routers(root)
    async with Client(root) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        schema = tools["network_find_nearest_transformers"].inputSchema
        assert set(schema["properties"]) == {
            "latitude",
            "longitude",
            "radius_meters",
            "limit",
            "network_service_url",
            "token",
        }
        assert schema["required"] == ["latitude", "longitude"]
        assert schema["properties"]["radius_meters"]["default"] == 1609.344
        assert schema["properties"]["limit"]["type"] == "integer"
        result = await client.call_tool(
            "network_find_nearest_transformers", {"latitude": 34, "longitude": -117}
        )
        assert result.structured_content["nearest"][0]["globalId"] == GLOBAL_ID
        assert json.loads(result.content[0].text)["featureServiceUrl"] == URL
        names = {
            entry["name"]
            for entry in (await client.call_tool("list_skills", {"tags": ["agent-runtime"]})).data[
                "skills"
            ]
        }
        assert "utility-transformer-lookup" in names
        skill = (await client.call_tool("get_skill", {"name": "utility-transformer-lookup"})).data
        assert skill["requires_tools"] == [
            "network_initialize_session",
            "network_find_nearest_transformers",
        ]
        for invalid in ({"limit": 1.0}, {"limit": True}, {"latitude": True}):
            error = await client.call_tool(
                "network_find_nearest_transformers",
                {"latitude": 34, "longitude": -117, **invalid},
                raise_on_error=False,
            )
            assert error.is_error


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ((0, 0), (0, 0), 0),
        ((0, 0), (0, 0.001), 111.3194908),
        ((34, -117), (34.0001, -117), 11.092239),
        ((0, 179.999), (0, -179.999), 222.6389816),
    ],
)
def test_wgs84_geodesic_distances(start, end, expected):
    assert lookup.geodesic_distance(*start, *end) == pytest.approx(expected, abs=0.0001)
    assert math.isfinite(lookup.geodesic_distance(*start, *end))
