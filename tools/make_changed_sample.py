"""Create samples/dbt_changed: a 'pull request' version of the sample dbt project used to demo diff."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "lineagelens" / "samples"
src = ROOT / "dbt" / "target"
dst = ROOT / "dbt_changed" / "target"
dst.mkdir(parents=True, exist_ok=True)
m = json.loads((src / "manifest.json").read_text())
c = json.loads((src / "catalog.json").read_text())

def edit(uid, old, new):
    n = m["nodes"][uid]
    for k in ("compiled_code", "raw_code"):
        assert old in n[k], (uid, old)
        n[k] = n[k].replace(old, new)

# 1) rename dim_store.SALES_REGION -> REGION_NAME
edit("model.retail_analytics.dim_store", "    sales_region,", "    sales_region as region_name,")
cols = m["nodes"]["model.retail_analytics.dim_store"]["columns"]
if "sales_region" in cols:
    cols["region_name"] = {**cols.pop("sales_region"), "name": "region_name"}
cc = c["nodes"]["model.retail_analytics.dim_store"]["columns"]
cc["REGION_NAME"] = {**cc.pop("SALES_REGION"), "name": "REGION_NAME"}
# 2) drop fct_sales.DISCOUNT_BAND
edit("model.retail_analytics.fct_sales", "    ol.discount_band,\n", "")
m["nodes"]["model.retail_analytics.fct_sales"]["columns"].pop("discount_band", None)
c["nodes"]["model.retail_analytics.fct_sales"]["columns"].pop("DISCOUNT_BAND")
# 3) logic change dim_product.PRICE_BAND
edit("model.retail_analytics.dim_product", "list_price >= 500", "list_price >= 350")
# 4) type change fct_sales.QUANTITY
c["nodes"]["model.retail_analytics.fct_sales"]["columns"]["QUANTITY"]["type"] = "FLOAT"
(dst / "manifest.json").write_text(json.dumps(m, indent=1))
(dst / "catalog.json").write_text(json.dumps(c, indent=1))
(ROOT / "dbt_changed" / "README.md").write_text(
    "Synthetic 'pull request' version of the sample dbt project for `lineagelens diff`.\n\n"
    "Changes: dim_store.SALES_REGION renamed to REGION_NAME, fct_sales.DISCOUNT_BAND dropped, "
    "dim_product.PRICE_BAND threshold changed, fct_sales.QUANTITY type NUMBER -> FLOAT.\n")
print("written", dst)
