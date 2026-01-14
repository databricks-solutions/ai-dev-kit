# Dash Framework Guide

Complete guide for building Databricks applications with Plotly Dash framework.

## When to Use Dash

**Best for**:
- Interactive dashboards with rich charts
- Business intelligence applications
- Data visualization heavy apps
- Multi-page applications
- Apps requiring custom styling with Bootstrap

**Alternatives**:
- Streamlit - Simpler syntax, faster prototyping
- APX - Full-stack with React frontend

## Dependencies

```txt
dash>=2.14.0
dash-bootstrap-components>=1.5.0
plotly>=5.18.0
pandas>=2.0.0
databricks-sdk>=0.35.0
databricks-sql-connector>=3.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

## Project Structure

```
dash-app/
├── models.py              # Pydantic data models
├── backend_mock.py        # Mock backend with sample data
├── backend_real.py        # Databricks SQL backend
├── dash_app.py            # Main Dash application
├── setup_database.py      # Database initialization
├── requirements.txt       # Dependencies
├── .env.example          # Environment template
├── run_app.sh            # Quick start script
└── README.md             # Documentation
```

## Dash Application Structure

### Basic Setup

```python
import os
import dash
from dash import dcc, html, dash_table, Input, Output, State, callback
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd

from backend_mock import MockBackend
from models import Status

# Initialize backend
USE_MOCK = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"
backend = MockBackend() if USE_MOCK else RealBackend()

# Initialize Dash app with Bootstrap theme
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    suppress_callback_exceptions=True,
    title="Application Name"
)

# Define color scheme
COLORS = {
    "primary": "#1F77B4",
    "success": "#2CA02C",
    "warning": "#FF7F0E",
    "danger": "#D62728",
    "info": "#17A2B8",
    "light": "#F8F9FA",
    "dark": "#343A40",
}

# Status color mappings
STATUS_COLORS = {
    Status.ACTIVE: COLORS["success"],
    Status.PENDING: COLORS["warning"],
    Status.FAILED: COLORS["danger"],
}

# Bootstrap badge colors (for dbc.Badge)
STATUS_BADGE_COLORS = {
    Status.ACTIVE: "success",
    Status.PENDING: "warning",
    Status.FAILED: "danger",
}
```

### Navigation Bar

```python
def create_navbar():
    """Create navigation bar"""
    return dbc.Navbar(
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.I(className="fas fa-chart-line me-2"),
                    dbc.NavbarBrand("Application Name", className="ms-2"),
                ], width="auto"),
            ], align="center", className="g-0"),
            dbc.Nav([
                dbc.NavItem(dbc.NavLink("Dashboard", href="/", active="exact")),
                dbc.NavItem(dbc.NavLink("Orders", href="/orders", active="exact")),
                dbc.NavItem(dbc.NavLink("Customers", href="/customers", active="exact")),
            ], navbar=True, className="ms-auto"),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-4"
    )
```

### Main Layout with Routing

```python
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    create_navbar(),
    html.Div(id='page-content', style={'minHeight': '80vh'}),
    dcc.Store(id='selected-item-id'),  # Client-side data storage
], style={'backgroundColor': COLORS["light"], 'minHeight': '100vh'})

@callback(
    Output('page-content', 'children'),
    Input('url', 'pathname')
)
def display_page(pathname):
    """Route to different pages"""
    if pathname == '/orders':
        return create_orders_layout()
    elif pathname == '/customers':
        return create_customers_layout()
    else:
        return create_dashboard_layout()
```

## Component Patterns

### Statistics Card

```python
def create_stat_card(title, value, icon, color="primary", subtitle=None):
    """Create a statistics card"""
    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.Div([
                    html.H6(title, className="text-muted mb-2"),
                    html.H3(value, className="mb-0"),
                    html.Small(subtitle, className="text-muted") if subtitle else None,
                ], className="flex-grow-1"),
                html.Div([
                    html.I(className=f"fas {icon} fa-2x text-{color}")
                ], className="ms-3"),
            ], className="d-flex align-items-center"),
        ]),
    ], className="shadow-sm mb-3")

