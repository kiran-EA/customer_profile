"""
LampsPlus — Internal Customer Data Platform Dashboard
All 8 pages: Overview, Pipeline Health, QC Status, Segments,
             Predictions, Top Customers, Data Lineage, Samples+Download
Run: python app.py  →  http://localhost:5050
"""
from flask import Flask, render_template, jsonify, Response, send_file
import os as _os
import pandas as pd, io, json
from datetime import date, datetime
import traceback

app   = Flask(__name__)
TABLE = "KIRAN.TBL_CUSTOMER_PROFILE"
DB    = dict(host="ea-non-prod.cxw4zfxatj9b.us-west-1.redshift.amazonaws.com",
             port=5439, database="express", user="easuper", password="LAMRedPWD@2024")

# Try to import redshift_connector, fallback to mock mode if not available
try:
    import redshift_connector
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("⚠️  Redshift connector not available. Running in MOCK/DEMO mode with sample data.")

def qdf(sql):
    if not DB_AVAILABLE:
        # Return mock data for demo/development
        return pd.DataFrame({"error": ["Database not available - running in demo mode"]})
    try:
        c = redshift_connector.connect(**DB); c.autocommit = True
        try:    df = pd.read_sql(sql, c)
        finally: c.close()
        return df
    except Exception as e:
        print(f"Database error: {e}")
        return pd.DataFrame({"error": [str(e)]})

# ── Segment helpers ──────────────────────────────────────
SEG_META = {
    "Champions":           {"color":"#00c8ff","emoji":"🏆","priority":1,"action":"VIP loyalty & early access"},
    "Loyal":               {"color":"#22c55e","emoji":"💛","priority":2,"action":"Loyalty programme enrollment"},
    "Potential Loyalists": {"color":"#84cc16","emoji":"🌱","priority":3,"action":"Nurture email series"},
    "At Risk":             {"color":"#f59e0b","emoji":"⚠️","priority":4,"action":"Re-engage: 15% off time-limited"},
    "Hibernating":         {"color":"#6b7280","emoji":"❄️","priority":5,"action":"Last-chance win-back"},
    "Cart Abandoner":      {"color":"#ef4444","emoji":"🛒","priority":1,"action":"Cart recovery < 24h"},
    "Re-Engaged":          {"color":"#3b82f6","emoji":"🔄","priority":1,"action":"Welcome-back 48h offer"},
    "Window Shopper":      {"color":"#a855f7","emoji":"👀","priority":3,"action":"First-purchase incentive"},
    "Non-Buyer":           {"color":"#4b5563","emoji":"👤","priority":5,"action":"Low-cost nurture email"},
}
SEG_FILTER = {
    "Champions":           "rfm_segment_v2='Champions'",
    "Loyal":               "rfm_segment_v2='Loyal'",
    "Potential Loyalists": "rfm_segment_v2='Potential Loyalists'",
    "At Risk":             "rfm_segment_v2='At Risk'",
    "Hibernating":         "rfm_segment_v2='Hibernating'",
    "Cart Abandoner":      "rfm_segment_v2='Cart Abandoner'",
    "Re-Engaged":          "rfm_segment_v2='Re-Engaged'",
    "Window Shopper":      "rfm_segment_v2='Window Shopper'",
    "Non-Buyer":           "rfm_segment_v2='Non-Buyer'",
}
CLTV_C  = {"Platinum":"#00c8ff","Gold":"#f59e0b","Silver":"#6b7280","Bronze":"#78350f","Dormant":"#374151"}
CHURN_C = {"High Risk":"#ef4444","Medium Risk":"#f59e0b","Low Risk":"#22c55e","Healthy":"#00c8ff"}
ENG_C   = {"Active":"#22c55e","Warm":"#84cc16","Cool":"#3b82f6","Cold":"#f59e0b","Dark":"#6b7280","NoData":"#374151"}

def date_where(years):
    """Activity-based filter covering ALL customer types within N years.

    Signals used (OR logic — customer included if ANY is within range):
      1. recency            — days since last ORDER (buyers; 9999 for non-buyers)
      2. effective_recency  — MIN(days_since_order, days_since_page_view, days_since_cart_add)
                              captures browsers + cart-active non-buyers
      3. customer_reg_date  — newly registered customers within the period
                              (includes email subscribers, window shoppers, new signups)

    years=0 → no filter (all 15.3M customers including NULL-activity records).
    """
    if not years or int(years) == 0:
        return "1=1"
    days = int(years) * 365
    return (
        f"("
        f"  LEAST(recency, COALESCE(effective_recency, 9999)) <= {days}"
        f"  OR CAST(customer_reg_date AS DATE) >= CAST(DATEADD(year, -{int(years)}, CURRENT_DATE) AS DATE)"
        f")"
    )

# ════════════════════════════════════════════════════════
# API ROUTES
# ════════════════════════════════════════════════════════

@app.route("/api/summary")
def api_summary():
    from flask import request as req
    
    if not DB_AVAILABLE:
        return jsonify({
            "total": 15300000,
            "buyers": 4200000,
            "non_buyers": 11100000,
            "avg_cltv": 1245.50,
            "total_portfolio": 5237100000,
            "urgent_winback": 12450,
            "revenue_at_risk": 15500000,
            "hot_leads": 450000,
            "cart_abandoners": 890000,
            "re_engaged": 125000,
            "champions": 350000,
            "high_risk_total": 2100000,
            "net_returners": 890000,
            "high_cancellers": 125000,
            "last_refresh": "2026-03-24T10:30:00",
            "churn_scored": "2026-03-23T23:45:00"
        })
    
    wh = date_where(req.args.get("years","0"))
    df = qdf(f"""
        SELECT
            COUNT(*)                                                           AS total,
            COUNT(CASE WHEN total_orders>0 THEN 1 END)                        AS buyers,
            COUNT(CASE WHEN total_orders=0 THEN 1 END)                        AS non_buyers,
            ROUND(AVG(cltv_adjusted_v2),2)                                    AS avg_cltv,
            ROUND(SUM(cltv_adjusted_v2),0)                                    AS total_portfolio,
            COUNT(CASE WHEN churn_segment='High Risk'
                        AND cltv_segment IN ('Platinum','Gold') THEN 1 END)   AS urgent_winback,
            ROUND(SUM(CASE WHEN churn_segment='High Risk'
                        AND cltv_segment IN ('Platinum','Gold')
                        THEN cltv_adjusted_v2 ELSE 0 END),0)                  AS revenue_at_risk,
            COUNT(CASE WHEN engagement_multiplier=1.3 THEN 1 END)             AS hot_leads,
            COUNT(CASE WHEN rfm_segment_v2='Cart Abandoner' THEN 1 END)       AS cart_abandoners,
            COUNT(CASE WHEN rfm_segment_v2='Re-Engaged' THEN 1 END)           AS re_engaged,
            COUNT(CASE WHEN rfm_segment_v2='Champions' THEN 1 END)            AS champions,
            COUNT(CASE WHEN churn_segment='High Risk' THEN 1 END)             AS high_risk_total,
            COUNT(CASE WHEN is_net_returner=1 THEN 1 END)                     AS net_returners,
            COUNT(CASE WHEN high_cancel_rate=1 THEN 1 END)                    AS high_cancellers,
            MAX(update_date)                                                   AS last_refresh,
            MAX(churn_scored_date)                                             AS churn_scored
        FROM {TABLE}
        WHERE {wh}
    """)
    return jsonify(df.iloc[0].to_dict())

