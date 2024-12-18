from flask import Flask, request
import flask
import dash
from dash import dcc, html, dash_table
import plotly.graph_objects as go
import pandas as pd
from lib_config.config import Config
from db.metrics import Metrics
from db.models import MetricSnapshot, DeviceMetricType, Device, MetricValue
from managers.database_manager import DatabaseManager
from datetime import datetime
import json
import logging
import requests
from sqlalchemy import create_engine

app = Flask(__name__)

# define dash app
dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dash/')

def get_device_options():
    session = None
    try:
        with DatabaseManager(application.logger, application.engine) as session:
            devices = session.query(Device.device_name).all()
            return [{'label': device[0], 'value': device[0]} for device in devices]
    except Exception as e:
        application.logger.error(f"Error fetching devices: {e}")
        return []


# dash layout
def gauge_page():
    device_options = get_device_options()
    return html.Div([
        html.H1("Gauge Dashboard"),
        dcc.Link("Go to Table", href="/dash/table"),
        html.Br(),
        dcc.Link("Go to Histogram", href="/dash/histogram"),
        html.Br(),
        dcc.Dropdown(
            id='device-dropdown',
            options=device_options,
            value=device_options[0]['value'] if device_options else None,
            placeholder="Select a device",
            style={'width': '50%'}
        ),
        dcc.Dropdown(
            id='metric-dropdown',
            options=[],
            placeholder="Select a metric",
            style={'width': '50%'}
        ),
        dcc.Graph(id="gauge"),
        dcc.Interval(
            id="gauge-interval",
            interval=5000,  # update every 5 seconds
            n_intervals=0
        )
    ])

def table_page():
    return html.Div([
        html.H1("Table Dashboard"),
        dcc.Link("Go to Gauge", href="/dash/gauge"),
        html.Br(),
        dcc.Link("Go to Histogram", href="/dash/histogram"),
        html.Br(),
        html.A(html.Button('Refresh Data'),href='/dash/table'),
        html.Br(),
        dash_table.DataTable(
            id="records-table",
            columns=[
                {"name": col, "id": col}
                for col in [
                    "metric_snapshot_id", "device_id", "device_name",
                    "metric_type_id", "metric_type_name", "metric_value",
                    "timestamp_utc"
                ]
            ],
            data=[],
        ),
        html.Div(id="page-number-display", children="Page 1 of X"),
        html.Button("Previous", id="previous-page", n_clicks=0, disabled=True),
        html.Button("Next", id="next-page", n_clicks=0, disabled=True),
        dcc.Store(id="current-page", data=1),  # store current page number
    ])

def histogram_page():
    return html.Div([
        html.H1("Histogram Dashboard"),
        dcc.Link("Go to Gauge", href="/dash/gauge"),
        html.Br(),
        dcc.Link("Go to Table", href="/dash/table"),
        html.Br(),
        dcc.Graph(id="histogram")
    ])

dash_app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    html.Div(id="page-content")
])

# current page callback
@dash_app.callback(
    dash.dependencies.Output("page-content", "children"),
    [dash.dependencies.Input("url", "pathname")]
)
def display_page(pathname):
    if pathname == "/dash/gauge":
        return gauge_page()
    elif pathname == "/dash/table":
        return table_page()
    elif pathname == "/dash/histogram":
        return histogram_page()
    else:
        # 404 page
        return html.Div([
            html.H1("404 - Page Not Found"),
            dcc.Link("Go to Gauge", href="/dash/gauge"),
            html.Br(),
            dcc.Link("Go to Table", href="/dash/table"),
            html.Br(),
            dcc.Link("Go to Histogram", href="/dash/histogram"),
        ])

# gauge callback
@dash_app.callback(
    dash.dependencies.Output("gauge", "figure"),
    [
        dash.dependencies.Input("device-dropdown", "value"),
        dash.dependencies.Input("metric-dropdown", "value"),
        dash.dependencies.Input("gauge-interval", "n_intervals")
    ]
)

