"""Real MySQL integration suite. Isolated test database only; opt in explicitly."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

ENABLED = os.environ.get("RUN_MYSQL_TESTS") == "1"
if ENABLED:
    from noir import create_app
    from noir.db import execute, query
    from werkzeug.security import check_password_hash, generate_password_hash


@unittest.skipUnless(ENABLED, "Use the isolated Docker test profile to run MySQL integration tests")
class MySQLWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("DB_NAME") != "noir_test":
            raise RuntimeError("Integration tests require DB_NAME=noir_test. No other database may be used.")
        cls.app = create_app({"TESTING": True, "ALLOW_REGISTRATION": True, "SESSION_COOKIE_SECURE": False})
        initialized = cls.app.test_cli_runner().invoke(args=["init-db"])
        if initialized.exit_code:
            raise initialized.exception

    def setUp(self):
        with self.app.app_context():
            execute("SET FOREIGN_KEY_CHECKS=0")
            for table in ("maintenance_records", "assets", "payments", "invoices", "cafe_sessions", "bookings", "stations", "audit_log", "auth_sessions", "rate_limits", "users"):
                execute(f"TRUNCATE TABLE {table}")
            execute("SET FOREIGN_KEY_CHECKS=1")
            execute("INSERT INTO users(name,email,password_hash,role) VALUES (%s,%s,%s,'administrator')",
                    ("Test Administrator", "admin@test.example", generate_password_hash("LongTestPassword!123")))
        self.admin = self.app.test_client()
        self.admin_csrf = self.login(self.admin, "admin@test.example")

    def login(self, client, address, secret="LongTestPassword!123"):
        csrf = client.get("/api/auth/me").json["csrf_token"]
        response = client.post("/api/auth/login", json={"email":address, "password":secret}, headers={"X-CSRF-Token":csrf})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["csrf_token"]

    def post(self, client, csrf, path, values):
        return client.post("/api"+path, json=values, headers={"X-CSRF-Token":csrf})

    def create_station(self):
        response=self.post(self.admin,self.admin_csrf,"/stations",{"name":"PC 01","hourly_rate":"60.00"})
        self.assertEqual(response.status_code,201,response.json)
        return response.json["id"]

    def member(self, address="member@test.example"):
        client=self.app.test_client()
        csrf=client.get("/api/auth/me").json["csrf_token"]
        response=self.post(client,csrf,"/auth/register",{"name":"Test Member","email":address,"password":"LongTestPassword!123","role":"administrator"})
        self.assertEqual(response.status_code,201,response.json)
        return client,self.login(client,address)

    def test_registration_persists_hash_and_never_grants_admin(self):
        client,csrf=self.member()
        with self.app.app_context():
            row=query("SELECT * FROM users WHERE email=%s",("member@test.example",),one=True)
            self.assertNotEqual(row["password_hash"],"LongTestPassword!123")
            self.assertTrue(check_password_hash(row["password_hash"],"LongTestPassword!123"))
            self.assertEqual(row["role"],"member")
        self.assertEqual(client.get("/api/accounts").status_code,403)
        self.assertEqual(self.post(client,csrf,"/stations",{"name":"X","hourly_rate":"60"}).status_code,403)

    def test_full_booking_session_invoice_payment_flow(self):
        sid=self.create_station()
        member,csrf=self.member()
        future=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        uid=member.get("/api/auth/me").json["user"]["id"]
        self.assertEqual(self.post(member,csrf,"/bookings",{"station_id":sid,"scheduled_at":future}).status_code,403)
        booking=self.post(self.admin,self.admin_csrf,"/bookings",{"station_id":sid,"user_id":uid,"scheduled_at":future})
        self.assertEqual(booking.status_code,201,booking.json)
        conflict=self.post(self.admin,self.admin_csrf,"/sessions",{"station_id":sid,"customer_name":"Walk-in"})
        self.assertEqual(conflict.status_code,409)
        start=self.post(self.admin,self.admin_csrf,"/sessions",{"station_id":sid,"booking_id":booking.json["id"]})
        self.assertEqual(start.status_code,201,start.json)
        with self.app.app_context():
            execute("UPDATE cafe_sessions SET started_at=UTC_TIMESTAMP(6)-INTERVAL 61 MINUTE, planned_end_at=UTC_TIMESTAMP(6)+INTERVAL 30 MINUTE WHERE id=%s",(start.json["id"],))
        ended=self.post(self.admin,self.admin_csrf,f"/sessions/{start.json['id']}/end",{})
        self.assertEqual(ended.status_code,200,ended.json)
        iid=ended.json["invoice_id"]
        self.assertEqual(self.post(self.admin,self.admin_csrf,f"/sessions/{start.json['id']}/end",{}).json["invoice_id"],iid)
        member_invoice=member.get(f"/api/invoices/{iid}")
        self.assertEqual(member_invoice.status_code,200)
        self.assertIsNone(member_invoice.json["invoice"]["payment_id"])
        self.assertEqual(self.post(member,csrf,f"/invoices/{iid}/pay",{"method":"cash"}).status_code,403)
        paid=self.post(self.admin,self.admin_csrf,f"/invoices/{iid}/pay",{"method":"cash","amount":"0.01"})
        self.assertEqual(paid.status_code,201,paid.json)
        repeated=self.post(self.admin,self.admin_csrf,f"/invoices/{iid}/pay",{"method":"cash"})
        self.assertEqual(repeated.json["id"],paid.json["id"])
        with self.app.app_context():
            values=query("SELECT i.amount AS invoice_amount,p.amount AS payment_amount FROM invoices i JOIN payments p ON p.invoice_id=i.id WHERE i.id=%s",(iid,),one=True)
            self.assertEqual(values["invoice_amount"],values["payment_amount"])
            self.assertGreater(values["invoice_amount"],60)
        other,_=self.member("another@test.example")
        self.assertEqual(other.get(f"/api/invoices/{iid}").status_code,404)
        self.assertEqual(len(other.get("/api/invoices").json["invoices"]),0)

    def test_concurrent_start_allows_only_one_session(self):
        sid=self.create_station()
        clients=[self.app.test_client(),self.app.test_client()]
        tokens=[self.login(c,"admin@test.example") for c in clients]
        def start(pair):
            client,csrf=pair
            return self.post(client,csrf,"/sessions",{"station_id":sid,"customer_name":"Concurrent Guest"}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(start,zip(clients,tokens)))
        self.assertEqual(sorted(results),[201,409])
        with self.app.app_context():
            self.assertEqual(query("SELECT COUNT(*) AS n FROM cafe_sessions WHERE ended_at IS NULL",one=True)["n"],1)

    def test_csrf_logout_and_disabled_account(self):
        self.assertEqual(self.admin.post("/api/stations",json={"name":"X","hourly_rate":"60"}).status_code,403)
        member,csrf=self.member()
        uid=member.get("/api/auth/me").json["user"]["id"]
        changed=self.admin.patch(f"/api/accounts/{uid}",json={"name":"Test Member","email":"member@test.example","role":"member","active":False},headers={"X-CSRF-Token":self.admin_csrf})
        self.assertEqual(changed.status_code,200,changed.json)
        self.assertEqual(member.get("/api/dashboard").status_code,401)
        saved_cookie=self.admin.get_cookie("noir_session")
        self.assertEqual(self.post(self.admin,self.admin_csrf,"/auth/logout",{}).status_code,200)
        self.admin.set_cookie("noir_session",saved_cookie.value)
        self.assertEqual(self.admin.get("/api/dashboard").status_code,401)

    def test_admin_cannot_disable_itself(self):
        uid=self.admin.get("/api/auth/me").json["user"]["id"]
        response=self.admin.patch(f"/api/accounts/{uid}",json={"name":"Test Administrator","email":"admin@test.example","role":"member","active":False},headers={"X-CSRF-Token":self.admin_csrf})
        self.assertEqual(response.status_code,400)

    def test_cancel_access_maintenance_and_rate_snapshot(self):
        sid=self.create_station()
        member,csrf=self.member()
        future=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        uid=member.get("/api/auth/me").json["user"]["id"]
        bid=self.post(self.admin,self.admin_csrf,"/bookings",{"station_id":sid,"user_id":uid,"scheduled_at":future}).json["id"]
        other,other_csrf=self.member("other@test.example")
        self.assertEqual(self.post(other,other_csrf,f"/bookings/{bid}/cancel",{}).status_code,403)
        self.assertEqual(self.post(member,csrf,f"/bookings/{bid}/cancel",{}).status_code,403)
        self.assertEqual(self.post(self.admin,self.admin_csrf,f"/bookings/{bid}/cancel",{}).status_code,200)
        changed=self.admin.patch(f"/api/stations/{sid}",json={"name":"PC 01","hourly_rate":"60","maintenance":True},headers={"X-CSRF-Token":self.admin_csrf})
        self.assertEqual(changed.status_code,200)
        self.assertEqual(self.post(self.admin,self.admin_csrf,"/sessions",{"station_id":sid,"customer_name":"Guest"}).status_code,409)
        self.admin.patch(f"/api/stations/{sid}",json={"name":"PC 01","hourly_rate":"60","maintenance":False},headers={"X-CSRF-Token":self.admin_csrf})
        start=self.post(self.admin,self.admin_csrf,"/sessions",{"station_id":sid,"customer_name":"Guest"})
        self.admin.patch(f"/api/stations/{sid}",json={"name":"PC 01","hourly_rate":"120","maintenance":False},headers={"X-CSRF-Token":self.admin_csrf})
        with self.app.app_context():
            row=query("SELECT hourly_rate FROM cafe_sessions WHERE id=%s",(start.json["id"],),one=True)
            self.assertEqual(str(row["hourly_rate"]),"60.00")


    def test_timed_session_expiry_and_station_removal_preserve_history(self):
        sid=self.create_station()
        member,csrf=self.member()
        uid=member.get("/api/auth/me").json["user"]["id"]
        started=self.post(self.admin,self.admin_csrf,"/sessions",{"station_id":sid,"user_id":uid,"duration_minutes":60})
        self.assertEqual(started.status_code,201,started.json)
        live_id=started.json["id"]
        self.assertEqual(member.delete(f"/api/stations/{sid}",json={},headers={"X-CSRF-Token":csrf}).status_code,403)
        self.assertEqual(self.admin.delete(f"/api/stations/{sid}",json={},headers={"X-CSRF-Token":self.admin_csrf}).status_code,409)
        with self.app.app_context():
            execute("UPDATE cafe_sessions SET started_at='2020-01-01 00:00:00',planned_end_at='2020-01-01 01:00:00' WHERE id=%s",(live_id,))
        dashboard=member.get("/api/dashboard")
        self.assertEqual(dashboard.status_code,200,dashboard.json)
        self.assertEqual(dashboard.json["sessions"],[])
        iid=member.get("/api/invoices").json["invoices"][0]["id"]
        self.assertEqual(member.get(f"/api/invoices/{iid}").json["invoice"]["amount"],"60.00")
        paid=self.post(self.admin,self.admin_csrf,f"/invoices/{iid}/pay",{"method":"cash"})
        self.assertEqual(paid.status_code,201,paid.json)
        removed=self.admin.delete(f"/api/stations/{sid}",json={},headers={"X-CSRF-Token":self.admin_csrf})
        self.assertEqual(removed.status_code,200,removed.json)
        self.assertEqual(self.admin.get("/api/dashboard").json["stations"],[])
        self.assertIsNotNone(member.get(f"/api/invoices/{iid}").json["invoice"]["payment_id"])
        with self.app.app_context():
            self.assertEqual(query("SELECT COUNT(*) AS n FROM invoices",one=True)["n"],1)

    def test_migration_upgrades_older_schema_idempotently(self):
        sid=self.create_station()
        with self.app.app_context():
            execute("ALTER TABLE stations DROP COLUMN deleted_at")
            execute("ALTER TABLE cafe_sessions DROP COLUMN planned_end_at")
        runner=self.app.test_cli_runner()
        for _ in range(2):
            migrated=runner.invoke(args=["migrate-db"])
            self.assertEqual(migrated.exit_code,0,migrated.output)
        self.assertEqual(self.admin.get("/api/dashboard").json["stations"][0]["id"],sid)

    def test_inventory_constraints_and_export_permissions(self):
        sid=self.create_station()
        values={'asset_tag':'NOIR-PC-01','name':'Customer PC','station_id':sid,'ip_address':'192.168.20.101','mac_address':'00:11:22:33:44:55'}
        created=self.post(self.admin,self.admin_csrf,'/assets',values)
        self.assertEqual(created.status_code,201,created.json)
        duplicate=self.post(self.admin,self.admin_csrf,'/assets',{**values,'asset_tag':'NOIR-PC-02','station_id':None})
        self.assertEqual(duplicate.status_code,409)
        member,csrf=self.member()
        self.assertEqual(member.get('/api/reports/assets.csv').status_code,403)
        self.assertEqual(self.admin.get('/api/reports/assets.csv').status_code,200)
        for _ in range(2):
            migrated=self.app.test_cli_runner().invoke(args=['migrate-db'])
            self.assertEqual(migrated.exit_code,0,migrated.output)
        self.assertEqual(len(self.admin.get('/api/assets').json['assets']),1)


if __name__ == "__main__":
    unittest.main()
