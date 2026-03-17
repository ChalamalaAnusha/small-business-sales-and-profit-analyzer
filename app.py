import streamlit as st
import init_db
from db import get_connection
import bcrypt
import os
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import re
from datetime import datetime, timedelta
import numpy as np
import io
from prophet import Prophet
from sklearn.linear_model import LinearRegression
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
st.set_page_config(page_title="Stock Management System", layout="wide", initial_sidebar_state="expanded")

ADMIN_REGISTRATION_KEY = os.environ.get("ADMIN_REGISTRATION_KEY", "ADMIN123")

# ===== PROFESSIONAL CSS =====
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    h1 {
        color: #1f3a93;
        font-size: 2.5rem;
        font-weight: 800;
    }
    h2 {
        color: #1f3a93;
        border-bottom: 3px solid #2563eb;
        padding-bottom: 10px;       
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# ===== SESSION STATE =====
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "username" not in st.session_state:
    st.session_state.username = None
if "role" not in st.session_state:
    st.session_state.role = None
if "business_id" not in st.session_state:
    st.session_state.business_id = None


def render_admin_dashboard(cur, con):
    st.header("🛠️ Admin Monitoring Dashboard")

    st.subheader("Database Summary")
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM businesses")
    total_businesses = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM transactions")
    total_transactions = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]

    cur.execute(
        "SELECT COALESCE(SUM(CASE WHEN type='Sale' THEN amount END),0), COALESCE(SUM(CASE WHEN type='Expense' THEN amount END),0) FROM transactions"
    )
    total_sales, total_expenses = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM transactions WHERE txn_date = CURDATE()")
    today_transactions = cur.fetchone()[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("👥 Users", total_users)
    col2.metric("🏢 Businesses", total_businesses)
    col3.metric("💰 Transactions", total_transactions)
    col4.metric("📦 Products", total_products)

    col5, col6, col7 = st.columns(3)
    col5.metric("🔵 Total Sales", f"₹{float(total_sales):,.0f}")
    col6.metric("🔴 Total Expenses", f"₹{float(total_expenses):,.0f}")
    col7.metric("📆 Today's Transactions", today_transactions)

    st.markdown("---")

    st.subheader("View All Sales Records")
    cur.execute(
        "SELECT id, business_id, category, amount, txn_date, notes FROM transactions WHERE type='Sale' ORDER BY txn_date DESC"
    )
    sales_rows = cur.fetchall()
    if sales_rows:
        sales_df = pd.DataFrame(sales_rows, columns=["ID", "Business ID", "Category", "Amount", "Date", "Notes"])
        st.dataframe(sales_df, use_container_width=True)
    else:
        st.info("No sales records found.")

    st.markdown("---")

    st.subheader("View All Expense Records")
    cur.execute(
        "SELECT id, business_id, category, amount, txn_date, notes FROM transactions WHERE type='Expense' ORDER BY txn_date DESC"
    )
    expense_rows = cur.fetchall()
    if expense_rows:
        expense_df = pd.DataFrame(expense_rows, columns=["ID", "Business ID", "Category", "Amount", "Date", "Notes"])
        st.dataframe(expense_df, use_container_width=True)
    else:
        st.info("No expense records found.")

    st.markdown("---")

    st.subheader("Manage Products")
    cur.execute("SELECT id, business_id, name, cost_price, sale_price, stock FROM products ORDER BY id DESC")
    product_rows = cur.fetchall()

    if product_rows:
        products_df = pd.DataFrame(
            product_rows,
            columns=["ID", "Business ID", "Name", "Cost Price", "Sale Price", "Stock"],
        )
        st.dataframe(products_df, use_container_width=True)

        product_ids = products_df["ID"].tolist()
        selected_product_id = st.selectbox("Select Product ID", product_ids, key="admin_selected_product_id")
        selected_stock = st.number_input("New Stock", min_value=0, step=1, key="admin_new_stock")

        col_update, col_delete = st.columns(2)
        with col_update:
            if st.button("Update Stock", use_container_width=True, key="admin_update_stock"):
                cur.execute("UPDATE products SET stock=? WHERE id=?", (int(selected_stock), selected_product_id))
                con.commit()
                st.success("Product stock updated")
                st.rerun()

        with col_delete:
            if st.button("Delete Product", use_container_width=True, key="admin_delete_product"):
                cur.execute("DELETE FROM products WHERE id=?", (selected_product_id,))
                con.commit()
                st.success("Product deleted")
                st.rerun()
    else:
        st.info("No products available.")

    st.markdown("---")
    st.subheader("Activity Summary")

    seven_days_ago = (datetime.now() - timedelta(days=7)).date()
    cur.execute(
        "SELECT type, COUNT(*), COALESCE(SUM(amount), 0) FROM transactions WHERE txn_date >= ? GROUP BY type",
        (seven_days_ago,),
    )
    weekly_rows = cur.fetchall()

    weekly_sales = 0.0
    weekly_expenses = 0.0
    weekly_transactions = 0
    for txn_type, txn_count, txn_total in weekly_rows:
        weekly_transactions += int(txn_count or 0)
        if str(txn_type).lower() == "sale":
            weekly_sales = float(txn_total or 0)
        elif str(txn_type).lower() == "expense":
            weekly_expenses = float(txn_total or 0)

    weekly_net = weekly_sales - weekly_expenses

    sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    sum_col1.metric("Last 7 Days Transactions", weekly_transactions)
    sum_col2.metric("Last 7 Days Sales", f"₹{weekly_sales:,.0f}")
    sum_col3.metric("Last 7 Days Expenses", f"₹{weekly_expenses:,.0f}")
    sum_col4.metric("Last 7 Days Net", f"₹{weekly_net:,.0f}")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        summary_chart = go.Figure(
            data=[
                go.Bar(
                    x=["Sales", "Expenses", "Net"],
                    y=[weekly_sales, weekly_expenses, weekly_net],
                    marker_color=["#2563eb", "#dc2626", "#059669" if weekly_net >= 0 else "#b91c1c"],
                )
            ]
        )
        summary_chart.update_layout(
            title="Last 7 Days Financial Snapshot",
            xaxis_title="Metric",
            yaxis_title="Amount (₹)",
            height=320,
            margin=dict(l=20, r=20, t=50, b=20),
        )
        st.plotly_chart(summary_chart, use_container_width=True)

    with chart_col2:
        cur.execute(
            "SELECT txn_date, COUNT(*), COALESCE(SUM(amount), 0) FROM transactions WHERE txn_date >= ? GROUP BY txn_date ORDER BY txn_date",
            (seven_days_ago,),
        )
        daily_rows = cur.fetchall()

        if daily_rows:
            daily_df = pd.DataFrame(daily_rows, columns=["Date", "Transactions", "Amount"])
            daily_df["Date"] = pd.to_datetime(daily_df["Date"])
            trend_chart = go.Figure()
            trend_chart.add_trace(
                go.Scatter(
                    x=daily_df["Date"],
                    y=daily_df["Transactions"],
                    mode="lines+markers",
                    name="Transactions",
                    line=dict(color="#1f3a93", width=2),
                )
            )
            trend_chart.update_layout(
                title="Daily Transaction Trend (7 Days)",
                xaxis_title="Date",
                yaxis_title="Transactions",
                height=320,
                margin=dict(l=20, r=20, t=50, b=20),
            )
            st.plotly_chart(trend_chart, use_container_width=True)
        else:
            st.info("No activity found in the last 7 days.")

    cur.execute(
        "SELECT category, COUNT(*), COALESCE(SUM(amount), 0) FROM transactions WHERE txn_date >= ? GROUP BY category ORDER BY COALESCE(SUM(amount), 0) DESC LIMIT 5",
        (seven_days_ago,),
    )
    top_category_rows = cur.fetchall()
    if top_category_rows:
        st.markdown("Top Categories (Last 7 Days)")
        top_categories_df = pd.DataFrame(
            top_category_rows,
            columns=["Category", "Transactions", "Amount"],
        )
        st.dataframe(top_categories_df, use_container_width=True)

    cur.execute(
        "SELECT id, business_id, type, category, amount, txn_date FROM transactions ORDER BY txn_date DESC, id DESC LIMIT 10"
    )
    recent_rows = cur.fetchall()
    if recent_rows:
        recent_df = pd.DataFrame(
            recent_rows,
            columns=["ID", "Business ID", "Type", "Category", "Amount", "Date"],
        )
        st.markdown("Recent Transactions")
        st.dataframe(recent_df, use_container_width=True)
    else:
        st.info("No recent transaction activity.")

# ===== PASSWORD VALIDATION =====
def check_password_strength(password):
    return len(password or "") >= 8


def is_valid_username(username):
    if not username:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,30}", username))


