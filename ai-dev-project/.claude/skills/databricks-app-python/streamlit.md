# Streamlit Framework Implementation Guide

Complete guide for building Databricks applications with Streamlit framework.

## Table of Contents

- [When to Use Streamlit](#when-to-use-streamlit)
- [Core Architecture](#core-architecture)
- [Essential Patterns](#essential-patterns)
- [Best Practices](#best-practices)
- [Component Guide](#component-guide)
- [Common Pitfalls](#common-pitfalls)
- [Performance Optimization](#performance-optimization)

---

## When to Use Streamlit

**Choose Streamlit when you need:**
- Rapid prototyping and development
- Data science and ML-focused applications
- Simple, script-like development workflow
- Built-in widgets and forms
- Interactive data exploration tools
- ML model demos and POCs

**Key Strengths:**
- ✅ Fastest development time (script-based)
- ✅ Excellent for data scientists (Pythonic)
- ✅ Built-in state management
- ✅ Automatic reactivity (reruns on interaction)
- ✅ Great for notebooks-to-apps workflow

**Limitations:**
- ❌ Less control over layout (compared to Dash)
- ❌ Full page reruns can be slower
- ❌ Harder to build complex multi-page apps
- ❌ Limited styling customization

---

## Core Architecture

### Application Structure

```python
"""
Streamlit App Structure
"""
import streamlit as st
from databricks.sdk.core import Config
from databricks import sql

# 1. Page configuration (MUST be first Streamlit command)
st.set_page_config(
    page_title="My App",
    page_icon="📊",
    layout="wide",  # or "centered"
    initial_sidebar_state="expanded"  # or "collapsed"
)

# 2. Backend initialization with caching
@st.cache_resource
def get_backend():
    """Initialize and cache backend connection"""
    # Your backend initialization
    return backend

# 3. Initialize backend
backend = get_backend()

# 4. Sidebar navigation
page = st.sidebar.radio("Navigation", ["Page 1", "Page 2"])

# 5. Page content
if page == "Page 1":
    # Page 1 content
    pass
elif page == "Page 2":
    # Page 2 content
    pass
```

### File Organization

```
streamlit-app/
├── streamlit_app.py          # Main application entry point
├── models.py                  # Pydantic data models
├── backend_mock.py            # Mock backend with sample data
├── backend_real.py            # Real Databricks backend
├── setup_database.py          # Database initialization
├── requirements.txt           # Python dependencies
├── app.yaml                   # Databricks Apps configuration
├── .env                       # Environment variables
└── README.md                  # Documentation
```

---

## Essential Patterns

### 1. Connection Caching (Critical)

**Always use `@st.cache_resource` for database connections:**

```python
from databricks.sdk.core import Config
from databricks import sql

@st.cache_resource(ttl=300, show_spinner=True)
def get_sql_connection(http_path: str):
    """
    Create and cache SQL warehouse connection

    Args:
        ttl: Time-to-live in seconds (5 minutes default)
        show_spinner: Show loading indicator during initialization
    """
    cfg = Config()  # Reads DATABRICKS_HOST automatically

    return sql.connect(
        server_hostname=cfg.host,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate
    )

# Usage
conn = get_sql_connection("/sql/1.0/warehouses/xxxxx")
```

**Why `@st.cache_resource`?**
- Persists across sessions and reruns
- Prevents connection exhaustion
- Improves performance dramatically
- Required for production apps

### 2. Backend Toggle Pattern

```python
import os

@st.cache_resource
def get_backend():
    """Initialize backend based on environment"""
    use_mock = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"

    if use_mock:
        from backend_mock import MockBackend
        return MockBackend()
    else:
        from backend_real import RealBackend
        catalog = os.getenv("DATABRICKS_CATALOG", "main")
        schema = os.getenv("DATABRICKS_SCHEMA", "app_schema")
        return RealBackend(catalog=catalog, schema=schema)
```

### 3. Session State Management

**Use `st.session_state` to persist data across reruns:**

```python
# Initialize state
if 'order_id' not in st.session_state:
    st.session_state.order_id = None

# Set state
if st.button("Load Order"):
    st.session_state.order_id = "ORD-001"

# Read state
if st.session_state.order_id:
    st.write(f"Current order: {st.session_state.order_id}")
```

**Common State Patterns:**

```python
# Form data
if 'form_data' not in st.session_state:
    st.session_state.form_data = {}

# Page navigation
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Dashboard"

# Filter persistence
if 'filters' not in st.session_state:
    st.session_state.filters = {
        'status': [],
        'date_from': None,
        'date_to': None
    }
```

### 4. Data Display Patterns

**DataFrames (Read-only):**

```python
import pandas as pd

df = backend.get_orders()
st.dataframe(
    df,
    use_container_width=True,  # Expand to container width
    hide_index=True,            # Hide row numbers
    column_config={
        "amount": st.column_config.NumberColumn(
            "Amount",
            format="$%.2f"
        ),
        "status": st.column_config.SelectColumn(
            "Status",
            options=["pending", "confirmed", "shipped"]
        )
    }
)
```

**Data Editor (Editable):**

```python
# For editable tables
edited_df = st.data_editor(
    df,
    num_rows="dynamic",         # Allow add/delete rows
    hide_index=True,
    column_config={
        "amount": st.column_config.NumberColumn(
            "Amount",
            min_value=0,
            max_value=10000,
            step=0.01,
            format="$%.2f"
        )
    }
)

# Detect changes
if st.button("Save Changes"):
    # Compare original vs edited
    df_diff = pd.concat([df, edited_df]).drop_duplicates(keep=False)
    if not df_diff.empty:
        backend.update_data(edited_df)
        st.success("Changes saved!")
```

### 5. Sidebar Navigation

```python
# Sidebar navigation pattern
st.sidebar.title("📊 My App")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Orders", "Customers", "Products"],
    label_visibility="collapsed"  # Hide "Navigation" label
)

# Filters in sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### Filters")

status_filter = st.sidebar.multiselect(
    "Status",
    options=["pending", "confirmed", "shipped"],
    default=None
)

date_range = st.sidebar.date_input(
    "Date Range",
    value=None
)
```

### 6. Metrics Display

```python
# Four-column metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Total Orders",
        value="1,234",
        delta="12%",           # Optional change indicator
        delta_color="normal"   # "normal", "inverse", or "off"
    )

with col2:
    st.metric(
        label="Revenue",
        value="$45,678",
        delta="-8%",
        delta_color="inverse"  # Red for negative when inverse
    )
```

### 7. Charts Integration

**Plotly Charts (Recommended):**

```python
import plotly.express as px
import plotly.graph_objects as go

# Pie chart
fig = px.pie(
    df,
    values='count',
    names='status',
    color='status',
    color_discrete_map={'pending': '#FFA500', 'confirmed': '#2CA02C'}
)
st.plotly_chart(fig, use_container_width=True)

# Bar chart
fig = px.bar(
    df,
    x='month',
    y='revenue',
    color='category'
)
fig.update_layout(showlegend=False)
st.plotly_chart(fig, use_container_width=True)
```

**Native Streamlit Charts:**

```python
# For simple charts (less customizable but faster)
st.line_chart(df[['date', 'revenue']])
st.bar_chart(df[['category', 'count']])
st.area_chart(df[['date', 'cumulative_revenue']])
```

### 8. Forms and Inputs

**Form Pattern (Prevents reruns on every input change):**

```python
with st.form("order_form"):
    st.write("Create New Order")

    customer = st.text_input("Customer Name")
    product = st.selectbox("Product", ["Product A", "Product B"])
    quantity = st.number_input("Quantity", min_value=1, value=1)
    notes = st.text_area("Notes")

    # Form is only submitted when button is clicked
    submitted = st.form_submit_button("Create Order")

    if submitted:
        # Process form data
        backend.create_order(customer, product, quantity, notes)
        st.success("Order created!")
```

**Without Forms (Immediate reactivity):**

```python
# These trigger reruns on every change
name = st.text_input("Name")
age = st.slider("Age", 0, 100)

if st.button("Submit"):
    # Only runs when button clicked
    st.write(f"{name} is {age} years old")
```

---

## Best Practices

### Page Configuration

**✅ ALWAYS set page config first:**

```python
# MUST be the first Streamlit command
st.set_page_config(
    page_title="Order Management",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)
```

**❌ Common mistake:**

```python
import streamlit as st

st.title("My App")  # ❌ Error: set_page_config must be first
st.set_page_config(...)  # ❌ Too late!
```

### State Management

**✅ Initialize state at the top:**

```python
# Initialize all state variables together
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'filters' not in st.session_state:
    st.session_state.filters = {}
```

**❌ Don't initialize in conditionals:**

```python
# ❌ Bad: state only initialized if condition is true
if some_condition:
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
```

### Caching

**✅ Cache expensive operations:**

```python
@st.cache_resource  # For connections, models
def get_connection():
    return create_connection()

@st.cache_data(ttl=60)  # For data, with TTL
def load_data():
    return fetch_data()
```

**When to use which:**
- `@st.cache_resource`: Connections, ML models, non-serializable objects
- `@st.cache_data`: DataFrames, lists, dicts, serializable data

### Layout Organization

**✅ Use columns for horizontal layout:**

```python
col1, col2, col3 = st.columns([2, 1, 1])  # Ratios: 2:1:1

with col1:
    st.write("Main content")

with col2:
    st.write("Sidebar content")
```

**✅ Use expanders for collapsible sections:**

```python
with st.expander("Advanced Filters"):
    filter1 = st.selectbox("Filter 1", options)
    filter2 = st.multiselect("Filter 2", options)
```

**✅ Use tabs for switching content:**

```python
tab1, tab2, tab3 = st.tabs(["Tab 1", "Tab 2", "Tab 3"])

with tab1:
    st.write("Tab 1 content")

with tab2:
    st.write("Tab 2 content")
```

### Error Handling

**✅ Graceful error handling:**

```python
try:
    data = backend.get_data()
    st.dataframe(data)
except Exception as e:
    st.error(f"Error loading data: {str(e)}")
    st.info("Please check your connection and try again")
```

**✅ Input validation:**

```python
user_input = st.text_input("Enter warehouse ID")

if user_input:
    if not user_input.startswith("/sql/"):
        st.warning("Warehouse path should start with /sql/")
    else:
        # Process input
        pass
```

---

## Component Guide

### Core Components

| Component | Use Case | Example |
|-----------|----------|---------|
| `st.title()` | Page titles | `st.title("Dashboard")` |
| `st.header()` | Section headers | `st.header("Overview")` |
| `st.subheader()` | Subsection headers | `st.subheader("Metrics")` |
| `st.text()` | Plain text | `st.text("Simple text")` |
| `st.markdown()` | Formatted text | `st.markdown("**Bold** text")` |
| `st.write()` | Auto-formatted | `st.write("Text", df, chart)` |

### Input Widgets

| Widget | Use Case | Example |
|--------|----------|---------|
| `st.button()` | Actions | `if st.button("Submit"):` |
| `st.text_input()` | Single-line text | `name = st.text_input("Name")` |
| `st.text_area()` | Multi-line text | `notes = st.text_area("Notes")` |
| `st.number_input()` | Numbers | `age = st.number_input("Age", 0, 100)` |
| `st.selectbox()` | Single selection | `choice = st.selectbox("Pick", options)` |
| `st.multiselect()` | Multiple selection | `choices = st.multiselect("Pick", options)` |
| `st.slider()` | Range selection | `value = st.slider("Value", 0, 100)` |
| `st.date_input()` | Date picker | `date = st.date_input("Date")` |
| `st.checkbox()` | Boolean toggle | `if st.checkbox("Agree"):` |
| `st.radio()` | Single choice | `choice = st.radio("Pick", options)` |

### Display Components

| Component | Use Case | Example |
|-----------|----------|---------|
| `st.dataframe()` | Read-only tables | `st.dataframe(df)` |
| `st.data_editor()` | Editable tables | `edited = st.data_editor(df)` |
| `st.metric()` | KPI displays | `st.metric("Sales", "$1M", "+10%")` |
| `st.json()` | JSON display | `st.json({"key": "value"})` |
| `st.code()` | Code blocks | `st.code("print('hello')")` |

### Layout Components

| Component | Use Case | Example |
|-----------|----------|---------|
| `st.columns()` | Side-by-side | `col1, col2 = st.columns(2)` |
| `st.expander()` | Collapsible | `with st.expander("Details"):` |
| `st.tabs()` | Tabbed interface | `tab1, tab2 = st.tabs(["A", "B"])` |
| `st.container()` | Grouping | `with st.container():` |
| `st.empty()` | Placeholder | `placeholder = st.empty()` |

### Status Components

| Component | Use Case | Example |
|-----------|----------|---------|
| `st.success()` | Success message | `st.success("Saved!")` |
| `st.error()` | Error message | `st.error("Failed!")` |
| `st.warning()` | Warning message | `st.warning("Caution!")` |
| `st.info()` | Info message | `st.info("Note: ...")` |
| `st.spinner()` | Loading indicator | `with st.spinner("Loading..."):` |
| `st.progress()` | Progress bar | `st.progress(0.5)` |

---

## Common Pitfalls

### 1. Page Config Not First

**❌ Wrong:**
```python
import streamlit as st
st.title("My App")
st.set_page_config(...)  # Error!
```

**✅ Correct:**
```python
import streamlit as st
st.set_page_config(...)  # Must be first!
st.title("My App")
```

### 2. Not Caching Connections

**❌ Wrong:**
```python
def get_data():
    conn = sql.connect(...)  # Creates new connection every rerun!
    return conn.cursor().fetchall()
```

**✅ Correct:**
```python
@st.cache_resource
def get_connection():
    return sql.connect(...)

def get_data():
    conn = get_connection()  # Reuses cached connection
    return conn.cursor().fetchall()
```

### 3. Expensive Operations in Main Flow

**❌ Wrong:**
```python
# Runs on every rerun!
data = expensive_api_call()
processed_data = expensive_processing(data)
```

**✅ Correct:**
```python
@st.cache_data(ttl=300)
def get_processed_data():
    data = expensive_api_call()
    return expensive_processing(data)

data = get_processed_data()  # Cached for 5 minutes
```

### 4. Not Using Forms for Multiple Inputs

**❌ Wrong:**
```python
# Page reruns on EVERY input change
name = st.text_input("Name")  # Rerun
email = st.text_input("Email")  # Rerun
phone = st.text_input("Phone")  # Rerun
```

**✅ Correct:**
```python
# Page only reruns on submit
with st.form("user_form"):
    name = st.text_input("Name")
    email = st.text_input("Email")
    phone = st.text_input("Phone")
    submitted = st.form_submit_button("Submit")
```

### 5. Modifying State During Render

**❌ Wrong:**
```python
if st.button("Increment"):
    st.session_state.count += 1  # ❌ Can cause issues
    st.write(st.session_state.count)  # May not update immediately
```

**✅ Correct:**
```python
if 'count' not in st.session_state:
    st.session_state.count = 0

if st.button("Increment"):
    st.session_state.count += 1

st.write(f"Count: {st.session_state.count}")  # Display outside callback
```

---

## Performance Optimization

### 1. Use Appropriate Caching

```python
# For connections (persist across sessions)
@st.cache_resource
def get_db_connection():
    return sql.connect(...)

# For data (serialize and cache with TTL)
@st.cache_data(ttl=600)
def load_orders():
    return fetch_orders()
```

### 2. Lazy Loading

```python
# Don't load all data upfront
def load_page():
    if page == "Dashboard":
        load_dashboard_data()  # Only load what's needed
    elif page == "Orders":
        load_orders_data()
```

### 3. Pagination

```python
# Don't display 10,000 rows at once
page_size = 50
page_num = st.number_input("Page", min_value=1, value=1)

start_idx = (page_num - 1) * page_size
end_idx = start_idx + page_size

st.dataframe(df[start_idx:end_idx])
```

### 4. Debouncing with Forms

```python
# Use forms to prevent reruns on every keystroke
with st.form("search_form"):
    search = st.text_input("Search")
    submitted = st.form_submit_button("Search")

if submitted and search:
    results = backend.search(search)
    st.dataframe(results)
```

### 5. Fragment Updates (Streamlit 1.24+)

```python
@st.experimental_fragment
def render_chart():
    """Only this fragment reruns, not entire page"""
    data = load_chart_data()
    st.plotly_chart(create_chart(data))

# Main page doesn't rerun when fragment updates
st.title("Dashboard")
render_chart()
```

---

## Deployment Configuration

### app.yaml for Databricks

```yaml
command:
  - "streamlit"
  - "run"
  - "streamlit_app.py"
  - "--server.port"
  - "8080"
  - "--server.address"
  - "0.0.0.0"
  - "--server.headless"
  - "true"

env:
  - name: USE_MOCK_BACKEND
    value: "false"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "your-warehouse-id"
  - name: DATABRICKS_CATALOG
    value: "main"
  - name: DATABRICKS_SCHEMA
    value: "app_schema"
```

### requirements.txt

```txt
streamlit>=1.28.0
pandas>=2.0.0
plotly>=5.17.0
databricks-sdk>=0.12.0
databricks-sql-connector>=3.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

---

## Reference Resources

- **[Databricks Streamlit Tutorial](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/tutorial-streamlit)** - Official tutorial
- **[Databricks Apps Cookbook - Streamlit](https://apps-cookbook.dev/docs/category/streamlit/)** - Code examples
- **[Streamlit Read Delta Table](https://apps-cookbook.dev/docs/streamlit/tables/tables_read/)** - Connection patterns
- **[Streamlit Documentation](https://docs.streamlit.io/)** - Full API reference

---

## Key Takeaways

1. **Always cache resources** - Use `@st.cache_resource` for connections
2. **Page config first** - Must be the first Streamlit command
3. **Use forms** - Prevent reruns for multiple inputs
4. **Session state** - For data persistence across reruns
5. **SDK Config pattern** - For Databricks authentication
6. **Layout wisely** - Columns, expanders, tabs for organization
7. **Handle errors** - Graceful degradation and user feedback

Streamlit is perfect for rapid development of data-focused applications on Databricks!
