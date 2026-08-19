"""Manual probe: how long does the UN data-element load actually take?

Run from the ps-mcp-fork root so .env is picked up:
    uv run python scripts/probe_data_element.py
"""

from __future__ import annotations

import time

from arcgis.features import FeatureLayerCollection

from psmcp_router_utilitynetwork import utility_network_service as svc


def main() -> None:
    url = svc.os.getenv("UTILITY_NETWORK_URL")
    print(f"UTILITY_NETWORK_URL = {url}")
    print(f"ARCGIS_PORTAL_URL   = {svc.ARCGIS_PORTAL_URL}")
    print(f"VERIFY_SSL          = {svc.VERIFY_SSL}")

    t = time.perf_counter()
    gis = svc._connect_gis(None)
    print(f"[1] _connect_gis: {time.perf_counter() - t:.2f}s")

    t = time.perf_counter()
    flc = FeatureLayerCollection(url.rstrip("/"), gis=gis)
    print(f"[2] FeatureLayerCollection(): {time.perf_counter() - t:.2f}s")

    t = time.perf_counter()
    controller = dict(flc.properties.get("controllerDatasetLayers", {}) or {})
    un_layer_id = controller.get("utilityNetworkLayerId")
    print(f"[3] flc.properties load: {time.perf_counter() - t:.2f}s (un_layer_id={un_layer_id})")

    # Raw REST call to queryDataElements so we can see the actual HTTP round-trip
    # and whatever the server returns (including an error body).
    t = time.perf_counter()
    rest_url = f"{url.rstrip('/')}/queryDataElements"
    params = {"layers": f"[{un_layer_id}]", "f": "json"}
    try:
        raw = gis._con.post(rest_url, params)
        dt = time.perf_counter() - t
        keys = list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__
        print(f"[4] RAW queryDataElements POST: {dt:.2f}s -> top-level keys: {keys}")
        if isinstance(raw, dict) and "error" in raw:
            print(f"    SERVER ERROR: {raw['error']}")
        elems = raw.get("layerDataElements") if isinstance(raw, dict) else None
        if elems:
            de = elems[0].get("dataElement", {})
            print(
                f"    domainNetworks={len(de.get('domainNetworks', []))} "
                f"terminalConfigurations={len(de.get('terminalConfigurations', []))}"
            )
    except Exception as exc:  # noqa: BLE001 - probe should report any failure
        print(f"[4] RAW queryDataElements POST raised after {time.perf_counter() - t:.2f}s: {exc!r}")

    # Now the arcgis python wrapper the tool actually uses.
    t = time.perf_counter()
    try:
        result = flc.query_data_elements([un_layer_id])
        print(f"[5] flc.query_data_elements(): {time.perf_counter() - t:.2f}s -> {type(result).__name__}")
    except Exception as exc:  # noqa: BLE001
        print(f"[5] flc.query_data_elements() raised after {time.perf_counter() - t:.2f}s: {exc!r}")

    # Time building layers_by_id (accesses lyr.properties.id per layer — may lazy-load).
    t = time.perf_counter()
    try:
        layers_by_id = {int(lyr.properties.id): lyr for lyr in flc.layers}
        print(f"[6] build layers_by_id ({len(layers_by_id)} layers): {time.perf_counter() - t:.2f}s")
    except Exception as exc:  # noqa: BLE001
        print(f"[6] build layers_by_id raised after {time.perf_counter() - t:.2f}s: {exc!r}")
        return

    # Grab a real Electric Device GlobalID (layer 3) to exercise the scan loop.
    sample_gid = None
    device_layer = layers_by_id.get(3)
    if device_layer is not None:
        t = time.perf_counter()
        feats = device_layer.query(where="1=1", out_fields="globalid", return_geometry=False, result_record_count=1).features
        print(f"[7] sample device query: {time.perf_counter() - t:.2f}s -> {len(feats)} feature(s)")
        if feats:
            attrs = {k.lower(): v for k, v in feats[0].attributes.items()}
            sample_gid = attrs.get("globalid")
    print(f"    sample GlobalID = {sample_gid}")

    if sample_gid:
        t = time.perf_counter()
        try:
            res = svc.get_device_terminals(gis, url, sample_gid)
            print(
                f"[8] get_device_terminals(): {time.perf_counter() - t:.2f}s -> "
                f"terminals={res.get('terminalCount')} isDevice={res.get('isDevice')}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[8] get_device_terminals() raised after {time.perf_counter() - t:.2f}s: {exc!r}")


if __name__ == "__main__":
    main()
