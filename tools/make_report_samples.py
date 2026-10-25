"""Generate the bundled SAMPLE Power BI reports (PBIR + a thin PBIR-Legacy report).

Synthetic demo content only. Run: python tools/make_report_samples.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

PBI = Path(__file__).resolve().parents[1] / "lineagelens" / "samples" / "powerbi"
VIS_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"


def col(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def meas(entity, prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def agg(entity, prop, fn=0):
    return {"Aggregation": {"Expression": col(entity, prop), "Function": fn}}


def hier(entity, hierarchy, level):
    return {"HierarchyLevel": {"Expression": {"Hierarchy": {"Expression": {"SourceRef": {"Entity": entity}}, "Hierarchy": hierarchy}}, "Level": level}}


def proj(field, active=None):
    kind = next(iter(field))
    if kind == "Aggregation":
        inner = field["Aggregation"]["Expression"]["Column"]
        fn = {0: "Sum", 1: "Avg", 2: "Count", 3: "Min", 4: "Max"}[field["Aggregation"]["Function"]]
        ref = f"{fn}({inner['Expression']['SourceRef']['Entity']}.{inner['Property']})"
        native = f"{fn} of {inner['Property']}"
    elif kind == "HierarchyLevel":
        h = field["HierarchyLevel"]
        ent = h["Expression"]["Hierarchy"]["Expression"]["SourceRef"]["Entity"]
        ref = f"{ent}.{h['Expression']['Hierarchy']['Hierarchy']}.{h['Level']}"
        native = h["Level"]
    else:
        d = field[kind]
        ref = f"{d['Expression']['SourceRef']['Entity']}.{d['Property']}"
        native = d["Property"]
    p = {"field": field, "queryRef": ref, "nativeQueryRef": native}
    if active:
        p["active"] = True
    return p


def title(text):
    return {"title": [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{text}'"}}}}}]}


def cat_filter(name, field, values=None):
    f = {"name": name, "field": field, "type": "Categorical"}
    if values:
        f["filter"] = {"Version": 2, "From": [{"Name": "x", "Entity": next(iter(field.values()))["Expression"]["SourceRef"]["Entity"], "Type": 0}],
                       "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "x"}}, "Property": next(iter(field.values()))["Property"]}}],
                                                       "Values": [[{"Literal": {"Value": f"'{v}'"}}] for v in values]}}}]}
    return f


def visual(name, vtype, roles: dict, x, y, w, h, ttl=None, sort=None, filters=None, objects=None, z=0):
    v = {"$schema": VIS_SCHEMA, "name": name, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
         "visual": {"visualType": vtype, "query": {"queryState": {r: {"projections": [proj(f) for f in fs]} for r, fs in roles.items()}}, "drillFilterOtherVisuals": True}}
    if sort:
        v["visual"]["query"]["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}], "isDefaultSort": False}
    if ttl:
        v["visual"]["visualContainerObjects"] = title(ttl)
    if objects:
        v["visual"]["objects"] = objects
    if filters:
        v["filterConfig"] = {"filters": filters}
    return v


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def retail_report():
    root = PBI / "RetailSales.Report"
    if root.exists():
        shutil.rmtree(root)
    write(root / "definition.pbir", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                                     "version": "4.0", "datasetReference": {"byPath": {"path": "../RetailSales.SemanticModel"}}})
    d = root / "definition"
    write(d / "version.json", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write(d / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU10", "type": "SharedResources"}},
        "filterConfig": {"filters": [cat_filter("rptYear", col("Date", "Year"))]},
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True}})
    write(d / "reportExtensions.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/reportExtension/1.0.0/schema.json",
        "name": "extension",
        "entities": [{"name": "Sales", "measures": [
            {"name": "Net Sales Label", "dataType": "Text", "expression": "\"Net sales: \" & FORMAT([Total Net Sales], \"$#,0\")", "references": {"measures": [{"entity": "Sales", "name": "Total Net Sales"}]}},
            {"name": "Discount Alert Colour", "dataType": "Text", "expression": "IF([Discount %] > 0.15, \"#D64545\", \"#2E7D32\")"}]}]})
    pages = {
        "a1b2c3d4e5f60718": ("Executive Overview", [
            visual("c0ffee000000000001", "card", {"Values": [meas("Sales", "Total Net Sales")]}, 20, 20, 280, 140, "Net Sales", z=1000,
                   objects={"labels": [{"properties": {"color": {"solid": {"color": {"expr": meas("Sales", "Discount Alert Colour")}}}}}]}),
            visual("c0ffee000000000002", "card", {"Values": [meas("Sales", "Order Count")]}, 320, 20, 280, 140, "Orders", z=2000),
            visual("c0ffee000000000003", "card", {"Values": [meas("Sales", "Avg Order Value")]}, 620, 20, 280, 140, "Avg Order Value", z=3000),
            visual("c0ffee000000000004", "kpi", {"Indicator": [meas("Sales", "Net Sales YoY %")], "TrendLine": [col("Date", "Date")]}, 920, 20, 340, 140, "Net Sales YoY", z=4000),
            visual("c0ffee000000000005", "lineChart", {"Category": [hier("Date", "Date Hierarchy", "Year"), hier("Date", "Date Hierarchy", "Month")],
                                                         "Y": [meas("Sales", "Total Net Sales"), meas("Sales", "Net Sales PY")]},
                   20, 180, 840, 360, "Net Sales vs Prior Year", z=5000),
            visual("c0ffee000000000006", "slicer", {"Values": [col("Store", "Sales Region")]}, 880, 180, 380, 360, "Region", z=6000),
        ], [cat_filter("pgStatus", col("Sales", "Discount Band"))]),
        "b2c3d4e5f6071829": ("Product Performance", [
            visual("beef00000000000001", "clusteredBarChart", {"Category": [col("Product", "Product Category")], "Y": [meas("Sales", "Total Net Sales")]},
                   20, 20, 600, 340, "Net Sales by Category", sort=(meas("Sales", "Total Net Sales"), "Descending"), z=1000),
            visual("beef00000000000002", "tableEx", {"Values": [col("Product", "Product Name"), col("Product", "Price Band"), meas("Sales", "Total Net Sales"), meas("Sales", "Discount %"), meas("Sales", "Premium Sales")]},
                   640, 20, 620, 340, "Product Detail", z=2000,
                   objects={"values": [{"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {"Input": meas("Sales", "Discount %"),
                                                                                                                   "FillRule": {"linearGradient2": {"min": {"color": {"Literal": {"Value": "'#FFFFFF'"}}}, "max": {"color": {"Literal": {"Value": "'#D64545'"}}}}}}}}}}},
                                        "selector": {"metadata": "Sales.Discount %"}}]}),
            visual("beef00000000000003", "pivotTable", {"Rows": [col("Customer", "Customer Tier")], "Columns": [col("Time Intelligence", "Time Calculation")], "Values": [col("Metric Selector", "Metric Selector")]},
                   20, 380, 820, 320, "Metric by Customer Tier", z=3000),
            visual("beef00000000000004", "slicer", {"Values": [col("Metric Selector", "Metric Selector")]}, 860, 380, 400, 320, "Choose metric", z=4000),
        ], [cat_filter("pgCategory", col("Product", "Product Category"), ["Outdoor", "Footwear", "Apparel"])]),
        "c3d4e5f60718293a": ("Customer Insights", [
            visual("f00d00000000000001", "columnChart", {"Category": [col("Customer", "Customer Segment")], "Y": [agg("Sales", "Quantity", 0)]},
                   20, 20, 620, 340, "Units by Segment", z=1000),
            visual("f00d00000000000002", "tableEx", {"Values": [col("Customer", "Customer Name"), col("Customer", "Country"), meas("Sales", "Total Net Sales"), meas("Sales", "Total Discount")]},
                   660, 20, 600, 340, "Top Customers", sort=(meas("Sales", "Total Net Sales"), "Descending"), z=2000,
                   filters=[cat_filter("visDiscount", col("Sales", "Discount Band"), ["High", "Low"])]),
            visual("f00d00000000000003", "card", {"Values": [meas("Sales", "Net Sales Label")]}, 20, 380, 400, 160, "Headline", z=3000),
        ], []),
    }
    write(d / "pages" / "pages.json", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
                                       "pageOrder": list(pages.keys()), "activePageName": list(pages.keys())[0]})
    for pid, (display, visuals, pfilters) in pages.items():
        page = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
                "name": pid, "displayName": display, "displayOption": "FitToPage", "height": 720, "width": 1280}
        if pfilters:
            page["filterConfig"] = {"filters": pfilters}
        write(d / "pages" / pid / "page.json", page)
        for v in visuals:
            write(d / "pages" / pid / "visuals" / v["name"] / "visual.json", v)


def legacy_container(name, vtype, from_, select, title_text, x, y, w, h, filters=None):
    cfg = {"name": name, "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h}}],
           "singleVisual": {"visualType": vtype, "projections": {"Values": [{"queryRef": s["Name"]} for s in select]},
                            "prototypeQuery": {"Version": 2, "From": from_, "Select": select},
                            "vcObjects": {"title": [{"properties": {"text": {"expr": {"Literal": {"Value": f"'{title_text}'"}}}}}]}}}
    return {"x": x, "y": y, "z": 0, "width": w, "height": h, "config": json.dumps(cfg), "filters": json.dumps(filters or [])}


def thin_report():
    """Thin report bound to the published semantic model, saved in PBIR-Legacy format (report.json)."""
    root = PBI / "RegionalScorecard.Report"
    if root.exists():
        shutil.rmtree(root)
    write(root / "definition.pbir", {"version": "1.0", "datasetReference": {"byConnection": {
        "connectionString": "Data Source=\"powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics\";initial catalog=\"Retail Sales\";integrated security=ClaimsToken;semanticmodelid=7e3c9b1a-5d2f-4c8e-9a6b-0f1e2d3c4b5a",
        "pbiServiceModelId": None, "pbiModelVirtualServerName": "sobe_wowvirtualserver", "pbiModelDatabaseName": "7e3c9b1a-5d2f-4c8e-9a6b-0f1e2d3c4b5a", "name": "EntityDataSource", "connectionType": "pbiServiceXmlaStyleLive"}}})
    fr_ss = [{"Name": "s", "Entity": "Sales Summary", "Type": 0}]
    sel_region = {"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Region"}, "Name": "Sales Summary.Region"}
    sel_net = {"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Scorecard Net Sales"}, "Name": "Sales Summary.Scorecard Net Sales"}
    sel_ord = {"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Scorecard Orders"}, "Name": "Sales Summary.Scorecard Orders"}
    fr_st = [{"Name": "t", "Entity": "Store", "Type": 0}, {"Name": "s1", "Entity": "Sales", "Type": 0}]
    sel_store = {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": "Store Name"}, "Name": "Store.Store Name"}
    sel_units = {"Measure": {"Expression": {"SourceRef": {"Source": "s1"}}, "Property": "Units Sold"}, "Name": "Sales.Units Sold"}
    vis_filter = [{"name": "f1", "expression": {"Column": {"Expression": {"SourceRef": {"Entity": "Store"}}, "Property": "Country Code"}}, "type": "Categorical", "howCreated": 1}]
    layout = {
        "id": 0, "resourcePackages": [], "config": json.dumps({"version": "5.55", "themeCollection": {}}),
        "filters": json.dumps([{"name": "rf1", "expression": {"Column": {"Expression": {"SourceRef": {"Entity": "Date"}}, "Property": "Quarter"}}, "type": "Categorical"}]),
        "sections": [{
            "name": "ReportSection1", "displayName": "Regional Scorecard", "ordinal": 0, "width": 1280, "height": 720,
            "filters": json.dumps([]),
            "visualContainers": [
                legacy_container("legacy01", "clusteredColumnChart", fr_ss, [sel_region, sel_net], "Net Sales by Region", 20, 20, 620, 340),
                legacy_container("legacy02", "multiRowCard", fr_ss, [sel_net, sel_ord], "Scorecard", 660, 20, 600, 340),
                legacy_container("legacy03", "tableEx", fr_st, [sel_store, sel_units], "Units by Store", 20, 380, 1240, 320, filters=vis_filter),
            ]}],
    }
    write(root / "report.json", layout)


if __name__ == "__main__":
    retail_report()
    thin_report()
    print("wrote", PBI)
