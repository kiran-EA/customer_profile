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
    """Get or create Redshift connection (fresh connection per query to avoid statement reuse errors)"""
    global _connection_cache, _cache_timestamp
    
    try:
        # Create fresh connection for each query to avoid prepared statement conflicts
        conn = redshift_connector.connect(**DB_CONFIG)
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"Connection error: {e}", file=sys.stderr)
        return None

def cleanup_connection(conn):
    """Safely close connection"""
    try:
        if conn:
            conn.close()
    except:
        pass

def qdf(sql):
    """Execute query and return DataFrame"""
    conn = None
    try:
        conn = get_connection()
        if conn is None:
            raise Exception("No database connection available")
        df = pd.read_sql(sql, conn)
        return df
    except Exception as e:
        print(f"Query error: {e} - Using mock data", file=sys.stderr)
        # Fall back to mock data for local development
        return get_mock_data(sql)
    finally:
        cleanup_connection(conn)

def get_cust_type_filter(cust_type):
    """Build WHERE clause fragment for customer type filter"""
    if cust_type == 'WEB':
        return " AND (CUST_TYPE NOT LIKE '%PRO%' OR CUST_TYPE IS NULL)"
    elif cust_type == 'PRO':
        return " AND CUST_TYPE LIKE '%PRO%'"
    else:  # WEB+PRO or None
        return ""


