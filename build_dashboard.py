"""Build FAQ-4 replay from the pinned observed data; never fit on later data.

Usage: python build_dashboard.py --source-root PINNED_CHECKOUT --run-dir LAB_OUTPUT
Requires the release's frozen DuckDB environment. Output works offline.
"""
import argparse
import csv
import hashlib
import json
import math
import runpy
from datetime import date
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
SHA = "0e40ce3cd0b788a3914ca4eb9f90d58ae1b62903"
SEGMENTS = [("search", "build_skill"), ("search", "save_time"),
            ("partner", "build_skill"), ("partner", "save_time")]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def asset_text(relative):
    """Read source assets from the checkout or complete bundled source ZIP."""
    path = HERE / relative
    if path.is_file():
        return path.read_text()
    import zipfile
    with zipfile.ZipFile(HERE / "dashboard-source.zip") as archive:
        return archive.read("studio-north-dashboard/" + relative).decode("utf-8")


def read(p):
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


def records(con, sql):
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return float(value)


def snapshot(data_dir, cutoff, schemas):
    """Cut off source records BEFORE running the original canonical SQL."""
    con = duckdb.connect()
    timestamp = {"people": "record_created_at", "transactions": "occurred_at",
                 "subscription_periods": "renewal_due_at", "product_events": "occurred_at",
                 "feedback": "submitted_at", "campaign_spend": "spend_date",
                 "acquisition_attribution": "credited_at"}
    for filename, schema in schemas.items():
        name = filename[:-4]
        con.read_csv(str(data_dir / filename), columns=schema, header=True).create_view("raw_" + name)
        if name == "channel_holdouts":
            where = f"followup_end_at <= TIMESTAMP '{cutoff}'"
        else:
            where = f"{timestamp[name]} < TIMESTAMP '{cutoff}'"
        if name == "people":
            # The frozen release records all segmentation attributes pre-acquisition.
            where += f" AND attributes_recorded_at < TIMESTAMP '{cutoff}'"
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM raw_{name} WHERE {where}")
    con.execute(f"CREATE TABLE lab_settings AS SELECT TIMESTAMP '{cutoff}' AS data_as_of")
    con.execute(asset_text("src/01_views.sql"))
    cells = records(con, "SELECT cohort_month,age_month,n_acquired,n_retained,net_revenue,contribution FROM cohort_totals ORDER BY cohort_month,age_month")
    groups = {}
    for cell in cells:
        groups.setdefault(str(cell["cohort_month"]), []).append(cell)
    summaries = []
    mix_rows = records(con, "SELECT cohort_month,channel,primary_need,count(*) AS n FROM acquired_customers GROUP BY ALL ORDER BY ALL")
    for month, rows in groups.items():
        n = rows[0]["n_acquired"]
        costs = con.execute("SELECT sum(acquisition_spend) FROM monthly_spend WHERE calendar_month=?", [month]).fetchone()[0]
        spend = float(costs or 0)
        prefix = sum(float(r["contribution"]) / 1.01 ** (r["age_month"] + 1) for r in rows if r["age_month"] < 12) / n
        cumulative = 0
        payback = None
        recross = False
        for r in rows:
            cumulative += float(r["contribution"])
            if cumulative >= spend and payback is None:
                payback = r["age_month"] + 1
            elif payback is not None and cumulative < spend:
                recross = True
        mix = [next((r["n"] for r in mix_rows if str(r["cohort_month"]) == month and (r["channel"], r["primary_need"]) == s), 0) for s in SEGMENTS]
        assert sum(mix) == n, "Unexpected cohort outside four baseline cells"
        summaries.append({"month": month[:7], "n": n, "age": rows[-1]["age_month"],
                          "retained": rows[-1]["n_retained"], "cac": spend/n,
                          "observedPV": prefix, "ltv": prefix if len(rows) >= 12 else None,
                          "netLtv": prefix-spend/n if len(rows) >= 12 else None,
                          "payback": payback, "recross": recross, "mix": mix})
    monthly = records(con, "SELECT * FROM company_totals ORDER BY calendar_month")
    experiments = records(con, "SELECT test_id,channel,primary_need,test_month,followup_end_at,icac,icac_ci_lower,icac_ci_upper,incremental_buyers FROM channel_cac_current ORDER BY channel,primary_need")
    con.close()
    return clean({"cutoff": cutoff, "cohorts": summaries, "cells": cells, "company": monthly, "tests": experiments})


