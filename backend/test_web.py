"""Flask route checks for authentication, role dashboards, and transport flows."""
import os
import tempfile
import unittest

from backend.app import create_app
from backend.service import TransportService


class TransportWebTests(unittest.TestCase):
    def setUp(self):
        descriptor, self.data_file = tempfile.mkstemp(suffix=".json")
        os.close(descriptor)
        os.unlink(self.data_file)
        self.transport = TransportService(self.data_file)
        self.transport.create_semester("Spring-2027", "2027-01-01", "2027-06-30", 1500, 2500, 2000, 1, 1)
        self.transport.add_provider("P1", "Campus Transport", "0300", "provider-pass")
        self.transport.add_driver("D1", "Driver One", "LIC-1", "0301", "driver-pass")
        self.transport.add_route("R1", "Gulberg", "FAST", 10, "Liberty")
        self.transport.add_vehicle("V1", "ABC-001", "Bus", True, "R1", "P1", 2, "D1")
        self.transport.add_user("S1", "Student One", "s1@test", "0302", "student", "ROLL-1", "student-pass")

        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="test-secret", TRANSPORT_SERVICE=self.transport)
        self.client = self.app.test_client()

    def tearDown(self):
        if os.path.exists(self.data_file):
            os.unlink(self.data_file)

    def csrf_token(self, path="/"):
        self.client.get(path)
        with self.client.session_transaction() as browser_session:
            return browser_session["_csrf_token"]

    def test_login_form_renders_the_session_csrf_token(self):
        response = self.client.get("/")
        token = self.csrf_token()
        self.assertIn(f'name="_csrf_token" value="{token}"'.encode(), response.data)
        self.assertNotIn(b'value="admin"', response.data)
        self.assertIn(b'href="/admin"', response.data)

    def login(self, role, user_id, password):
        path = "/admin" if role == "admin" else "/"
        return self.client.post(path, data={"_csrf_token": self.csrf_token(path), "role": role,
                                            "user_id": user_id, "password": password})

    def test_administrator_uses_dedicated_sign_in_route(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Administrator access", response.data)
        self.assertNotIn(b'<select name="role"', response.data)
        self.assertNotIn(b"admin123", response.data)

        rejected = self.client.post("/", data={
            "_csrf_token": self.csrf_token(), "role": "admin", "password": "admin123",
        })
        self.assertEqual(rejected.status_code, 302)
        with self.client.session_transaction() as browser_session:
            self.assertNotIn("user", browser_session)

        accepted = self.login("admin", "", "admin123")
        self.assertEqual(accepted.status_code, 302)
        with self.client.session_transaction() as browser_session:
            self.assertEqual(browser_session["user"]["role"], "admin")

    def test_unauthenticated_admin_pages_redirect_to_admin_sign_in(self):
        response = self.client.get("/admin/records/users")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/admin")

    def test_member_portal_cannot_write_admin_records(self):
        self.login("student", "S1", "student-pass")
        response = self.post_form("/admin/user", {
            "user_id": "S9", "name": "Unauthorized", "email": "s9@test", "phone": "0309",
            "role": "student", "identifier": "ROLL-9", "password": "pass",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.transport.search_records("users", "S9"))

    def post_form(self, path, values):
        data = dict(values)
        data["_csrf_token"] = self.csrf_token()
        return self.client.post(path, data=data)

    def test_role_login_keeps_password_out_of_signed_session(self):
        response = self.login("driver", "D1", "driver-pass")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as browser_session:
            self.assertEqual(browser_session["user"], {"id": "D1", "role": "driver", "name": "Driver One"})
            self.assertNotIn("password", browser_session["user"])
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_deactivated_account_cannot_keep_using_an_existing_session(self):
        self.login("student", "S1", "student-pass")
        self.transport.update_record("users", "S1", {"active": False})
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")
        with self.client.session_transaction() as browser_session:
            self.assertNotIn("user", browser_session)

    def test_admin_can_create_and_activate_semesters_and_inspect_records(self):
        self.login("admin", "", "admin123")
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Passengers", dashboard.data)
        semester_form = self.client.get("/admin/records/semesters")
        self.assertEqual(semester_form.status_code, 200)
        self.assertEqual(semester_form.data.count(b'max="9999-12-31"'), 4)
        response = self.client.post("/admin/semester", data={
            "_csrf_token": self.csrf_token(), "name": "Fall-2027", "starts": "2027-08-01",
            "ends": "2027-12-31", "student_fare": "1600", "faculty_fare": "2600",
            "ac_surcharge": "2100", "student_seats": "1", "faculty_seats": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.transport.data["settings"]["active_semester"], "Fall-2027")
        records = self.client.get("/admin/records/users")
        self.assertEqual(records.status_code, 200)
        self.assertNotIn(b"student-pass", records.data)
        search = self.client.get("/admin/records/users?q=S1")
        self.assertEqual(search.status_code, 200)
        self.assertIn(b"S1", search.data)

    def test_admin_can_create_all_operational_record_types(self):
        self.login("admin", "", "admin123")
        operations = (
            ("/admin/provider", {"provider_id": "P2", "name": "Second Provider",
                                 "contact": "0304", "password": "provider-pass"}),
            ("/admin/driver", {"driver_id": "D2", "name": "Second Driver",
                               "license_number": "LIC-2", "phone": "0305", "password": "driver-pass"}),
            ("/admin/route", {"route_id": "R2", "start": "DHA", "end": "FAST",
                              "distance": "8", "stops": "Model Town"}),
            ("/admin/vehicle", {"vehicle_id": "V2", "registration": "XYZ-002",
                                "vehicle_type": "Coaster", "route_id": "R2", "provider_id": "P2",
                                "capacity": "20", "driver_id": "", "ac": "on"}),
            ("/admin/assignment", {"vehicle_id": "V2", "driver_id": "D2"}),
            ("/admin/user", {"user_id": "F2", "name": "Faculty Two", "email": "f2@test",
                             "phone": "0306", "role": "faculty", "identifier": "EMP-2",
                             "password": "faculty-pass"}),
        )
        destination_pages = {
            "/admin/provider": "/admin/records/providers",
            "/admin/driver": "/admin/records/drivers",
            "/admin/route": "/admin/records/routes",
            "/admin/vehicle": "/admin/records/vehicles",
            "/admin/assignment": "/admin/records/vehicles",
            "/admin/user": "/admin/records/users",
        }
        for path, values in operations:
            response = self.post_form(path, values)
            self.assertEqual(response.status_code, 302, path)
            self.assertTrue(response.location.endswith(destination_pages[path]), path)
        self.assertEqual(self.transport.find("vehicles", "V2")["driver_id"], "D2")
        self.assertEqual(self.transport.find("users", "F2")["role"], "faculty")

    def test_admin_master_data_is_managed_on_its_own_page(self):
        self.login("admin", "", "admin123")
        dashboard = self.client.get("/dashboard")
        self.assertNotIn(b'name="user_id"', dashboard.data)
        self.assertIn(b'href="/admin/records/users"', dashboard.data)

        for category in ("semesters", "users", "providers", "drivers", "routes", "vehicles",
                         "bookings", "payments", "waitlists", "audit_log"):
            response = self.client.get(f"/admin/records/{category}")
            self.assertEqual(response.status_code, 200, category)

        updated = self.post_form("/admin/records/users/S1/update", {
            "name": "Student Updated", "email": "s1@test", "phone": "0302",
            "role": "student", "identifier": "ROLL-1", "active": "on", "password": "",
        })
        self.assertEqual(updated.status_code, 302)
        self.assertEqual(self.transport.find("users", "S1")["name"], "Student Updated")

        self.transport.add_user("S9", "Temporary User", "s9@test", "0309", "student", "ROLL-9", "pass")
        deleted = self.post_form("/admin/records/users/S9/delete", {})
        self.assertEqual(deleted.status_code, 302)
        self.assertNotIn("S9", [user["id"] for user in self.transport.records("users")])

    def test_admin_can_cancel_but_not_delete_transaction_history(self):
        self.transport.record_payment("S1", "V1")
        booking = self.transport.book("S1", "V1", "1")
        self.login("admin", "", "admin123")
        records = self.client.get("/admin/records/bookings")
        self.assertEqual(records.status_code, 200)
        self.assertIn(b"Cancel booking", records.data)
        response = self.post_form(f"/admin/bookings/{booking['id']}/cancel", {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.transport.find("bookings", booking["id"])["status"], "cancelled")
        self.assertEqual(self.client.post(f"/admin/records/bookings/{booking['id']}/delete",
                                          data={"_csrf_token": self.csrf_token()}).status_code, 404)

    def test_every_portal_dashboard_renders_for_its_role(self):
        self.transport.add_user("F1", "Faculty One", "f1@test", "0303", "faculty", "EMP-1", "faculty-pass")
        accounts = (
            ("admin", "", "admin123", b"admin portal"),
            ("student", "S1", "student-pass", b"student portal"),
            ("faculty", "F1", "faculty-pass", b"faculty portal"),
            ("driver", "D1", "driver-pass", b"driver portal"),
            ("provider", "P1", "provider-pass", b"provider portal"),
        )
        for role, user_id, password, expected in accounts:
            self.login(role, user_id, password)
            response = self.client.get("/dashboard")
            self.assertEqual(response.status_code, 200, role)
            self.assertIn(expected, response.data)
            self.client.get("/logout")

    def test_student_payment_booking_and_route_explorer(self):
        self.login("student", "S1", "student-pass")
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Gulberg", dashboard.data)

        payment = self.client.post("/member/payment", data={
            "_csrf_token": self.csrf_token(), "vehicle_id": "V1",
        })
        self.assertEqual(payment.status_code, 302)
        booking = self.client.post("/member/book", data={
            "_csrf_token": self.csrf_token(), "vehicle_id": "V1", "seat": "1",
        })
        self.assertEqual(booking.status_code, 302)
        self.assertEqual(self.transport.records("bookings", True)[0]["status"], "confirmed")

        self.transport.add_user("S2", "Student Two", "s2@test", "0304", "student", "ROLL-2", "student-pass")
        self.transport.record_payment("S2", "V1")
        self.client.get("/logout")
        self.login("student", "S2", "student-pass")
        waitlist_response = self.post_form("/member/waitlist", {"vehicle_id": "V1"})
        self.assertEqual(waitlist_response.status_code, 302)
        self.client.get("/logout")
        self.login("student", "S1", "student-pass")
        booking_id = self.transport.records("bookings", True)[0]["id"]
        cancel_response = self.post_form(f"/booking/{booking_id}/cancel", {})
        self.assertEqual(cancel_response.status_code, 302)
        self.assertEqual(self.transport.records("waitlists", True)[0]["status"], "offered")
        self.client.get("/logout")
        self.login("student", "S2", "student-pass")
        offered_dashboard = self.client.get("/dashboard")
        self.assertIn(b"Seat 1 has been offered to you", offered_dashboard.data)
        offered_booking = self.post_form("/member/book", {"vehicle_id": "V1", "seat": "1"})
        self.assertEqual(offered_booking.status_code, 302)
        self.assertEqual(self.transport.records("waitlists", True)[0]["status"], "accepted")

        route_page = self.client.post("/routes", data={
            "_csrf_token": self.csrf_token(), "start": "Gulberg", "end": "FAST",
        })
        self.assertEqual(route_page.status_code, 200)
        self.assertIn(b"10.00 km", route_page.data)
        self.assertIn(b"Network 1", route_page.data)

    def test_member_can_leave_only_their_own_waitlist_entry(self):
        self.transport.add_user("S2", "Student Two", "s2@test", "0304", "student", "ROLL-2", "student-pass")
        self.transport.record_payment("S1", "V1")
        self.transport.book("S1", "V1", "1")
        self.transport.record_payment("S2", "V1")
        entry = self.transport.join_waitlist("S2", "V1")

        self.login("student", "S1", "student-pass")
        unauthorized = self.post_form(f"/waitlist/{entry['id']}/leave", {})
        self.assertEqual(unauthorized.status_code, 302)
        self.assertEqual(entry["status"], "waiting")

        self.client.get("/logout")
        self.login("student", "S2", "student-pass")
        response = self.post_form(f"/waitlist/{entry['id']}/leave", {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(entry["status"], "cancelled")

    def test_driver_and_provider_passenger_access_is_limited_to_their_vehicles(self):
        self.transport.record_payment("S1", "V1")
        self.transport.book("S1", "V1", "1")
        self.login("driver", "D1", "driver-pass")
        passengers = self.client.get("/passengers/V1")
        self.assertEqual(passengers.status_code, 200)
        self.assertIn(b"Student One", passengers.data)

        self.client.get("/logout")
        self.login("provider", "P1", "provider-pass")
        self.assertEqual(self.client.get("/passengers/V1").status_code, 200)

        self.transport.add_provider("P2", "Other Transport", "0305", "other-pass")
        self.client.get("/logout")
        self.login("provider", "P2", "other-pass")
        self.assertEqual(self.client.get("/passengers/V1").status_code, 403)

    def test_post_without_csrf_token_is_rejected(self):
        self.assertEqual(self.client.post("/", data={"role": "admin", "password": "admin123"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