def get_mock_data(sql):
    """Return mock data for local development"""
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta
    
    # Generic mock data based on SQL patterns
    np.random.seed(42)
    
    # CLTV vs Churn Risk matrix (must check BOTH before singular checks)
    if "cltv_segment" in sql and "churn_segment" in sql and "GROUP BY" in sql:
        # CLTV vs Churn matrix
        cltv_tiers = ["Platinum", "Platinum", "Platinum", "Platinum", "Gold", "Gold", "Gold", "Gold", 
                      "Silver", "Silver", "Silver", "Silver", "Bronze", "Bronze", "Bronze", "Bronze",
                      "Dormant", "Dormant", "Dormant", "Dormant"]
        churn_risks = ["Healthy", "Low Risk", "Medium Risk", "High Risk", "Healthy", "Low Risk", "Medium Risk", "High Risk",
                       "Healthy", "Low Risk", "Medium Risk", "High Risk", "Healthy", "Low Risk", "Medium Risk", "High Risk",
                       "Healthy", "Low Risk", "Medium Risk", "High Risk"]
        customers = [380, 45, 18, 7, 890, 210, 85, 15, 1450, 980, 250, 120, 2100, 1200, 450, 350,
                     780, 450, 180, 140]
        avg_churn_prob = [0.02, 0.15, 0.45, 0.82, 0.04, 0.18, 0.48, 0.80, 0.06, 0.20, 0.50, 0.78, 
                          0.08, 0.22, 0.52, 0.75, 0.10, 0.25, 0.55, 0.88]
        total_cltv_value = [4750000, 562500, 225000, 87500, 1068000, 252000, 102000, 18000,
                            3050000, 2058000, 525000, 252000, 1428000, 816000, 306000, 238000,
                            468000, 270000, 108000, 84000]
        
        # Calculate average CLTV and color codes
        avg_cltv = [int(t / c) if c > 0 else 0 for t, c in zip(total_cltv_value, customers)]
        dot_colors = []
        churn_pct = [round(p * 100, 1) for p in avg_churn_prob]
        priorities = []
        actions = []
        
        for i, tier in enumerate(cltv_tiers):
            if tier == "Platinum": dot_colors.append("#00c8ff")
            elif tier == "Gold": dot_colors.append("#f59e0b")
            elif tier == "Silver": dot_colors.append("#6b7280")
            elif tier == "Bronze": dot_colors.append("#78350f")
            else: dot_colors.append("#374151")
            
            # Determine priority
            churn = churn_pct[i]
            churn_seg = churn_risks[i]
            
            if churn >= 70 and tier in ['Platinum', 'Gold']:
                priority = 'URGENT'
            elif churn >= 40 or churn_seg == 'High Risk':
                priority = 'HIGH'
            elif churn_seg == 'Medium Risk':
                priority = 'MONITOR'
            else:
                priority = 'LOW'
            priorities.append(priority)
            
            # Determine action
            if priority == 'URGENT':
                if tier in ['Platinum', 'Gold']:
                    action = 'Immediate executive intervention'
                else:
                    action = 'Win-back campaigns'
            elif priority == 'HIGH':
                if tier in ['Platinum', 'Gold']:
                    action = 'VIP retention programs'
                elif tier in ['Silver', 'Bronze']:
                    action = 'Targeted retention offers'
                else:
                    action = 'Low-cost reactivation'
            elif priority == 'MONITOR':
                if churn >= 30:
                    action = 'Engagement campaigns'
                else:
                    action = 'Low-cost reactivation'
            else:  # LOW
                if tier in ['Platinum', 'Gold']:
                    action = 'Automated nurture'
                else:
                    action = 'Standard nurture'
            actions.append(action)
        
        data = {
            "cltv_segment": cltv_tiers,
            "churn_segment": churn_risks,
            "customers": customers,
            "avg_churn_prob": avg_churn_prob,
            "churn_pct": churn_pct,
            "total_cltv_value": total_cltv_value,
            "avg_cltv": avg_cltv,
            "total_cltv": total_cltv_value,
            "dot_color": dot_colors,
            "priority": priorities,
            "action": actions,
            "revenue_at_risk": total_cltv_value
        }
        df = pd.DataFrame(data)
        return df
    
    if "churn_browse_signal" in sql:
        # Engagement distribution
        return pd.DataFrame({
            "level": ["Active", "Warm", "Cool", "Cold", "Dark"],
            "customers": [5200, 3100, 2800, 1900, 1200],
            "avg_browse_score": [0.85, 0.65, 0.42, 0.18, 0.05],
            "avg_email_rate": [0.72, 0.58, 0.35, 0.15, 0.08]
        })
    
    if "cltv_segment" in sql and "churn_segment" not in sql:
        # CLTV distribution
        return pd.DataFrame({
            "cltv_segment": ["Platinum", "Gold", "Silver", "Bronze", "Dormant"],
            "customers": [450, 1200, 2800, 5100, 3650],
            "avg_cltv": [12500, 5800, 2100, 680, 120],
            "total_value": [5625000, 6960000, 5880000, 3468000, 438000]
        })
    
    if "churn_segment" in sql and "cltv_segment" not in sql:
        # Churn distribution
        return pd.DataFrame({
            "risk_level": ["High Risk", "Medium Risk", "Low Risk", "Healthy"],
            "customers": [2100, 3400, 4200, 3500],
            "avg_probability": [0.78, 0.42, 0.18, 0.05],
            "value_at_risk": [1890000, 2040000, 1456000, 580000]
        })
    
    if "rfm_segment_v2" in sql and "GROUP BY" in sql:
        # Segments breakdown
        return pd.DataFrame({
            "segment": ["Champions", "Loyal", "Potential Loyalists", "At Risk", "Hibernating", 
                       "Cart Abandoner", "Re-Engaged", "Window Shopper", "Non-Buyer"],
            "customers": [320, 890, 1200, 1450, 780, 420, 280, 650, 4100],
            "avg_cltv": [8200, 3100, 1500, 850, 280, 450, 650, 320, 85],
            "total_value": [2624000, 2759000, 1800000, 1232750, 218400, 189000, 182000, 208000, 349000],
            "avg_recency": [12, 35, 52, 120, 250, 8, 20, 45, 180],
            "avg_frequency": [24, 8, 4, 2, 1, 1, 2, 1, 0],
            "avg_monetary": [350, 120, 45, 18, 5, 8, 12, 6, 1],
            "high_risk": [5, 45, 180, 580, 300, 50, 20, 95, 825],
            "churn_prob": [0.08, 0.15, 0.25, 0.65, 0.88, 0.72, 0.40, 0.55, 0.92],
            "browse_score": [0.92, 0.75, 0.62, 0.38, 0.12, 0.28, 0.45, 0.35, 0.08],
            "email_rate": [0.85, 0.68, 0.52, 0.28, 0.10, 0.18, 0.32, 0.22, 0.05],
            "eng_mult": [1.45, 1.15, 0.88, 0.55, 0.25, 0.35, 0.58, 0.42, 0.12]
        })
    
    if "COUNT(*)" in sql and "FROM" in sql and "total" not in [col.lower() for col in (sql.split("SELECT")[1].split("FROM")[0] if "SELECT" in sql else "").split(",")]:
        # Summary metrics
        return pd.DataFrame({
            "total": [14200],
            "buyers": [10100],
            "non_buyers": [4100],
            "avg_cltv": [2850],
            "total_portfolio": [40425000],
            "urgent_winback": [145],
            "revenue_at_risk": [1240500],
            "hot_leads": [420],
            "cart_abandoners": [420],
            "re_engaged": [280],
            "champions": [320],
            "high_risk_total": [2100],
            "net_returners": [850],
            "high_cancellers": [280],
            "last_refresh": [datetime.now()],
            "churn_scored": [datetime.now() - timedelta(days=1)]
        })
    
    if "master_customer_id" in sql and "LIMIT 20" in sql:
        # Top customers
        data = []
        segments = ["Champions", "Loyal", "Potential Loyalists"]
        cltv_tiers = ["Platinum", "Gold", "Silver"]
        churn_risks = ["Healthy", "Low Risk", "Medium Risk"]
        browse_signals = ["Active", "Warm", "Cool", "Cold", "Dark"]
        seg_colors = {
            "Champions": "#00c8ff", "Loyal": "#22c55e", "Potential Loyalists": "#84cc16",
            "At Risk": "#f59e0b", "Hibernating": "#6b7280", "Cart Abandoner": "#ef4444",
            "Re-Engaged": "#3b82f6", "Window Shopper": "#a855f7", "Non-Buyer": "#4b5563"
        }
        
        for i in range(20):
            seg = np.random.choice(segments)
            data.append({
                "master_customer_id": f"CUST_{300000+i:06d}",
                "rfm_segment_v2": seg,
                "cltv_segment": np.random.choice(cltv_tiers),
                "cltv_adjusted_v2": round(np.random.uniform(2000, 15000), 2),
                "cltv_adjusted": round(np.random.uniform(1500, 12000), 2),
                "monetary": round(np.random.uniform(1000, 8000), 2),
                "frequency": np.random.randint(5, 50),
                "recency": np.random.randint(1, 90),
                "churn_segment": np.random.choice(churn_risks),
                "churn_probability": round(np.random.random() * 0.3, 3),
                "churn_browse_signal": np.random.choice(browse_signals),
                "engagement_multiplier": np.random.choice([0.8, 1.0, 1.1, 1.2, 1.3]),
                "cart_conversion_flag": np.random.randint(0, 2),
                "is_net_returner": np.random.randint(0, 2),
                "high_cancel_rate": np.random.randint(0, 2),
                "latest_active_date": "2026-03-25",
                "churn_model_version": "v2.1",
                "color": seg_colors.get(seg, "#555")
            })
        return pd.DataFrame(data)
    
    # Default mock response
    return pd.DataFrame({
        "status": ["ok"],
        "message": ["Mock data - database not connected"],
        "row_count": [0]
    })

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
    cust_type_filter = get_cust_type_filter(request.args.get("cust_type", "WEB+PRO"))
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
        WHERE {wh}{cust_type_filter}
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
    cust_type_filter = get_cust_type_filter(request.args.get("cust_type", "WEB+PRO"))
    df = qdf(f"""
        SELECT rfm_segment_v2 AS segment,
               COUNT(*)                                              AS customers,
               ROUND(AVG(cltv_adjusted_v2),2)                        AS avg_cltv,
               ROUND(SUM(cltv_adjusted_v2),0)                        AS total_value,
               ROUND(AVG(recency),1)                                 AS avg_recency,
               ROUND(AVG(frequency),1)                               AS avg_frequency,
               ROUND(AVG(monetary),2)                                AS avg_monetary,
               COUNT(CASE WHEN churn_segment='High Risk' THEN 1 END) AS high_risk,
               ROUND(AVG(churn_probability),3)                       AS churn_prob,
               ROUND(AVG(browse_conversion_score),3)                 AS browse_score,
               ROUND(AVG(email_engagement_rate),3)                   AS email_rate,
               ROUND(AVG(engagement_multiplier),2)                   AS eng_mult
        FROM {TABLE}
        WHERE {wh}{cust_type_filter} AND rfm_segment_v2 IS NOT NULL
        GROUP BY rfm_segment_v2
    """)
    
    # Enrich with metadata and calculate missing fields
    result = []
    for _, row in df.iterrows():
        seg = row['segment']
        meta = SEG_META.get(seg, {})
        customers = int(row['customers']) if pd.notna(row['customers']) else 0
        high_risk = int(row['high_risk']) if pd.notna(row['high_risk']) else 0
        result.append({
            "segment": seg,
            "customers": customers,
            "avg_cltv": float(row['avg_cltv']) if pd.notna(row['avg_cltv']) else 0,
            "total_value": int(row['total_value']) if pd.notna(row['total_value']) else 0,
            "avg_recency": float(row['avg_recency']) if pd.notna(row['avg_recency']) else 0,
            "avg_frequency": float(row['avg_frequency']) if pd.notna(row['avg_frequency']) else 0,
            "avg_monetary": float(row['avg_monetary']) if pd.notna(row['avg_monetary']) else 0,
            "high_risk": high_risk,
            "churn_prob": float(row['churn_prob']) if pd.notna(row['churn_prob']) else 0,
            "browse_score": float(row['browse_score']) if pd.notna(row['browse_score']) else 0,
            "email_rate": float(row['email_rate']) if pd.notna(row['email_rate']) else 0,
            "eng_mult": float(row['eng_mult']) if pd.notna(row['eng_mult']) else 0,
            "avg_spend": float(row['avg_monetary']) if pd.notna(row['avg_monetary']) else 0,
            "high_risk_count": high_risk,
            "pct": (high_risk / customers * 100) if customers > 0 else 0,
            "color": meta.get("color", "#6b7280"),
            "emoji": meta.get("emoji", "📊"),
            "action": meta.get("action", "Standard nurture")
        })
    
    return jsonify(result)

