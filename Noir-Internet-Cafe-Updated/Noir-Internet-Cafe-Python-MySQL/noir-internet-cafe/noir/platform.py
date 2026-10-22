"""Administrator-maintained inventory and maintenance records; no device control."""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from ipaddress import IPv4Address
import re

from flask import Blueprint, Response

from .api import audit, payload, require, result
from .db import execute, query, transaction
from .domain import Problem, positive_id, text

platform = Blueprint("platform", __name__)
ASSET_TEXT = {"asset_tag":40, "name":80, "cpu":120, "motherboard":120,
              "storage":120, "psu":120, "input_devices":120, "output_devices":120,
              "nic":120, "os_version":120, "hostname":63, "location":120,
              "security_notes":500, "notes":500}


def choice(value, options, label):
    if not isinstance(value, str) or value not in options:
        raise Problem(f"Choose a valid {label}.")
    return value


def amount(value):
    try:
        value = Decimal(str(value))
        if not value.is_finite() or not 0 <= value <= 9999999999 or value != value.quantize(Decimal('.01')):
            raise ValueError
        return value
    except (ValueError, InvalidOperation):
        raise Problem("Cost must be a non-negative amount with at most two decimal places.")


def day(value):
    if value in (None, ''):
        return ''
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise Problem("Use a valid date in YYYY-MM-DD format.")


def asset_values(data):
    values = {key:text(data.get(key, ''), key.replace('_', ' '), 1 if key in ('asset_tag','name') else 0, size)
              for key, size in ASSET_TEXT.items()}
    values['category'] = choice(data.get('category', 'pc'), ('pc','server','network','printer','other'), 'category')
    values['status'] = choice(data.get('status', 'active'), ('active','repair','retired'), 'asset status')
    values['security_status'] = choice(data.get('security_status', 'not_checked'),
                                       ('not_checked','review_needed','verified'), 'security review')
    values['checked_on'] = day(data.get('checked_on'))
    if values['security_status'] == 'verified' and not (values['checked_on'] and values['security_notes']):
        raise Problem("Record a review date and evidence notes before marking security verified.")
    values['purchase_cost'] = amount(data.get('purchase_cost', 0))
    ram = str(data.get('ram_gb', 0))
    if not ram.isdigit() or not 0 <= int(ram) <= 4096:
        raise Problem("RAM must be a whole number from 0 to 4096 GB.")
    values['ram_gb'] = int(ram)
    values['station_id'] = positive_id(data['station_id'], 'station') if data.get('station_id') else None
    if values['station_id'] and not query('SELECT id FROM stations WHERE id=%s', (values['station_id'],), one=True):
        raise Problem("Station not found.", 404)
    ip = data.get('ip_address')
    try:
        values['ip_address'] = str(IPv4Address(str(ip))) if ip else None
    except ValueError:
        raise Problem("Enter a valid IPv4 address, such as 192.168.20.101.")
    mac = text(data.get('mac_address') or '', 'MAC address', 0, 17).upper().replace('-', ':')
    if mac and not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', mac):
        raise Problem("Use a MAC address such as 00:1A:2B:3C:4D:5E.")
    values['mac_address'] = mac or None
    if values['hostname'] and not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', values['hostname']):
        raise Problem("Hostname must contain letters, digits or internal hyphens.")
    return values


def record(table, record_id):
    row = query(f'SELECT * FROM {table} WHERE id=%s', (record_id,), one=True)
    if not row:
        raise Problem("Record not found.", 404)
    return row


def save(table, values, record_id=None):
    # Table/column identifiers are internal constants, never request-supplied SQL.
    with transaction():
        if record_id:
            record(table, record_id)
            execute(f"UPDATE {table} SET " + ','.join(f'{key}=%s' for key in values) + ' WHERE id=%s',
                    (*values.values(), record_id))
        else:
            record_id = execute(f"INSERT INTO {table} (" + ','.join(values) + ') VALUES (' +
                                ','.join('%s' for _ in values) + ')', tuple(values.values()))
        audit(f'{table}.save', f'Saved record #{record_id}')
    return result({'id':record_id})