@app.route("/api/pipeline_status")
def api_pipeline():
    if not DB_AVAILABLE:
        return jsonify({
            "rfm_rows": 15280000,
            "cltv_rows": 15280000,
            "churn_rows": 15280000,
            "churn_version": "v2.1.5",
            "churn_scored": "2026-03-23T23:45:00",
            "browse_rows": 13400000,
            "browse_ts": "2026-03-24T08:30:00",
            "latest_ts": "2026-03-24T10:30:00",
            "total_rows": 15300000,
            "null_rfm": 0,
            "null_cltv_adj": 0,
            "null_churn": 0,
            "null_cltv_v2": 0,
            "null_browse_sig": 120000,
            "bad_rfm": 0,
            "bad_cltv": 0,
            "bad_churn_prob": 0,
            "bad_mult": 0
        })
    
    df = qdf(f"""
        SELECT
            COUNT(CASE WHEN rfm_segment IS NOT NULL THEN 1 END)               AS rfm_rows,
            COUNT(CASE WHEN cltv_adjusted IS NOT NULL THEN 1 END)             AS cltv_rows,
            COUNT(CASE WHEN churn_model_version IS NOT NULL THEN 1 END)       AS churn_rows,
            MAX(churn_model_version)                                           AS churn_version,
            MAX(churn_scored_date)                                             AS churn_scored,
            COUNT(CASE WHEN update_source='PYSPARK_BROWSE_EMAIL_ENRICHMENT' THEN 1 END) AS browse_rows,
            MAX(CASE WHEN update_source='PYSPARK_BROWSE_EMAIL_ENRICHMENT' THEN update_date END) AS browse_ts,
            MAX(update_date)                                                   AS latest_ts,
            COUNT(*)                                                           AS total_rows,
            -- Null health
            COUNT(CASE WHEN rfm_score IS NULL THEN 1 END)                     AS null_rfm,
            COUNT(CASE WHEN cltv_adjusted IS NULL THEN 1 END)                 AS null_cltv_adj,
            COUNT(CASE WHEN churn_probability IS NULL THEN 1 END)             AS null_churn,
            COUNT(CASE WHEN cltv_adjusted_v2 IS NULL THEN 1 END)              AS null_cltv_v2,
            COUNT(CASE WHEN churn_browse_signal IS NULL THEN 1 END)           AS null_browse_sig,
            -- Range violations
            COUNT(CASE WHEN rfm_score<1 OR rfm_score>10 THEN 1 END)          AS bad_rfm,
            COUNT(CASE WHEN cltv_score<1 OR cltv_score>100 THEN 1 END)       AS bad_cltv,
            COUNT(CASE WHEN churn_probability<0 OR churn_probability>1 THEN 1 END) AS bad_churn_prob,
            COUNT(CASE WHEN engagement_multiplier NOT IN (0.8,1.0,1.1,1.2,1.3) THEN 1 END) AS bad_mult
        FROM {TABLE}
    """)
    return jsonify(df.iloc[0].to_dict())

@app.route("/api/segments")
def api_segments():
    from flask import request as req
    
    if not DB_AVAILABLE:
        mock_segments = [
            {"segment": "Champions", "customers": 350000, "pct": 2.29, "avg_cltv": 2450.75, "avg_spend": 890.25, "avg_churn_prob": 0.05, "high_risk_count": 2500, "avg_rfm": 9.2, "total_value": 857762500, "avg_eng_mult": 1.3, "avg_email_eng": 0.65, "avg_browse_conv": 0.45, "cart_buyers": 245000, "color": "#00c8ff", "emoji": "🏆", "priority": 1, "action": "VIP loyalty & early access"},
            {"segment": "Loyal", "customers": 890000, "pct": 5.82, "avg_cltv": 1850.50, "avg_spend": 650.75, "avg_churn_prob": 0.08, "high_risk_count": 15000, "avg_rfm": 8.1, "total_value": 1647945000, "avg_eng_mult": 1.2, "avg_email_eng": 0.55, "avg_browse_conv": 0.35, "cart_buyers": 578500, "color": "#22c55e", "emoji": "💛", "priority": 2, "action": "Loyalty programme enrollment"},
            {"segment": "Potential Loyalists", "customers": 1200000, "pct": 7.84, "avg_cltv": 950.25, "avg_spend": 425.50, "avg_churn_prob": 0.15, "high_risk_count": 95000, "avg_rfm": 6.8, "total_value": 1140300000, "avg_eng_mult": 1.1, "avg_email_eng": 0.45, "avg_browse_conv": 0.28, "cart_buyers": 600000, "color": "#84cc16", "emoji": "🌱", "priority": 3, "action": "Nurture email series"},
            {"segment": "At Risk", "customers": 2100000, "pct": 13.73, "avg_cltv": 1200.75, "avg_spend": 350.25, "avg_churn_prob": 0.45, "high_risk_count": 945000, "avg_rfm": 4.2, "total_value": 2521575000, "avg_eng_mult": 0.8, "avg_email_eng": 0.25, "avg_browse_conv": 0.15, "cart_buyers": 420000, "color": "#f59e0b", "emoji": "⚠️", "priority": 4, "action": "Re-engage: 15% off time-limited"},
            {"segment": "Hibernating", "customers": 3500000, "pct": 22.88, "avg_cltv": 450.50, "avg_spend": 125.75, "avg_churn_prob": 0.85, "high_risk_count": 2975000, "avg_rfm": 2.1, "total_value": 1576750000, "avg_eng_mult": 0.8, "avg_email_eng": 0.08, "avg_browse_conv": 0.05, "cart_buyers": 105000, "color": "#6b7280", "emoji": "❄️", "priority": 5, "action": "Last-chance win-back"},
            {"segment": "Cart Abandoner", "customers": 890000, "pct": 5.82, "avg_cltv": 1550.25, "avg_spend": 580.50, "avg_churn_prob": 0.35, "high_risk_count": 156000, "avg_rfm": 5.5, "total_value": 1379972500, "avg_eng_mult": 1.0, "avg_email_eng": 0.35, "avg_browse_conv": 0.42, "cart_buyers": 668500, "color": "#ef4444", "emoji": "🛒", "priority": 1, "action": "Cart recovery < 24h"},
            {"segment": "Re-Engaged", "customers": 125000, "pct": 0.82, "avg_cltv": 1100.35, "avg_spend": 425.60, "avg_churn_prob": 0.12, "high_risk_count": 5000, "avg_rfm": 7.3, "total_value": 137543750, "avg_eng_mult": 1.15, "avg_email_eng": 0.48, "avg_browse_conv": 0.32, "cart_buyers": 87500, "color": "#3b82f6", "emoji": "🔄", "priority": 1, "action": "Welcome-back 48h offer"},
            {"segment": "Window Shopper", "customers": 2800000, "pct": 18.30, "avg_cltv": 125.50, "avg_spend": 45.75, "avg_churn_prob": 0.60, "high_risk_count": 840000, "avg_rfm": 3.4, "total_value": 351400000, "avg_eng_mult": 0.8, "avg_email_eng": 0.12, "avg_browse_conv": 0.08, "cart_buyers": 168000, "color": "#a855f7", "emoji": "👀", "priority": 3, "action": "First-purchase incentive"},
            {"segment": "Non-Buyer", "customers": 3845000, "pct": 25.13, "avg_cltv": 0.0, "avg_spend": 0.0, "avg_churn_prob": 0.90, "high_risk_count": 3460500, "avg_rfm": 1.2, "total_value": 0, "avg_eng_mult": 0.8, "avg_email_eng": 0.02, "avg_browse_conv": 0.01, "cart_buyers": 0, "color": "#4b5563", "emoji": "👤", "priority": 5, "action": "Low-cost nurture email"}
        ]
        return jsonify(mock_segments)
    
    wh = date_where(req.args.get("years","0"))
    df = qdf(f"""
        SELECT rfm_segment_v2 AS segment,
               COUNT(*)                                              AS customers,
               ROUND(COUNT(*)*100.0/SUM(COUNT(*)) OVER(),2)         AS pct,
               ROUND(AVG(cltv_adjusted_v2),2)                       AS avg_cltv,
               ROUND(AVG(monetary),2)                               AS avg_spend,
               ROUND(AVG(churn_probability),4)                      AS avg_churn_prob,
               COUNT(CASE WHEN churn_segment='High Risk' THEN 1 END) AS high_risk_count,
               ROUND(AVG(rfm_score),3)                              AS avg_rfm,
               ROUND(SUM(cltv_adjusted_v2),0)                       AS total_value,
               ROUND(AVG(engagement_multiplier),3)                  AS avg_eng_mult,
               ROUND(AVG(email_engagement_rate),4)                  AS avg_email_eng,
               ROUND(AVG(browse_conversion_score),4)                AS avg_browse_conv,
               COUNT(CASE WHEN cart_conversion_flag=1 THEN 1 END)   AS cart_buyers
        FROM {TABLE}
        WHERE {wh}
        GROUP BY rfm_segment_v2 ORDER BY customers DESC
    """)
    out = []
    for _, r in df.iterrows():
        seg  = str(r["segment"])
        meta = SEG_META.get(seg, {"color":"#4b5563","emoji":"📊","priority":3,"action":"—"})
        out.append({**{k:(None if pd.isna(v) else v) for k,v in r.items()}, **meta})
    return jsonify(out)

