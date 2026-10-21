import io
import json
import os
import re
import pandas as pd
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
    df = pd.read_csv(export_url, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ==========================================
# 4. HELPER FUNCTIONS
# ==========================================
def get_unique_items(series: pd.Series) -> list:
    """
    Extracts unique terms separated by commas or semicolons,
    stripping out parentheses and consolidating case duplicates.
    """
    all_items = {}
    for entry in series.dropna():
        cleaned_entry = re.sub(r"\(.*?\)", "", str(entry))
        items = re.split(r"[,;]", cleaned_entry)
        for item in items:
            cleaned = item.strip()
            if cleaned and cleaned.upper() not in ["N/A", "NA"]:
                lower_key = cleaned.lower()
                if lower_key not in all_items:
                    all_items[lower_key] = cleaned
                elif cleaned.isupper() or cleaned.istitle():
                    all_items[lower_key] = cleaned

    return sorted(list(all_items.values()), key=lambda s: s.lower())


# ==========================================
# 5. PERSISTENT SAVED SEARCHES SYSTEM
# ==========================================
SAVED_SEARCHES_FILE = "saved_searches.json"

def get_base_saved_searches() -> dict:
    """Loads searches from st.secrets if configured, or local file fallback."""
    searches = {}
    
    # 1. First check st.secrets (permanent on Streamlit Cloud)
    if "saved_searches" in st.secrets:
        try:
            searches.update(dict(st.secrets["saved_searches"]))
        except Exception:
            pass

    # 2. Check local file if it exists
    if os.path.exists(SAVED_SEARCHES_FILE):
        try:
            with open(SAVED_SEARCHES_FILE, "r") as f:
                searches.update(json.load(f))
        except Exception:
            pass

    return searches

# Initialize saved searches in session state
if "saved_searches" not in st.session_state:
    st.session_state.saved_searches = get_base_saved_searches()

def save_search(name: str, criteria: dict):
    st.session_state.saved_searches[name] = criteria
    try:
        with open(SAVED_SEARCHES_FILE, "w") as f:
            json.dump(st.session_state.saved_searches, f, indent=2)
    except Exception:
        pass

def delete_search(name: str):
    if name in st.session_state.saved_searches:
        del st.session_state.saved_searches[name]
        try:
            with open(SAVED_SEARCHES_FILE, "w") as f:
                json.dump(st.session_state.saved_searches, f, indent=2)
        except Exception:
            pass


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
# 7. SIDEBAR: SAVED SEARCHES (PERSISTENT)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ Saved Searches")

search_options = ["-- None --"] + list(st.session_state.saved_searches.keys())
selected_saved = st.sidebar.selectbox("Load a preset search:", options=search_options)

if selected_saved != "-- None --":
    if st.sidebar.button(f"🗑️ Delete '{selected_saved}'", type="secondary"):
        delete_search(selected_saved)
        st.sidebar.success(f"Deleted '{selected_saved}'!")
        st.rerun()

loaded_criteria = st.session_state.saved_searches.get(selected_saved, {}) if selected_saved != "-- None --" else {}

# Backup / Restore Utility (Protects searches across server reboots)
with st.sidebar.expander("📦 Backup / Restore Searches"):
    st.caption("Since Streamlit Cloud containers reset on logout, you can download or upload your search profiles here:")
    searches_json_str = json.dumps(st.session_state.saved_searches, indent=2)
    st.download_button(
        label="💾 Download Searches Backup",
        data=searches_json_str,
        file_name="saved_searches.json",
        mime="application/json",
        use_container_width=True
    )

    uploaded_searches = st.file_uploader("Upload searches backup (.json)", type=["json"])
    if uploaded_searches is not None:
        try:
            restored = json.load(uploaded_searches)
            if isinstance(restored, dict):
                st.session_state.saved_searches.update(restored)
                st.success("Searches restored!")
                st.rerun()
        except Exception as err:
            st.error(f"Invalid file: {err}")


# ==========================================
# 8. SIDEBAR: FILTER CONTROLS
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
    "Group Studied",
    options=all_groups,
    default=default_gp
)

# 5. Free Text Search in Findings
default_search = loaded_criteria.get("notes_query", "")
findings_query = st.sidebar.text_input("Search Findings & Notes", value=default_search)

# Save current search expander
with st.sidebar.expander("💾 Save Current Filter Set"):
    new_search_name = st.text_input("Search Name")
    if st.button("Save Filter Preset"):
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


# ==========================================
# 9. FILTERING ENGINE (PANDAS)
# ==========================================
filtered_df = df.copy()

def row_matches_items(cell_value, selected_items, mode="Any (OR)"):
    """
    Checks if a row matches the selected items, fully case-insensitive,
    stripping parentheses and their contents from the cell text.
    """
    if not selected_items:
        return True

    cleaned_cell = re.sub(r"\(.*?\)", "", str(cell_value)).lower()
    selected_lower = [sel.strip().lower() for sel in selected_items if sel.strip()]

    if mode == "All (AND)":
        return all(sel in cleaned_cell for sel in selected_lower)
    else:
        return any(sel in cleaned_cell for sel in selected_lower)

if selected_keywords and kw_col in df.columns:
    mask = filtered_df[kw_col].apply(lambda x: row_matches_items(x, selected_keywords, kw_mode))
    filtered_df = filtered_df[mask]

if selected_theories and theory_col in df.columns:
    mask = filtered_df[theory_col].apply(lambda x: row_matches_items(x, selected_theories, "Any (OR)"))
    filtered_df = filtered_df[mask]

if selected_methods and method_col in df.columns:
    mask = filtered_df[method_col].apply(lambda x: row_matches_items(x, selected_methods, "Any (OR)"))
    filtered_df = filtered_df[mask]

if selected_groups and sample_col in df.columns:
    mask = filtered_df[sample_col].apply(lambda x: row_matches_items(x, selected_groups, "Any (OR)"))
    filtered_df = filtered_df[mask]

if findings_query and notes_col in df.columns:
    filtered_df = filtered_df[
        filtered_df[notes_col]
        .astype(str)
        .str.contains(findings_query, case=False, na=False)
    ]


# ==========================================
# 10. DISPLAY SPREADSHEET RESULTS
# ==========================================
st.title("📚 Literature Review Explorer")

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
                        st.markdown("🔗 **DOI:** N/A")
                    else:
                        doi_link = doi_val if doi_val.startswith("http") else f"https://doi.org/{doi_val}"
                        st.markdown(f"🔗 **DOI:** [{doi_val}]({doi_link})")

            notes_val = str(row.get(notes_col, "")).strip()
            if notes_val:
                st.markdown(f"**Findings:**\n> {notes_val}")