# Usage
dbc.Row([
    dbc.Col(create_stat_card(
        "Total Orders",
        f"{stats['total_orders']:,}",
        "fa-shopping-cart",
        "primary"
    ), md=3),
    dbc.Col(create_stat_card(
        "Total Revenue",
        f"${stats['total_revenue']:,.2f}",
        "fa-dollar-sign",
        "success"
    ), md=3),
])
```

### Interactive Data Table

```python
def create_data_table(data, table_id, selectable=False):
    """Create interactive data table"""
    if not data:
        return html.Div("No data available.", className="text-muted")

    return dash_table.DataTable(
        id=table_id,
        data=data,
        columns=[{"name": col, "id": col} for col in data[0].keys()],
        page_size=20,
        style_table={'overflowX': 'auto'},
        style_cell={
            'textAlign': 'left',
            'padding': '12px',
            'fontFamily': 'Arial, sans-serif'
        },
        style_header={
            'backgroundColor': COLORS["dark"],
            'color': 'white',
            'fontWeight': 'bold'
        },
        style_data_conditional=[
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': COLORS["light"]
            }
        ],
        filter_action="native",
        sort_action="native",
        row_selectable='single' if selectable else False,
    )
```

### Plotly Charts

```python
# Pie Chart
@callback(
    Output('status-pie-chart', 'figure'),
    Input('url', 'pathname')
)
def update_pie_chart(pathname):
    """Create pie chart for status distribution"""
    stats = backend.get_statistics()
    status_data = stats['status_distribution']

    fig = px.pie(
        values=list(status_data.values()),
        names=[s.title() for s in status_data.keys()],
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig.update_layout(
        margin=dict(t=20, b=20, l=20, r=20),
        showlegend=True,
        height=300
    )
    return fig

# Bar Chart
@callback(
    Output('revenue-bar-chart', 'figure'),
    Input('url', 'pathname')
)
def update_bar_chart(pathname):
    """Create bar chart for revenue by category"""
    data = backend.get_revenue_by_category()

    # Create color map with error handling
    color_map = {}
    for category in data.keys():
        color_map[category] = COLORS.get(category.lower(), COLORS["primary"])

    fig = px.bar(
        x=list(data.keys()),
        y=list(data.values()),
        labels={'x': 'Category', 'y': 'Revenue ($)'},
        color=list(data.keys()),
        color_discrete_map=color_map
    )
    fig.update_layout(
        margin=dict(t=20, b=40, l=40, r=20),
        showlegend=False,
        height=300,
        xaxis_title="",
        yaxis_title="Revenue ($)"
    )
    fig.update_xaxes(tickangle=-45)  # Note: update_xaxes, not update_xaxis
    return fig
```


## Callback Patterns

### Basic Callback

```python
@callback(
    Output('output-div', 'children'),
    Input('input-button', 'n_clicks')
)
def update_output(n_clicks):
    """Basic callback pattern"""
    if n_clicks is None:
        return "Click the button"
    return f"Button clicked {n_clicks} times"
```

### Multiple Inputs

```python
@callback(
    Output('filtered-table', 'children'),
    [Input('filter-status', 'value'),
     Input('filter-date', 'value'),
     Input('refresh-button', 'n_clicks')]
)
def update_table(status, date, n_clicks):
    """Callback with multiple inputs"""
    filter_criteria = {
        "status": Status(status) if status else None,
        "date": date
    }
    data = backend.get_data(filter_criteria)
    return create_data_table(data, "result-table")
```

### Using State (Non-Triggering Inputs)

```python
@callback(
    Output('result', 'children'),
    Input('submit-button', 'n_clicks'),
    [State('input-field', 'value'),
     State('dropdown', 'value')]
)
def process_form(n_clicks, input_value, dropdown_value):
    """State doesn't trigger callback, only provides values"""
    if n_clicks is None:
        return ""
    return f"Processing: {input_value}, {dropdown_value}"
```

### Callback Context

```python
@callback(
    Output('result', 'children'),
    [Input('button1', 'n_clicks'),
     Input('button2', 'n_clicks')]
)
def handle_multiple_buttons(n1, n2):
    """Determine which input triggered the callback"""
    ctx = dash.callback_context

    if not ctx.triggered:
        return "No button clicked"

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == 'button1':
        return "Button 1 clicked"
    elif trigger_id == 'button2':
        return "Button 2 clicked"

    return "Unknown trigger"
```

## Complete Page Example

```python
def create_orders_layout():
    """Complete orders page with table, filters, and modal"""
    return dbc.Container([
        html.H2("Orders", className="mb-4"),

        # Filters
        create_filters(),

        # Data Table
        dbc.Card([
            dbc.CardHeader(html.H5([
                html.I(className="fas fa-table me-2"),
                "Order List"
            ])),
            dbc.CardBody([
                html.Div(id="orders-table")
            ]),
        ], className="shadow-sm mb-4"),

        # Detail Modal
        create_detail_modal(),
    ], fluid=True)

@callback(
    Output('orders-table', 'children'),
    [Input('filter-status', 'value'),
     Input('refresh-button', 'n_clicks')]
)
def update_orders_table(status, n_clicks):
    """Update orders table with filters"""
    filter_criteria = {"status": Status(status) if status else None}
    orders = backend.get_orders(filter_criteria)

    if not orders:
        return html.Div("No orders found.", className="text-muted")

    order_data = [
        {
            "Order ID": o.order_id,
            "Customer": o.customer_name,
            "Date": o.order_date.strftime("%Y-%m-%d %H:%M"),
            "Status": o.status.value.title(),
            "Total": f"${float(o.total):.2f}",
        }
        for o in orders
    ]

    return create_data_table(order_data, "orders-data-table", selectable=True)
```

## Best Practices

### Performance
1. **Use `dcc.Store`** for client-side caching
2. **Implement pagination** for large datasets
3. **Use `prevent_initial_call=True`** for expensive operations
4. **Minimize callback dependencies**
5. **Cache backend queries** when appropriate


### Consistent Styling
```python
# Define color constants at top of file
COLORS = {...}
STATUS_COLORS = {...}
STATUS_BADGE_COLORS = {...}

# Use consistently throughout app
dbc.Badge(status, color=STATUS_BADGE_COLORS[status])
```

## Common Pitfalls

### ❌ Wrong: Missing ID on dynamically created component
```python
def update_table():
    return dash_table.DataTable(
        # Missing id!
        data=data,
        columns=columns
    )
```

### ✅ Correct: Always provide ID
```python
def update_table():
    return dash_table.DataTable(
        id='dynamic-table',  # Always include id
        data=data,
        columns=columns
    )
```

### ❌ Wrong: Accessing data before checking if exists
```python
@callback(...)
def toggle_modal(selected_rows, table_data, is_open):
    item_id = table_data[selected_rows[0]]["id"]  # May fail!
```

### ✅ Correct: Check before accessing
```python
@callback(..., prevent_initial_call=True)
def toggle_modal(selected_rows, table_data, is_open):
    if not selected_rows or not table_data:
        return False, "", ""
    item_id = table_data[selected_rows[0]]["id"]  # Safe
```

### ❌ Wrong: Using hex colors for Bootstrap badges
```python
dbc.Badge(status, color="#2CA02C")  # Won't work!
```

### ✅ Correct: Use Bootstrap color names
```python
dbc.Badge(status, color="success")  # Correct
```

### ❌ Wrong: Plotly method typo
```python
fig.update_xaxis(tickangle=-45)  # AttributeError!
```

### ✅ Correct: Use plural form
```python
fig.update_xaxes(tickangle=-45)  # Correct
```

## Running the App

### Development Mode
```bash
# With uv
USE_MOCK_BACKEND=true DEBUG=true DATABRICKS_APP_PORT=8080 uv run python dash_app.py

# With python directly
USE_MOCK_BACKEND=true DEBUG=true python dash_app.py
```

### Production Mode
```python
if __name__ == '__main__':
    port = int(os.getenv("DATABRICKS_APP_PORT", "8080"))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    app.run(host='0.0.0.0', port=port, debug=debug)
```

## Deployment to Databricks

### app.yaml
```yaml
command:
  - "python"
  - "dash_app.py"

env:
  - name: USE_MOCK_BACKEND
    value: "false"
  - name: DATABRICKS_CONFIG_PROFILE
    value: ""
  - name: DATABRICKS_APP_PORT
    value: "8080"
```

### Deploy Commands
```bash
databricks apps deploy
databricks apps list
databricks apps logs <app-name>
```


## Additional Resources

- **Plotly Dash Docs**: https://dash.plotly.com/
- **Dash Bootstrap Components**: https://dash-bootstrap-components.opensource.faculty.ai/
- **Plotly Charts**: https://plotly.com/python/
- **Example App Snippets**: https://apps-cookbook.dev/docs/category/dash

## Success Checklist

- [ ] App runs with mock backend
- [ ] All pages render without errors
- [ ] Callbacks work correctly
- [ ] Filters update data tables
- [ ] Charts display properly
- [ ] Modals open and close
- [ ] Consistent styling throughout
- [ ] Empty states handled
- [ ] Error handling in callbacks
- [ ] Real backend tested
- [ ] Documentation complete
