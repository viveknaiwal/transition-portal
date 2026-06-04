import os
import time
import random
import base64
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DEV_MODE     = os.getenv("DEV_MODE", "false").lower() == "true"
SESSION_DAYS = 7   # how many days before token expires and user must log in again


# ── Session token (URL query param) ───────────────────────────────────────────

def _encode_token(email: str) -> str:
    data = f"{email}:{int(time.time())}"
    return base64.urlsafe_b64encode(data.encode()).decode()


def _decode_token(token: str) -> str | None:
    """Returns email if token is valid and not expired, else None."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        email, ts = decoded.rsplit(":", 1)
        if int(time.time()) - int(ts) < SESSION_DAYS * 86400:
            return email
    except Exception:
        pass
    return None


def restore_session() -> bool:
    """
    Called on every page load before showing login.
    Checks URL for a saved session token — restores login if valid.
    Returns True if user was auto-logged in.
    """
    if st.session_state.get("authenticated"):
        return True

    token = st.query_params.get("t", "")
    if not token:
        return False

    email = _decode_token(token)
    if not email:
        # Token expired — remove it silently
        try:
            del st.query_params["t"]
        except Exception:
            pass
        return False

    role = _get_role(email)
    if not role:
        return False

    st.session_state.authenticated = True
    st.session_state.user_email    = email
    st.session_state.role          = role
    return True


def _set_token(email: str):
    try:
        st.query_params["t"] = _encode_token(email)
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