def is_valid_email(email):
    if not email:
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def generate_pdf_report(title, dataframe=None, metrics=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(title, styles["Title"]),
        Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]),
        Spacer(1, 12)
    ]

    if metrics:
        metric_rows = [["Metric", "Value"]] + [[str(key), str(value)] for key, value in metrics.items()]
        metric_table = Table(metric_rows, repeatRows=1)
        metric_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a93")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT")
        ]))
        elements.append(metric_table)
        elements.append(Spacer(1, 12))

    if dataframe is not None and not dataframe.empty:
        safe_df = dataframe.copy().astype(str)
        max_rows = 25
        table_data = [safe_df.columns.tolist()] + safe_df.head(max_rows).values.tolist()
        data_table = Table(table_data, repeatRows=1)
        data_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8)
        ]))
        elements.append(data_table)

        if len(safe_df) > max_rows:
            elements.append(Spacer(1, 8))
            elements.append(Paragraph(f"Showing first {max_rows} rows out of {len(safe_df)} rows.", styles["Italic"]))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def read_uploaded_dataframe(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    filename = (uploaded_file.name or "").lower()
    file_buffer = io.BytesIO(file_bytes)

    if filename.endswith((".xls", ".xlsx")):
        return pd.read_excel(file_buffer, engine="openpyxl")

    file_buffer.seek(0)
    try:
        return pd.read_csv(file_buffer)
    except UnicodeDecodeError:
        file_buffer.seek(0)
        return pd.read_csv(file_buffer, encoding="latin1")

# ===== REGISTER USER =====
def register_user(username, email, password, role="user", admin_key=None):
    if not is_valid_username(username):
        return "invalid_username"

    normalized_email = (email or "").strip().lower()
    if not is_valid_email(normalized_email):
        return "invalid_email"

    if not check_password_strength(password):
        return "weak"

    if role == "admin" and admin_key != ADMIN_REGISTRATION_KEY:
        return "invalid_admin_key"

    if role not in {"user", "admin"}:
        return "invalid_role"
    
    con = get_connection()
    if con is None:
        return "db_error"
    cur = con.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username=?", (username,))
        if cur.fetchone():
            con.close()
            return "exists"

        cur.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(?)", (normalized_email,))
        if cur.fetchone():
            con.close()
            return "email_exists"
        
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username,email,password,role,created_at) VALUES (?,?,?,?,?)",
            (username, normalized_email, hashed, role, datetime.now()),
        )
        con.commit()
        user_id = cur.lastrowid
        
        cur.execute("INSERT INTO businesses (user_id,name,created_at) VALUES (?,?,?)",
                    (user_id, f"{username}'s Business", datetime.now()))
        con.commit()
        con.close()
        return "success"
    except Exception:
        con.close()
        return "db_error"