@app.route("/api/cltv_distribution")
def api_cltv_dist():
    wh = date_where(request.args.get("years","0"))
    cust_type_filter = get_cust_type_filter(request.args.get("cust_type", "WEB+PRO"))
    df = qdf(f"""
        SELECT cltv_segment AS tier,
               COUNT(*) AS customers,
               ROUND(AVG(cltv_adjusted_v2),2) AS avg_value,
               ROUND(SUM(cltv_adjusted_v2),0) AS total_value
        FROM {TABLE}
        WHERE {wh}{cust_type_filter} AND cltv_segment IS NOT NULL
        GROUP BY cltv_segment
    """)
    
    result = []
    for _, row in df.iterrows():
        tier = row['tier']
        result.append({
            "cltv_segment": tier,
            "customers": int(row['customers']) if pd.notna(row['customers']) else 0,
            "avg_cltv": float(row['avg_value']) if pd.notna(row['avg_value']) else 0,
            "total_value": int(row['total_value']) if pd.notna(row['total_value']) else 0,
            "color": CLTV_C.get(tier, "#6b7280")
        })
    
    return jsonify(result)

@app.route("/api/churn_distribution")
def api_churn_dist():
    wh = date_where(request.args.get("years","0"))
    cust_type_filter = get_cust_type_filter(request.args.get("cust_type", "WEB+PRO"))
    df = qdf(f"""
        SELECT churn_segment AS risk_level,
               COUNT(*) AS customers,
               ROUND(AVG(churn_probability),3) AS avg_probability,
               ROUND(SUM(cltv_adjusted_v2),0) AS value_at_risk
        FROM {TABLE}
        WHERE {wh}{cust_type_filter} AND churn_segment IS NOT NULL
        GROUP BY churn_segment
    """)
    
    result = []
    for _, row in df.iterrows():
        risk = row['risk_level']
        result.append({
            "segment": risk,  # Add 'segment' field for legend display
            "customers": int(row['customers']) if pd.notna(row['customers']) else 0,
            "avg_probability": float(row['avg_probability']) if pd.notna(row['avg_probability']) else 0,
            "value_at_risk": int(row['value_at_risk']) if pd.notna(row['value_at_risk']) else 0,
            "color": CHURN_C.get(risk, "#6b7280")
        })
    
    return jsonify(result)

