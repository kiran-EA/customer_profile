"""
LampsPlus Customer Dashboard — Vercel Serverless API
Optimized for Vercel's serverless environment with connection pooling
"""
from flask import Flask, jsonify, Response, request, send_from_directory
import os
import json
from datetime import date, datetime
import sys

# Import Redshift connector with error handling
try:
    import redshift_connector
    import pandas as pd
    import io
except ImportError as e:
    print(f"Import error: {e}", file=sys.stderr)
    raise

app = Flask(__name__)

# Resolve the absolute path to the public directory
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'public')

# ══════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════

TABLE = "KIRAN.TBL_CUSTOMER_PROFILE"

# Redshift connection config from environment variables
DB_CONFIG = {
    "host": os.environ.get("REDSHIFT_HOST", "ea-non-prod.cxw4zfxatj9b.us-west-1.redshift.amazonaws.com"),
    "port": int(os.environ.get("REDSHIFT_PORT", "5439")),
    "database": os.environ.get("REDSHIFT_DATABASE", "express"),
    "user": os.environ.get("REDSHIFT_USER", "easuper"),
    "password": os.environ.get("REDSHIFT_PASSWORD", "LAMRedPWD@2024")
}

# Connection pooling for Vercel
_connection_cache = None
_cache_timestamp = None
CACHE_TIMEOUT = 300  # 5 minutes

def get_connection():
    """Get or reuse Redshift connection with timeout"""
    global _connection_cache, _cache_timestamp
    
    current_time = datetime.now().timestamp()
    
    # Reuse connection if valid
    if _connection_cache and _cache_timestamp:
        if current_time - _cache_timestamp < CACHE_TIMEOUT:
            try:
                # Test connection
                _connection_cache.cursor().execute("SELECT 1")
                return _connection_cache
            except:
                _connection_cache = None
    
    # Create new connection
    _connection_cache = redshift_connector.connect(**DB_CONFIG)
    _connection_cache.autocommit = True
    _cache_timestamp = current_time
    return _connection_cache

def qdf(sql):
    """Execute query and return DataFrame"""
    try:
        conn = get_connection()
        df = pd.read_sql(sql, conn)
        return df
    except Exception as e:
        print(f"Query error: {e}", file=sys.stderr)
        raise

# ══════════════════════════════════════════════════════════
# SEGMENT METADATA
# ══════════════════════════════════════════════════════════

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
    """Activity-based filter covering ALL customer types within N years"""
    if not years or int(years) == 0:
        return "1=1"
    days = int(years) * 365
    return (
        f"("
        f"  LEAST(recency, COALESCE(effective_recency, 9999)) <= {days}"
        f"  OR CAST(customer_reg_date AS DATE) >= CAST(DATEADD(year, -{int(years)}, CURRENT_DATE) AS DATE)"
        f")"
    )

# ══════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════

@app.route("/api/health")
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "table": TABLE
    })