@app.route("/api/churn")
def api_churn():
    from flask import request as req
    
    if not DB_AVAILABLE:
        mock_data = [
            {"churn_segment": "High Risk", "customers": 2100000, "pct": 13.73, "avg_prob": 0.7250, "avg_cltv": 1120.50, "total_value": 2353050000, "color": "#ef4444"},
            {"churn_segment": "Medium Risk", "customers": 4500000, "pct": 29.41, "avg_prob": 0.3850, "avg_cltv": 890.75, "total_value": 4008375000, "color": "#f59e0b"},
            {"churn_segment": "Low Risk", "customers": 5900000, "pct": 38.56, "avg_prob": 0.1250, "avg_cltv": 1450.25, "total_value": 8556475000, "color": "#22c55e"},
            {"churn_segment": "Healthy", "customers": 2800000, "pct": 18.30, "avg_prob": 0.0150, "avg_cltv": 2100.00, "total_value": 5880000000, "color": "#00c8ff"}
        ]
        return jsonify(mock_data)
    
    wh = date_where(req.args.get("years","0"))
    df = qdf(f"""
        SELECT churn_segment,
               COUNT(*)                                              AS customers,
               ROUND(COUNT(*)*100.0/SUM(COUNT(*)) OVER(),2)         AS pct,
               ROUND(AVG(churn_probability),4)                      AS avg_prob,
               ROUND(AVG(cltv_adjusted_v2),2)                       AS avg_cltv,
               ROUND(SUM(cltv_adjusted_v2),0)                       AS total_value
        FROM {TABLE}
        WHERE {wh}
        GROUP BY churn_segment ORDER BY avg_prob DESC
    """)
    df["color"] = df["churn_segment"].map(CHURN_C)
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/cltv")
def api_cltv():
    from flask import request as req
    
    if not DB_AVAILABLE:
        mock_data = [
            {"cltv_segment": "Platinum", "customers": 125000, "avg_cltv": 5000.50, "total_value": 625062500, "avg_score": 95.2, "color": "#00c8ff"},
            {"cltv_segment": "Gold", "customers": 890000, "avg_cltv": 2100.75, "total_value": 1870767500, "avg_score": 78.5, "color": "#f59e0b"},
            {"cltv_segment": "Silver", "customers": 2800000, "avg_cltv": 750.50, "total_value": 2101400000, "avg_score": 58.3, "color": "#6b7280"},
            {"cltv_segment": "Bronze", "customers": 5400000, "avg_cltv": 350.25, "total_value": 1891350000, "avg_score": 35.7, "color": "#78350f"},
            {"cltv_segment": "Dormant", "customers": 6085000, "avg_cltv": 0.0, "total_value": 0, "avg_score": 5.2, "color": "#374151"}
        ]
        return jsonify(mock_data)
    
    wh = date_where(req.args.get("years","0"))
    df = qdf(f"""
        SELECT cltv_segment,
               COUNT(*)                             AS customers,
               ROUND(AVG(cltv_adjusted_v2),2)       AS avg_cltv,
               ROUND(SUM(cltv_adjusted_v2),0)        AS total_value,
               ROUND(AVG(cltv_score),2)              AS avg_score
        FROM {TABLE}
        WHERE {wh}
        GROUP BY cltv_segment ORDER BY avg_score DESC
    """)
    df["color"] = df["cltv_segment"].map(CLTV_C)
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/engagement")
def api_engagement():
    from flask import request as req
    
    if not DB_AVAILABLE:
        mock_data = [
            {"signal": "Active", "customers": 3200000, "pct": 20.92, "color": "#22c55e"},
            {"signal": "Warm", "customers": 4100000, "pct": 26.80, "color": "#84cc16"},
            {"signal": "Cool", "customers": 3800000, "pct": 24.84, "color": "#3b82f6"},
            {"signal": "Cold", "customers": 2900000, "pct": 18.95, "color": "#f59e0b"},
            {"signal": "Dark", "customers": 1100000, "pct": 7.19, "color": "#6b7280"},
            {"signal": "NoData", "customers": 100000, "pct": 0.65, "color": "#374151"}
        ]
        return jsonify(mock_data)
    
    wh = date_where(req.args.get("years","0"))
    df = qdf(f"""
        SELECT churn_browse_signal AS signal,
               COUNT(*)            AS customers,
               ROUND(COUNT(*)*100.0/SUM(COUNT(*)) OVER(),2) AS pct
        FROM {TABLE}
        WHERE {wh}
        GROUP BY churn_browse_signal ORDER BY customers DESC
    """)
    df["color"] = df["signal"].map(ENG_C)
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/cltv_churn_matrix")
def api_cltv_churn_matrix():
    from flask import request as req
    
    if not DB_AVAILABLE:
        # Mock matrix data
        mock_matrix = [
            # Platinum
            {"cltv_segment": "Platinum", "churn_segment": "High Risk", "customers": 5000, "avg_cltv": 4800.75, "total_cltv": 24003750, "churn_pct": 72.5, "revenue_at_risk": 17402718, "priority": "URGENT", "priority_color": "#b91c1c", "action": "Immediate executive intervention", "dot_color": "#00c8ff"},
            {"cltv_segment": "Platinum", "churn_segment": "Medium Risk", "customers": 12000, "avg_cltv": 5200.50, "total_cltv": 62406000, "churn_pct": 42.0, "revenue_at_risk": 26210520, "priority": "Critical", "priority_color": "#dc2626", "action": "VIP retention programs", "dot_color": "#00c8ff"},
            {"cltv_segment": "Platinum", "churn_segment": "Low Risk", "customers": 38000, "avg_cltv": 5350.25, "total_cltv": 203309500, "churn_pct": 8.5, "revenue_at_risk": 17281308, "priority": "Protect", "priority_color": "#16a34a", "action": "Maintain excellence", "dot_color": "#00c8ff"},
            {"cltv_segment": "Platinum", "churn_segment": "Healthy", "customers": 70000, "avg_cltv": 5450.00, "total_cltv": 381500000, "churn_pct": 1.2, "revenue_at_risk": 4578000, "priority": "Protect", "priority_color": "#16a34a", "action": "Maintain excellence", "dot_color": "#00c8ff"},
            # Gold
            {"cltv_segment": "Gold", "churn_segment": "High Risk", "customers": 45000, "avg_cltv": 2050.25, "total_cltv": 92261250, "churn_pct": 68.0, "revenue_at_risk": 62657700, "priority": "URGENT", "priority_color": "#b91c1c", "action": "Immediate executive intervention", "dot_color": "#f59e0b"},
            {"cltv_segment": "Gold", "churn_segment": "Medium Risk", "customers": 120000, "avg_cltv": 2100.75, "total_cltv": 252090000, "churn_pct": 40.5, "revenue_at_risk": 102096450, "priority": "Critical", "priority_color": "#dc2626", "action": "VIP retention programs", "dot_color": "#f59e0b"},
            {"cltv_segment": "Gold", "churn_segment": "Low Risk", "customers": 380000, "avg_cltv": 2150.50, "total_cltv": 817190000, "churn_pct": 9.0, "revenue_at_risk": 73547100, "priority": "Protect", "priority_color": "#16a34a", "action": "Maintain excellence", "dot_color": "#f59e0b"},
            {"cltv_segment": "Gold", "churn_segment": "Healthy", "customers": 345000, "avg_cltv": 2200.00, "total_cltv": 759000000, "churn_pct": 1.5, "revenue_at_risk": 11385000, "priority": "Protect", "priority_color": "#16a34a", "action": "Maintain excellence", "dot_color": "#f59e0b"},
            # Silver
            {"cltv_segment": "Silver", "churn_segment": "High Risk", "customers": 280000, "avg_cltv": 720.50, "total_cltv": 201740000, "churn_pct": 65.0, "revenue_at_risk": 131131000, "priority": "Monitor", "priority_color": "#d97706", "action": "Engagement campaigns", "dot_color": "#6b7280"},
            {"cltv_segment": "Silver", "churn_segment": "Medium Risk", "customers": 850000, "avg_cltv": 760.75, "total_cltv": 646637500, "churn_pct": 38.0, "revenue_at_risk": 245602050, "priority": "Monitor", "priority_color": "#d97706", "action": "Engagement campaigns", "dot_color": "#6b7280"},
            {"cltv_segment": "Silver", "churn_segment": "Low Risk", "customers": 1200000, "avg_cltv": 800.50, "total_cltv": 960600000, "churn_pct": 10.5, "revenue_at_risk": 100863000, "priority": "Low", "priority_color": "#6b7280", "action": "Automated nurture", "dot_color": "#6b7280"},
            {"cltv_segment": "Silver", "churn_segment": "Healthy", "customers": 470000, "avg_cltv": 850.00, "total_cltv": 399500000, "churn_pct": 2.0, "revenue_at_risk": 7990000, "priority": "Low", "priority_color": "#6b7280", "action": "Automated nurture", "dot_color": "#6b7280"},
            # Bronze
            {"cltv_segment": "Bronze", "churn_segment": "High Risk", "customers": 750000, "avg_cltv": 330.25, "total_cltv": 247687500, "churn_pct": 62.0, "revenue_at_risk": 153606250, "priority": "Monitor", "priority_color": "#d97706", "action": "Low-cost reactivation", "dot_color": "#78350f"},
            {"cltv_segment": "Bronze", "churn_segment": "Medium Risk", "customers": 1800000, "avg_cltv": 350.50, "total_cltv": 630900000, "churn_pct": 36.5, "revenue_at_risk": 230378500, "priority": "Low", "priority_color": "#6b7280", "action": "Automated nurture", "dot_color": "#78350f"},
            {"cltv_segment": "Bronze", "churn_segment": "Low Risk", "customers": 2100000, "avg_cltv": 380.25, "total_cltv": 799125000, "churn_pct": 11.0, "revenue_at_risk": 87903750, "priority": "Low", "priority_color": "#6b7280", "action": "Standard nurture", "dot_color": "#78350f"},
            {"cltv_segment": "Bronze", "churn_segment": "Healthy", "customers": 750000, "avg_cltv": 420.00, "total_cltv": 315000000, "churn_pct": 2.5, "revenue_at_risk": 7875000, "priority": "Low", "priority_color": "#6b7280", "action": "Standard nurture", "dot_color": "#78350f"},
            # Dormant
            {"cltv_segment": "Dormant", "churn_segment": "High Risk", "customers": 1020000, "avg_cltv": 0.0, "total_cltv": 0, "churn_pct": 85.0, "revenue_at_risk": 0, "priority": "Low", "priority_color": "#6b7280", "action": "Automated nurture", "dot_color": "#374151"},
            {"cltv_segment": "Dormant", "churn_segment": "Medium Risk", "customers": 1730000, "avg_cltv": 0.0, "total_cltv": 0, "churn_pct": 50.0, "revenue_at_risk": 0, "priority": "Low", "priority_color": "#6b7280", "action": "Automated nurture", "dot_color": "#374151"},
            {"cltv_segment": "Dormant", "churn_segment": "Low Risk", "customers": 1420000, "avg_cltv": 0.0, "total_cltv": 0, "churn_pct": 20.0, "revenue_at_risk": 0, "priority": "Low", "priority_color": "#6b7280", "action": "Automated nurture", "dot_color": "#374151"},
            {"cltv_segment": "Dormant", "churn_segment": "Healthy", "customers": 915000, "avg_cltv": 0.0, "total_cltv": 0, "churn_pct": 5.0, "revenue_at_risk": 0, "priority": "Low", "priority_color": "#6b7280", "action": "Automated nurture", "dot_color": "#374151"}
        ]
        return jsonify(mock_matrix)
    
    wh = date_where(req.args.get("years","0"))
    # Cross cltv_segment x churn_segment with priority + action logic
    df = qdf(f"""
        SELECT
            cltv_segment,
            churn_segment,
            COUNT(*)                                AS customers,
            ROUND(AVG(cltv_adjusted_v2),2)          AS avg_cltv,
            ROUND(SUM(cltv_adjusted_v2),0)           AS total_cltv,
            ROUND(AVG(churn_probability)*100,1)      AS churn_pct,
            ROUND(SUM(CASE WHEN churn_probability > 0.5
                      THEN cltv_adjusted_v2 ELSE 0 END),0) AS revenue_at_risk
        FROM {TABLE}
        WHERE {wh}
          AND cltv_segment IS NOT NULL
          AND churn_segment IS NOT NULL
        GROUP BY cltv_segment, churn_segment
        ORDER BY avg_cltv DESC, churn_pct DESC
    """)

    # Assign priority + action based on cltv_tier × churn_risk
    priority_map = {
        ("Platinum","High Risk"):   ("URGENT","#b91c1c","Immediate executive intervention"),
        ("Platinum","Medium Risk"): ("Critical","#dc2626","VIP retention programs"),
        ("Platinum","Low Risk"):    ("Protect","#16a34a","Maintain excellence"),
        ("Platinum","Healthy"):     ("Protect","#16a34a","Maintain excellence"),
        ("Gold","High Risk"):       ("URGENT","#b91c1c","Win-back campaigns"),
        ("Gold","Medium Risk"):     ("Critical","#dc2626","Targeted retention offers"),
        ("Gold","Low Risk"):        ("Protect","#16a34a","Loyalty rewards"),
        ("Gold","Healthy"):         ("Protect","#16a34a","Loyalty rewards"),
        ("Silver","High Risk"):     ("Monitor","#d97706","Engagement campaigns"),
        ("Silver","Medium Risk"):   ("Monitor","#d97706","Engagement campaigns"),
        ("Silver","Low Risk"):      ("Low","#6b7280","Automated nurture"),
        ("Silver","Healthy"):       ("Low","#6b7280","Automated nurture"),
        ("Bronze","High Risk"):     ("Monitor","#d97706","Low-cost reactivation"),
        ("Bronze","Medium Risk"):   ("Low","#6b7280","Automated nurture"),
        ("Bronze","Low Risk"):      ("Low","#6b7280","Standard nurture"),
        ("Bronze","Healthy"):       ("Low","#6b7280","Standard nurture"),
        ("Dormant","High Risk"):    ("Low","#6b7280","Automated nurture"),
        ("Dormant","Medium Risk"):  ("Low","#6b7280","Automated nurture"),
        ("Dormant","Low Risk"):     ("Low","#6b7280","Automated nurture"),
        ("Dormant","Healthy"):      ("Low","#6b7280","Automated nurture"),
    }
    cltv_dot = {"Platinum":"#00c8ff","Gold":"#f59e0b","Silver":"#6b7280","Bronze":"#78350f","Dormant":"#374151"}
    rows = []
    for _, r in df.iterrows():
        key = (str(r["cltv_segment"]), str(r["churn_segment"]))
        pri, pri_color, action = priority_map.get(key, ("Low","#6b7280","Standard nurture"))
        rows.append({
            **{k:(None if pd.isna(v) else v) for k,v in r.items()},
            "priority": pri,
            "priority_color": pri_color,
            "action": action,
            "dot_color": cltv_dot.get(str(r["cltv_segment"]),"#555")
        })
    # Sort by priority: Urgent → Critical → Monitor → Low → Protect
    priority_order = {"URGENT": 0, "Critical": 1, "Monitor": 2, "Low": 3, "Protect": 4}
    rows.sort(key=lambda r: (priority_order.get(r["priority"], 99), -float(r.get("avg_cltv") or 0)))
    return jsonify(rows)

