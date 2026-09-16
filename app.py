import io
import json
import os
import re
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Literature Review Explorer",
    page_icon="📚",
    layout="wide"
)

# ==========================================
# 2. PASSWORD PROTECTION (ENTER KEY SUPPORT)
# ==========================================
try:
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    APP_PASSWORD = "research2026"

def check_password():
    """Returns True if the user has authenticated."""
    if st.session_state.get("authenticated", False):
        return True

    st.title("🔒 Literature Review Database")
    st.write("Please enter the password to access your research library.")

    with st.form("login_form"):
        pwd_input = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Log In")

        if submit_button:
            if pwd_input == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")

    return False

if not check_password():
    st.stop()


# ==========================================
# 3. DATA LOADING & URL PARSING
# ==========================================
def format_google_sheets_url(url: str) -> str:
    """Converts a standard Google Sheets share link to a clean CSV export URL."""
    url = url.strip().strip('"').strip("'")
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if match:
        sheet_id = match.group(1)
        gid = "0"
        gid_match = re.search(r"[#&?]gid=([0-9]+)", url)
        if gid_match:
            gid = gid_match.group(1)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    return url

@st.cache_data(ttl=60)
def load_data(source_url: str) -> pd.DataFrame:
    """Reads live data directly from Google Sheets while preserving literal N/A values."""
    export_url = format_google_sheets_url(source_url)
    
    # keep_default_na=False ensures "N/A", "NA", and "None" are read as actual text
    df = pd.read_csv(export_url, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# ==========================================
# 4. HELPER FUNCTIONS & CROSSREF RADAR
# ==========================================
def get_unique_items(series: pd.Series) -> list:
    """
    Extracts unique terms separated by commas or semicolons, 
    stripping out parentheses and any content inside them.
    """
    all_items = set()
    for entry in series.dropna():
        # 1. Remove anything in parentheses: e.g. "Adolescents (grades 9-12)" -> "Adolescents "
        cleaned_entry = re.sub(r"\(.*?\)", "", str(entry))
        
        # 2. Split strictly on commas or semicolons
        items = re.split(r"[,;]", cleaned_entry)
        for item in items:
            cleaned = item.strip()
            # Omit blanks and N/A values
            if cleaned and cleaned.upper() not in ["N/A", "NA"]:
                all_items.add(cleaned)
                
    return sorted(list(all_items), key=lambda s: s.lower())

@st.cache_data(ttl=3600)
def check_recent_publications(keywords: list[str], max_results: int = 5):
    """
    Queries Crossref for journal articles from the past 365 days where
    the keywords appear in the title, scoped to developmental/health/family disciplines.
    """
    if not keywords:
        return []

    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    title_query = " ".join([f'"{k}"' if " " in k else k for k in keywords])
    relevant_disciplines = (
    "development psychology health adolescent youth child family pediatric "
    "clinical psychiatry social emotional 'social-emotional' wellbeing"
)

    url = "https://api.crossref.org/works"
    params = {
        "query.title": title_query,
        "query.container-title": relevant_disciplines,
        "filter": f"from-pub-date:{one_year_ago},type:journal-article",
        "rows": max_results,
        "sort": "score",
        "order": "desc"
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": "LitReviewExplorer/1.0 (mailto:researcher@example.com)"},
            timeout=8
        )
        if response.status_code == 200:
            items = response.json().get("message", {}).get("items", [])
            matches = []
            for item in items:
                title = item.get("title", ["Untitled"])[0]
                doi = item.get("DOI", "")
                link = item.get("URL", f"https://doi.org/{doi}")
                journal = item.get("container-title", ["Unknown Journal"])[0]

                date_parts = item.get("published", {}).get("date-parts", [[None]])[0]
                pub_date = "-".join([str(p) for p in date_parts if p]) if date_parts else "Recent"
                pub_year = str(date_parts[0]) if date_parts and date_parts[0] else ""

                authors = item.get("author", [])
                first_author = authors[0].get("family", "Unknown") if authors else "Unknown"
                author_year = f"{first_author} et al. ({pub_year})" if pub_year else first_author

                matches.append({
                    "title": title,
                    "journal": journal,
                    "author": first_author,
                    "author_year": author_year,
                    "date": pub_date,
                    "link": link,
                    "doi": doi
                })
            return matches
    except Exception:
        return []
    return []


# ==========================================
# 5. SAVED SEARCHES & BOOKMARKS STORAGE
# ==========================================
SAVED_SEARCHES_FILE = "saved_searches.json"
ALERT_BOOKMARKS_FILE = "alert_bookmarks.json"

def load_saved_searches() -> dict:
    if os.path.exists(SAVED_SEARCHES_FILE):
        try:
            with open(SAVED_SEARCHES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_search(name: str, criteria: dict):
    searches = load_saved_searches()
    searches[name] = criteria
    with open(SAVED_SEARCHES_FILE, "w") as f:
        json.dump(searches, f, indent=2)

def delete_search(name: str):
    searches = load_saved_searches()
    if name in searches:
        del searches[name]
        with open(SAVED_SEARCHES_FILE, "w") as f:
            json.dump(searches, f, indent=2)

def load_alert_bookmarks() -> dict:
    """Loads whole alert bundles saved by keyword title."""
    if os.path.exists(ALERT_BOOKMARKS_FILE):
        try:
            with open(ALERT_BOOKMARKS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_alert_bookmark(title: str, hits: list, terms: list):
    """Saves an entire alert notification bundle."""
    bms = load_alert_bookmarks()
    bms[title] = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "terms": terms,
        "hits": hits
    }
    with open(ALERT_BOOKMARKS_FILE, "w") as f:
        json.dump(bms, f, indent=2)

def delete_alert_bookmark(title: str):
    """Deletes an alert bundle."""
    bms = load_alert_bookmarks()
    if title in bms:
        del bms[title]
        with open(ALERT_BOOKMARKS_FILE, "w") as f:
            json.dump(bms, f, indent=2)


# ==========================================
# 6. SIDEBAR: DATA SOURCE & REFRESH
# ==========================================
st.sidebar.title("⚙️ Settings & Sources")

try:
    secret_url = st.secrets.get("SHEET_URL", "")
except Exception:
    secret_url = ""

if secret_url:
    sheet_link = secret_url
    st.sidebar.success(" Connected to private research sheet")
else:
    sheet_link = st.sidebar.text_input("Google Sheets Share Link", value="")

if st.sidebar.button("🔄 Force Refresh Sheet"):
    st.cache_data.clear()
    st.rerun()

if not sheet_link.strip():
    st.info("👈 Please configure `SHEET_URL` in your Streamlit Secrets or paste a link in the sidebar.")
    st.stop()

try:
    df = load_data(sheet_link)
except Exception as e:
    st.error(f"Could not load file from Google Sheets. Error: {e}")
    st.stop()

if st.sidebar.button("🔒 Log Out"):
    st.session_state.authenticated = False
    st.rerun()


# ==========================================
# 7. SIDEBAR: SAVED SEARCHES & BOOKMARKS
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ Saved Searches")

saved_searches = load_saved_searches()
search_options = ["-- None --"] + list(saved_searches.keys())
selected_saved = st.sidebar.selectbox("Load a preset search:", options=search_options)

if selected_saved != "-- None --":
    if st.sidebar.button(f"🗑️ Delete '{selected_saved}'", type="secondary"):
        delete_search(selected_saved)
        st.sidebar.success(f"Deleted '{selected_saved}'!")
        st.rerun()

loaded_criteria = saved_searches.get(selected_saved, {}) if selected_saved != "-- None --" else {}

# Saved Alert Notifications Tray
st.sidebar.markdown("---")
saved_alert_bms = load_alert_bookmarks()
with st.sidebar.expander(f"🔖 Bookmarked Alerts ({len(saved_alert_bms)})"):
    if not saved_alert_bms:
        st.caption("No alert notifications bookmarked yet.")
    else:
        for b_title, b_data in list(saved_alert_bms.items()):
            st.markdown(f"**{b_title}**")
            st.caption(f"📅 Saved: {b_data.get('saved_at', '')} | Papers: {len(b_data.get('hits', []))}")
            
            col_view, col_del = st.columns([2, 1])
            with col_view:
                if st.button("View Alert", key=f"view_alert_{b_title}"):
                    st.session_state["active_view_bundle"] = (b_title, b_data["hits"], b_data["terms"])
                    st.rerun()
            with col_del:
                if st.button("Delete", key=f"del_alert_{b_title}", type="secondary"):
                    delete_alert_bookmark(b_title)
                    st.rerun()
            st.divider()


# ==========================================
# 8. SIDEBAR: FILTER CONTROLS & RADAR UI
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filters")

author_col = "Article Authors and Year"
kw_col     = "Main Topics"
sample_col = "Group Studied"
theory_col = "Theory used"
method_col = "Statistical Analysis"
notes_col  = "Findings"
doi_col    = "DOI"

# 1. Main Topics (Keywords)
all_keywords = get_unique_items(df[kw_col]) if kw_col in df.columns else []
default_kw = loaded_criteria.get("keywords", [])
selected_keywords = st.sidebar.multiselect(
    "Main Topics (Keywords)",
    options=all_keywords,
    default=default_kw
)

kw_mode = st.sidebar.radio(
    "Topic Match Logic",
    ["Any (OR)", "All (AND)"],
    index=0 if loaded_criteria.get("kw_mode", "Any (OR)") == "Any (OR)" else 1,
    horizontal=True
)

# 2. Theory Used
all_theories = get_unique_items(df[theory_col]) if theory_col in df.columns else []
default_th = loaded_criteria.get("theories", [])
selected_theories = st.sidebar.multiselect(
    "Theory Used",
    options=all_theories,
    default=default_th
)

# 3. Statistical Analysis
all_methods = get_unique_items(df[method_col]) if method_col in df.columns else []
default_me = loaded_criteria.get("methods", [])
selected_methods = st.sidebar.multiselect(
    "Statistical Analysis",
    options=all_methods,
    default=default_me
)

# 4. Group Studied
all_groups = get_unique_items(df[sample_col]) if sample_col in df.columns else []
default_gp = loaded_criteria.get("groups", [])
selected_groups = st.sidebar.multiselect(
    "Group Studied", options=all_groups, default=default_gp
)

# 5. Free Text Search in Findings
default_search = loaded_criteria.get("notes_query", "")
findings_query = st.sidebar.text_input("Search Findings & Notes", value=default_search)

# Save current search expander
with st.sidebar.expander("💾 Save This Search Configuration"):
    new_search_name = st.text_input("Search Name")
    if st.button("Save Current Filters"):
        if new_search_name.strip():
            save_search(new_search_name.strip(), {
                "keywords": selected_keywords,
                "kw_mode": kw_mode,
                "theories": selected_theories,
                "methods": selected_methods,
                "groups": selected_groups,
                "notes_query": findings_query
            })
            st.success(f"Saved '{new_search_name}'!")
            st.rerun()

# 6. New Paper Radar UI (Sidebar)
st.sidebar.markdown("---")
st.sidebar.subheader("📡 New Paper Radar (Past 1 Year)")
enable_radar = st.sidebar.checkbox("Enable New Paper Alerts", value=True)

if enable_radar:
    radar_sheet_kw = st.sidebar.multiselect(
        "Track sheet keywords:",
        options=all_keywords,
        default=all_keywords[:2] if len(all_keywords) >= 2 else []
    )
    custom_radar_kw = st.sidebar.text_input("Or custom keywords:", placeholder="e.g. adolescent wellbeing")

    active_radar_terms = list(radar_sheet_kw)
    if custom_radar_kw.strip():
        active_radar_terms.extend([k.strip() for k in custom_radar_kw.split(",") if k.strip()])
else:
    active_radar_terms = []


def row_matches_items(cell_value, selected_items, mode="Any (OR)"):
    if not selected_items:
        return True
    
    # Strip parentheses from cell content before comparing
    cleaned_cell = re.sub(r"\(.*?\)", "", str(cell_value)).lower()
    selected_lower = [sel.strip().lower() for sel in selected_items if sel.strip()]

    if mode == "All (AND)":
        return all(sel in cleaned_cell for sel in selected_lower)
    else:
        return any(sel in cleaned_cell for sel in selected_lower)


# ==========================================
# 10. DISPLAY RADAR MODAL & SPREADSHEET RESULTS
# ==========================================
st.title("📚 Literature Review Explorer")

# --- POPUP MODAL FUNCTION ---
@st.dialog("🔔 New Research Radar Alert", width="large")
def show_radar_dialog(hits, terms):
    alert_title = f"Alert: {', '.join(terms)} ({len(hits)} papers)"
    st.subheader(alert_title)
    st.caption("Review new findings below. You can bookmark this entire notification for later or dismiss it to view your library.")

    # Action Bar: Bookmark Whole Notification or Dismiss
    saved_alert_bms = load_alert_bookmarks()
    is_already_bookmarked = alert_title in saved_alert_bms

    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        if is_already_bookmarked:
            st.success("✓ Entire Alert Bookmarked")
        else:
            if st.button("🔖 Bookmark Alert for Later", use_container_width=True):
                save_alert_bookmark(alert_title, hits, terms)
                st.success("Saved to your bookmarks tray!")
                st.rerun()

    with btn_col2:
        if st.button("Dismiss & Open Dashboard", type="primary", use_container_width=True):
            terms_key = "_".join(sorted(terms))
            st.session_state[f"dismissed_{terms_key}"] = True
            if "active_view_bundle" in st.session_state:
                del st.session_state["active_view_bundle"]
            st.rerun()

    st.divider()

    # List the papers in this notification
    for pub in hits:
        st.markdown(f"#### [{pub['title']}]({pub['link']})")
        st.markdown(f"📖 *{pub['journal']}*  \n👤 {pub['author_year']} | 📅 `{pub['date']}` | 🔗 [{pub['doi']}]({pub['link']})")

        topics_str = ", ".join(terms)
        row_paste_text = f"{pub['author_year']}\t{topics_str}\t\t\t\t{pub['title']} ({pub['journal']})\t{pub['doi']}"
        with st.popover("📋 Copy Row for Sheet"):
            st.caption("Copy and paste directly into Google Sheets:")
            st.code(row_paste_text, language="text")

        st.divider()


# --- RADAR TRIGGER LOGIC ---
# Check if user clicked to review a bookmarked alert from the sidebar
if "active_view_bundle" in st.session_state:
    _, b_hits, b_terms = st.session_state["active_view_bundle"]
    show_radar_dialog(b_hits, b_terms)

elif enable_radar and active_radar_terms:
    terms_key = "_".join(sorted(active_radar_terms))
    recent_hits = check_recent_publications(active_radar_terms, max_results=5)

    if recent_hits:
        # Re-open button in sidebar
        if st.sidebar.button(f"🔔 View Radar Alerts ({len(recent_hits)})"):
            st.session_state[f"dismissed_{terms_key}"] = False

        # Automatically open if not dismissed for these terms
        if not st.session_state.get(f"dismissed_{terms_key}", False):
            show_radar_dialog(recent_hits, active_radar_terms)


# --- SPREADSHEET DATABASE RESULTS (ALWAYS VISIBLE UNDERNEATH) ---
st.write(f"Showing **{len(filtered_df)}** of **{len(df)}** studies")

csv_data = filtered_df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Export Results to CSV",
    data=csv_data,
    file_name="filtered_literature.csv",
    mime="text/csv",
    key="download_filtered_csv_btn"
)

st.markdown("---")

if len(filtered_df) == 0:
    st.info("No papers match your selected filter criteria. Try clearing some filters.")
else:
    for idx, row in filtered_df.iterrows():
        author_val = str(row.get(author_col, "")).strip()
        card_title = author_val if author_val else f"Study #{idx + 1}"

        with st.expander(f"📄 **{card_title}**", expanded=True):
            col1, col2 = st.columns([1, 1])

            with col1:
                theory_val = str(row.get(theory_col, "")).strip()
                if theory_val:
                    st.markdown(f"**Theory Used:** {theory_val}")

                method_val = str(row.get(method_col, "")).strip()
                if method_val:
                    st.markdown(f"**Statistical Analysis:** {method_val}")

                sample_val = str(row.get(sample_col, "")).strip()
                if sample_val:
                    st.markdown(f"**Group Studied:** {sample_val}")

            with col2:
                kw_val = str(row.get(kw_col, "")).strip()
                if kw_val:
                    st.markdown(f"**Main Topics:** `{kw_val}`")

                doi_val = str(row.get(doi_col, "")).strip()
                if doi_val:
                    if doi_val.upper() in ["N/A", "NA"]:
                        st.markdown(f"🔗 **DOI:** N/A")
                    else:
                        doi_link = doi_val if doi_val.startswith("http") else f"https://doi.org/{doi_val}"
                        st.markdown(f"🔗 **DOI:** [{doi_val}]({doi_link})")

            notes_val = str(row.get(notes_col, "")).strip()
            if notes_val:
                st.markdown(f"**Findings:**\n> {notes_val}")