@app.route("/api/summary")
def api_summary():
    wh = date_where(request.args.get("years","0"))
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
            COUNT(CASE WHEN rfm_score IS NULL THEN 1 END)                     AS null_rfm,
            COUNT(CASE WHEN cltv_adjusted IS NULL THEN 1 END)                 AS null_cltv_adj,
            COUNT(CASE WHEN churn_probability IS NULL THEN 1 END)             AS null_churn,
            COUNT(CASE WHEN cltv_adjusted_v2 IS NULL THEN 1 END)              AS null_cltv_v2,
            COUNT(CASE WHEN churn_browse_signal IS NULL THEN 1 END)           AS null_browse_sig,
            COUNT(CASE WHEN rfm_score<1 OR rfm_score>10 THEN 1 END)          AS bad_rfm,
            COUNT(CASE WHEN cltv_score<1 OR cltv_score>100 THEN 1 END)       AS bad_cltv,
            COUNT(CASE WHEN churn_probability<0 OR churn_probability>1 THEN 1 END) AS bad_churn_prob,
            COUNT(CASE WHEN engagement_multiplier NOT IN (0.8,1.0,1.1,1.2,1.3) THEN 1 END) AS bad_mult
        FROM {TABLE}
    """)
    return jsonify(df.iloc[0].to_dict())

@app.route("/api/segments")
def api_segments():
    wh = date_where(request.args.get("years","0"))
    df = qdf(f"""
        SELECT rfm_segment_v2 AS segment,
               COUNT(*)                                              AS customers,
               ROUND(AVG(cltv_adjusted_v2),2)                        AS avg_cltv,
               ROUND(SUM(cltv_adjusted_v2),0)                        AS total_value,
               ROUND(AVG(recency),1)                                 AS avg_recency,
               ROUND(AVG(frequency),1)                               AS avg_frequency,
               ROUND(AVG(monetary),2)                                AS avg_monetary,
               COUNT(CASE WHEN churn_segment='High Risk' THEN 1 END) AS high_risk
        FROM {TABLE}
        WHERE {wh} AND rfm_segment_v2 IS NOT NULL
        GROUP BY rfm_segment_v2
    """)
    
    # Enrich with metadata
    result = []
    for _, row in df.iterrows():
        seg = row['segment']
        meta = SEG_META.get(seg, {})
        result.append({
            **row.to_dict(),
            "color": meta.get("color", "#6b7280"),
            "emoji": meta.get("emoji", "📊"),
            "action": meta.get("action", "Standard nurture")
        })
    
    return jsonify(result)

@app.route("/api/cltv_distribution")
def api_cltv_dist():
    wh = date_where(request.args.get("years","0"))
    df = qdf(f"""
        SELECT cltv_segment AS tier,
               COUNT(*) AS customers,
               ROUND(AVG(cltv_adjusted_v2),2) AS avg_value,
               ROUND(SUM(cltv_adjusted_v2),0) AS total_value
        FROM {TABLE}
        WHERE {wh} AND cltv_segment IS NOT NULL
        GROUP BY cltv_segment
    """)
    
    result = []
    for _, row in df.iterrows():
        tier = row['tier']
        result.append({
            **row.to_dict(),
            "color": CLTV_C.get(tier, "#6b7280")
        })
    
    return jsonify(result)

@app.route("/api/churn_distribution")
def api_churn_dist():
    wh = date_where(request.args.get("years","0"))
    df = qdf(f"""
        SELECT churn_segment AS risk_level,
               COUNT(*) AS customers,
               ROUND(AVG(churn_probability),3) AS avg_probability,
               ROUND(SUM(cltv_adjusted_v2),0) AS value_at_risk
        FROM {TABLE}
        WHERE {wh} AND churn_segment IS NOT NULL
        GROUP BY churn_segment
    """)
    
    result = []
    for _, row in df.iterrows():
        risk = row['risk_level']
        result.append({
            **row.to_dict(),
            "color": CHURN_C.get(risk, "#6b7280")
        })
    
    return jsonify(result)

@app.route("/api/engagement_distribution")
def api_engagement_dist():
    wh = date_where(request.args.get("years","0"))
    df = qdf(f"""
        SELECT churn_browse_signal AS level,
               COUNT(*) AS customers,
               ROUND(AVG(browse_conversion_score),3) AS avg_browse_score,
               ROUND(AVG(email_engagement_rate),3) AS avg_email_rate
        FROM {TABLE}
        WHERE {wh} AND churn_browse_signal IS NOT NULL
        GROUP BY churn_browse_signal
    """)
    
    result = []
    for _, row in df.iterrows():
        level = row['level']
        result.append({
            **row.to_dict(),
            "color": ENG_C.get(level, "#6b7280")
        })
    
    return jsonify(result)

@app.route("/api/top_customers")
def api_top_customers():
    wh = date_where(request.args.get("years","0"))
    df = qdf(f"""
        SELECT 
            master_customer_id,
            rfm_segment_v2,
            cltv_segment,
            ROUND(cltv_adjusted_v2,2) AS cltv_value,
            ROUND(monetary,2) AS total_spend,
            frequency AS orders,
            recency AS days_since_order,
            churn_segment,
            ROUND(churn_probability,3) AS churn_prob
        FROM {TABLE}
        WHERE {wh} AND cltv_adjusted_v2 IS NOT NULL
        ORDER BY cltv_adjusted_v2 DESC
        LIMIT 20
    """)
    return jsonify(df.to_dict(orient="records"))

@app.route("/api/samples/<path:segment>")
def api_samples(segment):
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
    """Download segment data as CSV"""
    PII_TABLE = "KIRAN.TBL_D_CUSTOMER"
    PII_JOIN_KEY = "master_customer_id"
    PII_EMAIL_COL = "email_address"
    PII_PHONE_COL = "phone_number"
    PII_FNAME_COL = "first_name"
    PII_LNAME_COL = "last_name"
    PII_ADDR_COL = "address_line1"
    PII_CITY_COL = "city"
    PII_STATE_COL = "state"
    PII_ZIP_COL = "zip_code"
    
    n = int(request.args.get("n", 100))
    n = min(n, 500)  # hard cap
    
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
        # Fallback without PII join
        df = qdf(f"""
            SELECT
                master_customer_id                              AS "Customer ID",
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
    
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    fname = f"LP_{segment.replace(' ','_')}_top{n}_{date.today()}.csv"
    
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )

# ══════════════════════════════════════════════════════════
# SERVE STATIC HTML
# ══════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the main dashboard HTML"""
    return send_from_directory(PUBLIC_DIR, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    """Serve static files"""
    return send_from_directory(PUBLIC_DIR, path)

# Vercel serverless handler
def handler(request):
    with app.request_context(request):
        return app.full_dispatch_request()