@app.route("/api/cltv_churn_matrix/export")
def api_cltv_churn_matrix_export():
    from flask import request as req
    wh = date_where(req.args.get("years","0"))
    years_label = req.args.get("years","all")
    
    if not DB_AVAILABLE:
        # Return mock CSV for demo mode
        mock_export = """CLTV Tier,Churn Risk,Customer Count,Avg CLTV ($),Total CLTV Value ($),Churn Risk %,Revenue at Risk ($)
Platinum,High Risk,5000,4800.75,24003750,72.5,17402718
Platinum,Medium Risk,12000,5200.50,62406000,42.0,26210520
Platinum,Low Risk,38000,5350.25,203309500,8.5,17281308
Platinum,Healthy,70000,5450.00,381500000,1.2,4578000
Gold,High Risk,45000,2050.25,92261250,68.0,62657700
Gold,Medium Risk,120000,2100.75,252090000,40.5,102096450
Gold,Low Risk,380000,2150.50,817190000,9.0,73547100
Gold,Healthy,345000,2200.00,759000000,1.5,11385000
Silver,High Risk,280000,720.50,201740000,65.0,131131000
Silver,Medium Risk,850000,760.75,646637500,38.0,245602050
Silver,Low Risk,1200000,800.50,960600000,10.5,100863000
Silver,Healthy,470000,850.00,399500000,2.0,7990000
Bronze,High Risk,750000,330.25,247687500,62.0,153606250
Bronze,Medium Risk,1800000,350.50,630900000,36.5,230378500
Bronze,Low Risk,2100000,380.25,799125000,11.0,87903750
Bronze,Healthy,750000,420.00,315000000,2.5,7875000
Dormant,High Risk,1020000,0.00,0,85.0,0
Dormant,Medium Risk,1730000,0.00,0,50.0,0
Dormant,Low Risk,1420000,0.00,0,20.0,0
Dormant,Healthy,915000,0.00,0,5.0,0"""
        
        buf = io.StringIO()
        buf.write(mock_export)
        fname = f"LP_CLTV_Churn_Matrix_{years_label}yr_{date.today()}.csv"
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={fname}"})
    
    df = qdf(f"""
        SELECT
            cltv_segment                            AS "CLTV Tier",
            churn_segment                           AS "Churn Risk",
            COUNT(*)                                AS "Customer Count",
            ROUND(AVG(cltv_adjusted_v2),2)          AS "Avg CLTV ($)",
            ROUND(SUM(cltv_adjusted_v2),0)           AS "Total CLTV Value ($)",
            ROUND(AVG(churn_probability)*100,1)      AS "Churn Risk %",
            ROUND(SUM(CASE WHEN churn_probability > 0.5
                      THEN cltv_adjusted_v2 ELSE 0 END),0) AS "Revenue at Risk ($)"
        FROM {TABLE}
        WHERE {wh}
          AND cltv_segment IS NOT NULL
          AND churn_segment IS NOT NULL
        GROUP BY cltv_segment, churn_segment
        ORDER BY "Avg CLTV ($)" DESC
    """)
    buf = io.StringIO(); df.to_csv(buf, index=False)
    fname = f"LP_CLTV_Churn_Matrix_{years_label}yr_{date.today()}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.route("/api/download/matrix/<path:cltv_seg>/<path:churn_seg>")
