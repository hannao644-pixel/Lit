import streamlit as st
import pandas as pd
import requests
import io
import json
import os

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Literature Review Explorer",
    page_icon="📚",
    layout="wide"
)

# ==========================================
# 2. PASSWORD PROTECTION
# ==========================================
try:
  APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
  APP_PASSWORD = "research2026"


def check_password():
  """Returns True if the user has entered the correct password."""
  # If the user has already successfully authenticated, keep them in
  if st.session_state.get("authenticated", False):
    return True

  # Otherwise, show the login form
  st.title("🔒 Literature Review Database")
  st.write("Please enter the password to access your research library.")

  pwd_input = st.text_input("Password", type="password")

  if st.button("Log In"):
    if pwd_input == APP_PASSWORD:
      st.session_state.authenticated = True
      st.rerun()
    else:
      st.error("Incorrect password. Please try again.")

  return False


# CRITICAL: This line stops the rest of the app from running until logged in!
if not check_password():
  st.stop()

# ==========================================
# 3. DATA LOADING (GOOGLE SHEETS & LOCAL)
# ==========================================
def format_google_sheets_url(url: str) -> str:
    """Converts a standard Google Sheets share link to a direct CSV export link."""
    if "docs.google.com/spreadsheets" in url:
        # Extract the unique Spreadsheet ID from the URL
        parts = url.split("/d/")
        if len(parts) > 1:
            sheet_id = parts[1].split("/")[0]
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    return url


@st.cache_data(ttl=60)  # Caches data for 60 seconds; auto-refreshes on edits
def load_data(source_url: str) -> pd.DataFrame:
    """Reads live data directly from Google Sheets."""
    export_url = format_google_sheets_url(source_url.strip().strip('"'))

    # pandas can read the Google Sheets CSV export directly via URL!
    df = pd.read_csv(export_url)

    # Clean up column headers (strip accidental spaces)
    df.columns = [str(c).strip() for c in df.columns]

    # Fill empty/blank cells so they don't show up as 'NaN'
    df = df.fillna("")
    return df

import re  # Make sure to add this import at the very top of app.py!

# ==========================================
# 4. HELPER: EXTRACT UNIQUE LIST ITEMS
# ==========================================
def get_unique_items(series: pd.Series) -> list:
    """
    Takes a column where cells have items separated by commas or semicolons
    (e.g., 'SEM, Regression' or 'SEM; Regression') and returns a clean, sorted list.
    """
    all_items = set()
    for entry in series.dropna():
        # This splits by either comma OR semicolon: [,;]
        items = re.split(r"[,;]", str(entry))
        for item in items:
            cleaned = item.strip()
            if cleaned:
                all_items.add(cleaned)
    return sorted(list(all_items))


# ==========================================
# 5. SAVED SEARCHES MANAGEMENT
# ==========================================
SAVED_SEARCHES_FILE = "saved_searches.json"


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


# ==========================================
# 6. SIDEBAR: DATA SOURCE & REFRESH
# ==========================================
st.sidebar.title("⚙️ Settings & Sources")

# 1. Safely retrieve the sheet URL from Streamlit Secrets
try:
    secret_url = st.secrets.get("SHEET_URL", "")
except Exception:
    secret_url = ""

# 2. Check if a secret URL exists
if secret_url:
    # If the URL is in secrets, load it automatically without showing the raw link
    sheet_link = secret_url
    st.sidebar.success(" Connected to private research sheet")
else:
    # Fallback: if no secret is set, show a normal text box where you can paste it
    sheet_link = st.sidebar.text_input("Google Sheets Share Link", value="")

# 3. Refresh button to manually clear cache and pull newest edits
if st.sidebar.button(" Force Refresh Sheet"):
    st.cache_data.clear()
    st.rerun()

# 4. Stop gracefully if no link is provided
if not sheet_link.strip():
    st.info(" Please configure `SHEET_URL` in your Streamlit Secrets or paste a link in the sidebar.")
    st.stop()

# 5. Load the data
try:
    df = load_data(sheet_link)
except Exception as e:
    st.error(f"Could not load file from Google Sheets. Error: {e}")
    st.stop()

# ==========================================
# 7. SIDEBAR: SAVED SEARCHES
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ Saved Searches")