def update_gauge(device_name, metric_type, n):
    return _update_gauge_callback(device_name, metric_type)
    
def _update_gauge_callback(device_name, metric_type):
    session = None
    final_value = 0
    try:
        with DatabaseManager(application.logger, application.engine) as session:
            latest_metric_value = session.query(
                MetricValue.value,
                MetricSnapshot.metric_snapshot_id
            )\
                .join(MetricSnapshot, MetricValue.metric_snapshot_id == MetricSnapshot.metric_snapshot_id)\
                .join(DeviceMetricType, MetricValue.device_metric_type_id == DeviceMetricType.device_metric_type_id)\
                .join(Device, DeviceMetricType.device_id == Device.device_id)\
                .filter(
                    Device.device_name == device_name,  # now using the selected device name
                    DeviceMetricType.name == metric_type  # now using the selected metric type
                )\
                .order_by(MetricSnapshot.metric_snapshot_id.desc())\
                .first()
    
    except Exception as e:
        application.logger.error(f"Error fetching data: {e}")
        final_value = 0

    if latest_metric_value:
        final_value = latest_metric_value[0]
    else:
        final_value = 0

    # update the gauge figure
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=final_value,
        title={"text": f"{metric_type} Value"},
        gauge={"axis": {"range": [0, 100]}}
    ))
    return fig

# metrics callback
@dash_app.callback(
    dash.dependencies.Output("metric-dropdown", "options"),
    [dash.dependencies.Input("device-dropdown", "value")]
)
def update_metrics_dropdown(device_name):
    # updating the metrics dropdown options based on the selected device
    session = None
    try:
        # getting metrics types for the selected device
        with DatabaseManager(application.logger, application.engine) as session:
            metrics = session.query(DeviceMetricType.name)\
                .join(Device, DeviceMetricType.device_id == Device.device_id)\
                .filter(Device.device_name == device_name)\
                .all()
            
            # format results for the dropdown
            metric_options = [{'label': metric[0], 'value': metric[0]} for metric in metrics]
            return metric_options
    except Exception as e:
        application.logger.error(f"Error fetching metrics for device '{device_name}': {e}")
        return []

def get_total_records(session):
    try:
        # count total number of MetricSnapshots in db
        total_records = session.query(MetricSnapshot).count()
        return total_records
    except Exception as e:
        print(f"Error calculating total records: {e}")
        return 0

def fetch_metric_details_paginated(session, page, page_size=20):
    try:
        # calculating the offset
        offset = (page - 1) * page_size

        # paginated query
        results = session.query(
            MetricSnapshot.metric_snapshot_id,
            Device.device_name,
            Device.device_id,
            DeviceMetricType.device_metric_type_id,
            DeviceMetricType.name.label("metric_type_name"),
            MetricValue.value,
            MetricSnapshot.server_timestamp_utc
        )\
        .join(Device, MetricSnapshot.device_id == Device.device_id)\
        .join(MetricValue, MetricSnapshot.metric_snapshot_id == MetricValue.metric_snapshot_id)\
        .join(DeviceMetricType, MetricValue.device_metric_type_id == DeviceMetricType.device_metric_type_id)\
        .order_by(MetricSnapshot.metric_snapshot_id.desc())\
        .offset(offset)\
        .limit(page_size)\
        .all()

        result_list = [
            {
                "metric_snapshot_id": row.metric_snapshot_id,
                "device_id": row.device_id,
                "device_name": row.device_name,
                "metric_type_id": row.device_metric_type_id,
                "metric_type_name": row.metric_type_name,
                "metric_value": row.value,
                "timestamp_utc": row.server_timestamp_utc,
            }
            for row in results
        ]
        return result_list

    except Exception as e:
        print(f"Error fetching metric details: {e}")
        return []

