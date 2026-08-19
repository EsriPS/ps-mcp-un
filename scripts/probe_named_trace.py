"""Standalone diagnostic for the `network_named_trace` tool.

Reproduces / diagnoses the `-2147208614 "No starting points found."` error by
running a named trace in-process (fast, no MCP round-trip) against a real start
feature and sweeping every terminal so you can see which start-point/terminal
combinations the trace engine accepts vs. rejects.

Run from the ps-mcp-fork root so .env is picked up:

    # auto-pick a distribution transformer, sweep all its terminals
    uv run python scripts/probe_named_trace.py

    # target a specific feature + named trace
    uv run python scripts/probe_named_trace.py \
        --global-id "{D1EB95AC-E4FA-450B-9C35-939F85C34B46}" \
        --named-trace "Downstream - XFR Load and Customer Count"

    # list candidate transformer start features and exit
    uv run python scripts/probe_named_trace.py --list-transformers
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from arcgis.features import FeatureLayerCollection
from arcgis.features._utility import UtilityNetworkManager

from psmcp_router_utilitynetwork import utility_network_service as svc

# High Voltage Transformer + Distribution Transformer are the usual balanced-
# distribution start features. Asset group codes vary by dataset, so we match on
# the human-readable asset id prefix instead and let the sweep reveal validity.
_TRANSFORMER_HINTS = ("XFR", "TRANSFORMER", "TRANS")
_ELECTRIC_DEVICE_LAYER = "Electric Device"


# region --- helpers -----------------------------------------------------------


def _short(value: Any, limit: int = 300) -> str:
    """Compact single-line preview of an arbitrary value for logging."""
    text = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + " ..."


def _error_of(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the ArcGIS error block from a raw trace response, if any."""
    if not isinstance(raw, dict):
        return None
    if raw.get("success") is False or "error" in raw:
        return raw.get("error", {"unknown": raw})
    return None


def _list_transformers(gis, url: str, limit: int = 20) -> None:
    """Print candidate transformer start features (assetid + globalid)."""
    layer = svc._find_layer(gis, url, _ELECTRIC_DEVICE_LAYER)
    like = " OR ".join(f"UPPER(assetid) LIKE '%{h}%'" for h in _TRANSFORMER_HINTS)
    feats = layer.query(
        where=like,
        out_fields="objectid,assetid,assetgroup,assettype,globalid,subnetworkname",
        return_geometry=False,
        result_record_count=limit,
    ).features
    print(f"\nCandidate transformer start features ({len(feats)} shown):")
    for f in feats:
        a = {k.lower(): v for k, v in f.attributes.items()}
        print(
            f"  assetid={a.get('assetid'):<14} "
            f"AG={a.get('assetgroup')} AT={a.get('assettype')} "
            f"subnet={a.get('subnetworkname')!r} "
            f"globalid={a.get('globalid')}"
        )


def _pick_transformer(gis, url: str) -> str | None:
    """Return the GlobalID of the first transformer-like device found."""
    layer = svc._find_layer(gis, url, _ELECTRIC_DEVICE_LAYER)
    like = " OR ".join(f"UPPER(assetid) LIKE '%{h}%'" for h in _TRANSFORMER_HINTS)
    feats = layer.query(
        where=like,
        out_fields="assetid,globalid",
        return_geometry=False,
        result_record_count=1,
    ).features
    if not feats:
        return None
    a = {k.lower(): v for k, v in feats[0].attributes.items()}
    print(f"Auto-picked start feature: assetid={a.get('assetid')} globalid={a.get('globalid')}")
    return str(a.get("globalid"))


# endregion


# region --- probe -------------------------------------------------------------