# ===== LOGIN USER =====
def login_user(login_identifier, password):
    con = get_connection()
    if con is None:
        return False, None, None, None, None
    cur = con.cursor()
    try:
        identifier = (login_identifier or "").strip()
        cur.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cur.fetchall()}
        has_email = "email" in user_columns

        if has_email:
            cur.execute(
                "SELECT id,username,password,role FROM users WHERE username=? OR LOWER(email)=LOWER(?) LIMIT 1",
                (identifier, identifier),
            )
        else:
            cur.execute(
                "SELECT id,username,password,role FROM users WHERE username=? LIMIT 1",
                (identifier,),
            )
        user = cur.fetchone()
        
        if not user or not bcrypt.checkpw(password.encode(), user[2].encode()):
            con.close()
            return False, None, None, None, None
        
        user_id = user[0]
        account_username = user[1]
        role = user[3] or "user"
        
        cur.execute("SELECT id FROM businesses WHERE user_id=? LIMIT 1", (user_id,))
        b = cur.fetchone()
        if b:
            business_id = b[0]
        else:
            cur.execute("INSERT INTO businesses (user_id,name,created_at) VALUES (?,?,?)",
                       (user_id, f"{account_username}'s Business", datetime.now()))
            con.commit()
            business_id = cur.lastrowid
        
        con.close()
        return True, user_id, business_id, role, account_username
    except Exception:
        con.close()
        return False, None, None, None, None


def get_user_profile(user_id):
    con = get_connection()
    if con is None:
        return None

    cur = con.cursor()
    try:
        cur.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cur.fetchall()}
        has_email = "email" in user_columns

        if has_email:
            cur.execute(
                "SELECT username, email, role, created_at FROM users WHERE id=? LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            con.close()
            if not row:
                return None
            return {
                "username": row[0],
                "email": row[1],
                "role": row[2] or "user",
                "created_at": row[3],
                "has_email": True,
            }

        cur.execute(
            "SELECT username, role, created_at FROM users WHERE id=? LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        return {
            "username": row[0],
            "email": None,
            "role": row[1] or "user",
            "created_at": row[2],
            "has_email": False,
        }
    except Exception:
        con.close()
        return None


def update_user_profile(user_id, username, email=None):
    if not is_valid_username(username):
        return "invalid_username"

    normalized_email = (email or "").strip()
    if normalized_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized_email):
        return "invalid_email"

    con = get_connection()
    if con is None:
        return "db_error"

    cur = con.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username=? AND id<>?", (username, user_id))
        if cur.fetchone():
            con.close()
            return "username_exists"

        cur.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cur.fetchall()}
        has_email = "email" in user_columns

        if has_email:
            email_value = normalized_email if normalized_email else None
            cur.execute(
                "UPDATE users SET username=?, email=? WHERE id=?",
                (username, email_value, user_id),
            )
        else:
            cur.execute("UPDATE users SET username=? WHERE id=?", (username, user_id))

        con.commit()
        con.close()
        return "success"
    except Exception:
        con.close()
        return "db_error"


def change_user_password(user_id, current_password, new_password):
    con = get_connection()
    if con is None:
        return "db_error"

    cur = con.cursor()
    try:
        cur.execute("SELECT password FROM users WHERE id=? LIMIT 1", (user_id,))
        row = cur.fetchone()
        if not row:
            con.close()
            return "not_found"

        stored_password = row[0]
        if not bcrypt.checkpw(current_password.encode(), stored_password.encode()):
            con.close()
            return "invalid_current_password"

        hashed_new_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        cur.execute("UPDATE users SET password=? WHERE id=?", (hashed_new_password, user_id))
        con.commit()
        con.close()
        return "success"
    except Exception:
        con.close()
        return "db_error"


# ===== AUTHENTICATION PAGE =====
if not st.session_state.logged_in:
    st.sidebar.title("Navigation")
    action = st.sidebar.radio(
        "Menu",
        ["Login", "Register", "Dashboard", "Admin Dashboard"],
        label_visibility="collapsed",
        key="auth_action",
    )
    
    st.title("📊 Stock Management System")
    st.write("Professional Business Analytics Platform")
    st.markdown("---")

    if "redirect_message" in st.session_state:
        st.error(st.session_state.redirect_message)
        del st.session_state["redirect_message"]

    if action == "Register":
        st.header("Create Account")
        username = st.text_input("Username")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        account_type = st.selectbox("Account Type", ["user", "admin"])
        admin_key = ""
        if account_type == "admin":
            admin_key = st.text_input("Admin Secret Key", type="password")
            st.caption("Admin account is created only when a valid admin key is provided.")
        
        if username and not is_valid_username(username):
            st.error("Username must be 3-30 characters: letters, numbers, underscore only")
        if email and not is_valid_email(email):
            st.error("Please enter a valid email address")
        if password and not check_password_strength(password):
            st.error("❌ Password must be at least 8 characters")
        elif password and is_valid_username(username) and is_valid_email(email):
            st.success("✓ Password OK")
        
        if st.button("Register", use_container_width=True):
            result = register_user(username, email, password, role=account_type, admin_key=admin_key)
            if result == "invalid_username":
                st.error("Invalid username format")
            elif result == "invalid_email":
                st.error("Please enter a valid email address")
            elif result == "weak":
                st.error("Password too weak (min 8 chars)")
            elif result == "invalid_admin_key":
                st.error("Incorrect admin key. Admin account not created.")
            elif result == "exists":
                st.error("Username already registered")
            elif result == "email_exists":
                st.error("Email already registered")
            elif result == "invalid_role":
                st.error("Invalid account role")
            elif result == "db_error":
                st.error("Database error")
            else:
                st.success(f"✓ {account_type.title()} account created! Login now.")

    elif action == "Login":
        st.header("Sign In")
        username = st.text_input("Username or Email")
        password = st.text_input("Password", type="password")
        
        if st.button("Sign In", use_container_width=True):
            ok, user_id, business_id, role, account_username = login_user(username, password)
            if ok:
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.session_state.business_id = business_id
                st.session_state.username = account_username
                st.session_state.role = role
                st.session_state.nav_menu = "Admin Dashboard" if role == "admin" else "Dashboard"
                st.success("✓ Login successful!")
                st.balloons()
                st.rerun()
            else:
                st.error("❌ Invalid credentials")

    elif action == "Dashboard":
        st.info("Please log in to access dashboard features.")

    elif action == "Admin Dashboard":
        st.error("Access Denied – Admin Only")