# table callback
@dash_app.callback(
    [
        dash.dependencies.Output("records-table", "data"),
        dash.dependencies.Output("page-number-display", "children"),
        dash.dependencies.Output("next-page", "disabled"),
        dash.dependencies.Output("previous-page", "disabled"),
        dash.dependencies.Output("current-page", "data")
    ],
    [
        dash.dependencies.Input("next-page", "n_clicks"),
        dash.dependencies.Input("previous-page", "n_clicks")
    ],
    [
        dash.dependencies.State("current-page", "data")
    ]
)
def update_table(next_clicks, previous_clicks, current_page):
    page = current_page or 1
    page_size = 20  # number of records per page

    # find which button was clicked and update page number accordingly
    ctx = dash.callback_context
    if ctx.triggered:
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        if button_id == "next-page":
            page += 1
        elif button_id == "previous-page" and page > 1:
            page -= 1

    try:
        with DatabaseManager(application.logger, application.engine) as session:
            # number of total records
            total_records = get_total_records(session)
            max_page = (total_records + page_size - 1) // page_size  # formula for page number calculation
            
            # fetch data for the current page
            data = fetch_metric_details_paginated(session, page, page_size)
            
            # determine whether buttons should be disabled
            disable_next = page >= max_page
            disable_previous = page <= 1
            
            application.logger.debug(f"Page: {page}, Max Page: {max_page}, Next: {disable_next}, Previous: {disable_previous}")

        return data, f"Page {page} of {max_page}", disable_next, disable_previous, page
    except Exception as e:
        print(f"Error updating table: {e}")
        return [], "Error loading data", True, True, current_page

@dash_app.callback(
    dash.dependencies.Output("histogram", "figure"),
    [dash.dependencies.Input("url", "pathname")]  # trigger when the page is loaded
)
def update_histogram(pathname):
    if pathname != "/dash/histogram":
        return dash.no_update
    
    try:
        # query to fetch all metric data grouped by metric_type_id
        with DatabaseManager(application.logger, application.engine) as session:
            query = session.query(
                MetricValue.device_metric_type_id,
                DeviceMetricType.name.label("metric_type_name"),
                MetricValue.value
            )\
            .join(DeviceMetricType, MetricValue.device_metric_type_id == DeviceMetricType.device_metric_type_id)\
            .order_by(MetricValue.device_metric_type_id).all()

            # processing the data
            data_by_type = {}
            names_by_type = {}
            for record in query:
                metric_type_id = record.device_metric_type_id
                metric_type_name = record.metric_type_name
                value = record.value

                if metric_type_id not in names_by_type:
                    names_by_type[metric_type_id] = metric_type_name

                if metric_type_id not in data_by_type:
                    data_by_type[metric_type_id] = []
                data_by_type[metric_type_id].append(value)

            # creating traces for each metric_type_id
            traces = []
            for metric_type_id, values in data_by_type.items():
                x_indices = list(range(len(values)))  # indexing for x-axis
                metric_type_name = names_by_type[metric_type_id]
                traces.append(go.Scatter(
                    x=x_indices,
                    y=values,
                    mode="lines",
                    name=f"Metric Type {metric_type_name}"
                ))

            # layout
            layout = go.Layout(
                title="Metric Values by Metric Type",
                xaxis={"title": "Index"},
                yaxis={"title": "Metric Value"},
                legend={"title": "Metric Types"}
            )

            return {"data": traces, "layout": layout}

    except Exception as e:
        print(f"Error fetching data for histogram: {e}")
        return {
            "data": [],
            "layout": {"title": "Error loading histogram"}
        }

class Application:
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Application starting...")
        # connect to the SQLite database
        try:
            self.engine = create_engine(self.config.database.engine_string)

        except Exception as e:
            self.logger.error("An error occurred: %s", e)
            raise e
        self.data = Metrics(self.logger)

application = Application()

@app.route("/")
def home():
    application.logger.info("Home called")
    return flask.render_template('home.html')

