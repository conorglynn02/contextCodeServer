# coding: utf-8
from sqlalchemy import Column, Float, ForeignKey, Integer, Table, Text
from sqlalchemy.sql.sqltypes import NullType
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
metadata = Base.metadata


class Device(Base):
    __tablename__ = 'devices'

    device_id = Column(Integer, primary_key=True)
    device_name = Column(Text, nullable=False)


t_sqlite_sequence = Table(
    'sqlite_sequence', metadata,
    Column('name', NullType),
    Column('seq', NullType)
)


class DeviceMetricType(Base):
    __tablename__ = 'device_metric_types'

    device_metric_type_id = Column(Integer, primary_key=True)
    device_id = Column(ForeignKey('devices.device_id'), nullable=False)
    name = Column(Text, nullable=False)

    device = relationship('Device')


class MetricSnapshot(Base):
    __tablename__ = 'metric_snapshots'

    metric_snapshot_id = Column(Integer, primary_key=True)
    device_id = Column(ForeignKey('devices.device_id'), nullable=False)
    client_timestamp_utc = Column(Text, nullable=False)
    client_timezone_mins = Column(Integer, nullable=False)
    server_timestamp_utc = Column(Text, nullable=False)
    server_timezone_mins = Column(Integer, nullable=False)

    device = relationship('Device')

    def to_dict(self):
        return {
            "metric_snapshot_id": self.metric_snapshot_id,
            "device_id": self.device_id,
            "client_timestamp_utc": self.client_timestamp_utc,
            "client_timezone_mins": self.client_timezone_mins,
            "server_timestamp_utc": self.server_timestamp_utc,
            "server_timezone_mins": self.server_timezone_mins,
        }


class MetricValue(Base):
    __tablename__ = 'metric_values'

    metric_snapshot_id = Column(ForeignKey('metric_snapshots.metric_snapshot_id'), primary_key=True, nullable=False)
    device_metric_type_id = Column(ForeignKey('device_metric_types.device_metric_type_id'), primary_key=True, nullable=False)
    value = Column(Float)

    device_metric_type = relationship('DeviceMetricType')
    metric_snapshot = relationship('MetricSnapshot')
