import time
import random
import base64
import streamlit as st
from lib.config import get_secret

DEV_MODE = get_secret("DEV_MODE", "false").lower() == "true"


def _set_token(email: str):
    """Store session token in URL so refresh doesn't log user out."""
    try:
        data  = f"{email}:{int(time.time())}"
        token = base64.urlsafe_b64encode(data.encode()).decode()
        st.query_params["t"] = token
    except Exception:
        pass


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_role(email: str) -> str | None:
    from lib.db import get_user_role
    return get_user_role(email)


def _send_otp(email: str, otp: str):
    from lib.email_utils import send_otp
    send_otp(email, otp)


# ── Login page ─────────────────────────────────────────────────────────────────

def login_page():
    st.markdown(
        """
        <div style="text-align:center;padding:40px 0 8px;">
          <h1 style="color:#e31837;margin-bottom:4px;">🔄 Transition Portal</h1>
          <p style="color:#666;">Cars24 · Employee Separation Management</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        if DEV_MODE:
            st.warning("**DEV MODE** — OTP skipped. Set `DEV_MODE=false` and add Gmail App Password for production.")

        if not st.session_state.get("otp_sent"):
            with st.form("login_form"):
                email  = st.text_input("Work Email", placeholder="you@cars24.com / you@cariotauto.com")
                submit = st.form_submit_button(
                    "Send OTP" if not DEV_MODE else "Login",
                    type="primary",
                    use_container_width=True,
                )

            if submit:
                email = email.strip().lower()
                if not any(email.endswith(d) for d in ("@cars24.com", "@cariotauto.com")):
                    st.error("Only @cars24.com and @cariotauto.com emails are allowed.")
                    return
                role = _get_role(email)
                if not role:
                    st.error("Access denied. Contact HR admin to get access.")
                    return

                if DEV_MODE:
                    st.session_state.authenticated = True
                    st.session_state.user_email    = email
                    st.session_state.role          = role
                    _set_token(email)
                    st.rerun()
                else:
                    otp = str(random.randint(100000, 999999))
                    try:
                        _send_otp(email, otp)
                        st.session_state.otp_code    = otp
                        st.session_state.otp_email   = email
                        st.session_state.otp_sent_at = time.time()
                        st.session_state.otp_sent    = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to send OTP: {e}")
        else:
            pending_email = st.session_state.get("otp_email", "")
            st.info(f"OTP sent to **{pending_email}**. Check your inbox.")

            with st.form("otp_form"):
                otp_input = st.text_input("Enter 6-digit OTP", max_chars=6, placeholder="123456")
                c1, c2    = st.columns(2)
                verify    = c1.form_submit_button("Verify",     type="primary", use_container_width=True)
                resend    = c2.form_submit_button("Resend OTP", use_container_width=True)

            if verify:
                stored  = st.session_state.get("otp_code", "")
                sent_at = st.session_state.get("otp_sent_at", 0)
                if time.time() - sent_at > 600:
                    st.error("OTP expired. Click Resend.")
                elif otp_input.strip() != stored:
                    st.error("Incorrect OTP.")
                else:
                    role = _get_role(pending_email)
                    st.session_state.authenticated = True
                    st.session_state.user_email    = pending_email
                    st.session_state.role          = role
                    for k in ["otp_code", "otp_email", "otp_sent_at", "otp_sent"]:
                        st.session_state.pop(k, None)
                    _set_token(pending_email)
                    st.rerun()

            if resend:
                otp = str(random.randint(100000, 999999))
                try:
                    _send_otp(pending_email, otp)
                    st.session_state.otp_code    = otp
                    st.session_state.otp_sent_at = time.time()
                    st.success("New OTP sent!")
                except Exception as e:
                    st.error(f"Failed to send OTP: {e}")


def logout():
    try:
        del st.query_params["t"]
    except Exception:
        pass
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