@platform.get('/assets')
@require('administrator')
def assets():
    return result({'assets':query('SELECT a.*,s.name AS station_name FROM assets a LEFT JOIN stations s ON s.id=a.station_id ORDER BY a.asset_tag')})


@platform.post('/assets')
@require('administrator')
def create_asset():
    response, _ = save('assets', asset_values(payload()))
    return response, 201


@platform.patch('/assets/<int:asset_id>')
@require('administrator')
def edit_asset(asset_id):
    values = record('assets', asset_id)
    values.update(payload())
    return save('assets', asset_values(values), asset_id)


@platform.get('/maintenance')
@require('administrator')
def maintenance():
    return result({'maintenance':query('SELECT m.*,a.asset_tag,a.name AS asset_name FROM maintenance_records m JOIN assets a ON a.id=m.asset_id ORDER BY m.id DESC')})


def maintenance_values(data):
    values = {'asset_id':positive_id(data.get('asset_id'), 'asset'),
              'issue':text(data.get('issue'), 'issue', 2, 500),
              'action_taken':text(data.get('action_taken', ''), 'action taken', 0, 500),
              'technician':text(data.get('technician', ''), 'technician', 0, 80),
              'scheduled_on':day(data.get('scheduled_on')), 'completed_on':day(data.get('completed_on')),
              'cost':amount(data.get('cost', 0)),
              'status':choice(data.get('status','open'), ('open','in_progress','completed'), 'maintenance status')}
    record('assets', values['asset_id'])
    if values['status'] == 'completed' and not all(values[k] for k in ('completed_on','action_taken','technician')):
        raise Problem("Completed work needs a completion date, technician, and action taken.")
    if values['status'] != 'completed' and values['completed_on']:
        raise Problem("Set status to completed before recording a completion date.")
    return values


@platform.post('/maintenance')
@require('administrator')
def create_maintenance():
    response, _ = save('maintenance_records', maintenance_values(payload()))
    return response, 201


@platform.patch('/maintenance/<int:record_id>')
@require('administrator')
def edit_maintenance(record_id):
    data = record('maintenance_records', record_id)
    data.update(payload())
    return save('maintenance_records', maintenance_values(data), record_id)


REPORTS = {
    'assets':('SELECT * FROM assets ORDER BY asset_tag',
              ['id',*ASSET_TEXT,'category','ram_gb','ip_address','mac_address','station_id','purchase_cost','status','security_status','checked_on']),
    'maintenance':('SELECT m.*,a.asset_tag FROM maintenance_records m JOIN assets a ON a.id=m.asset_id ORDER BY m.id',
                   ['id','asset_tag','issue','action_taken','technician','scheduled_on','completed_on','status','cost']),
    'usage':('SELECT c.*,s.name AS station_name FROM cafe_sessions c JOIN stations s ON s.id=c.station_id ORDER BY c.id',
             ['id','station_name','customer_name','started_at','planned_end_at','ended_at','hourly_rate']),
    'payments':('SELECT p.*,c.customer_name,s.name AS station_name FROM payments p JOIN invoices i ON i.id=p.invoice_id JOIN cafe_sessions c ON c.id=i.session_id JOIN stations s ON s.id=c.station_id ORDER BY p.id',
                 ['id','invoice_id','station_name','customer_name','amount','method','reference','paid_at'])}


def csv_cell(value):
    value = '' if value is None else str(value)
    # Neutralize spreadsheet formulas, including whitespace-prefixed payloads.
    return "'" + value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value


@platform.get('/reports/<kind>.csv')
@require('administrator')
def export_report(kind):
    if kind not in REPORTS:
        raise Problem("Report not found.", 404)
    sql, columns = REPORTS[kind]
    output = StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows([csv_cell(row.get(column)) for column in columns] for row in query(sql))
    audit('report.export', f'Exported {kind} CSV')
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':f'attachment; filename="noir-{kind}.csv"'})