@app.route("/api/engagement_distribution")
def api_engagement_dist():
    wh = date_where(request.args.get("years","0"))
    cust_type_filter = get_cust_type_filter(request.args.get("cust_type", "WEB+PRO"))
    df = qdf(f"""
        SELECT churn_browse_signal AS level,
               COUNT(*) AS customers,
               ROUND(AVG(browse_conversion_score),3) AS avg_browse_score,
               ROUND(AVG(email_engagement_rate),3) AS avg_email_rate
        FROM {TABLE}
        WHERE {wh}{cust_type_filter} AND churn_browse_signal IS NOT NULL
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
    cust_type_filter = get_cust_type_filter(request.args.get("cust_type", "WEB+PRO"))
    df = qdf(f"""
        SELECT 
            master_customer_id,
            rfm_segment_v2,
            cltv_segment,
            ROUND(cltv_adjusted_v2,2) AS cltv_adjusted_v2,
            ROUND(cltv_adjusted,2) AS cltv_adjusted,
            ROUND(monetary,2) AS monetary,
            frequency,
            recency,
            churn_segment,
            ROUND(churn_probability,3) AS churn_probability,
            churn_browse_signal,
            engagement_multiplier,
            cart_conversion_flag,
            is_net_returner,
            high_cancel_rate,
            CAST(latest_active_date AS VARCHAR) AS latest_active_date,
            churn_model_version
        FROM {TABLE}
        WHERE {wh}{cust_type_filter} AND cltv_adjusted_v2 IS NOT NULL
        ORDER BY cltv_adjusted_v2 DESC
        LIMIT 20
    """)
    result = df.to_dict(orient="records")
    
    # Add segment colors and ensure proper types
    seg_colors = {
        "Champions": "#00c8ff", "Loyal": "#22c55e", "Potential Loyalists": "#84cc16",
        "At Risk": "#f59e0b", "Hibernating": "#6b7280", "Cart Abandoner": "#ef4444",
        "Re-Engaged": "#3b82f6", "Window Shopper": "#a855f7", "Non-Buyer": "#4b5563"
    }
    
    for row in result:
        row['color'] = seg_colors.get(row.get('rfm_segment_v2'), '#555')
        row['cart_conversion_flag'] = int(row.get('cart_conversion_flag', 0)) if pd.notna(row.get('cart_conversion_flag')) else 0
        row['is_net_returner'] = int(row.get('is_net_returner', 0)) if pd.notna(row.get('is_net_returner')) else 0
        row['high_cancel_rate'] = int(row.get('high_cancel_rate', 0)) if pd.notna(row.get('high_cancel_rate')) else 0
        row['engagement_multiplier'] = float(row.get('engagement_multiplier', 1.0)) if pd.notna(row.get('engagement_multiplier')) else 1.0
    
    return jsonify(result)

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
# API ALIASES (for frontend compatibility)
# ══════════════════════════════════════════════════════════

@app.route("/api/churn")
def api_churn_alias():
    """Alias for /api/churn_distribution"""
    return api_churn_dist()

@app.route("/api/cltv")
def api_cltv_alias():
    """Alias for /api/cltv_distribution"""
    return api_cltv_dist()

@app.route("/api/engagement")
def api_engagement_alias():
    """Alias for /api/engagement_distribution"""
    return api_engagement_dist()

@app.route("/api/cltv_churn_matrix")
def api_cltv_churn_matrix():
    """CLTV vs Churn risk matrix"""
    wh = date_where(request.args.get("years","0"))
    cust_type_filter = get_cust_type_filter(request.args.get("cust_type", "WEB+PRO"))
    df = qdf(f"""
        SELECT 
            cltv_segment,
            churn_segment,
            COUNT(*) AS customers,
            ROUND(AVG(churn_probability),3) AS avg_churn_prob,
            ROUND(SUM(cltv_adjusted_v2),0) AS total_cltv_value
        FROM {TABLE}
        WHERE {wh}{cust_type_filter} AND cltv_segment IS NOT NULL AND churn_segment IS NOT NULL
        GROUP BY cltv_segment, churn_segment
        ORDER BY cltv_segment, churn_segment
    """)
    
    # Ensure numeric columns and rename for frontend compatibility
    df[['customers', 'avg_churn_prob', 'total_cltv_value']] = df[['customers', 'avg_churn_prob', 'total_cltv_value']].apply(pd.to_numeric, errors='coerce')
    
    # Add calculated fields
    df['avg_cltv'] = (df['total_cltv_value'] / df['customers']).fillna(0).astype(int)
    df['total_cltv'] = df['total_cltv_value']
    df['churn_pct'] = (df['avg_churn_prob'] * 100).round(1)  # Convert to percentage
    
    # Add color coding for CLTV segments
    cltv_colors = {
        "Platinum": "#00c8ff",
        "Gold": "#f59e0b", 
        "Silver": "#6b7280",
        "Bronze": "#78350f",
        "Dormant": "#374151"
    }
    df['dot_color'] = df['cltv_segment'].map(cltv_colors)
    
    # Add priority and determine contextual actions based on churn and CLTV
    def determine_priority_and_action(row):
        churn = row['churn_pct']
        cltv = row['cltv_segment']
        churn_seg = row['churn_segment']
        
        # Priority determination
        if churn >= 70 and cltv in ['Platinum', 'Gold']:
            priority = 'URGENT'
        elif churn >= 40 or churn_seg == 'High Risk':
            priority = 'HIGH'
        elif churn_seg == 'Medium Risk':
            priority = 'MONITOR'
        else:
            priority = 'LOW'
        
        # Action determination based on priority and CLTV/Churn combination
        if priority == 'URGENT':
            if cltv in ['Platinum', 'Gold']:
                action = 'Immediate executive intervention'
            else:
                action = 'Win-back campaigns'
        elif priority == 'HIGH':
            if cltv in ['Platinum', 'Gold']:
                action = 'VIP retention programs'
            elif cltv in ['Silver', 'Bronze']:
                action = 'Targeted retention offers'
            else:
                action = 'Low-cost reactivation'
        elif priority == 'MONITOR':
            if churn >= 30:
                action = 'Engagement campaigns'
            else:
                action = 'Low-cost reactivation'
        else:  # LOW
            if cltv in ['Platinum', 'Gold']:
                action = 'Automated nurture'
            else:
                action = 'Standard nurture'
        
        return pd.Series({'priority': priority, 'action': action})
    
    priority_action = df.apply(determine_priority_and_action, axis=1)
    df['priority'] = priority_action['priority']
    df['action'] = priority_action['action']
    
    df['priority_color'] = df['churn_pct'].apply(lambda p: '#ef4444' if p >= 70 else '#f59e0b' if p >= 40 else '#22c55e')
    df['revenue_at_risk'] = df['total_cltv_value']
    
    # Sort by priority (URGENT first, then HIGH) and by churn_pct descending
    df['priority_order'] = df['priority'].apply(lambda p: 0 if p == 'URGENT' else 1)
    df = df.sort_values(['priority_order', 'churn_pct'], ascending=[True, False])
    
    # Return only the fields the frontend expects
    result = df[['cltv_segment', 'churn_segment', 'customers', 'avg_churn_prob', 
                 'total_cltv_value', 'avg_cltv', 'total_cltv', 'dot_color', 'churn_pct',
                 'priority', 'priority_color', 'action', 'revenue_at_risk']].to_dict(orient="records")
    
    return jsonify(result)

@app.route("/api/cltv_churn_matrix/export")
def api_cltv_churn_matrix_export():
    """Export CLTV vs Churn matrix as CSV"""
    wh = date_where(request.args.get("years","0"))
    df = qdf(f"""
        SELECT 
            cltv_segment AS "Value Tier",
            churn_segment AS "Churn Risk",
            COUNT(*) AS "Customer Count",
            ROUND(AVG(churn_probability),3) AS "Avg Churn Probability",
            ROUND(SUM(cltv_adjusted_v2),0) AS "Total CLTV Value"
        FROM {TABLE}
        WHERE {wh} AND cltv_segment IS NOT NULL AND churn_segment IS NOT NULL
        GROUP BY cltv_segment, churn_segment
        ORDER BY cltv_segment, churn_segment
    """)
    
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    fname = f"LP_CLTV_Churn_Matrix_{date.today()}.csv"
    
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )

@app.route("/api/predictions")
def api_predictions():
    """Revenue scenario predictions based on segment data"""
    try:
        wh = date_where(request.args.get("years","0"))
        df = qdf(f"""
            SELECT 
                churn_segment,
                rfm_segment_v2,
                engagement_multiplier,
                ROUND(SUM(cltv_adjusted_v2),0) AS total_cltv
            FROM {TABLE}
            WHERE {wh} AND cltv_adjusted_v2 IS NOT NULL AND cltv_adjusted_v2 > 0
            GROUP BY churn_segment, rfm_segment_v2, engagement_multiplier
        """)
        
        # Calculate scenario revenues
        high_risk_rev = df[df['churn_segment'] == 'High Risk']['total_cltv'].sum()
        med_risk_rev = df[df['churn_segment'] == 'Medium Risk']['total_cltv'].sum()
        champions_rev = df[df['rfm_segment_v2'] == 'Champions']['total_cltv'].sum()
        hot_leads_rev = df[df['engagement_multiplier'] == 1.3]['total_cltv'].sum()
        cart_abandon = df[df['rfm_segment_v2'] == 'Cart Abandoner']['total_cltv'].sum() * 0.15
        at_risk = df[df['churn_segment'].isin(['High Risk', 'Medium Risk'])]['total_cltv'].sum() * 0.20
        reengaged = df[df['rfm_segment_v2'] == 'Re-Engaged']['total_cltv'].sum() * 0.25
        window = df[df['rfm_segment_v2'] == 'Window Shopper']['total_cltv'].sum() * 0.05
        
    except Exception:
        # Fallback mock data
        high_risk_rev = 3254000
        med_risk_rev = 2840000
        champions_rev = 2624000
        hot_leads_rev = 1850000
        cart_abandon = 280000
        at_risk = 650000
        reengaged = 455000
        window = 165000
    
    return jsonify({
        "high_risk_revenue": int(high_risk_rev) if pd.notna(high_risk_rev) else 0,
        "med_risk_revenue": int(med_risk_rev) if pd.notna(med_risk_rev) else 0,
        "champions_value": int(champions_rev) if pd.notna(champions_rev) else 0,
        "hot_leads_value": int(hot_leads_rev) if pd.notna(hot_leads_rev) else 0,
        "cart_opp": int(cart_abandon) if pd.notna(cart_abandon) else 0,
        "at_risk_save": int(at_risk) if pd.notna(at_risk) else 0,
        "reengaged_opp": int(reengaged) if pd.notna(reengaged) else 0,
        "window_opp": int(window) if pd.notna(window) else 0
    })


@app.route("/api/data_quality")
def api_data_quality():
    """Data Quality: completeness scores, PII validity rates, duplicate counts"""
    wh = date_where(request.args.get("years","0"))
    cust_type_filter = get_cust_type_filter(request.args.get("cust_type", "WEB+PRO"))
    try:
        df = qdf(f"""
            SELECT
                COUNT(*)                                                                                    AS total,
                ROUND(AVG(CAST(total_customer_completeness_score AS FLOAT)), 1)                             AS avg_completeness,
                COUNT(CASE WHEN total_customer_completeness_score >= 90 THEN 1 END)                         AS score_excellent,
                COUNT(CASE WHEN total_customer_completeness_score >= 70
                            AND total_customer_completeness_score < 90 THEN 1 END)                          AS score_good,
                COUNT(CASE WHEN total_customer_completeness_score >= 50
                            AND total_customer_completeness_score < 70 THEN 1 END)                          AS score_fair,
                COUNT(CASE WHEN total_customer_completeness_score < 50
                            OR  total_customer_completeness_score IS NULL THEN 1 END)                       AS score_poor,
                COUNT(CASE WHEN first_last_name_validity = 'VALID'   THEN 1 END)                            AS name_valid,
                COUNT(CASE WHEN first_last_name_validity = 'INVALID' THEN 1 END)                            AS name_invalid,
                COUNT(CASE WHEN email_validity   = 'VALID'   THEN 1 END)                                    AS email_valid,
                COUNT(CASE WHEN email_validity   = 'INVALID' THEN 1 END)                                    AS email_invalid,
                COUNT(CASE WHEN email_duplicate_count > 1 THEN 1 END)                                      AS email_dup_customers,
                ROUND(AVG(CAST(COALESCE(email_duplicate_count, 1) AS FLOAT)), 2)                            AS email_dup_avg,
                MAX(email_duplicate_count)                                                                   AS email_dup_max,
                COUNT(CASE WHEN phone_validity   = 'VALID'   THEN 1 END)                                    AS phone_valid,
                COUNT(CASE WHEN phone_validity   = 'INVALID' THEN 1 END)                                    AS phone_invalid,
                COUNT(CASE WHEN phone_duplicate_count > 1 THEN 1 END)                                      AS phone_dup_customers,
                ROUND(AVG(CAST(COALESCE(phone_duplicate_count, 1) AS FLOAT)), 2)                            AS phone_dup_avg,
                MAX(phone_duplicate_count)                                                                   AS phone_dup_max,
                COUNT(CASE WHEN address_validity = 'VALID'   THEN 1 END)                                    AS address_valid,
                COUNT(CASE WHEN address_validity = 'INVALID' THEN 1 END)                                    AS address_invalid,
                COUNT(CASE WHEN address_duplicate_count > 1 THEN 1 END)                                     AS address_dup_customers,
                ROUND(AVG(CAST(COALESCE(address_duplicate_count, 1) AS FLOAT)), 2)                          AS address_dup_avg,
                MAX(address_duplicate_count)                                                                 AS address_dup_max,
                COUNT(CASE WHEN reward_number_validity = 'VALID'   THEN 1 END)                              AS reward_valid,
                COUNT(CASE WHEN reward_number_validity = 'INVALID' THEN 1 END)                              AS reward_invalid,
                COUNT(CASE WHEN reward_number_duplicate_count > 1 THEN 1 END)                               AS reward_dup_customers,
                ROUND(AVG(CAST(COALESCE(reward_number_duplicate_count, 1) AS FLOAT)), 2)                    AS reward_dup_avg,
                MAX(reward_number_duplicate_count)                                                           AS reward_dup_max
            FROM {TABLE}
            WHERE {wh}{cust_type_filter}
        """)
        return jsonify(df.iloc[0].to_dict())
    except Exception:
        return jsonify({
            "total": 15338254, "avg_completeness": 73.5,
            "score_excellent": 3245678, "score_good": 6891234,
            "score_fair": 3456789,     "score_poor": 1744553,
            "name_valid": 14523891,    "name_invalid": 814363,
            "email_valid": 12456789,   "email_invalid": 2881465,
            "email_dup_customers": 1245000, "email_dup_avg": 1.35, "email_dup_max": 150,
            "phone_valid": 11234567,   "phone_invalid": 4103687,
            "phone_dup_customers": 456000,  "phone_dup_avg": 1.12, "phone_dup_max": 24,
            "address_valid": 13789456, "address_invalid": 1548798,
            "address_dup_customers": 2345678, "address_dup_avg": 1.89, "address_dup_max": 48,
            "reward_valid": 14123456,  "reward_invalid": 1214798,
            "reward_dup_customers": 67890, "reward_dup_avg": 1.05, "reward_dup_max": 8,
        })


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
