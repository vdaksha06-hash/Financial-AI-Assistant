import sqlite3
from pathlib import Path
from typing import Dict, Tuple

import streamlit as st

DB_PATH = Path("bank_customers.db")

# -----------------------------
# DATABASE LAYER
# -----------------------------
def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            credit_score INTEGER NOT NULL,
            monthly_income REAL NOT NULL,
            existing_loan_amount REAL DEFAULT 0,
            monthly_debt_payments REAL DEFAULT 0,
            missed_payments INTEGER DEFAULT 0,
            account_balance REAL DEFAULT 0,
            years_with_bank REAL DEFAULT 0,
            loan_repayment_history TEXT DEFAULT 'Average',
            avg_monthly_deposits REAL DEFAULT 0,
            overdraft_count INTEGER DEFAULT 0
        )
        """
    )

    sample_customers = [
        (1, "Aarav Patel", 790, 7200, 12000, 450, 0, 28000, 7, "Excellent", 3200, 0),
        (2, "Sara Johnson", 735, 5100, 15000, 700, 1, 11000, 4, "Good", 2400, 1),
        (3, "Michael Lee", 668, 3900, 22000, 1100, 3, 4200, 2, "Average", 1600, 2),
        (4, "Priya Sharma", 602, 2900, 26000, 1300, 5, 1500, 1, "Poor", 900, 4),
    ]

    cursor.executemany(
        """
        INSERT OR REPLACE INTO customers (
            customer_id, full_name, credit_score, monthly_income,
            existing_loan_amount, monthly_debt_payments, missed_payments,
            account_balance, years_with_bank, loan_repayment_history,
            avg_monthly_deposits, overdraft_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_customers,
    )

    conn.commit()
    conn.close()


def fetch_all_customers():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT customer_id, full_name FROM customers ORDER BY customer_id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def fetch_customer(customer_id: int):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# -----------------------------
# RISK / ELIGIBILITY ENGINE
# -----------------------------
def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def normalize_repayment_history(label: str) -> str:
    allowed = {"Excellent", "Good", "Average", "Poor"}
    return label if label in allowed else "Average"


