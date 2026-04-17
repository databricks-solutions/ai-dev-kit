# Complete Dashboard Examples

Production-ready templates you can adapt for your use case.

## Basic Dashboard (NYC Taxi)

```python
import json

# Step 1: Check table schema
table_info = get_table_stats_and_schema(catalog="samples", schema="nyctaxi")

# Step 2: Test queries
execute_sql("SELECT COUNT(*) as trips, AVG(fare_amount) as avg_fare, AVG(trip_distance) as avg_distance FROM samples.nyctaxi.trips")
execute_sql("""
    SELECT pickup_zip, COUNT(*) as trip_count
    FROM samples.nyctaxi.trips
    GROUP BY pickup_zip
    ORDER BY trip_count DESC
    LIMIT 10
""")

# Step 3: Build dashboard JSON
dashboard = {
    "datasets": [
        {
            "name": "summary",
            "displayName": "Summary Stats",
            "queryLines": [
                "SELECT COUNT(*) as trips, AVG(fare_amount) as avg_fare, ",
                "AVG(trip_distance) as avg_distance ",
                "FROM samples.nyctaxi.trips "
            ]
        },
        {
            "name": "by_zip",
            "displayName": "Trips by ZIP",
            "queryLines": [
                "SELECT pickup_zip, COUNT(*) as trip_count ",
                "FROM samples.nyctaxi.trips ",
                "GROUP BY pickup_zip ",
                "ORDER BY trip_count DESC ",
                "LIMIT 10 "
            ]
        }
    ],
    "pages": [{
        "name": "overview",
        "displayName": "NYC Taxi Overview",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            # Text header - NO spec block! Use SEPARATE widgets for title and subtitle!
            {
                "widget": {
                    "name": "title",
                    "multilineTextboxSpec": {
                        "lines": ["## NYC Taxi Dashboard"]
                    }
                },
                "position": {"x": 0, "y": 0, "width": 6, "height": 1}
            },
            {
                "widget": {
                    "name": "subtitle",
                    "multilineTextboxSpec": {
                        "lines": ["Trip statistics and analysis"]
                    }
                },
                "position": {"x": 0, "y": 1, "width": 6, "height": 1}
            },
            # Counter - version 2, width 2!
            {
                "widget": {
                    "name": "total-trips",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "trips", "expression": "`trips`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "trips", "displayName": "Total Trips"}
                        },
                        "frame": {"title": "Total Trips", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 2, "width": 2, "height": 3}
            },
            {
                "widget": {
                    "name": "avg-fare",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "avg_fare", "expression": "`avg_fare`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "avg_fare", "displayName": "Avg Fare"}
                        },
                        "frame": {"title": "Average Fare", "showTitle": True}
                    }
                },
                "position": {"x": 2, "y": 2, "width": 2, "height": 3}
            },
            {
                "widget": {
                    "name": "total-distance",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "avg_distance", "expression": "`avg_distance`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "avg_distance", "displayName": "Avg Distance"}
                        },
                        "frame": {"title": "Average Distance", "showTitle": True}
                    }
                },
                "position": {"x": 4, "y": 2, "width": 2, "height": 3}
            },
            # Bar chart - version 3
            {
                "widget": {
                    "name": "trips-by-zip",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "by_zip",
                            "fields": [
                                {"name": "pickup_zip", "expression": "`pickup_zip`"},
                                {"name": "trip_count", "expression": "`trip_count`"}
                            ],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 3,
                        "widgetType": "bar",
                        "encodings": {
                            "x": {"fieldName": "pickup_zip", "scale": {"type": "categorical"}, "displayName": "ZIP"},
                            "y": {"fieldName": "trip_count", "scale": {"type": "quantitative"}, "displayName": "Trips"}
                        },
                        "frame": {"title": "Trips by Pickup ZIP", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 5, "width": 6, "height": 5}
            },
            # Table - version 2, minimal column props!
            {
                "widget": {
                    "name": "zip-table",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "by_zip",
                            "fields": [
                                {"name": "pickup_zip", "expression": "`pickup_zip`"},
                                {"name": "trip_count", "expression": "`trip_count`"}
                            ],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "table",
                        "encodings": {
                            "columns": [
                                {"fieldName": "pickup_zip", "displayName": "ZIP Code"},
                                {"fieldName": "trip_count", "displayName": "Trip Count"}
                            ]
                        },
                        "frame": {"title": "Top ZIP Codes", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 10, "width": 6, "height": 5}
            }
        ]
    }]
}

# Step 4: Deploy
result = manage_dashboard(
    action="create_or_update",
    display_name="NYC Taxi Dashboard",
    parent_path="/Workspace/Users/me/dashboards",
    serialized_dashboard=json.dumps(dashboard),
    warehouse_id=manage_warehouse(action="get_best"),
)
print(result["url"])
```

## Dashboard with Global Filters

```python
import json

# Dashboard with a global filter for region
dashboard_with_filters = {
    "datasets": [
        {
            "name": "sales",
            "displayName": "Sales Data",
            "queryLines": [
                "SELECT region, SUM(revenue) as total_revenue ",
                "FROM catalog.schema.sales ",
                "GROUP BY region"
            ]
        }
    ],
    "pages": [
        {
            "name": "overview",
            "displayName": "Sales Overview",
            "pageType": "PAGE_TYPE_CANVAS",
            "layout": [
                {
                    "widget": {
                        "name": "total-revenue",
                        "queries": [{
                            "name": "main_query",
                            "query": {
                                "datasetName": "sales",
                                "fields": [{"name": "total_revenue", "expression": "`total_revenue`"}],
                                "disaggregated": True
                            }
                        }],
                        "spec": {
                            "version": 2,  # Version 2 for counters!
                            "widgetType": "counter",
                            "encodings": {
                                "value": {"fieldName": "total_revenue", "displayName": "Total Revenue"}
                            },
                            "frame": {"title": "Total Revenue", "showTitle": True}
                        }
                    },
                    "position": {"x": 0, "y": 0, "width": 6, "height": 3}
                }
            ]
        },
        {
            "name": "filters",
            "displayName": "Filters",
            "pageType": "PAGE_TYPE_GLOBAL_FILTERS",  # Required for global filter page!
            "layout": [
                {
                    "widget": {
                        "name": "filter_region",
                        "queries": [{
                            "name": "ds_sales_region",
                            "query": {
                                "datasetName": "sales",
                                "fields": [
                                    {"name": "region", "expression": "`region`"}
                                    # DO NOT use associative_filter_predicate_group - causes SQL errors!
                                ],
                                "disaggregated": False  # False for filters!
                            }
                        }],
                        "spec": {
                            "version": 2,  # Version 2 for filters!
                            "widgetType": "filter-multi-select",  # NOT "filter"!
                            "encodings": {
                                "fields": [{
                                    "fieldName": "region",
                                    "displayName": "Region",
                                    "queryName": "ds_sales_region"  # Must match query name!
                                }]
                            },
                            "frame": {"showTitle": True, "title": "Region"}  # Always show title!
                        }
                    },
                    "position": {"x": 0, "y": 0, "width": 2, "height": 2}
                }
            ]
        }
    ]
}

# Deploy with filters
result = manage_dashboard(
    action="create_or_update",
    display_name="Sales Dashboard with Filters",
    parent_path="/Workspace/Users/me/dashboards",
    serialized_dashboard=json.dumps(dashboard_with_filters),
    warehouse_id=manage_warehouse(action="get_best"),
)
print(result["url"])
```
