#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import re
from pathlib import Path
from typing import List, Dict, Any

def tokenize_m3u(m3u_text: str) -> List[Dict[str, Any]]:
    """Return list of items: {attrs: {…}, display: str, url: str, raw_extinf: str}"""
    items = []
    lines = [ln.rstrip("\n") for ln in m3u_text.splitlines()]
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            ext = lines[i]
            # Find the first non-comment line after EXTINF as the URL
            j = i + 1
            while j < len(lines) and (not lines[j] or lines[j].startswith("#")):
                j += 1
            url = lines[j].strip() if j < len(lines) else ""

            m = re.match(r'^#EXTINF:[^ ]*\s*(?P<attrs>.*?),(?P<name>.*)$', ext)
            attrs_text = m.group("attrs") if m else ""
            display = (m.group("name").strip() if m else "").strip()

            attrs = {}
            for key, val in re.findall(r'([A-Za-z0-9\-]+)="([^"]*)"', attrs_text):
                attrs[key.lower()] = val

            items.append({"attrs": attrs, "display": display, "url": url, "raw_extinf": ext})
            # next element after url
            i = (j + 1) if j < len(lines) else (i + 1)
        else:
            i += 1
    return items

def write_m3u(items: List[Dict[str, Any]], path: Path) -> None:
    lines = ["#EXTM3U"]
    for it in items:
        attrs = it["attrs"].copy()

        # Pretty-print a consistent subset (preserves others too)
        ordered_keys = ["tvg-id","tvg-name","tvg-chno","tvg-language","tvg-country","group-title","tvg-logo"]
        seen = set(k for k in attrs if k in ordered_keys)

        parts = []
        for k in ordered_keys:
            v = attrs.get(k)
            if v:
                parts.append(f'{k}="{v}"')
        # include any extra attrs that were present originally
        for k,v in attrs.items():
            if k not in seen and v:
                parts.append(f'{k}="{v}"')

        display = it.get("display","")
        url = it.get("url","")
        lines.append(f'#EXTINF:-1 {" ".join(parts)},{display}')
        lines.append(url)
    path.write_text("\n".join(lines), encoding="utf-8")

def load_overrides(path: Path) -> Dict[str, Dict[str, str]]:
    """Load JSON array of override objects and index by id (tvg-id)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Overrides JSON must be an array of objects.")
    by_id = {}
    for obj in data:
        if not isinstance(obj, dict):
            continue
        # Accept case variations in keys
        oid = obj.get("id") or obj.get("ID") or obj.get("tvg_id") or obj.get("tvg-id")
        if not oid:
            continue
        # normalize fields we care about
        display = obj.get("displayName") or obj.get("displayname") or obj.get("name")
        chno    = obj.get("channel") or obj.get("tvg-chno") or obj.get("tvg_chno")
        logo    = obj.get("imageUrl") or obj.get("imageURL") or obj.get("tvg-logo")
        group   = obj.get("groupTitle") or obj.get("group-title") or obj.get("group")
        by_id[str(oid)] = {
            "displayName": display,
            "channel": chno,
            "imageUrl": logo,
            "groupTitle": group
        }
    return by_id

def apply_overrides(items: List[Dict[str, Any]], overrides_by_id: Dict[str, Dict[str, str]], verbose: bool=False) -> int:
    """Apply overrides to matching tvg-id entries. Returns count of modified items."""
    changed = 0
    for it in items:
        tvg_id = it["attrs"].get("tvg-id")
        if not tvg_id:
            continue
        ov = overrides_by_id.get(tvg_id)
        if not ov:
            continue
        before = (it["display"], it["attrs"].get("tvg-chno"), it["attrs"].get("tvg-logo"), it["attrs"].get("group-title"))
        # display name
        if ov.get("displayName"):
            it["display"] = ov["displayName"]
        # tvg-chno
        if ov.get("channel"):
            it["attrs"]["tvg-chno"] = str(ov["channel"])
        # tvg-logo
        if ov.get("imageUrl"):
            it["attrs"]["tvg-logo"] = str(ov["imageUrl"])
        # group-title
        if ov.get("groupTitle"):
            it["attrs"]["group-title"] = str(ov["groupTitle"])

        after = (it["display"], it["attrs"].get("tvg-chno"), it["attrs"].get("tvg-logo"), it["attrs"].get("group-title"))
        if before != after:
            changed += 1
            if verbose:
                print(f'Updated {tvg_id}: {before} => {after}')
    return changed

def main():
    ap = argparse.ArgumentParser(description="Apply JSON overrides to an M3U by tvg-id.")
    ap.add_argument("--m3u", default="channels.m3u", help="Path to channels.m3u (default: channels.m3u in current dir)")
    ap.add_argument("--overrides", default="overrides.json", help="Path to overrides JSON (default: overrides.json in current dir)")
    ap.add_argument("--out", help="Optional output path. If omitted, overwrite input .m3u")
    ap.add_argument("--verbose", action="store_true", help="Print details of changes")
    args = ap.parse_args()

    m3u_path = Path(args.m3u)
    ov_path  = Path(args.overrides)
    out_path = Path(args.out) if args.out else m3u_path

    if not m3u_path.exists():
        raise SystemExit(f"channels.m3u not found: {m3u_path.resolve()}")
    if not ov_path.exists():
        raise SystemExit(f"overrides JSON not found: {ov_path.resolve()}")

    items = tokenize_m3u(m3u_path.read_text(encoding="utf-8", errors="ignore"))
    overrides = load_overrides(ov_path)
    updated = apply_overrides(items, overrides, verbose=args.verbose)
    write_m3u(items, out_path)

    print(f"Applied overrides to {updated} channel(s). Wrote: {out_path}")

if __name__ == "__main__":
    main()