def api_download_matrix(cltv_seg, churn_seg):
    """Export 100 customers filtered by cltv_segment x churn_segment with full PII."""
    PII_TABLE    = "KIRAN.TBL_D_CUSTOMER"
    PII_JOIN_KEY = "master_customer_id"
    PII_EMAIL_COL = "email_address"
    PII_PHONE_COL = "phone_number"
    PII_FNAME_COL = "first_name"
    PII_LNAME_COL = "last_name"
    PII_ADDR_COL  = "address_line1"
    PII_CITY_COL  = "city"
    PII_STATE_COL = "state"
    PII_ZIP_COL   = "zip_code"

    from flask import request as freq
    wh = date_where(freq.args.get("years", "0"))

    if not DB_AVAILABLE:
        # Return mock CSV for the matrix segment in demo mode
        mock_matrix_csv = f"""Customer ID,First Name,Last Name,Email Address,Phone Number,Address,City,State,Zip Code,Value Tier,Churn Risk Level,Customer Segment,Predicted Value (12m $),Total Spend to Date ($),Total Orders,Days Since Last Order,Churn Probability,Online Engagement,Browse Score,Email Engagement Rate,Engagement Multiplier,Completed Cart,Net Returner,Last Active Date
MC{cltv_seg[:1]}{churn_seg[:1]}001,John,Smith,john.smith@email.com,555-0101,123 Main St,New York,NY,10001,{cltv_seg},{churn_seg},Champions,2500.50,5800.75,45,3,0.12,Active,0.78,0.65,1.2,Yes,Yes,2026-03-24
MC{cltv_seg[:1]}{churn_seg[:1]}002,Sarah,Johnson,sarah.j@email.com,555-0102,456 Oak Ave,Los Angeles,CA,90001,{cltv_seg},{churn_seg},Loyal,2200.75,5200.50,38,5,0.15,Warm,0.75,0.62,1.1,Yes,No,2026-03-22
MC{cltv_seg[:1]}{churn_seg[:1]}003,Michael,Davis,m.davis@email.com,555-0103,789 Pine Rd,Chicago,IL,60601,{cltv_seg},{churn_seg},At Risk,1850.25,4100.50,28,12,0.45,Cool,0.58,0.48,0.9,No,Yes,2026-03-18
MC{cltv_seg[:1]}{churn_seg[:1]}004,Emily,Wilson,e.wilson@email.com,555-0104,321 Elm St,Houston,TX,77001,{cltv_seg},{churn_seg},Cart Abandoner,1650.50,3900.25,24,2,0.25,Warm,0.68,0.55,1.0,No,No,2026-03-24
MC{cltv_seg[:1]}{churn_seg[:1]}005,David,Martinez,d.martinez@email.com,555-0105,654 Maple Dr,Phoenix,AZ,85001,{cltv_seg},{churn_seg},Window Shopper,450.75,1200.50,8,18,0.65,Cold,0.35,0.25,0.8,No,No,2026-03-20"""
        
        buf = io.StringIO()
        buf.write(mock_matrix_csv)
        safe_cltv  = cltv_seg.replace(" ","_")
        safe_churn = churn_seg.replace(" ","_")
        fname = f"LP_{safe_cltv}_{safe_churn}_top100_{date.today()}.csv"
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={fname}"})

    where = f"p.cltv_segment='{cltv_seg}' AND p.churn_segment='{churn_seg}' AND {wh}"

    try:
        df = qdf(f"""
            SELECT
                p.master_customer_id                                AS "Customer ID",
                pii.{PII_FNAME_COL}                                 AS "First Name",
                pii.{PII_LNAME_COL}                                 AS "Last Name",
                pii.{PII_EMAIL_COL}                                 AS "Email Address",
                pii.{PII_PHONE_COL}                                 AS "Phone Number",
                pii.{PII_ADDR_COL}                                  AS "Address",
                pii.{PII_CITY_COL}                                  AS "City",
                pii.{PII_STATE_COL}                                 AS "State",
                pii.{PII_ZIP_COL}                                   AS "Zip Code",
                p.cltv_segment                                      AS "Value Tier",
                p.churn_segment                                     AS "Churn Risk Level",
                p.rfm_segment_v2                                    AS "Customer Segment",
                ROUND(p.cltv_adjusted_v2, 2)                        AS "Predicted Value (12m $)",
                ROUND(p.monetary, 2)                                AS "Total Spend to Date ($)",
                p.frequency                                         AS "Total Orders",
                p.recency                                           AS "Days Since Last Order",
                ROUND(p.churn_probability, 3)                       AS "Churn Probability",
                p.churn_browse_signal                               AS "Online Engagement",
                ROUND(p.browse_conversion_score, 3)                 AS "Browse Score",
                ROUND(p.email_engagement_rate, 3)                   AS "Email Engagement Rate",
                p.engagement_multiplier                             AS "Engagement Multiplier",
                CASE WHEN p.cart_conversion_flag=1 THEN 'Yes' ELSE 'No' END AS "Completed Cart",
                CASE WHEN p.is_net_returner=1      THEN 'Yes' ELSE 'No' END AS "Net Returner",
                CAST(p.latest_active_date AS VARCHAR)               AS "Last Active Date"
            FROM {TABLE} p
            LEFT JOIN {PII_TABLE} pii
                ON p.{PII_JOIN_KEY} = pii.{PII_JOIN_KEY}
            WHERE {where}
            ORDER BY p.cltv_adjusted_v2 DESC
            LIMIT 100
        """)
    except Exception as e:
        import traceback; traceback.print_exc()
        pii_err = str(e).replace("'","")
        df = qdf(f"""
            SELECT
                master_customer_id                              AS "Customer ID",
                '-- PII join failed: {pii_err[:80]}' AS "First Name",
                '' AS "Last Name", '' AS "Email Address", '' AS "Phone Number",
                '' AS "Address", '' AS "City", '' AS "State", '' AS "Zip Code",
                cltv_segment AS "Value Tier", churn_segment AS "Churn Risk Level",
                rfm_segment_v2 AS "Customer Segment",
                ROUND(cltv_adjusted_v2,2) AS "Predicted Value (12m $)",
                ROUND(monetary,2) AS "Total Spend to Date ($)",
                frequency AS "Total Orders", recency AS "Days Since Last Order",
                ROUND(churn_probability,3) AS "Churn Probability"
            FROM {TABLE} p
            WHERE {where}
            ORDER BY cltv_adjusted_v2 DESC
            LIMIT 100
        """)

    buf = io.StringIO(); df.to_csv(buf, index=False)
    safe_cltv  = cltv_seg.replace(" ","_")
    safe_churn = churn_seg.replace(" ","_")
    fname = f"LP_{safe_cltv}_{safe_churn}_top100_{date.today()}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})