# ===== MAIN APPLICATION =====
else:
    st.sidebar.title("Navigation")
    nav_options = [
        "Home",
        "Dashboard",
        "Profile",
        "Sales Entry",
        "Expenses",
        "Advanced Analytics",
        "Inventory",
        "Products",
        "Upload Dataset",
        "Reports",
        "Logout",
    ]
    if st.session_state.role == "admin":
        nav_options.insert(-1, "Admin Dashboard")

    page = st.sidebar.radio("Menu", nav_options, label_visibility="collapsed", key="nav_menu")

    st.sidebar.markdown(f"**User:** {st.session_state.username}")
    st.sidebar.markdown(f"**Role:** {st.session_state.role}")
    
    st.markdown(f"<h1>Welcome, {st.session_state.username}! 👋</h1>", unsafe_allow_html=True)
    
    con = get_connection()
    if con is None:
        st.error("Database connection failed!")
        st.stop()
    cur = con.cursor()

    # ===== ADMIN DASHBOARD =====
    if page == "Admin Dashboard":
        if st.session_state.role == "admin":
            render_admin_dashboard(cur, con)
        else:
            st.session_state.clear()
            st.session_state.redirect_message = "Access denied. Please log in with an admin account."
            st.rerun()

    # ===== HOME =====
    elif page == "Home":
        st.header("🏠 Home")
        st.write("Quick overview of your business performance.")

        try:
            cur.execute(
                "SELECT SUM(CASE WHEN type='Sale' THEN amount ELSE 0 END), SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END), COUNT(*) FROM transactions WHERE business_id=?",
                (st.session_state.business_id,),
            )
            summary = cur.fetchone() or (0, 0, 0)
            total_sales = float(summary[0] or 0)
            total_expenses = float(summary[1] or 0)
            total_transactions = int(summary[2] or 0)
            net_profit = total_sales - total_expenses

            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Total Sales", f"₹{total_sales:,.0f}")
            h2.metric("Total Expenses", f"₹{total_expenses:,.0f}")
            h3.metric("Net Profit", f"₹{net_profit:,.0f}")
            h4.metric("Transactions", total_transactions)

            st.markdown("---")
            st.info("Use Dashboard for detailed analytics and Reports for exports.")
        except Exception as e:
            st.error(f"Error loading home summary: {str(e)}")

    # ===== PROFILE =====
    elif page == "Profile":
        st.header("👤 Profile")

        profile = get_user_profile(st.session_state.user_id)
        if profile is None:
            st.error("Unable to load profile details.")
        else:
            st.subheader("Account Details")
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Username", value=profile["username"] or "", disabled=True, key="profile_view_username")
                st.text_input("User Role", value=profile["role"] or "user", disabled=True, key="profile_view_role")
            with c2:
                email_value = profile["email"] if profile["has_email"] else "Not available"
                st.text_input("Email", value=email_value or "", disabled=True, key="profile_view_email")
                created_display = str(profile["created_at"]) if profile["created_at"] else "Not available"
                st.text_input("Account Created", value=created_display, disabled=True, key="profile_view_created")

            st.markdown("---")
            st.subheader("Update Profile")
            edit_username = st.text_input("New Username", value=profile["username"] or "", key="profile_edit_username")
            edit_email = ""
            if profile["has_email"]:
                edit_email = st.text_input("New Email", value=profile["email"] or "", key="profile_edit_email")
            else:
                st.caption("Email update is not available because this database does not include an email column.")

            if st.button("Save Profile", use_container_width=True, key="profile_save_button"):
                update_result = update_user_profile(st.session_state.user_id, edit_username, edit_email)
                if update_result == "invalid_username":
                    st.error("Username must be 3-30 characters: letters, numbers, underscore only")
                elif update_result == "invalid_email":
                    st.error("Please enter a valid email address.")
                elif update_result == "username_exists":
                    st.error("Username already exists. Choose a different username.")
                elif update_result == "db_error":
                    st.error("Database error while updating profile.")
                else:
                    st.session_state.username = edit_username
                    st.success("Profile updated successfully.")

            st.markdown("---")
            st.subheader("Change Password")
            current_password = st.text_input("Current Password", type="password", key="profile_current_password")
            new_password = st.text_input("New Password", type="password", key="profile_new_password")
            confirm_password = st.text_input("Confirm New Password", type="password", key="profile_confirm_password")

            if st.button("Update Password", use_container_width=True, key="profile_update_password"):
                if not current_password or not new_password or not confirm_password:
                    st.error("Please fill in all password fields.")
                elif new_password != confirm_password:
                    st.error("New password and confirm password do not match.")
                elif not check_password_strength(new_password):
                    st.error("New password must be at least 8 characters.")
                else:
                    pwd_result = change_user_password(st.session_state.user_id, current_password, new_password)
                    if pwd_result == "invalid_current_password":
                        st.error("Current password is incorrect.")
                    elif pwd_result in {"db_error", "not_found"}:
                        st.error("Unable to update password right now.")
                    else:
                        st.success("Password updated successfully.")

    # ===== SALES ENTRY =====
    elif page == "Sales Entry":
        st.header("💰 Add Sales Transaction")
        
        col1, col2 = st.columns(2)
        with col1:
            product = st.text_input("Product / Service Name")
            amount = st.number_input("Sale Amount (₹)", min_value=0.0, step=100.0)
        with col2:
            quantity = st.number_input("Quantity", min_value=1, step=1)
            notes = st.text_area("Notes")
        
        if st.button("Record Sale", use_container_width=True):
            if product and amount > 0:
                try:
                    cur.execute(
                        "INSERT INTO transactions (business_id,type,category,amount,txn_date,notes) VALUES (?,?,?,?,?,?)",
                        (st.session_state.business_id, "Sale", product, amount*quantity, datetime.now().date(), notes)
                    )
                    con.commit()
                    st.success(f"✓ Sale added: {product} x{quantity} - ₹{amount*quantity:,.2f}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            else:
                st.warning("Enter valid details")

    # ===== EXPENSES =====
    elif page == "Expenses":
        st.header("💸 Add Expense Transaction")
        
        col1, col2 = st.columns(2)
        with col1:
            description = st.text_input("Expense Description")
            amount = st.number_input("Expense Amount (₹)", min_value=0.0, step=100.0)
        with col2:
            category = st.selectbox("Category", ["Rent", "Salary", "Utilities", "Supplies", "Other"])
            notes = st.text_area("Notes")
        
        if st.button("Record Expense", use_container_width=True):
            if description and amount > 0:
                try:
                    cur.execute(
                        "INSERT INTO transactions (business_id,type,category,amount,txn_date,notes) VALUES (?,?,?,?,?,?)",
                        (st.session_state.business_id, "Expense", category, amount, datetime.now().date(), notes)
                    )
                    con.commit()
                    st.success(f"✓ Expense added: {description} - ₹{amount:,.2f}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            else:
                st.warning("Enter valid details")

    # ===== UPLOAD DATASET (CSV / EXCEL) =====
    elif page == "Upload Dataset":
        st.header("📁 Upload Dataset (CSV / Excel)")
        st.write("Upload a CSV or Excel file with transaction data. Columns: Category, Amount, Type (Sale/Expense), Date (optional)")

        file = st.file_uploader("Choose file (CSV or Excel)", type=["csv", "xls", "xlsx"])

        if file:
            try:
                df = read_uploaded_dataframe(file)

                st.dataframe(df.head(), use_container_width=True)

                # Auto-detect columns
                def detect_column(names):
                    for name in names:
                        for col in df.columns:
                            if name.lower() in str(col).lower():
                                return col
                    return None

                type_col = detect_column(["type", "transaction", "nature"])
                category_col = detect_column(["category", "product", "item", "description"])
                amount_col = detect_column(["amount", "price", "total", "value", "revenue"])
                date_col = detect_column(["date", "txn_date", "transaction_date"])

                st.info(f"✓ Detected - Category: {category_col}, Amount: {amount_col}, Type: {type_col}, Date: {date_col}")

                if st.button("Import Data", use_container_width=True):
                    if not all([category_col, amount_col]):
                        st.error("Could not detect Category and Amount columns")
                    else:
                        try:
                            progress_bar = st.progress(0)
                            total_rows = len(df)
                            count = 0

                            for idx, (_, row) in enumerate(df.iterrows()):
                                # Detect transaction type
                                detected_type = "Sale"
                                if type_col and "expense" in str(row[type_col]).lower():
                                    detected_type = "Expense"

                                # Get date or use today
                                txn_date = datetime.now().date()
                                if date_col:
                                    try:
                                        txn_date = pd.to_datetime(row[date_col]).date()
                                    except:
                                        pass

                                # Get category and amount
                                category = str(row[category_col])
                                try:
                                    amount = float(row[amount_col])
                                except:
                                    continue

                                # Insert transaction
                                cur.execute(
                                    "INSERT INTO transactions (business_id,type,category,amount,txn_date,notes) VALUES (?,?,?,?,?,?)",
                                    (st.session_state.business_id, detected_type, category, amount, txn_date, "Imported from file")
                                )
                                count += 1
                                progress_bar.progress((idx + 1) / total_rows)

                            con.commit()
                            st.success(f"✓ Successfully imported {count} transactions!")
                            # ==========================================
                            # STORE UPLOADED DATA FOR ADVANCED ANALYTICS
                            # ==========================================

                            uploaded_df = df.copy()

                            # Ensure proper columns
                            if date_col:
                                uploaded_df["Date"] = pd.to_datetime(uploaded_df[date_col])
                            else:
                                uploaded_df["Date"] = datetime.now()

                            uploaded_df["Amount"] = pd.to_numeric(uploaded_df[amount_col], errors="coerce")

                            # Detect Type column
                            if type_col:
                                uploaded_df["Type"] = uploaded_df[type_col]
                            else:
                                uploaded_df["Type"] = "Sale"

                            if category_col:
                                uploaded_df["Category"] = uploaded_df[category_col].astype(str)
                            else:
                                uploaded_df["Category"] = "Unknown"

                            # Keep only required columns
                            uploaded_df = uploaded_df[["Date", "Amount", "Type", "Category"]]

                            # Save in session
                            st.session_state.uploaded_df = uploaded_df

                            st.success("Dataset stored for Advanced Analytics forecasting ✅")

                            # Show summary
                            cur.execute(
                                "SELECT type, COUNT(*), SUM(amount) FROM transactions WHERE business_id=? AND notes LIKE 'Imported%' GROUP BY type",
                                (st.session_state.business_id,)
                            )
                            summary = cur.fetchall()

                            st.subheader("📊 Import Summary")
                            for row in summary:
                                txn_type, count_txn, total_amt = row
                                st.metric(f"{txn_type}s Imported", f"{count_txn} transactions | ₹{total_amt:,.2f}")

                            # Calculate and display totals
                            cur.execute(
                                "SELECT SUM(CASE WHEN type='Sale' THEN amount ELSE 0 END) as sales, SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END) as expenses FROM transactions WHERE business_id=?",
                                (st.session_state.business_id,)
                            )
                            totals = cur.fetchone()
                            total_sales = totals[0] or 0
                            total_expenses = totals[1] or 0
                            total_profit = total_sales - total_expenses

                            st.markdown("---")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("💰 Total Sales", f"₹{total_sales:,.0f}")
                            with col2:
                                st.metric("💸 Total Expenses", f"₹{total_expenses:,.0f}")
                            with col3:
                                st.metric("🟢 Net Profit", f"₹{total_profit:,.0f}")

                            # Display transactions chart
                            cur.execute(
                                "SELECT type, COUNT(*), SUM(amount) FROM transactions WHERE business_id=? GROUP BY type",
                                (st.session_state.business_id,)
                            )
                            chart_data = cur.fetchall()

                            if chart_data:
                                st.subheader("📈 Transaction Overview")
                                fig = go.Figure(data=[
                                    go.Bar(
                                        x=[row[0] for row in chart_data],
                                        y=[row[2] for row in chart_data],
                                        marker_color=['#2563eb', '#dc2626']
                                    )
                                ])
                                fig.update_layout(
                                    title="Total Amount by Transaction Type",
                                    xaxis_title="Type",
                                    yaxis_title="Amount (₹)"
                                )
                                st.plotly_chart(fig, use_container_width=True)

                        except Exception as e:
                            st.error(f"Import failed: {str(e)}")

            except Exception as e:
                st.error(f"Error reading file: {str(e)}")

    # ===== DASHBOARD WITH PROFIT CALCULATION =====
    elif page == "Dashboard":
        st.header("📊 Dashboard - Profit & Inventory Tracking")
        
        try:
            # Get transaction data
            cur.execute(
                "SELECT type, amount, txn_date FROM transactions WHERE business_id=? ORDER BY txn_date DESC",
                (st.session_state.business_id,)
            )
            rows = cur.fetchall()
            
            if not rows:
                st.info("No data yet. Start adding transactions!")
            else:
                df_txn = pd.DataFrame(rows, columns=["Type", "Amount", "Date"])
                df_txn["Amount"] = pd.to_numeric(df_txn["Amount"])
                
                # Calculate totals
                sales = df_txn[df_txn["Type"] == "Sale"]["Amount"].sum()
                expenses = df_txn[df_txn["Type"] == "Expense"]["Amount"].sum()
                profit = sales - expenses
                profit_margin = (profit / sales * 100) if sales > 0 else 0
                
                # Metrics Row
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("🔵 Total Sales", f"₹{sales:,.0f}")
                with col2:
                    st.metric("🔴 Total Expenses", f"₹{expenses:,.0f}")
                with col3:
                    st.metric("🟢 Net Profit", f"₹{profit:,.0f}")
                with col4:
                    st.metric("📈 Profit Margin", f"{profit_margin:.1f}%")
                
                st.markdown("---")
                
                # Charts
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Sales vs Expenses")
                    fig = go.Figure(data=[
                        go.Bar(name='Sales', x=['Sales', 'Expenses'], y=[sales, expenses], 
                               marker_color=['#2563eb', '#dc2626'])
                    ])
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.subheader("Profit Distribution")
                    fig = go.Figure(data=[go.Pie(
                        labels=['Sales', 'Expenses'],
                        values=[sales, expenses],
                        marker=dict(colors=['#059669', '#dc2626'])
                    )])
                    st.plotly_chart(fig, use_container_width=True)
                
                # Daily totals
                df_txn['Date'] = pd.to_datetime(df_txn['Date'])
                daily_sales = df_txn[df_txn['Type'] == 'Sale'].groupby('Date')['Amount'].sum()
                daily_expenses = df_txn[df_txn['Type'] == 'Expense'].groupby('Date')['Amount'].sum()
                
                st.subheader("Daily Totals")
                daily_df = pd.DataFrame({
                    'Date': daily_sales.index.union(daily_expenses.index),
                    'Sales': daily_sales,
                    'Expenses': daily_expenses
                }).fillna(0)
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=daily_df['Date'], y=daily_df['Sales'], 
                                        name='Sales', mode='lines+markers'))
                fig.add_trace(go.Scatter(x=daily_df['Date'], y=daily_df['Expenses'], 
                                        name='Expenses', mode='lines+markers'))
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("Monthly Profit Analysis")
                df_txn['Month'] = df_txn['Date'].dt.to_period('M')
                monthly = df_txn.groupby(['Month', 'Type'])['Amount'].sum().unstack(fill_value=0)
                monthly['Profit'] = monthly.get('Sale', 0) - monthly.get('Expense', 0)
                st.dataframe(monthly, use_container_width=True)
        
        except Exception as e:
            st.error(f"Error loading dashboard: {str(e)}")
    elif page == "Advanced Analytics":

            st.header("📊 Advanced Business Analytics")

            # ======================================
            # SELECT DATA SOURCE
            # ======================================

            if "uploaded_df" in st.session_state:

                st.success("Using Uploaded Dataset 📁")

                df = st.session_state.uploaded_df.copy()
                df["Date"] = pd.to_datetime(df["Date"])
                df["Amount"] = pd.to_numeric(df["Amount"])
                if "Category" not in df.columns:
                    df["Category"] = "Unknown"

            else:

                st.info("Using Database Transactions 🗄")

                cur.execute(
                    "SELECT type, category, amount, txn_date FROM transactions WHERE business_id=?",
                    (st.session_state.business_id,)
                )
                rows = cur.fetchall()

                if not rows:
                    st.warning("No data available.")
                    st.stop()

                df = pd.DataFrame(rows, columns=["Type", "Category", "Amount", "Date"])
                df["Date"] = pd.to_datetime(df["Date"])
                df["Amount"] = pd.to_numeric(df["Amount"])
                df["Category"] = df["Category"].fillna("Uncategorized")

            # ======================================
            # DAILY AGGREGATION
            # ======================================

            daily = df.groupby("Date")["Amount"].sum().reset_index()
            daily = daily.sort_values("Date")

            # ======================================
            # DAILY PROPHET FORECAST
            # ======================================

            st.subheader("📅 Daily Prophet Forecast")

            if len(daily) >= 5:

                prophet_daily = daily.rename(columns={"Date": "ds", "Amount": "y"})

                model = Prophet()
                model.fit(prophet_daily)

                future = model.make_future_dataframe(periods=30)
                forecast = model.predict(future)

                fig, ax = plt.subplots(figsize=(12,6))

                ax.scatter(prophet_daily["ds"], prophet_daily["y"],
                        color="black", s=25, label="Historical")

                ax.plot(forecast["ds"], forecast["yhat"],
                        color="blue", linewidth=2, label="Forecast")

                ax.fill_between(forecast["ds"],
                                forecast["yhat_lower"],
                                forecast["yhat_upper"],
                                alpha=0.3)

                ax.set_title("Daily Sales Forecast")
                ax.legend()
                ax.grid(True)

                st.pyplot(fig)

            else:
                st.info("Not enough daily data for forecast.")

            # ======================================
            # MONTHLY FORECAST
            # ======================================

            st.subheader("📆 Monthly Prophet Forecast")

            df["Month"] = df["Date"].dt.to_period("M")
            monthly = df.groupby("Month")["Amount"].sum().reset_index()
            monthly["Month"] = monthly["Month"].dt.to_timestamp()

            if len(monthly) >= 3:

                prophet_monthly = monthly.rename(columns={"Month": "ds", "Amount": "y"})

                model_m = Prophet()
                model_m.fit(prophet_monthly)

                future_m = model_m.make_future_dataframe(periods=3, freq="M")
                forecast_m = model_m.predict(future_m)

                fig2, ax2 = plt.subplots(figsize=(12,6))

                ax2.scatter(prophet_monthly["ds"], prophet_monthly["y"],
                            color="black", s=30)

                ax2.plot(forecast_m["ds"], forecast_m["yhat"],
                        color="green", linewidth=2)

                ax2.fill_between(forecast_m["ds"],
                                forecast_m["yhat_lower"],
                                forecast_m["yhat_upper"],
                                alpha=0.3)

                ax2.set_title("Monthly Sales Forecast")
                ax2.grid(True)

                st.pyplot(fig2)

            else:
                st.info("Not enough monthly data for forecast.")

            # ======================================
            # LINEAR REGRESSION (OPTIONAL)
            # ======================================

            st.subheader("📈 Linear Regression Forecast")

            if len(daily) >= 5:

                daily["Date_Ordinal"] = daily["Date"].map(datetime.toordinal)

                X = daily[["Date_Ordinal"]]
                y = daily["Amount"]

                model_lr = LinearRegression()
                model_lr.fit(X, y)

                last_date = daily["Date"].max()
                future_dates = pd.date_range(start=last_date + timedelta(days=1), periods=30)

                future_df = pd.DataFrame({"Date": future_dates})
                future_df["Date_Ordinal"] = future_df["Date"].map(datetime.toordinal)

                predictions = model_lr.predict(future_df[["Date_Ordinal"]])

                fig3, ax3 = plt.subplots(figsize=(12,6))

                ax3.scatter(daily["Date"], daily["Amount"], s=20)
                ax3.plot(daily["Date"], model_lr.predict(X), color="green")
                ax3.plot(future_df["Date"], predictions, linestyle="--", color="orange")

                ax3.set_title("Linear Regression Forecast")
                ax3.grid(True)

                st.pyplot(fig3)

            # ======================================
            # CATEGORY-WISE EXPENSE BREAKDOWN
            # ======================================

            st.subheader("🧾 Category-wise Expense Breakdown")

            expense_df = df[df["Type"].astype(str).str.lower() == "expense"].copy()

            if not expense_df.empty:
                category_expense = expense_df.groupby("Category", dropna=False)["Amount"].sum().reset_index()
                category_expense["Category"] = category_expense["Category"].fillna("Uncategorized")
                category_expense = category_expense.sort_values("Amount", ascending=False)

                fig_cat = go.Figure(data=[go.Pie(
                    labels=category_expense["Category"],
                    values=category_expense["Amount"],
                    hole=0.35
                )])
                fig_cat.update_layout(title="Expense Share by Category")
                st.plotly_chart(fig_cat, use_container_width=True)

                st.dataframe(
                    category_expense.rename(columns={"Category": "Expense Category", "Amount": "Total Expense (₹)"}),
                    use_container_width=True
                )
            else:
                st.info("No expense transactions available for category breakdown.")

            # ======================================
            # DOWNLOAD FORECAST
            # ======================================

            st.subheader("📥 Download Forecast")

            if len(daily) >= 5:
                download_df = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]
                csv = download_df.to_csv(index=False).encode("utf-8")

                st.download_button(
                    "Download Daily Forecast CSV",
                    data=csv,
                    file_name="daily_forecast.csv",
                    mime="text/csv"
                )
    # ===== INVENTORY TRACKING =====
    elif page == "Inventory":
        st.header("📦 Inventory Tracking")
        
        try:
            cur.execute(
                "SELECT id, name, stock, cost_price, sale_price FROM products WHERE business_id=?",
                (st.session_state.business_id,)
            )
            products = cur.fetchall()
            
            st.subheader("Add New Product")
            col1, col2, col3 = st.columns(3)
            with col1:
                prod_name = st.text_input("Product Name")
            with col2:
                cost_price = st.number_input("Cost Price (₹)", min_value=0.0)
            with col3:
                sale_price = st.number_input("Sale Price (₹)", min_value=0.0)
            
            stock = st.number_input("Initial Stock", min_value=0)
            
            if st.button("Add Product", use_container_width=True):
                if prod_name and cost_price > 0 and sale_price > 0:
                    try:
                        cur.execute(
                            "INSERT INTO products (business_id,name,cost_price,sale_price,stock) VALUES (?,?,?,?,?)",
                            (st.session_state.business_id, prod_name, cost_price, sale_price, stock)
                        )
                        con.commit()
                        st.success(f"✓ Product added: {prod_name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
            
            st.markdown("---")
            st.subheader("Current Inventory")
            
            if products:
                df_inv = pd.DataFrame(products, columns=["ID", "Product", "Stock", "Cost Price", "Sale Price"])
                df_inv["Profit/Unit"] = df_inv["Sale Price"] - df_inv["Cost Price"]
                df_inv["Total Value"] = df_inv["Stock"] * df_inv["Cost Price"]
                st.dataframe(df_inv.drop("ID", axis=1), use_container_width=True)
                
                # COGS Calculation
                st.subheader("📊 Inventory Analysis")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Items", df_inv["Stock"].sum())
                with col2:
                    st.metric("Total Inventory Value", f"₹{df_inv['Total Value'].sum():,.0f}")
                with col3:
                    st.metric("Avg Profit/Unit", f"₹{df_inv['Profit/Unit'].mean():.2f}")
                
                # Low stock alerts
                low_stock = df_inv[df_inv["Stock"] < 5]
                if not low_stock.empty:
                    st.warning("⚠️ Low Stock Items:")
                    st.dataframe(low_stock, use_container_width=True)
            else:
                st.info("No products added yet")
        
        except Exception as e:
            st.error(f"Error: {str(e)}")

    # ===== PRODUCTS MANAGEMENT =====
    elif page == "Products":
        st.header("🛍️ Products Management")
        
        try:
            cur.execute(
                "SELECT id, name, cost_price, sale_price, stock FROM products WHERE business_id=?",
                (st.session_state.business_id,)
            )
            products = cur.fetchall()
            
            if products:
                df_prod = pd.DataFrame(products, columns=["ID", "Name", "Cost", "Sale", "Stock"])
                st.dataframe(df_prod, use_container_width=True)
                
                st.markdown("---")
                st.subheader("Update Product Stock")
                prod_id = st.selectbox("Select Product", [p[0] for p in products], 
                                       format_func=lambda x: next(p[1] for p in products if p[0] == x))
                new_stock = st.number_input("New Stock Quantity", min_value=0)
                
                if st.button("Update Stock", use_container_width=True):
                    try:
                        cur.execute("UPDATE products SET stock=? WHERE id=? AND business_id=?",
                                   (new_stock, prod_id, st.session_state.business_id))
                        con.commit()
                        st.success("✓ Stock updated")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
            else:
                st.info("No products found")
        
        except Exception as e:
            st.error(f"Error: {str(e)}")

    # ===== REPORTS GENERATION =====
    elif page == "Reports":
        st.header("📄 Generate Reports")
        
        try:
            report_type = st.selectbox("Report Type", 
                ["Daily Summary", "Monthly Summary", "Profit Analysis", "Inventory Report", "Category Expense Breakdown"])

            cur.execute(
                "SELECT type, category, amount, txn_date FROM transactions WHERE business_id=? ORDER BY txn_date DESC",
                (st.session_state.business_id,)
            )
            rows = cur.fetchall()

            if not rows and report_type != "Inventory Report":
                st.info("No transaction data to generate report")
            else:
                report_df = None
                report_metrics = {}
                report_file_base = report_type.lower().replace(" ", "_")

                if rows:
                    df = pd.DataFrame(rows, columns=["Type", "Category", "Amount", "Date"])
                    df["Amount"] = pd.to_numeric(df["Amount"])
                    df["Date"] = pd.to_datetime(df["Date"])
                    df["Category"] = df["Category"].fillna("Uncategorized")

                if report_type == "Daily Summary" and rows:
                    report_df = df.groupby("Date", as_index=False)["Amount"].sum()
                    st.dataframe(report_df, use_container_width=True)

                elif report_type == "Monthly Summary" and rows:
                    df["Month"] = df["Date"].dt.to_period("M").astype(str)
                    report_df = df.groupby("Month", as_index=False)["Amount"].sum()
                    st.dataframe(report_df, use_container_width=True)

                elif report_type == "Profit Analysis" and rows:
                    sales = df[df["Type"] == "Sale"]["Amount"].sum()
                    expenses = df[df["Type"] == "Expense"]["Amount"].sum()
                    profit = sales - expenses
                    margin = (profit / sales * 100) if sales > 0 else 0

                    report_metrics = {
                        "Total Sales": f"₹{sales:,.2f}",
                        "Total Expenses": f"₹{expenses:,.2f}",
                        "Net Profit": f"₹{profit:,.2f}",
                        "Profit Margin": f"{margin:.2f}%"
                    }
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Sales", report_metrics["Total Sales"])
                    col2.metric("Expenses", report_metrics["Total Expenses"])
                    col3.metric("Net Profit", report_metrics["Net Profit"])
                    col4.metric("Margin", report_metrics["Profit Margin"])

                    report_df = pd.DataFrame(
                        [{"Metric": key, "Value": value} for key, value in report_metrics.items()]
                    )

                elif report_type == "Category Expense Breakdown" and rows:
                    expense_df = df[df["Type"].astype(str).str.lower() == "expense"]
                    if expense_df.empty:
                        st.info("No expense records found.")
                    else:
                        report_df = expense_df.groupby("Category", as_index=False)["Amount"].sum()
                        report_df = report_df.sort_values("Amount", ascending=False)
                        st.dataframe(report_df, use_container_width=True)
                        fig = go.Figure(data=[go.Pie(labels=report_df["Category"], values=report_df["Amount"], hole=0.35)])
                        fig.update_layout(title="Category-wise Expense Distribution")
                        st.plotly_chart(fig, use_container_width=True)

                elif report_type == "Inventory Report":
                    cur.execute(
                        "SELECT name, stock, cost_price, sale_price FROM products WHERE business_id=?",
                        (st.session_state.business_id,)
                    )
                    inv = cur.fetchall()
                    if inv:
                        report_df = pd.DataFrame(inv, columns=["Product", "Stock", "Cost Price", "Sale Price"])
                        report_df["Inventory Value"] = report_df["Stock"] * report_df["Cost Price"]
                        st.dataframe(report_df, use_container_width=True)
                    else:
                        st.info("No products found for inventory report")

                if report_df is not None and not report_df.empty:
                    st.markdown("---")
                    st.subheader("📥 Export Report")

                    csv_data = report_df.to_csv(index=False).encode("utf-8")
                    col_csv, col_excel, col_pdf = st.columns(3)

                    with col_csv:
                        st.download_button(
                            "Download CSV",
                            data=csv_data,
                            file_name=f"{report_file_base}.csv",
                            mime="text/csv"
                        )

                    with col_excel:
                        excel_buffer = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                            report_df.to_excel(writer, index=False, sheet_name="Report")
                        excel_buffer.seek(0)
                        st.download_button(
                            "Download Excel",
                            data=excel_buffer,
                            file_name=f"{report_file_base}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                    with col_pdf:
                        pdf_data = generate_pdf_report(
                            title=f"{report_type} Report",
                            dataframe=report_df,
                            metrics=report_metrics
                        )
                        st.download_button(
                            "Download PDF",
                            data=pdf_data,
                            file_name=f"{report_file_base}.pdf",
                            mime="application/pdf"
                        )
        
        except Exception as e:
            st.error(f"Error: {str(e)}")

    # ===== LOGOUT =====
    elif page == "Logout":
        st.session_state.clear()
        st.success("✓ Logged out successfully!")
        st.rerun()

    con.close()