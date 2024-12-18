from datetime import datetime, timezone
from dataclasses import dataclass
from .models import Base, Device, DeviceMetricType, MetricSnapshot, MetricValue

@dataclass
class Metrics:
    def __init__(self, logger):
        self.logger = logger

    def getAllMetrics(self, session):
        self.logger.debug("Fetching all metrics")
        all_snapshots = session.query(MetricSnapshot).all()
        if not all_snapshots:
            self.logger.error("No snapshot found")
            return None
        for snapshot in all_snapshots:
            self.logger.info(f"Line 1: Snapshot ID: {snapshot.metric_snapshot_id}, Device ID: {snapshot.device_id}, Client timestamp: {snapshot.client_timestamp_utc}")
            self.logger.info(f"Line 2: Client timezone: {snapshot.client_timezone_mins},  Server timestamp: {snapshot.server_timestamp_utc}, Server timezone: {snapshot.server_timezone_mins}")
        self.logger.debug(f"Type of all_snapshots: {type(all_snapshots)}")
        return all_snapshots

    def addMetricSnapshot(self, device_id, device_name, snapshots,
                           client_timestamp_utc, client_timezone_mins,
                             session):
        
        # find or create device
        device = session.query(Device).filter_by(device_id=device_id).first()
        if not device:
            device = Device(
                device_id=device_id,
                device_name=device_name
            )
            session.add(device)
            session.flush()  # get the id of newly created device to use later

        server_timestamp_utc = datetime.now().strftime("%d-%m-%Y %H:%M:%S") 
        now_UTC = datetime.now(timezone.utc)
        server_timezone_mins = int(now_UTC.astimezone().utcoffset().total_seconds() / 60)

        for snapshot in snapshots:
            device_metric_type_id = snapshot["device_metric_type_id"]
            device_metric_type_name = snapshot["device_metric_type_name"]
            metric_value = snapshot["metric_value"]

            metric_snapshot = MetricSnapshot(
                device_id = device_id,
                client_timestamp_utc = client_timestamp_utc,
                client_timezone_mins = client_timezone_mins,
                server_timestamp_utc = server_timestamp_utc,
                server_timezone_mins = server_timezone_mins
            )
            session.add(metric_snapshot)
            session.flush()

            metric_snapshot_id = metric_snapshot.metric_snapshot_id

            device_metric_type = session.query(DeviceMetricType).filter_by(
                device_metric_type_id=device_metric_type_id, 
                device_id=device_id
            ).first()
            
            if not device_metric_type:
                device_metric_type = DeviceMetricType(
                    device_metric_type_id = device_metric_type_id,
                    device_id = device_id,
                    name = device_metric_type_name
                )
                session.add(device_metric_type)
                session.flush()

            metric_value = MetricValue(
                metric_snapshot_id = metric_snapshot_id,
                device_metric_type_id = device_metric_type_id,
                value = metric_value
            )
            session.add(metric_value)

        self.logger.info(f"Added metric snapshot: {snapshots}")
        return snapshots
    
    def getMetricSnapshot(self, metric_snapshot_id, session):
        snapshot = session.query(MetricSnapshot).filter(MetricSnapshot.metric_snapshot_id == metric_snapshot_id).first()
        if not snapshot:
            self.logger.error(f"Snapshot with ID {metric_snapshot_id} not found")
            return None
        self.logger.info(f"Snapshot found: {snapshot}")
        return snapshot