def evaluate_customer(data: Dict, requested_loan_amount: float) -> Dict:
    monthly_income = float(data["monthly_income"])
    monthly_debt_payments = float(data["monthly_debt_payments"])
    credit_score = int(data["credit_score"])
    missed_payments = int(data["missed_payments"])
    account_balance = float(data["account_balance"])
    years_with_bank = float(data["years_with_bank"])
    avg_monthly_deposits = float(data["avg_monthly_deposits"])
    overdraft_count = int(data["overdraft_count"])
    existing_loan_amount = float(data["existing_loan_amount"])
    repayment_history = normalize_repayment_history(str(data["loan_repayment_history"]))

    # Estimated monthly payment for the requested loan.
    estimated_new_loan_payment = requested_loan_amount / 36 if requested_loan_amount > 0 else 0

    current_dti = safe_div(monthly_debt_payments, monthly_income)
    projected_dti = safe_div(monthly_debt_payments + estimated_new_loan_payment, monthly_income)
    savings_cushion_months = safe_div(account_balance, monthly_income)
    requested_loan_to_income = safe_div(requested_loan_amount, monthly_income * 12)

    score = 0
    reasons = []

    # Credit score: max 30
    if credit_score >= 780:
        score += 30
        reasons.append("Excellent credit score")
    elif credit_score >= 740:
        score += 26
        reasons.append("Very strong credit score")
    elif credit_score >= 700:
        score += 22
        reasons.append("Good credit score")
    elif credit_score >= 660:
        score += 15
        reasons.append("Fair credit score")
    elif credit_score >= 620:
        score += 8
        reasons.append("Below-preferred credit score")
    else:
        score += 2
        reasons.append("High-risk credit score range")

    # Income: max 15
    if monthly_income >= 8000:
        score += 15
        reasons.append("Strong monthly income")
    elif monthly_income >= 5000:
        score += 12
        reasons.append("Stable income level")
    elif monthly_income >= 3500:
        score += 9
        reasons.append("Moderate income level")
    elif monthly_income >= 2500:
        score += 6
        reasons.append("Basic income level")
    else:
        score += 2
        reasons.append("Income may be too low for comfortable repayment")

    # Projected DTI: max 20
    if projected_dti <= 0.20:
        score += 20
        reasons.append("Very healthy projected debt-to-income ratio")
    elif projected_dti <= 0.30:
        score += 16
        reasons.append("Healthy projected debt-to-income ratio")
    elif projected_dti <= 0.40:
        score += 10
        reasons.append("Manageable projected debt-to-income ratio")
    elif projected_dti <= 0.50:
        score += 4
        reasons.append("Projected debt burden is elevated")
    else:
        reasons.append("Projected debt burden is high")

    # Payment history: max 15
    if missed_payments == 0:
        score += 10
        reasons.append("No missed payments on record")
    elif missed_payments <= 2:
        score += 6
        reasons.append("Only a small number of missed payments")
    else:
        reasons.append("Multiple missed payments increase risk")

    history_bonus = {"Excellent": 5, "Good": 4, "Average": 2, "Poor": 0}
    score += history_bonus[repayment_history]
    reasons.append(f"Repayment history is {repayment_history.lower()}")

    # Banking relationship: max 10
    if years_with_bank >= 7:
        score += 10
        reasons.append("Long and established banking relationship")
    elif years_with_bank >= 4:
        score += 8
        reasons.append("Good banking relationship history")
    elif years_with_bank >= 2:
        score += 5
        reasons.append("Moderate banking relationship history")
    else:
        score += 2
        reasons.append("Limited history with the bank")

    # Liquidity and deposit behavior: max 10
    if savings_cushion_months >= 6:
        score += 6
        reasons.append("Strong liquid balance cushion")
    elif savings_cushion_months >= 3:
        score += 4
        reasons.append("Reasonable liquid balance cushion")
    elif savings_cushion_months >= 1:
        score += 2
        reasons.append("Limited liquid balance cushion")
    else:
        reasons.append("Very limited cash buffer")

    if avg_monthly_deposits >= monthly_income * 0.6:
        score += 4
        reasons.append("Healthy deposit behavior")
    elif avg_monthly_deposits >= monthly_income * 0.35:
        score += 2
        reasons.append("Moderate deposit behavior")
    else:
        reasons.append("Weak deposit consistency")

    # Overdraft behavior: penalty up to -10
    if overdraft_count == 0:
        reasons.append("No overdraft activity")
    elif overdraft_count <= 2:
        score -= 3
        reasons.append("Some overdraft activity")
    else:
        score -= 8
        reasons.append("Frequent overdraft activity")

    # Loan size fit: max 10
    if requested_loan_to_income <= 0.20:
        score += 10
        reasons.append("Requested loan size is conservative for income level")
    elif requested_loan_to_income <= 0.40:
        score += 7
        reasons.append("Requested loan size is reasonable")
    elif requested_loan_to_income <= 0.60:
        score += 3
        reasons.append("Requested loan size is somewhat aggressive")
    else:
        reasons.append("Requested loan size is large relative to income")

    # Hard rule overlays
    hard_decline = False
    manual_review = False
    policy_flags = []

    if credit_score < 580:
        hard_decline = True
        policy_flags.append("Credit score is below minimum policy threshold")

    if projected_dti > 0.55:
        hard_decline = True
        policy_flags.append("Projected debt-to-income ratio exceeds policy threshold")

    if missed_payments >= 6:
        hard_decline = True
        policy_flags.append("Too many missed payments for auto-approval")

    if overdraft_count >= 5:
        manual_review = True
        policy_flags.append("Frequent overdrafts require manual review")

    if repayment_history == "Poor":
        manual_review = True
        policy_flags.append("Poor repayment history requires extra review")

    # Final label
    if hard_decline:
        status = "Not Eligible"
        risk = "High Risk"
        recommendation = "Do not approve under current rules. Consider credit improvement or a lower loan amount."
    else:
        if score >= 85 and not manual_review:
            status = "Highly Eligible"
            risk = "Low Risk"
            recommendation = "Strong approval candidate."
        elif score >= 70:
            status = "Eligible"
            risk = "Moderate Risk"
            recommendation = "Can likely be approved with standard underwriting review."
        elif score >= 55:
            status = "Review Needed"
            risk = "Medium-High Risk"
            recommendation = "Borderline case. Recommend manual underwriting or a smaller loan amount."
        else:
            status = "Not Eligible"
            risk = "High Risk"
            recommendation = "Not a strong loan candidate right now. Improve profile or reduce requested amount."

        if manual_review and status in {"Highly Eligible", "Eligible"}:
            status = "Review Needed"
            recommendation = "Potentially approvable, but manual review is recommended before making a decision."

    return {
        "score": max(score, 0),
        "status": status,
        "risk": risk,
        "recommendation": recommendation,
        "policy_flags": policy_flags,
        "reasons": reasons,
        "metrics": {
            "Current DTI": round(current_dti * 100, 1),
            "Projected DTI": round(projected_dti * 100, 1),
            "Savings Cushion (months)": round(savings_cushion_months, 1),
            "Loan-to-Annual-Income": round(requested_loan_to_income * 100, 1),
            "Estimated New Monthly Payment": round(estimated_new_loan_payment, 2),
            "Existing Loan Amount": round(existing_loan_amount, 2),
        },
    }


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Financial AI Assistant", layout="wide")
init_db()