@app.route(application.config.server.api.endpoints.post_metric_snapshot, methods=["POST"])
def post_metric_snapshot():
    session = None
    # structure of body:
    # data = {
    #     "device_id": 1,
    #     "device_name": "ConorG",
    #     "snapshots": [
    #         {
    #             "device_metric_type_id": 1,
    #             "device_metric_type_name": "RamUsage",
    #             "metric_value": 22.3
    #         },
    #         {
    #             "device_metric_type_id": 2,
    #             "device_metric_type_name": "DownloadSpeed",
    #             "metric_value": 5
    #         }
    #     ],
    #     "client_timestamp_utc": "12-12-2024 14:26:45",
    #     "client_timezone_mins": 0
    # }
    try:
        application.logger.info("Post metric called")
        with DatabaseManager(application.logger, application.engine) as session:
            data = request.json
            device_id = data["device_id"]
            device_name = data["device_name"]
            snapshots = data["snapshots"]
            client_timestamp_utc = data["client_timestamp_utc"]
            client_timezone_mins = data["client_timezone_mins"]

            metric = application.data.addMetricSnapshot(device_id, device_name, snapshots,
                                                            client_timestamp_utc, client_timezone_mins,
                                                            session=session)
            response = {
                "data": metric,
                "status": "success",
                "time": datetime.now().strftime("%H:%M:%S %d-%m-%Y")
            }
            pretty_response = json.dumps(response, indent=4)
            return app.response_class(pretty_response, content_type="application/json")
    
    except Exception as e:
        application.logger.error("An error occurred: %s", e)
        response = {
            "error": str(e),
            "status": "failure",
            "time": datetime.now().strftime("%H:%M:%S %d-%m-%Y")
        }
        pretty_response = json.dumps(response, indent=4)
        return app.response_class(pretty_response, status=400, content_type="application/json")

@app.route(application.config.server.api.endpoints.get_all_metrics, methods=["GET"])
def get_all_metrics():
    session = None
    try:
        application.logger.info("Get all called")
        with DatabaseManager(application.logger, application.engine) as session:
            all_metrics = application.data.getAllMetrics(session)
            if not all_metrics:
                raise Exception("No metrics found")
            return_data = [metric.to_dict() for metric in all_metrics]
            response = {
                "data": return_data,
                "status": "success",
                "time": datetime.now().strftime("%H:%M:%S %d-%m-%Y")
            }
            application.logger.debug(f"Type of response: {type(response)}")
            pretty_response = json.dumps(response, indent=4)
            return app.response_class(pretty_response, content_type="application/json")
    
    except Exception as e:
        application.logger.error("An error occurred: %s", e)
        response = {
            "error": str(e),
            "status": "failure",
            "time": datetime.now().strftime("%H:%M:%S %d-%m-%Y")
        }
        pretty_response = json.dumps(response, indent=4)
        return app.response_class(pretty_response, status=404, content_type="application/json")

@app.route(application.config.server.api.endpoints.get_metric_snapshot + "/<int:metric_snapshot_id>", methods=["GET"])
def getMetricSnapshot(metric_snapshot_id):
    try:
        application.logger.info("Get metric snapshot called")
        with DatabaseManager(application.logger, application.engine) as session:
            snapshot = application.data.getMetricSnapshot(metric_snapshot_id, session)
            if snapshot is None:
                raise Exception("snapshot not found")
            response = {
                "data": snapshot.to_dict(),
                "status": "success",
                "time": datetime.now().strftime("%H:%M:%S %d-%m-%Y")
            }
            pretty_response = json.dumps(response, indent=4)
            return app.response_class(pretty_response, content_type="application/json")
    
    except Exception as e:
        application.logger.error("An error occurred: %s", e)
        response = {
            "error": str(e),
            "status": "failure",
            "time": datetime.now().strftime("%H:%M:%S %d-%m-%Y")
        }
        pretty_response = json.dumps(response, indent=4)
        return app.response_class(pretty_response, content_type="application/json")

if __name__ == "__main__":
    app.run()
