import streamlit as st
from lib.auth import login_page, logout

st.set_page_config(
    page_title="Transition Portal — Cars24",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session defaults ───────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# ── Not logged in → show login ─────────────────────────────────────────────────
if not st.session_state.authenticated:
    login_page()
    st.stop()

# ── Logged in ──────────────────────────────────────────────────────────────────
user_email = st.session_state.user_email
role       = st.session_state.role

with st.sidebar:
    st.markdown("### 🔄 Transition Portal")
    st.caption("Cars24 · HR")
    st.divider()
    st.write(f"**{user_email}**")
    st.caption(f"Role: `{role}`")
    st.divider()
    if st.button("Logout", use_container_width=True):
        logout()

# ── Route by role ──────────────────────────────────────────────────────────────
if role == "ADMIN":
    from views.admin_view import admin_dashboard
    admin_dashboard(user_email)

elif role == "MANAGER":
    from views.manager_view import manager_dashboard
    manager_dashboard(user_email)

elif role == "PAYROLL":
    from views.payroll_view import payroll_dashboard
    payroll_dashboard(user_email)

else:
    st.error("Access denied. Contact HR admin.")