st.title("🏦 Financial AI Assistant for Loan Eligibility")
st.caption("A bank-style decision support app using Python + SQLite + Streamlit")

with st.sidebar:
    st.header("How to use")
    st.write("1. Choose pre-stored data or manual input.")
    st.write("2. Enter the requested loan amount.")
    st.write("3. Review eligibility, risk, metrics, and policy flags.")
    st.markdown("---")
    st.subheader("Decision scale")
    st.write("- 85+ → Highly Eligible")
    st.write("- 70–84 → Eligible")
    st.write("- 55–69 → Review Needed")
    st.write("- Below 55 → Not Eligible")

source_mode = st.radio("Choose customer data source", ["Pre-stored bank customer", "Manual input"], horizontal=True)

requested_loan_amount = st.number_input("Requested loan amount ($)", min_value=0.0, value=10000.0, step=500.0)

customer_data = None
customer_name = ""

if source_mode == "Pre-stored bank customer":
    customers = fetch_all_customers()
    options = {f"{customer_id} - {name}": customer_id for customer_id, name in customers}
    selected_label = st.selectbox("Choose a customer", list(options.keys()))
    selected_id = options[selected_label]
    customer_data = fetch_customer(selected_id)
    customer_name = customer_data["full_name"]

    with st.expander("View selected customer profile"):
        st.json(customer_data)

else:
    col1, col2, col3 = st.columns(3)

    with col1:
        full_name = st.text_input("Customer name", value="New Applicant")
        credit_score = st.number_input("Credit score", min_value=300, max_value=850, value=700)
        monthly_income = st.number_input("Monthly income ($)", min_value=0.0, value=4500.0, step=100.0)
        monthly_debt_payments = st.number_input("Current monthly debt payments ($)", min_value=0.0, value=500.0, step=50.0)

    with col2:
        existing_loan_amount = st.number_input("Existing total loan amount ($)", min_value=0.0, value=10000.0, step=500.0)
        missed_payments = st.number_input("Missed payments", min_value=0, value=0, step=1)
        account_balance = st.number_input("Account balance ($)", min_value=0.0, value=8000.0, step=100.0)
        years_with_bank = st.number_input("Years with bank", min_value=0.0, value=3.0, step=0.5)

    with col3:
        loan_repayment_history = st.selectbox("Repayment history", ["Excellent", "Good", "Average", "Poor"])
        avg_monthly_deposits = st.number_input("Average monthly deposits ($)", min_value=0.0, value=2200.0, step=100.0)
        overdraft_count = st.number_input("Overdraft count", min_value=0, value=0, step=1)

    customer_data = {
        "customer_id": None,
        "full_name": full_name,
        "credit_score": credit_score,
        "monthly_income": monthly_income,
        "existing_loan_amount": existing_loan_amount,
        "monthly_debt_payments": monthly_debt_payments,
        "missed_payments": missed_payments,
        "account_balance": account_balance,
        "years_with_bank": years_with_bank,
        "loan_repayment_history": loan_repayment_history,
        "avg_monthly_deposits": avg_monthly_deposits,
        "overdraft_count": overdraft_count,
    }
    customer_name = full_name

if st.button("Evaluate Loan Eligibility", type="primary"):
    result = evaluate_customer(customer_data, requested_loan_amount)

    st.subheader(f"Decision for {customer_name}")

    a, b, c = st.columns(3)
    a.metric("Eligibility", result["status"])
    b.metric("Risk", result["risk"])
    c.metric("AI Score", f"{result['score']} / 110")

    st.markdown(f"**Recommendation:** {result['recommendation']}")

    if result["policy_flags"]:
        st.warning("Policy flags: " + " | ".join(result["policy_flags"]))

    st.markdown("### Key Metrics")
    metric_cols = st.columns(3)
    for idx, (label, value) in enumerate(result["metrics"].items()):
        metric_cols[idx % 3].metric(label, value)

    st.markdown("### Why the assistant made this decision")
    for reason in result["reasons"]:
        st.write(f"- {reason}")

    st.markdown("### Example SQL query for reporting")
    st.code(
        """
SELECT
    customer_id,
    full_name,
    credit_score,
    monthly_income,
    existing_loan_amount,
    missed_payments,
    account_balance
FROM customers
WHERE credit_score >= 700
ORDER BY credit_score DESC;
        """.strip(),
        language="sql",
    )

st.markdown("---")
st.markdown(
    """
**Run locally:**
```bash
pip install streamlit
streamlit run financial_ai_assistant_streamlit_app.py
```
"""
)
