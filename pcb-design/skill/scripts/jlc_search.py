#!/usr/bin/env python3
# Purpose: search JLC's parts library live — LCSC code, Basic/Preferred/Extended, assembly type (economic vs
#          Standard-only), stock, price, package; optionally download the datasheet into docs/datasheets/.
# Usage:   python3 -I scripts/jlc_search.py "<keyword or Cxxxxx>" [-n 10] [--basic] [--economic] [--json]
#                                           [--datasheet docs/datasheets]
# Pitfalls: undocumented endpoint, may change or rate-limit; on failure search jlcpcb.com/parts by hand and
#           record the date. componentProductType: 2 was observed on a Standard-only part (hypothesis) — the
#           parts page label is the authority; record JLC_Assembly from what you actually see.
import argparse, json, os, re, sys, urllib.request

URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"


def category(p):
    if p.get("componentLibraryType") == "base":
        return "Basic"
    if p.get("preferredComponentFlag"):
        return "Preferred"
    return "Extended"


def assembly(p):
    """Economic & Standard vs Standard only. Field semantics are not documented by JLC; 2 has been seen on a
    Standard-only part. Anything else is reported as the raw value so the reader checks the page."""
    t = p.get("componentProductType")
    if t == 2:
        return "STD-ONLY?"
    if t in (1, None):
        return "eco/std"
    return f"type={t}"


def search(keyword, n):
    body = json.dumps({"keyword": keyword, "currentPage": 1, "pageSize": n}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    return (d.get("data") or {}).get("componentPageInfo", {}).get("list") or []


def price(p, qty):
    for t in p.get("componentPrices") or []:
        if t["startNumber"] <= qty and (t["endNumber"] == -1 or qty <= t["endNumber"]):
            return t["productPrice"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--basic", action="store_true", help="only Basic/Preferred")
    ap.add_argument("--economic", action="store_true", help="hide parts that look Standard-only")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--datasheet", metavar="DIR", help="download each result's datasheet PDF into DIR")
    a = ap.parse_args()
    try:
        rows = search(a.keyword, a.n)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"JLC API failed ({e}). Search jlcpcb.com/parts by hand and record category, assembly type, "
                 f"stock and the date in the symbol fields.")
    if a.basic:
        rows = [p for p in rows if category(p) != "Extended"]
    if a.economic:
        rows = [p for p in rows if assembly(p) != "STD-ONLY?"]
    if a.json:
        json.dump(rows, sys.stdout, indent=1)
        return
    for p in rows:
        print(f'{p["componentCode"]:>9}  {category(p):9}  {assembly(p):10}  stock {p.get("stockCount", 0):>7}  '
              f'${price(p, 10) or 0:.4f}  {p.get("componentModelEn", "")[:28]:28}  '
              f'{p.get("componentSpecificationEn", "")[:14]:14}  {p.get("describe", "")[:60]}')
        if a.datasheet:
            url = p.get("dataManualUrl") or p.get("datasheetUrl")
            if url:
                os.makedirs(a.datasheet, exist_ok=True)
                brand = re.sub(r"[^A-Za-z0-9]+", "", p.get("componentBrandEn", "") or "")[:20]
                mpn = re.sub(r"[^A-Za-z0-9._-]+", "_", p.get("componentModelEn", "") or p["componentCode"])
                dst = os.path.join(a.datasheet, f"{brand}_{mpn}.pdf")
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
                        f.write(r.read())
                    print(f"           datasheet -> {dst}")
                except Exception as e:  # noqa: BLE001
                    print(f"           datasheet download failed ({e}): {url}")
            else:
                print("           no datasheet URL in the API record — fetch from the parts page")


if __name__ == "__main__":
    main()