def assert_close(a, b, name, tol=1e-7):
    if not math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol):
        raise AssertionError(f"Reconciliation failed: {name}: {a} != {b}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    source, run = args.source_root.resolve(), args.run_dir.resolve()
    schemas = runpy.run_path(str(source / "cohort_lab/data.py"))["SCHEMAS"]
    pdf = run / "report/customer-economics-report.pdf"
    baseline_hash = digest(pdf)
    snapshots = []
    for year in (2024, 2025):
        for month in range(1, 13):
            cutoff = date(year+1, 1, 1) if month == 12 else date(year, month+1, 1)
            s = snapshot(source / "data", cutoff.isoformat(), schemas)
            s["month"] = f"{year}-{month:02}"
            snapshots.append(s)
    # Independent earlier-month rebuild from PHYSICALLY truncated raw exports.
    import tempfile
    selected = "2025-07-01"
    fields = {"people.csv":"record_created_at", "subscription_periods.csv":"renewal_due_at", "transactions.csv":"occurred_at", "product_events.csv":"occurred_at", "feedback.csv":"submitted_at", "campaign_spend.csv":"spend_date", "acquisition_attribution.csv":"credited_at", "channel_holdouts.csv":"followup_end_at"}
    with tempfile.TemporaryDirectory() as tmp:
        for filename, field in fields.items():
            rows = read(source / "data" / filename)
            kept = [r for r in rows if (r[field][:10] <= selected if filename == "channel_holdouts.csv" else r[field][:10] < selected)]
            with (Path(tmp) / filename).open("w", newline="") as f:
                w=csv.DictWriter(f,fieldnames=list(schemas[filename]));w.writeheader();w.writerows(kept)
        rebuilt = snapshot(Path(tmp), selected, schemas)
    expected = {k:v for k,v in snapshots[17].items() if k != "month"}
    assert rebuilt == expected, "Earlier-month physical truncation check failed"
    latest = snapshots[-1]
    saved = read(run / "tables/cohort_totals.csv")
    assert len(saved) == len(latest["cells"])
    for a,b in zip(latest["cells"], saved):
        assert a["cohort_month"] == b["cohort_month"] and a["age_month"] == int(b["age_month"])
        for key in ("n_acquired","n_retained","net_revenue","contribution"):
            assert_close(a[key], b[key], key)
    for a,b in zip(latest["company"],read(run/"tables/company_totals.csv")):
        for key in ("n_retained","net_revenue","contribution","acquisition_spend"):
            assert_close(a[key],b[key],key)
    final_value = read(run / "tables/cohort_valuation.csv")
    for r in latest["cohorts"]:
        v=next(x for x in final_value if x["cohort_month"][:7]==r["month"])
        assert_close(r["cac"],v["cac"],"historical CAC")
        assert_close(r["observedPV"],v["observed_discounted_contribution_per_customer"],"observed discounted prefix")
        if r["ltv"] is not None:
            assert_close(r["ltv"],v["ltv_before_cac_mean"],"mature LTV")
    forecasts = [{k:(r[k] if k in ("cohort_month","payback_status") else float(r[k]) if r[k] else None) for k in ("cohort_month","ltv_before_cac_mean","net_ltv_mean","forecast_share","payback_month","payback_status")} for r in final_value]
    curve=clean(read(run/"tables/forecast_curve.csv"))
    decisions=read(run/"tables/channel_value_decision.csv")
    payload={"snapshots":snapshots,"finalForecasts":forecasts,"finalCurves":curve,"decisions":decisions,"segments":[a.title()+" / "+b.replace('_',' ') for a,b in SEGMENTS]}
    text=json.dumps(payload,separators=(",",":"),allow_nan=False)
    (HERE/"data").mkdir(exist_ok=True)
    (HERE/"data/monthly-snapshots.json").write_text(text)
    template=asset_text("src/dashboard.html.in")
    (HERE/"dashboard.html").write_text(template.replace("__PAYLOAD__",text.replace("<","\\u003c")))
    assert digest(pdf)==baseline_hash
    audit={"source_commit":SHA,"pdf_sha256_unchanged":baseline_hash,"canonical_sql_sha256":hashlib.sha256(asset_text("src/01_views.sql").encode()).hexdigest(),"snapshot_count":24,"forecast_policy":"FAQ 4 fallback: original model forecasts only at December 2025; earlier incomplete horizons blank; no later parameters reused", "latest_reconciliation":"passed: all 300 cohort-age cells, 24 company months, historical CAC and observed discounted prefixes; saved final forecasts copied without re-estimation", "physical_truncation_check":{"as_of_month":"2025-06","cutoff_exclusive":selected,"status":"passed; identical snapshot from physically truncated raw files"},"recommendation_timing":"December 2025 is the first evaluable joint recommendation in this fallback. Earliest historical support cannot be established without as-of forecast refits.","input_hashes":{str(p.relative_to(source)):digest(p) for p in (source/"data").glob('*.csv')}}
    (HERE/"validation.json").write_text(json.dumps(audit,indent=2))
    print(json.dumps({"snapshots":24,"reconciliation":"passed","truncation":"passed","payload_bytes":len(text),"dashboard":str(HERE/"dashboard.html")},indent=2))


if __name__ == "__main__":
    main()