saved_searches = load_saved_searches()
selected_saved = st.sidebar.selectbox(
    "Load a preset search:",
    options=["-- None --"] + list(saved_searches.keys())
)

# Preset state handler
loaded_criteria = saved_searches.get(selected_saved, {}) if selected_saved != "-- None --" else {}

# ==========================================
# 8. SIDEBAR: FILTER CONTROLS (CUSTOM HEADERS)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filters")

# Map to your exact column names
author_col = "Article Authors and Year"
kw_col = "Main Topics"  # Your keywords
sample_col = "Group Studied"  # Your sample
theory_col = "Theory used"  # Your theory
method_col = "Statistical Analysis"  # Your statistical methods
notes_col = "Findings"  # Your notes/findings
doi_col = "DOI"

# --- 1. Keywords / Main Topics Filter ---
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

# --- 2. Theory Filter ---
all_theories = get_unique_items(df[theory_col]) if theory_col in df.columns else []
default_th = loaded_criteria.get("theories", [])
selected_theories = st.sidebar.multiselect(
    "Theory Used",
    options=all_theories,
    default=default_th
)

# --- 3. Statistical Analysis Filter ---
all_methods = get_unique_items(df[method_col]) if method_col in df.columns else []
default_me = loaded_criteria.get("methods", [])
selected_methods = st.sidebar.multiselect(
    "Statistical Analysis",
    options=all_methods,
    default=default_me
)

# --- 4. Group Studied (Sample) Filter ---
all_groups = get_unique_items(df[sample_col]) if sample_col in df.columns else []
default_gp = loaded_criteria.get("groups", [])
selected_groups = st.sidebar.multiselect(
    "Group Studied",
    options=all_groups,
    default=default_gp
)

# --- 5. Free Text Search (Findings / Notes) ---
default_search = loaded_criteria.get("notes_query", "")
findings_query = st.sidebar.text_input("Search Findings & Notes", value=default_search)

# --- Save current search button ---
st.sidebar.markdown("---")
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

# ==========================================
# 9. FILTERING ENGINE (PANDAS)
# ==========================================
filtered_df = df.copy()


# Helper function to handle commas, semicolons, and exact phrases
def row_matches_items(cell_value, selected_items, mode="Any (OR)"):
    if not selected_items:
        return True
    cell_items = [i.strip().lower() for i in re.split(r"[,;]", str(cell_value)) if i.strip()]
    selected_lower = [i.lower() for i in selected_items]

    if mode == "All (AND)":
        return all(sel in cell_items for sel in selected_lower)
    else:
        return any(sel in cell_items for sel in selected_lower)


# 1. Main Topics (Keywords) Filter
if selected_keywords and kw_col in df.columns:
    mask = filtered_df[kw_col].apply(lambda x: row_matches_items(x, selected_keywords, kw_mode))
    filtered_df = filtered_df[mask]

# 2. Theory Filter
if selected_theories and theory_col in df.columns:
    mask = filtered_df[theory_col].apply(lambda x: row_matches_items(x, selected_theories, "Any (OR)"))
    filtered_df = filtered_df[mask]

# 3. Statistical Analysis Filter
if selected_methods and method_col in df.columns:
    mask = filtered_df[method_col].apply(lambda x: row_matches_items(x, selected_methods, "Any (OR)"))
    filtered_df = filtered_df[mask]

# 4. Group Studied Filter
if selected_groups and sample_col in df.columns:
    mask = filtered_df[sample_col].apply(lambda x: row_matches_items(x, selected_groups, "Any (OR)"))
    filtered_df = filtered_df[mask]

# 5. Free Text Search in Findings
if findings_query and notes_col in df.columns:
    filtered_df = filtered_df[filtered_df[notes_col].astype(str).str.contains(findings_query, case=False, na=False)]

# ==========================================
# 10. DISPLAY RESULTS
# ==========================================
st.title("📚 Literature Review Explorer")
st.write(f"Showing **{len(filtered_df)}** of **{len(df)}** studies")

# Quick export option
csv_data = filtered_df.to_csv(index=False).encode('utf-8')
st.download_button("📥 Export Results to CSV", data=csv_data, file_name="filtered_literature.csv", mime="text/csv")

st.markdown("---")