@app.route("/api/predictions")
def api_predictions():
    if not DB_AVAILABLE:
        return jsonify({
            "high_risk_revenue": 2353050000,
            "med_risk_revenue": 4008375000,
            "champions_value": 857762500,
            "hot_leads_value": 584500000,
            "cart_opp": 206995875,
            "window_opp": 17570000,
            "at_risk_save": 504315000,
            "reengaged_opp": 34385937,
            "total_portfolio": 5237100000
        })
    
    df = qdf(f"""
        SELECT
            ROUND(SUM(CASE WHEN churn_segment='High Risk'   THEN cltv_adjusted_v2 ELSE 0 END),0) AS high_risk_revenue,
            ROUND(SUM(CASE WHEN churn_segment='Medium Risk' THEN cltv_adjusted_v2 ELSE 0 END),0) AS med_risk_revenue,
            ROUND(SUM(CASE WHEN rfm_segment_v2='Champions'  THEN cltv_adjusted_v2 ELSE 0 END),0) AS champions_value,
            ROUND(SUM(CASE WHEN engagement_multiplier=1.3   THEN cltv_adjusted_v2 ELSE 0 END),0) AS hot_leads_value,
            ROUND(SUM(CASE WHEN rfm_segment_v2='Cart Abandoner' THEN cltv_adjusted_v2*0.15 ELSE 0 END),0) AS cart_opp,
            ROUND(SUM(CASE WHEN rfm_segment_v2='Window Shopper' THEN cltv_adjusted_v2*0.05 ELSE 0 END),0) AS window_opp,
            ROUND(SUM(CASE WHEN rfm_segment_v2='At Risk'    THEN cltv_adjusted_v2*0.20 ELSE 0 END),0) AS at_risk_save,
            ROUND(SUM(CASE WHEN rfm_segment_v2='Re-Engaged' THEN cltv_adjusted_v2*0.25 ELSE 0 END),0) AS reengaged_opp,
            ROUND(SUM(cltv_adjusted_v2),0)                                                          AS total_portfolio
        FROM {TABLE}
    """)
    return jsonify(df.iloc[0].to_dict())

