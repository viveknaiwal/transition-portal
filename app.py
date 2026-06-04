import time
import base64
import streamlit as st
from lib.auth import login_page, logout

st.set_page_config(
    page_title="Transition Portal — Cars24",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _restore_session():
    """Check URL token and auto-login if valid (survives browser refresh)."""
    if st.session_state.get("authenticated"):
        return
    token = st.query_params.get("t", "")
    if not token:
        return
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        email, ts = decoded.rsplit(":", 1)
        if int(time.time()) - int(ts) > 7 * 86400:   # 7-day expiry
            del st.query_params["t"]
            return
        from lib.db import get_user_role
        role = get_user_role(email)
        if role:
            st.session_state.authenticated = True
            st.session_state.user_email    = email
            st.session_state.role          = role
    except Exception:
        pass


# Restore session from URL token on every page load
_restore_session()

# ── Not logged in → show login ─────────────────────────────────────────────────
if not st.session_state.get("authenticated"):
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