# Render each study as an expandable card
for idx, row in filtered_df.iterrows():
    # Primary header for each card
    header_text = row.get(author_col, "").strip() or f"Study #{idx + 1}"

    with st.expander(f"📄 **{header_text}**", expanded=True):
        col1, col2 = st.columns([1, 1])

        with col1:
            if theory_col in row and str(row[theory_col]).strip():
                st.markdown(f"**Theory Used:** {row[theory_col]}")
            if method_col in row and str(row[method_col]).strip():
                st.markdown(f"**Statistical Analysis:** {row[method_col]}")
            if sample_col in row and str(row[sample_col]).strip():
                st.markdown(f"**Group Studied:** {row[sample_col]}")

        with col2:
            if kw_col in row and str(row[kw_col]).strip():
                st.markdown(f"**Main Topics:** `{row[kw_col]}`")
            if doi_col in row and str(row[doi_col]).strip():
                doi_val = str(row[doi_col]).strip()
                doi_link = doi_val if doi_val.startswith("http") else f"https://doi.org/{doi_val}"
                st.markdown(f"🔗 **DOI:** [{doi_val}]({doi_link})")

        if notes_col in row and str(row[notes_col]).strip():
            st.markdown(f"**Findings:**\n> {row[notes_col]}")

# ==========================================
# 9. FILTERING ENGINE (PANDAS)
# ==========================================
filtered_df = df.copy()

# 1. Keyword Filtering
if selected_keywords and kw_col in df.columns:
    if kw_mode == "All (AND)":
        for kw in selected_keywords:
            filtered_df = filtered_df[filtered_df[kw_col].str.contains(rf"\b{kw}\b", case=False, na=False)]
    else:  # Any (OR)
        pattern = "|".join([rf"\b{kw}\b" for kw in selected_keywords])
        filtered_df = filtered_df[filtered_df[kw_col].str.contains(pattern, case=False, na=False)]

# 2. Theory Filtering
if selected_theories and theory_col in df.columns:
    th_pattern = "|".join([rf"\b{th}\b" for th in selected_theories])
    filtered_df = filtered_df[filtered_df[theory_col].str.contains(th_pattern, case=False, na=False)]

# 3. Method Filtering
if selected_methods and method_col in df.columns:
    me_pattern = "|".join([rf"\b{m}\b" for m in selected_methods])
    filtered_df = filtered_df[filtered_df[method_col].str.contains(me_pattern, case=False, na=False)]

# 4. Free text notes search
if notes_query and notes_col in df.columns:
    filtered_df = filtered_df[filtered_df[notes_col].str.contains(notes_query, case=False, na=False)]

# ==========================================
# 10. DISPLAY RESULTS
# ==========================================
st.title("📚 Literature Review Explorer")
st.write(f"Showing **{len(filtered_df)}** of **{len(df)}** studies")

# Quick export option
csv_data = filtered_df.to_csv(index=False).encode('utf-8')
st.download_button("📥 Export Results to CSV", data=csv_data, file_name="filtered_literature.csv", mime="text/csv")

st.markdown("---")

# Render each paper as a clean expandable card
for idx, row in filtered_df.iterrows():
    author_title = row.get(author_col, f"Paper #{idx + 1}")
    with st.expander(f"📄 **{author_title}**", expanded=True):
        col1, col2 = st.columns([1, 1])

        with col1:
            if theory_col in row and row[theory_col]:
                st.markdown(f"**Theory:** {row[theory_col]}")
            if method_col in row and row[method_col]:
                st.markdown(f"**Method:** {row[method_col]}")
            if sample_col in row and row[sample_col]:
                st.markdown(f"**Sample:** {row[sample_col]}")

        with col2:
            if kw_col in row and row[kw_col]:
                st.markdown(f"**Keywords:** `{row[kw_col]}`")
            if doi_col in row and row[doi_col]:
                doi_val = str(row[doi_col]).strip()
                # Format URL if not already full link
                doi_link = doi_val if doi_val.startswith("http") else f"https://doi.org/{doi_val}"
                st.markdown(f"🔗 **DOI:** [{doi_val}]({doi_link})")

        if notes_col in row and row[notes_col]:
            st.markdown(f"**Notes:**\n> {row[notes_col]}")