@app.route("/api/top_customers")
def api_top():
    if not DB_AVAILABLE:
        mock_customers = [
            {"master_customer_id": "CUST001845", "rfm_segment_v2": "Champions", "rfm_segment": "5-5-5", "cltv_segment": "Platinum", "cltv_adjusted_v2": 8950.50, "cltv_adjusted": 8750.25, "monetary": 15420.75, "frequency": 156, "recency": 2, "churn_segment": "Healthy", "churn_probability": 0.002, "churn_score": 1, "churn_browse_signal": "Active", "browse_conversion_score": 0.925, "email_engagement_rate": 0.876, "engagement_multiplier": 1.3, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0, "latest_active_date": "2026-03-24", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST002156", "rfm_segment_v2": "Champions", "rfm_segment": "5-5-5", "cltv_segment": "Platinum", "cltv_adjusted_v2": 8420.75, "cltv_adjusted": 8250.50, "monetary": 14856.25, "frequency": 142, "recency": 3, "churn_segment": "Healthy", "churn_probability": 0.003, "churn_score": 1, "churn_browse_signal": "Active", "browse_conversion_score": 0.891, "email_engagement_rate": 0.845, "engagement_multiplier": 1.3, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0, "latest_active_date": "2026-03-24", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST003452", "rfm_segment_v2": "Loyal", "rfm_segment": "4-5-5", "cltv_segment": "Gold", "cltv_adjusted_v2": 3650.25, "cltv_adjusted": 3450.00, "monetary": 8950.50, "frequency": 98, "recency": 5, "churn_segment": "Low Risk", "churn_probability": 0.045, "churn_score": 2, "churn_browse_signal": "Warm", "browse_conversion_score": 0.756, "email_engagement_rate": 0.712, "engagement_multiplier": 1.2, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0, "latest_active_date": "2026-03-22", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST004789", "rfm_segment_v2": "Loyal", "rfm_segment": "4-5-4", "cltv_segment": "Gold", "cltv_adjusted_v2": 3425.50, "cltv_adjusted": 3200.75, "monetary": 8420.25, "frequency": 92, "recency": 6, "churn_segment": "Low Risk", "churn_probability": 0.051, "churn_score": 2, "churn_browse_signal": "Warm", "browse_conversion_score": 0.734, "email_engagement_rate": 0.698, "engagement_multiplier": 1.2, "cart_conversion_flag": 1, "is_net_returner": 0, "high_cancel_rate": 0, "latest_active_date": "2026-03-21", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST005234", "rfm_segment_v2": "Potential Loyalists", "rfm_segment": "3-4-4", "cltv_segment": "Silver", "cltv_adjusted_v2": 1850.75, "cltv_adjusted": 1650.50, "monetary": 4500.25, "frequency": 45, "recency": 12, "churn_segment": "Medium Risk", "churn_probability": 0.287, "churn_score": 5, "churn_browse_signal": "Cool", "browse_conversion_score": 0.562, "email_engagement_rate": 0.445, "engagement_multiplier": 1.1, "cart_conversion_flag": 1, "is_net_returner": 0, "high_cancel_rate": 0, "latest_active_date": "2026-03-18", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST006751", "rfm_segment_v2": "At Risk", "rfm_segment": "2-3-3", "cltv_segment": "Silver", "cltv_adjusted_v2": 1250.50, "cltv_adjusted": 1050.25, "monetary": 3200.75, "frequency": 32, "recency": 45, "churn_segment": "High Risk", "churn_probability": 0.742, "churn_score": 8, "churn_browse_signal": "Cold", "browse_conversion_score": 0.234, "email_engagement_rate": 0.156, "engagement_multiplier": 0.8, "cart_conversion_flag": 0, "is_net_returner": 1, "high_cancel_rate": 0, "latest_active_date": "2026-02-07", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST007923", "rfm_segment_v2": "Cart Abandoner", "rfm_segment": "3-3-2", "cltv_segment": "Bronze", "cltv_adjusted_v2": 820.75, "cltv_adjusted": 650.50, "monetary": 1950.25, "frequency": 28, "recency": 2, "churn_segment": "Medium Risk", "churn_probability": 0.365, "churn_score": 6, "churn_browse_signal": "Warm", "browse_conversion_score": 0.645, "email_engagement_rate": 0.534, "engagement_multiplier": 1.0, "cart_conversion_flag": 0, "is_net_returner": 0, "high_cancel_rate": 0, "latest_active_date": "2026-03-23", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST008456", "rfm_segment_v2": "Window Shopper", "rfm_segment": "2-1-4", "cltv_segment": "Bronze", "cltv_adjusted_v2": 350.25, "cltv_adjusted": 250.75, "monetary": 0.00, "frequency": 0, "recency": 8, "churn_segment": "High Risk", "churn_probability": 0.825, "churn_score": 8, "churn_browse_signal": "Cool", "browse_conversion_score": 0.156, "email_engagement_rate": 0.089, "engagement_multiplier": 0.8, "cart_conversion_flag": 0, "is_net_returner": 0, "high_cancel_rate": 0, "latest_active_date": "2026-03-16", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST009187", "rfm_segment_v2": "Re-Engaged", "rfm_segment": "4-3-3", "cltv_segment": "Silver", "cltv_adjusted_v2": 1420.50, "cltv_adjusted": 1250.75, "monetary": 3850.25, "frequency": 34, "recency": 18, "churn_segment": "Low Risk", "churn_probability": 0.128, "churn_score": 3, "churn_browse_signal": "Warm", "browse_conversion_score": 0.678, "email_engagement_rate": 0.567, "engagement_multiplier": 1.15, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0, "latest_active_date": "2026-03-19", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST010234", "rfm_segment_v2": "Hibernating", "rfm_segment": "1-1-1", "cltv_segment": "Dormant", "cltv_adjusted_v2": 0.00, "cltv_adjusted": 0.00, "monetary": 500.25, "frequency": 3, "recency": 892, "churn_segment": "High Risk", "churn_probability": 0.951, "churn_score": 9, "churn_browse_signal": "Dark", "browse_conversion_score": 0.012, "email_engagement_rate": 0.001, "engagement_multiplier": 0.8, "cart_conversion_flag": 0, "is_net_returner": 0, "high_cancel_rate": 0, "latest_active_date": "2022-12-15", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST011567", "rfm_segment_v2": "Champions", "rfm_segment": "5-5-5", "cltv_segment": "Platinum", "cltv_adjusted_v2": 7850.25, "cltv_adjusted": 7650.75, "monetary": 13500.50, "frequency": 128, "recency": 1, "churn_segment": "Healthy", "churn_probability": 0.001, "churn_score": 1, "churn_browse_signal": "Active", "browse_conversion_score": 0.912, "email_engagement_rate": 0.892, "engagement_multiplier": 1.3, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0, "latest_active_date": "2026-03-24", "churn_model_version": "v2.1.5"},
            {"master_customer_id": "CUST012890", "rfm_segment_v2": "Loyal", "rfm_segment": "4-4-5", "cltv_segment": "Gold", "cltv_adjusted_v2": 3200.75, "cltv_adjusted": 3000.50, "monetary": 7850.25, "frequency": 87, "recency": 7, "churn_segment": "Low Risk", "churn_probability": 0.067, "churn_score": 2, "churn_browse_signal": "Warm", "browse_conversion_score": 0.712, "email_engagement_rate": 0.667, "engagement_multiplier": 1.2, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0, "latest_active_date": "2026-03-20", "churn_model_version": "v2.1.5"},
        ]
        return jsonify(mock_customers)
    
    df = qdf(f"""
        SELECT
            master_customer_id,
            rfm_segment_v2,
            rfm_segment,
            cltv_segment,
            ROUND(cltv_adjusted_v2,2)          AS cltv_adjusted_v2,
            ROUND(cltv_adjusted,2)              AS cltv_adjusted,
            ROUND(monetary,2)                   AS monetary,
            frequency,
            recency,
            churn_segment,
            ROUND(churn_probability,3)          AS churn_probability,
            churn_score,
            churn_browse_signal,
            ROUND(browse_conversion_score,3)    AS browse_conversion_score,
            ROUND(email_engagement_rate,3)      AS email_engagement_rate,
            engagement_multiplier,
            cart_conversion_flag,
            is_net_returner,
            high_cancel_rate,
            CAST(latest_active_date AS VARCHAR) AS latest_active_date,
            churn_model_version
        FROM {TABLE}
        ORDER BY cltv_adjusted_v2 DESC
        LIMIT 20
    """)
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/samples/<path:segment>")
def api_samples(segment):
    if not DB_AVAILABLE:
        # Return mock samples regardless of segment
        mock_samples = [
            {"master_customer_id": "SM001", "rfm_segment_v2": "Champions", "rfm_segment": "5-5-5", "cltv_segment": "Platinum", "cltv_adjusted_v2": 5200.75, "monetary": 12500.25, "frequency": 125, "recency": 2, "churn_segment": "Healthy", "churn_probability": 0.002, "churn_browse_signal": "Active", "browse_conversion_score": 0.89, "email_engagement_rate": 0.85, "engagement_multiplier": 1.3, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0},
            {"master_customer_id": "SM002", "rfm_segment_v2": "Champions", "rfm_segment": "5-5-5", "cltv_segment": "Platinum", "cltv_adjusted_v2": 4850.50, "monetary": 11800.75, "frequency": 112, "recency": 3, "churn_segment": "Healthy", "churn_probability": 0.003, "churn_browse_signal": "Active", "browse_conversion_score": 0.87, "email_engagement_rate": 0.82, "engagement_multiplier": 1.3, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0},
            {"master_customer_id": "SM003", "rfm_segment_v2": "Loyal", "rfm_segment": "4-5-5", "cltv_segment": "Gold", "cltv_adjusted_v2": 2450.25, "monetary": 6500.50, "frequency": 78, "recency": 5, "churn_segment": "Low Risk", "churn_probability": 0.045, "churn_browse_signal": "Warm", "browse_conversion_score": 0.65, "email_engagement_rate": 0.60, "engagement_multiplier": 1.2, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0},
            {"master_customer_id": "SM004", "rfm_segment_v2": "Loyal", "rfm_segment": "4-5-4", "cltv_segment": "Gold", "cltv_adjusted_v2": 2200.75, "monetary": 5950.25, "frequency": 72, "recency": 6, "churn_segment": "Low Risk", "churn_probability": 0.051, "churn_browse_signal": "Warm", "browse_conversion_score": 0.62, "email_engagement_rate": 0.58, "engagement_multiplier": 1.2, "cart_conversion_flag": 1, "is_net_returner": 0, "high_cancel_rate": 0},
            {"master_customer_id": "SM005", "rfm_segment_v2": "Potential Loyalists", "rfm_segment": "3-4-4", "cltv_segment": "Silver", "cltv_adjusted_v2": 950.50, "monetary": 3200.75, "frequency": 35, "recency": 12, "churn_segment": "Medium Risk", "churn_probability": 0.287, "churn_browse_signal": "Cool", "browse_conversion_score": 0.45, "email_engagement_rate": 0.38, "engagement_multiplier": 1.1, "cart_conversion_flag": 0, "is_net_returner": 0, "high_cancel_rate": 0},
            {"master_customer_id": "SM006", "rfm_segment_v2": "At Risk", "rfm_segment": "2-3-3", "cltv_segment": "Silver", "cltv_adjusted_v2": 750.25, "monetary": 2100.50, "frequency": 22, "recency": 45, "churn_segment": "High Risk", "churn_probability": 0.742, "churn_browse_signal": "Cold", "browse_conversion_score": 0.22, "email_engagement_rate": 0.12, "engagement_multiplier": 0.8, "cart_conversion_flag": 0, "is_net_returner": 1, "high_cancel_rate": 1},
            {"master_customer_id": "SM007", "rfm_segment_v2": "Cart Abandoner", "rfm_segment": "3-3-2", "cltv_segment": "Bronze", "cltv_adjusted_v2": 550.75, "monetary": 1450.25, "frequency": 18, "recency": 2, "churn_segment": "Medium Risk", "churn_probability": 0.365, "churn_browse_signal": "Warm", "browse_conversion_score": 0.58, "email_engagement_rate": 0.48, "engagement_multiplier": 1.0, "cart_conversion_flag": 0, "is_net_returner": 0, "high_cancel_rate": 0},
            {"master_customer_id": "SM008", "rfm_segment_v2": "Window Shopper", "rfm_segment": "2-1-4", "cltv_segment": "Bronze", "cltv_adjusted_v2": 125.50, "monetary": 0.00, "frequency": 0, "recency": 8, "churn_segment": "High Risk", "churn_probability": 0.825, "churn_browse_signal": "Cool", "browse_conversion_score": 0.12, "email_engagement_rate": 0.06, "engagement_multiplier": 0.8, "cart_conversion_flag": 0, "is_net_returner": 0, "high_cancel_rate": 0},
            {"master_customer_id": "SM009", "rfm_segment_v2": "Re-Engaged", "rfm_segment": "4-3-3", "cltv_segment": "Silver", "cltv_adjusted_v2": 1100.25, "monetary": 2950.75, "frequency": 28, "recency": 18, "churn_segment": "Low Risk", "churn_probability": 0.128, "churn_browse_signal": "Warm", "browse_conversion_score": 0.62, "email_engagement_rate": 0.50, "engagement_multiplier": 1.15, "cart_conversion_flag": 1, "is_net_returner": 1, "high_cancel_rate": 0},
            {"master_customer_id": "SM010", "rfm_segment_v2": "Hibernating", "rfm_segment": "1-1-1", "cltv_segment": "Dormant", "cltv_adjusted_v2": 0.00, "monetary": 300.25, "frequency": 2, "recency": 892, "churn_segment": "High Risk", "churn_probability": 0.951, "churn_browse_signal": "Dark", "browse_conversion_score": 0.01, "email_engagement_rate": 0.00, "engagement_multiplier": 0.8, "cart_conversion_flag": 0, "is_net_returner": 0, "high_cancel_rate": 0}
        ]
        return jsonify(mock_samples)
    
    where = SEG_FILTER.get(segment, f"rfm_segment_v2='{segment}'")
    df = qdf(f"""
        SELECT master_customer_id, rfm_segment_v2, rfm_segment, cltv_segment,
               ROUND(cltv_adjusted_v2,2) AS cltv_adjusted_v2,
               ROUND(monetary,2) AS monetary, frequency, recency,
               churn_segment, ROUND(churn_probability,3) AS churn_probability,
               churn_browse_signal, engagement_multiplier,
               ROUND(browse_conversion_score,3) AS browse_conversion_score,
               ROUND(email_engagement_rate,3)   AS email_engagement_rate,
               cart_conversion_flag, is_net_returner, high_cancel_rate
        FROM {TABLE} WHERE {where}
        ORDER BY cltv_adjusted_v2 DESC LIMIT 10
    """)
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/download/<path:segment>")
def api_download(segment):
    from flask import request as freq
    n = int(freq.args.get("n", 100))
    n = min(n, 500)  # hard cap

    if not DB_AVAILABLE:
        # Return mock CSV data in demo mode
        mock_csv = """Customer ID,First Name,Last Name,Email Address,Phone Number,Address,City,State,Zip Code,Customer Segment,Value Tier,Predicted Value (12m $),Total Spend to Date ($),Total Orders,Days Since Last Order,Churn Risk Level,Churn Probability,Online Engagement,Browse Conversion Score,Email Engagement Rate,Engagement Multiplier,Completed Cart Checkout,Net Returner,High Cancel Rate,Last Active Date
CUST001845,John,Smith,john.smith@email.com,555-0101,123 Main St,New York,NY,10001,Champions,Platinum,8950.50,15420.75,156,2,Healthy,0.002,Active,0.925,0.876,1.3,Yes,Yes,No,2026-03-24
CUST002156,Sarah,Johnson,sarah.j@email.com,555-0102,456 Oak Ave,Los Angeles,CA,90001,Champions,Platinum,8420.75,14856.25,142,3,Healthy,0.003,Active,0.891,0.845,1.3,Yes,Yes,No,2026-03-24
CUST003452,Michael,Davis,m.davis@email.com,555-0103,789 Pine Rd,Chicago,IL,60601,Loyal,Gold,3650.25,8950.50,98,5,Low Risk,0.045,Warm,0.756,0.712,1.2,Yes,Yes,No,2026-03-22
CUST004789,Emily,Wilson,e.wilson@email.com,555-0104,321 Elm St,Houston,TX,77001,Loyal,Gold,3425.50,8420.25,92,6,Low Risk,0.051,Warm,0.734,0.698,1.2,Yes,No,No,2026-03-21
CUST005234,David,Martinez,d.martinez@email.com,555-0105,654 Maple Dr,Phoenix,AZ,85001,Potential Loyalists,Silver,1850.75,4500.25,45,12,Medium Risk,0.287,Cool,0.562,0.445,1.1,Yes,No,No,2026-03-18
CUST006751,Jessica,Taylor,j.taylor@email.com,555-0106,987 Cedar Ln,Philadelphia,PA,19101,At Risk,Silver,1250.50,3200.75,32,45,High Risk,0.742,Cold,0.234,0.156,0.8,No,Yes,No,2026-02-07
CUST007923,Robert,Anderson,r.anderson@email.com,555-0107,147 Birch St,San Antonio,TX,78201,Cart Abandoner,Bronze,820.75,1950.25,28,2,Medium Risk,0.365,Warm,0.645,0.534,1.0,No,No,No,2026-03-23
CUST008456,Amanda,Thomas,a.thomas@email.com,555-0108,258 Walnut Ave,San Diego,CA,92101,Window Shopper,Bronze,350.25,0.00,0,8,High Risk,0.825,Cool,0.156,0.089,0.8,No,No,No,2026-03-16
CUST009187,Christopher,Jackson,c.jackson@email.com,555-0109,369 Ash Rd,Dallas,TX,75201,Re-Engaged,Silver,1420.50,3850.25,34,18,Low Risk,0.128,Warm,0.678,0.567,1.15,Yes,Yes,No,2026-03-19
CUST010234,Lisa,White,l.white@email.com,555-0110,741 Spruce Dr,San Jose,CA,95101,Hibernating,Dormant,0.00,500.25,3,892,High Risk,0.951,Dark,0.012,0.001,0.8,No,No,No,2022-12-15"""
        
        buf = io.StringIO()
        buf.write(mock_csv)
        fname = f"LP_{segment.replace(' ','_')}_top{n}_{date.today()}.csv"
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={fname}"})
    
    # ── PII table config ──────────────────────────────────
    PII_TABLE       = "KIRAN.TBL_D_CUSTOMER"
    PII_JOIN_KEY    = "master_customer_id"
    PII_EMAIL_COL   = "email_address"
    PII_PHONE_COL   = "phone_number"
    PII_FNAME_COL   = "first_name"
    PII_LNAME_COL   = "last_name"
    PII_ADDR_COL    = "address_line1"
    PII_CITY_COL    = "city"
    PII_STATE_COL   = "state"
    PII_ZIP_COL     = "zip_code"
    # ─────────────────────────────────────────────────────

    where = "1=1" if segment == "all" else SEG_FILTER.get(segment, f"rfm_segment_v2='{segment}'")

    try:
        df = qdf(f"""
            SELECT
                p.master_customer_id                                AS "Customer ID",
                pii.{PII_FNAME_COL}                                 AS "First Name",
                pii.{PII_LNAME_COL}                                 AS "Last Name",
                pii.{PII_EMAIL_COL}                                 AS "Email Address",
                pii.{PII_PHONE_COL}                                 AS "Phone Number",
                pii.{PII_ADDR_COL}                                  AS "Address",
                pii.{PII_CITY_COL}                                  AS "City",
                pii.{PII_STATE_COL}                                 AS "State",
                pii.{PII_ZIP_COL}                                   AS "Zip Code",
                p.rfm_segment_v2                                    AS "Customer Segment",
                p.cltv_segment                                      AS "Value Tier",
                ROUND(p.cltv_adjusted_v2, 2)                        AS "Predicted Value (12m $)",
                ROUND(p.monetary, 2)                                AS "Total Spend to Date ($)",
                p.frequency                                         AS "Total Orders",
                p.recency                                           AS "Days Since Last Order",
                p.churn_segment                                     AS "Churn Risk Level",
                ROUND(p.churn_probability, 2)                       AS "Churn Probability",
                p.churn_browse_signal                               AS "Online Engagement",
                ROUND(p.browse_conversion_score, 3)                 AS "Browse Conversion Score",
                ROUND(p.email_engagement_rate, 3)                   AS "Email Engagement Rate",
                p.engagement_multiplier                             AS "Engagement Multiplier",
                CASE WHEN p.cart_conversion_flag=1 THEN 'Yes' ELSE 'No' END AS "Completed Cart Checkout",
                CASE WHEN p.is_net_returner=1      THEN 'Yes' ELSE 'No' END AS "Net Returner",
                CASE WHEN p.high_cancel_rate=1     THEN 'Yes' ELSE 'No' END AS "High Cancel Rate",
                CAST(p.latest_active_date AS VARCHAR)               AS "Last Active Date"
            FROM {TABLE} p
            LEFT JOIN {PII_TABLE} pii
                ON p.{PII_JOIN_KEY} = pii.{PII_JOIN_KEY}
            WHERE {where}
            ORDER BY p.cltv_adjusted_v2 DESC
            LIMIT {n}
        """)
    except Exception as e:
        import traceback; traceback.print_exc()
        pii_err = str(e).replace("'","")
        df = qdf(f"""
            SELECT
                master_customer_id                              AS "Customer ID",
                '-- PII join failed: {pii_err[:80]}' AS "First Name",
                ''                                              AS "Last Name",
                ''                                             AS "Email Address",
                ''                                             AS "Phone Number",
                ''                                             AS "Address",
                ''                                             AS "City",
                ''                                             AS "State",
                ''                                             AS "Zip Code",
                rfm_segment_v2                                  AS "Customer Segment",
                cltv_segment                                    AS "Value Tier",
                ROUND(cltv_adjusted_v2, 2)                      AS "Predicted Value (12m $)",
                ROUND(monetary, 2)                              AS "Total Spend to Date ($)",
                frequency                                       AS "Total Orders",
                recency                                         AS "Days Since Last Order",
                churn_segment                                   AS "Churn Risk Level",
                ROUND(churn_probability, 2)                     AS "Churn Probability",
                churn_browse_signal                             AS "Online Engagement",
                ROUND(browse_conversion_score, 3)               AS "Browse Conversion Score",
                ROUND(email_engagement_rate, 3)                 AS "Email Engagement Rate",
                engagement_multiplier                           AS "Engagement Multiplier",
                CASE WHEN cart_conversion_flag=1 THEN 'Yes' ELSE 'No' END AS "Completed Cart Checkout",
                CASE WHEN is_net_returner=1      THEN 'Yes' ELSE 'No' END AS "Net Returner",
                CASE WHEN high_cancel_rate=1     THEN 'Yes' ELSE 'No' END AS "High Cancel Rate",
                CAST(latest_active_date AS VARCHAR)             AS "Last Active Date"
            FROM {TABLE}
            WHERE {where}
            ORDER BY cltv_adjusted_v2 DESC
            LIMIT {n}
        """)

    buf = io.StringIO(); df.to_csv(buf, index=False)
    fname = f"LP_{segment.replace(' ','_')}_top{n}_{date.today()}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})

@app.route("/")
def index():
    # Serve internal_dashboard.html from same directory as this script
    html_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "internal_dashboard.html")
    return send_file(html_path)

if __name__ == "__main__":
    print("\n  ╔════════════════════════════════════════════════╗")
    print("  ║  LampsPlus Internal Data Platform             ║")
    print("  ║  http://localhost:5050                        ║")
    print("  ╚════════════════════════════════════════════════╝\n")
    app.run(debug=True, port=5050, host="0.0.0.0")

