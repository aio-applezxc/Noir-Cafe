"""HTTP workflow checks against a disposable SQLite adapter.

Exercises role guards, record visibility, timers and history preservation using
real Flask requests. This does not validate MySQL syntax or concurrent row locks;
those are covered by the separately enabled test_mysql.py suite.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch

from flask import session
from noir import create_app
from noir.domain import utcnow

sqlite3.register_adapter(datetime, lambda value: value.isoformat(' '))
sqlite3.register_converter('TIMESTAMP', lambda value: datetime.fromisoformat(value.decode()))

SCHEMA = '''
CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, role TEXT, active BOOLEAN DEFAULT 1, created_at TIMESTAMP);
CREATE TABLE stations (id INTEGER PRIMARY KEY, name TEXT UNIQUE, hourly_rate TEXT, maintenance BOOLEAN DEFAULT 0, deleted_at TIMESTAMP, created_at TIMESTAMP);
CREATE TABLE bookings (id INTEGER PRIMARY KEY, station_id INTEGER REFERENCES stations(id), user_id INTEGER, customer_name TEXT, scheduled_at TIMESTAMP, status TEXT DEFAULT 'reserved', created_by INTEGER, reserved_station_id INTEGER GENERATED ALWAYS AS (CASE WHEN status='reserved' THEN station_id END) STORED UNIQUE);
CREATE TABLE cafe_sessions (id INTEGER PRIMARY KEY, station_id INTEGER REFERENCES stations(id), user_id INTEGER, customer_name TEXT, booking_id INTEGER, hourly_rate TEXT, started_at TIMESTAMP, ended_at TIMESTAMP, planned_end_at TIMESTAMP, started_by INTEGER, active_station_id INTEGER GENERATED ALWAYS AS (CASE WHEN ended_at IS NULL THEN station_id END) STORED UNIQUE);
CREATE TABLE invoices (id INTEGER PRIMARY KEY, session_id INTEGER UNIQUE REFERENCES cafe_sessions(id), minutes INTEGER, amount TEXT, created_at TIMESTAMP, created_by INTEGER);
CREATE TABLE payments (id INTEGER PRIMARY KEY, invoice_id INTEGER UNIQUE REFERENCES invoices(id), amount TEXT, method TEXT, reference TEXT, paid_at TIMESTAMP, received_by INTEGER);
CREATE TABLE audit_log (id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT, detail TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
'''


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', detect_types=sqlite3.PARSE_DECLTYPES, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript(SCHEMA)
        from pathlib import Path
        import re
        ddl = (Path(__file__).resolve().parent.parent / 'database/platform.sql').read_text()
        ddl = ddl.replace('INT PRIMARY KEY AUTO_INCREMENT', 'INTEGER PRIMARY KEY')
        ddl = re.sub(r', INDEX \(asset_id\)', '', ddl)
        ddl = re.sub(r'ENGINE=InnoDB[^;]*', '', ddl)
        self.db.executescript(ddl)
        for uid, role in ((1, 'administrator'), (2, 'member'), (3, 'member')):
            self.db.execute('INSERT INTO users(id,name,email,role,created_at) VALUES (?,?,?,?,?)',
                            (uid, f'User {uid}', f'user{uid}@test.example', role, utcnow()))
        self.app = create_app({'TESTING':True, 'SECRET_KEY':'test-only-key-'*5, 'SESSION_COOKIE_SECURE':False})
        self.patches = [patch('noir.platform.query', self.query), patch('noir.platform.execute', self.execute), patch('noir.platform.transaction', self.transaction), patch('noir.api.query', self.query), patch('noir.api.execute', self.execute),
                        patch('noir.api.transaction', self.transaction), patch('noir.api.current_user', self.current_user)]
        for item in self.patches: item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])
        self.addCleanup(self.db.close)
        self.admin, self.member, self.other = (self.client(uid) for uid in (1, 2, 3))

    def client(self, uid):
        client = self.app.test_client()
        with client.session_transaction() as cookie:
            cookie['test_uid'] = uid
            cookie['csrf'] = 'test-csrf'
        return client

    def current_user(self):
        return self.query('SELECT * FROM users WHERE id=%s', (session.get('test_uid'),), one=True)

    def cursor(self, sql, args):
        return self.db.execute(sql.replace('%s', '?').replace(' FOR UPDATE', ''),
                               tuple(str(v) if isinstance(v, Decimal) else v for v in args))

    def query(self, sql, args=(), one=False):
        rows = [dict(row) for row in self.cursor(sql, args).fetchall()]
        return (rows[0] if rows else None) if one else rows

    def execute(self, sql, args=()):
        return self.cursor(sql, args).lastrowid

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN')
        try:
            yield self.db
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def request(self, client, method, route, data=None, status=200):
        response = client.open('/api'+route, method=method, json=data or {}, headers={'X-CSRF-Token':'test-csrf'})
        self.assertEqual(response.status_code, status, response.json)
        return response.json

    def station(self, name='PC 01'):
        return self.request(self.admin, 'POST', '/stations', {'name':name,'hourly_rate':'60'}, 201)['id']

    def start(self, sid, user_id=2, minutes=60):
        return self.request(self.admin, 'POST', '/sessions', {'station_id':sid, 'user_id':user_id,'duration_minutes':minutes}, 201)['id']

    def test_members_cannot_manage_bookings_stations_sessions_or_payments(self):
        sid = self.station()
        for method, path in [('POST','/bookings'), ('POST','/bookings/1/cancel'), ('POST','/stations'),
                             ('PATCH',f'/stations/{sid}'), ('DELETE',f'/stations/{sid}'), ('POST','/sessions'),
                             ('POST','/sessions/1/end'), ('PATCH','/sessions/1/time'), ('POST','/invoices/1/pay')]:
            with self.subTest(path=path, method=method):
                self.request(self.member, method, path, {}, 403)
        self.assertEqual(self.member.get('/api/accounts').status_code, 403)
        self.assertEqual(self.member.get('/api/activity').status_code, 403)
        self.assertEqual(self.query('SELECT * FROM bookings'), [])
        self.assertEqual(self.query('SELECT * FROM cafe_sessions'), [])
        self.assertIsNone(self.query('SELECT deleted_at FROM stations',one=True)['deleted_at'])

    def test_admin_booking_checkin_member_visibility_and_own_billing(self):
        sid = self.station()
        future = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        bid = self.request(self.admin,'POST','/bookings',{'station_id':sid,'user_id':2,'scheduled_at':future},201)['id']
        self.request(self.admin,'DELETE',f'/stations/{sid}',{},409)
        self.assertEqual(self.member.get('/api/dashboard').json['bookings'], [])
        started = self.request(self.admin,'POST','/sessions',{'station_id':sid,'booking_id':bid,'duration_minutes':90},201)['id']
        mine = self.member.get('/api/dashboard').json
        other = self.other.get('/api/dashboard').json
        self.assertEqual(len(mine['sessions']), 1)
        self.assertTrue(mine['sessions'][0]['planned_end_at'])
        self.assertEqual(other['sessions'], [])
        self.assertIsNone(other['stations'][0]['session'])
        iid = self.request(self.admin,'POST',f'/sessions/{started}/end')['invoice_id']
        self.assertEqual(len(self.member.get('/api/invoices').json['invoices']), 1)
        self.assertEqual(self.member.get(f'/api/invoices/{iid}').status_code, 200)
        self.assertEqual(self.other.get(f'/api/invoices/{iid}').status_code, 404)
        self.assertEqual(self.other.get('/api/invoices').json['invoices'], [])

    def test_delete_station_retains_invoices_payments_and_blocks_reuse(self):
        sid = self.station()
        live = self.start(sid)
        self.request(self.admin,'DELETE',f'/stations/{sid}',{},409)
        iid = self.request(self.admin,'POST',f'/sessions/{live}/end')['invoice_id']
        self.request(self.admin,'POST',f'/invoices/{iid}/pay',{'method':'cash'},201)
        self.request(self.admin,'DELETE',f'/stations/{sid}')
        self.assertEqual(self.admin.get('/api/dashboard').json['stations'], [])
        self.assertEqual(self.member.get('/api/dashboard').json['stations'], [])
        old = self.member.get(f'/api/invoices/{iid}').json['invoice']
        self.assertEqual(old['station_name'], 'PC 01')
        self.assertIsNotNone(old['payment_id'])
        self.request(self.admin,'POST','/sessions',{'station_id':sid,'user_id':2},404)
        self.request(self.admin,'PATCH',f'/stations/{sid}',{'name':'PC 01','hourly_rate':'60','maintenance':False},404)
        self.request(self.admin,'DELETE',f'/stations/{sid}')
        self.assertEqual(self.request(self.admin,'POST',f'/sessions/{live}/end')['invoice_id'],iid)

    def test_delete_maintenance_pc_and_release_cancelled_reservation(self):
        sid=self.station()
        future=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        bid=self.request(self.admin,'POST','/bookings',{'station_id':sid,'customer_name':'Guest','scheduled_at':future},201)['id']
        self.request(self.admin,'POST',f'/bookings/{bid}/cancel')
        self.request(self.admin,'PATCH',f'/stations/{sid}',{'name':'PC 01','hourly_rate':'60','maintenance':True})
        self.request(self.admin,'DELETE',f'/stations/{sid}')
        self.assertEqual(self.admin.get('/api/dashboard').json['stations'],[])
        self.assertEqual(self.query('SELECT status FROM bookings',one=True)['status'],'cancelled')

    def test_expiry_caps_charge_and_creates_one_invoice_after_downtime(self):
        sid=self.station()
        live=self.start(sid,minutes=60)
        started=utcnow()-timedelta(hours=3)
        deadline=started+timedelta(hours=1)
        self.execute('UPDATE cafe_sessions SET started_at=%s,planned_end_at=%s WHERE id=%s',(started,deadline,live))
        dashboard=self.member.get('/api/dashboard')
        self.assertEqual(dashboard.status_code,200,dashboard.json)
        self.assertEqual(dashboard.json['sessions'],[])
        self.assertEqual(dashboard.json['stations'][0]['status'],'available')
        self.assertEqual(float(dashboard.json['finances']['outstanding']),60)
        self.member.get('/api/dashboard')
        self.request(self.admin,'POST',f'/sessions/{live}/end')
        rows=self.query('SELECT * FROM invoices')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['minutes'],60)
        self.assertEqual(Decimal(rows[0]['amount']),Decimal('60.00'))
        self.assertEqual(self.query('SELECT ended_at FROM cafe_sessions',one=True)['ended_at'],deadline)

    def test_remaining_time_validation_and_legacy_session_upgrade(self):
        sid=self.station()
        for value in (0,-1,1441,'abc',1.5,True,None):
            self.request(self.admin,'POST','/sessions',{'station_id':sid,'user_id':2,'duration_minutes':value},400)
        live=self.start(sid)
        self.execute('UPDATE cafe_sessions SET planned_end_at=NULL WHERE id=%s',(live,))
        dashboard=self.member.get('/api/dashboard').json
        self.assertIsNone(dashboard['sessions'][0]['planned_end_at'])
        before=utcnow()
        self.request(self.admin,'PATCH',f'/sessions/{live}/time',{'remaining_minutes':30})
        deadline=self.query('SELECT planned_end_at FROM cafe_sessions',one=True)['planned_end_at']
        self.assertTrue(1799 <= (deadline-before).total_seconds() <= 1802)
        self.request(self.admin,'PATCH',f'/sessions/{live}/time',{'remaining_minutes':0},400)

    def test_delete_requires_csrf_and_authentication(self):
        sid=self.station()
        self.assertEqual(self.admin.delete(f'/api/stations/{sid}',json={}).status_code,403)
        anonymous=self.client(None)
        self.request(anonymous,'DELETE',f'/stations/{sid}',{},401)
        self.request(self.admin,'DELETE','/stations/999',{},404)


    def test_platform_records_are_admin_only_and_validate_network(self):
        for path in ('/assets','/maintenance','/reports/assets.csv','/reports/maintenance.csv','/reports/usage.csv','/reports/payments.csv'):
            self.assertEqual(self.member.get('/api'+path).status_code,403)
        for path in ('/assets','/maintenance'):
            self.request(self.member,'POST',path,{},403)
            self.request(self.member,'PATCH',path+'/1',{},403)
        data={'asset_tag':'PC-01','name':'Desk computer','ip_address':'999.2.3.4'}
        self.request(self.admin,'POST','/assets',data,400)
        data['ip_address']='192.168.20.101'
        data['mac_address']='00-11-22-33-44-55'
        aid=self.request(self.admin,'POST','/assets',data,201)['id']
        row=self.request(self.admin,'GET','/assets')['assets'][0]
        self.assertEqual(row['mac_address'],'00:11:22:33:44:55')
        self.request(self.admin,'PATCH',f'/assets/{aid}',{'ram_gb':16,'security_status':'verified'},400)
        self.request(self.admin,'PATCH',f'/assets/{aid}',{'ram_gb':16,'security_status':'verified','checked_on':'2026-10-14','security_notes':'Firewall screenshot reviewed'})
        row=self.request(self.admin,'GET','/assets')['assets'][0]
        self.assertEqual(row['name'],'Desk computer')
        self.assertEqual(row['ram_gb'],16)

    def test_repair_history_and_csv_survive_station_removal(self):
        sid=self.station()
        aid=self.request(self.admin,'POST','/assets',{'asset_tag':'PC-01','name':'=HYPERLINK("bad")','station_id':sid},201)['id']
        mid=self.request(self.admin,'POST','/maintenance',{'asset_id':aid,'issue':'Power failure','scheduled_on':'2026-10-15'},201)['id']
        self.request(self.admin,'PATCH',f'/maintenance/{mid}',{'status':'completed'},400)
        self.request(self.admin,'PATCH',f'/maintenance/{mid}',{'status':'completed','completed_on':'2026-10-15','action_taken':'Replaced PSU','technician':'Test Tech','cost':'2500.00'})
        self.request(self.admin,'DELETE',f'/stations/{sid}')
        self.assertEqual(len(self.request(self.admin,'GET','/maintenance')['maintenance']),1)
        response=self.admin.get('/api/reports/assets.csv')
        self.assertEqual(response.status_code,200)
        import csv,io
        exported=list(csv.DictReader(io.StringIO(response.data.decode('utf-8-sig'))))
        self.assertEqual(exported[0]['name'],"'=HYPERLINK(\"bad\")")
        self.assertEqual(exported[0]['station_id'],str(sid))
        self.assertEqual(self.admin.get('/api/reports/unknown.csv').status_code,404)

if __name__ == '__main__':
    unittest.main()