def _run_once(
    gis,
    url: str,
    named_trace: str,
    global_id: str,
    terminal_id: int | None,
) -> None:
    """Run the named trace once for a given terminal and print the outcome."""
    label = f"terminal_id={terminal_id}" if terminal_id is not None else "terminal_id=<none>"
    t = time.perf_counter()
    try:
        raw = svc.run_named_trace(
            gis=gis,
            network_service_url=url,
            named_trace_name=named_trace,
            global_id=global_id,
            trace_type=None,  # use the configuration's persisted type
            terminal_id=terminal_id,
        )
        dt = time.perf_counter() - t
        err = _error_of(raw)
        if err:
            print(f"  [{label}] FAIL {dt:.2f}s -> {_short(err)}")
        else:
            results = raw.get("traceResults", raw)
            elements = results.get("elements") if isinstance(results, dict) else None
            n = len(elements) if isinstance(elements, list) else "?"
            print(f"  [{label}] OK   {dt:.2f}s -> elements={n} keys={list(results) if isinstance(results, dict) else type(results).__name__}")
    except Exception as exc:  # noqa: BLE001 - probe reports every failure verbatim
        print(f"  [{label}] RAISED {time.perf_counter() - t:.2f}s -> {exc!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-id", help="GlobalID of the start feature.")
    parser.add_argument(
        "--named-trace",
        default="Downstream - XFR Load and Customer Count",
        help="Named trace configuration to run.",
    )
    parser.add_argument(
        "--list-transformers",
        action="store_true",
        help="List candidate transformer start features and exit.",
    )
    args = parser.parse_args()

    url = svc.os.getenv("UTILITY_NETWORK_URL")
    print(f"UTILITY_NETWORK_URL = {url}")
    print(f"ARCGIS_PORTAL_URL   = {svc.ARCGIS_PORTAL_URL}")

    t = time.perf_counter()
    gis = svc._connect_gis(None)
    print(f"_connect_gis: {time.perf_counter() - t:.2f}s")

    if args.list_transformers:
        _list_transformers(gis, url)
        return

    # Show the available named traces so we know we picked a real one.
    un_manager = UtilityNetworkManager(svc._utility_network_url(url), gis=gis)
    configs = un_manager.trace_configurations().query().get("traceConfigurations", []) or []
    names = [str(c.get("title") or c.get("name") or "") for c in configs]
    print(f"\nAvailable named traces ({len(names)}): {names}")
    match = next((n for n in names if n.strip().lower() == args.named_trace.strip().lower()), None)
    if match is None:
        print(f"!! '{args.named_trace}' is NOT one of the configured named traces. Aborting.")
        return
    cfg = next(c for c in configs if str(c.get("title") or c.get("name") or "") == match)
    print(f"Using named trace '{match}' (persisted traceType={cfg.get('traceType')!r}).")

    global_id = args.global_id or _pick_transformer(gis, url)
    if not global_id:
        print("!! No start feature available. Try --list-transformers.")
        return

    # Inspect the start feature's terminals so we can sweep every one.
    print(f"\nInspecting terminals for {global_id} ...")
    try:
        info = svc.get_device_terminals(gis, url, global_id)
    except Exception as exc:  # noqa: BLE001
        print(f"  get_device_terminals raised: {exc!r}")
        info = {}
    terminals = info.get("terminals", []) or []
    print(
        f"  assetGroup={info.get('assetGroupName')!r} "
        f"assetType={info.get('assetTypeName')!r} "
        f"usageType={info.get('usageType')!r}"
    )
    for term in terminals:
        print(
            f"    terminalId={term.get('terminalId')} "
            f"name={term.get('terminalName')!r} "
            f"recommendedFor={term.get('recommendedFor')!r}"
        )

    # Sweep: no terminal, then every terminal id. This reveals whether the
    # feature is traceable at all and which terminal the engine accepts.
    print(f"\nRunning '{match}' from {global_id}:")
    _run_once(gis, url, match, global_id, None)
    for term in terminals:
        _run_once(gis, url, match, global_id, term.get("terminalId"))


# endregion


if __name__ == "__main__":
    main()
