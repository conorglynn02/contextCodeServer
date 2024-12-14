from flask import Flask, request
import flask
import dash
from dash import dcc, html, dash_table
import plotly.graph_objects as go
import pandas as pd
# from dash.dependencies import Input, Output
from lib_config.config import Config
from db.metrics import Metrics
from db.models import MetricSnapshot, DeviceMetricType, Device, MetricValue
from managers.database_manager import DatabaseManager
import datetime
import json
import logging
import requests
from sqlalchemy import create_engine

app = Flask(__name__)

# Define the Dash app
dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dash/')

# Dash layout
def gauge_page():
    return html.Div([
        html.H1("Gauge Dashboard"),
        dcc.Link("Go to Table", href="/dash/table"),
        dcc.Graph(id="gauge"),
        dcc.Interval(
            id="gauge-interval",
            interval=5000,  # Update every 5 seconds
            n_intervals=0
        )
    ])

def table_page():
    return html.Div([
        html.H1("Table Dashboard"),
        dcc.Link("Go to Gauge", href="/dash/gauge"),
        dash_table.DataTable(
            id="records-table",
            columns=[{"name": i, "id": i} for i in ["device_id", "device_name", "device_metric_type_id", 
                                                    "device_metric_type_name", "client_timestamp_utc", 
                                                    "client_timezone_mins", "metric_value", "server_timestamp_utc", 
                                                    "server_timezone_mins"]],
            data=[]
        ),
        dcc.Interval(
            id="table-interval",
            interval=10000,  # Update every 5 seconds
            n_intervals=0
        )
    ])

dash_app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    html.Div(id="page-content")
])

# Callback to update the gauge with data from Flask
@dash_app.callback(
    dash.dependencies.Output("page-content", "children"),
    [dash.dependencies.Input("url", "pathname")]
)
def display_page(pathname):
    if pathname == "/dash/gauge":
        return gauge_page()
    elif pathname == "/dash/table":
        return table_page()
    else:
        # Default page or 404
        return html.Div([
            html.H1("404 - Page Not Found"),
            dcc.Link("Go to Gauge", href="/dash/gauge"),
            html.Br(),
            dcc.Link("Go to Table", href="/dash/table"),
        ])

# Callback to update the gauge
@dash_app.callback(
    dash.dependencies.Output("gauge", "figure"),
    [dash.dependencies.Input("gauge-interval", "n_intervals")]
)
def update_gauge(n):
    return _update_gauge_callback()
    
def _update_gauge_callback():
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
                    Device.device_name == "ConorG",
                    DeviceMetricType.name == 'RamUsage'
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

    # Update the gauge figure
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=final_value,
        title={"text": "Metric Value"},
        gauge={"axis": {"range": [0, 100]}}  # Adjust range as needed
    ))
    return fig

# Callback to update the table
@dash_app.callback(
    [
        dash.dependencies.Output("records-table", "columns"),
        dash.dependencies.Output("records-table", "data"),
    ],
    [dash.dependencies.Input("table-interval", "n_intervals")]
)
def update_table(n):
    try:
        get_endpoint = application.server.api.endpoints.get_all_metrics
        if application.server.isRemote:
            response = requests.get(application.server.remote.base + get_endpoint)
        else:
            response = requests.get(application.server.local.base + get_endpoint)
        data = response.json()
        if data["status"] == "success":
            records = data["data"]
            df = pd.DataFrame(records)
            columns = [{"name": col, "id": col} for col in df.columns]
            data = df.to_dict('records')
        else:
            columns = []
            data = []
    except Exception as e:
        print(f"Error fetching data: {e}")
        columns = []
        data = []

    return columns, data

class Application:
    def __init__(self):
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Application starting...")
        # Connect to the SQLite database
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
        application.logger.info("Add metric called")
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
                "time": datetime.datetime.now().strftime("%H:%M:%S %d-%m-%Y")
            }
            pretty_response = json.dumps(response, indent=4)
            return app.response_class(pretty_response, content_type="application/json")
    
    except Exception as e:
        application.logger.error("An error occurred: %s", e)
        response = {
            "error": str(e),
            "status": "failure",
            "time": datetime.datetime.now().strftime("%H:%M:%S %d-%m-%Y")
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
                "time": datetime.datetime.now().strftime("%H:%M:%S %d-%m-%Y")
            }
            application.logger.debug(f"Type of response: {type(response)}")
            pretty_response = json.dumps(response, indent=4)
            return app.response_class(pretty_response, content_type="application/json")
    
    except Exception as e:
        application.logger.error("An error occurred: %s", e)
        response = {
            "error": str(e),
            "status": "failure",
            "time": datetime.datetime.now().strftime("%H:%M:%S %d-%m-%Y")
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
                "time": datetime.datetime.now().strftime("%H:%M:%S %d-%m-%Y")
            }
            pretty_response = json.dumps(response, indent=4)
            return app.response_class(pretty_response, content_type="application/json")
    
    except Exception as e:
        application.logger.error("An error occurred: %s", e)
        response = {
            "error": str(e),
            "status": "failure",
            "time": datetime.datetime.now().strftime("%H:%M:%S %d-%m-%Y")
        }
        pretty_response = json.dumps(response, indent=4)
        return app.response_class(pretty_response, content_type="application/json")

if __name__ == "__main__":
    # app.run(port=8000, debug=True)
    app.run()
    # wsgi return server.server