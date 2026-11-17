"""End-to-end checks for the persistence and business-rule layer.

Run from the repository root with: python -m unittest backend.test_service
"""
import os
import tempfile
import unittest

from backend.service import TransportService, ValidationError


class TransportServiceTests(unittest.TestCase):
    def setUp(self):
        descriptor, self.file = tempfile.mkstemp(suffix=".json")
        os.close(descriptor)
        os.unlink(self.file)
        self.service = TransportService(self.file)
        self.service.create_semester("Spring-2027", "2027-01-01", "2027-06-30", 1500, 2500, 2000, 1, 1)
        self.service.add_provider("P1", "Campus Transport", "0300", "provider-pass")
        self.service.add_driver("D1", "Driver One", "LIC-1", "0300", "driver-pass")
        self.service.add_driver("D2", "Driver Two", "LIC-2", "0301", "driver-pass")
        self.service.add_route("R1", "Gulberg", "FAST", 10, "Liberty")
        self.service.add_vehicle("V1", "ABC-001", "Bus", True, "R1", "P1", 2, "D1")
        self.service.add_user("S1", "Student One", "s1@test", "0300", "student", "ROLL-1", "pass")
        self.service.add_user("S2", "Student Two", "s2@test", "0301", "student", "ROLL-2", "pass")
        self.service.add_user("F1", "Faculty One", "f1@test", "0302", "faculty", "EMP-1", "pass")

    def tearDown(self):
        if os.path.exists(self.file): os.unlink(self.file)

    def test_booking_payment_waitlist_cancellation_and_persistence(self):
        with self.assertRaises(ValidationError): self.service.book("S1", "V1", "1")
        with self.assertRaises(ValidationError): self.service.record_payment("S1", "V1", 1500)
        self.assertEqual(self.service.record_payment("S1", "V1")["amount"], 3500)
        first = self.service.book("S1", "V1", "1")
        with self.assertRaises(ValidationError): self.service.book("S1", "V1", "1")
        self.service.record_payment("S2", "V1")
        waiting = self.service.join_waitlist("S2", "V1")
        offered_to = self.service.cancel_booking(first["id"], "S1")
        self.assertEqual(offered_to, "S2")
        self.assertEqual(waiting["status"], "offered")
        self.assertEqual(self.service.find("bookings", first["id"])["status"], "cancelled")
        self.assertEqual(self.service.available_seats("V1", "student"), [])
        accepted = self.service.book("S2", "V1", "1")
        self.assertEqual(accepted["user_id"], "S2")
        self.assertEqual(waiting["status"], "accepted")
        reloaded = TransportService(self.file)
        self.assertEqual(reloaded.find("bookings", first["id"])["status"], "cancelled")
        self.assertEqual(reloaded.find("waitlists", waiting["id"])["status"], "accepted")

    def test_roles_seats_assignment_and_graph(self):
        self.assertEqual(self.service.available_seats("V1", "student"), ["1"])
        self.assertEqual(self.service.available_seats("V1", "faculty"), ["2"])
        self.service.add_vehicle("V2", "XYZ-002", "Bus", False, "R1", "P1", 20)
        self.assertEqual(self.service.vehicle_seats("V2"), [("1", "student"), ("2", "faculty")])
        with self.assertRaises(ValidationError):
            self.service.add_vehicle("V3", "XYZ-003", "Bus", False, "R1", "P1", 1)
        with self.assertRaises(ValidationError): self.service.assign_driver("V1", "D2")
        self.assertEqual(self.service.search_records("users", "S2")["id"], "S2")
        self.assertIsNone(self.service.search_records("users", "missing"))
        self.assertEqual(set(self.service.route_networks()[0]), {"Gulberg", "Liberty", "FAST"})
        self.assertTrue(self.service.notifications.values())
        graph = self.service.route_graph()
        self.assertEqual(graph.bfs("Gulberg"), ["Gulberg", "Liberty", "FAST"])
        self.assertEqual(set(graph.dfs("Gulberg")), {"Gulberg", "Liberty", "FAST"})
        path, distance = graph.shortest_path("Gulberg", "FAST")
        self.assertEqual(path, ["Gulberg", "Liberty", "FAST"])
        self.assertEqual(distance, 10.0)

    def test_new_semester_keeps_previous_history_separate(self):
        self.service.record_payment("S1", "V1")
        booking = self.service.book("S1", "V1", "1")
        self.assertEqual(self.service.report_bookings(), [booking])
        self.service.create_semester("Fall-2027", "2027-08-01", "2027-12-31", 1600, 2600, 2100, 1, 1)
        self.assertEqual(self.service.records("bookings", True), [])
        self.assertEqual(self.service.find("bookings", booking["id"])["semester_id"], "Spring-2027")
        with self.assertRaises(ValidationError):
            self.service.record_payment("S1", "V1")
        with self.assertRaises(ValidationError):
            self.service.book("S1", "V1", "1")
        with self.assertRaises(ValidationError):
            self.service.join_waitlist("S1", "V1")
        with self.assertRaises(ValidationError):
            self.service.assign_driver("V1", "D2")

        self.service.add_route("R2", "DHA", "FAST", 8, "Model Town")
        self.service.add_vehicle("V2", "XYZ-002", "Coaster", False, "R2", "P1", 2)
        self.service.record_payment("S1", "V2")
        current_booking = self.service.book("S1", "V2", "1")
        self.assertEqual(self.service.report_bookings(), [current_booking])
        self.assertEqual(self.service.find("bookings", booking["id"])["status"], "confirmed")

    def test_record_changes_protect_transaction_consistency(self):
        self.service.record_payment("S1", "V1")
        booking = self.service.book("S1", "V1", "1")
        with self.assertRaises(ValidationError):
            self.service.record_payment("S1", "V1")
        with self.assertRaises(ValidationError):
            self.service.update_record("users", "S1", {"role": "faculty"})
        with self.assertRaises(ValidationError):
            self.service.update_record("vehicles", "V1", {"ac": False})
        with self.assertRaises(ValidationError):
            self.service.update_record("routes", "R1", {"start": "DHA"})
        for category, record_id in (("users", "S1"), ("vehicles", "V1"), ("routes", "R1"),
                                    ("providers", "P1"), ("drivers", "D1")):
            with self.assertRaises(ValidationError):
                self.service.delete_record(category, record_id)

        updated_user = self.service.update_record("users", "S1", {"name": "Student Updated"})
        self.assertEqual(updated_user["name"], "Student Updated")
        self.assertEqual(self.service.find("bookings", booking["id"])["user_id"], "S1")

    def test_leaving_an_offered_waitlist_seat_passes_it_to_the_next_member(self):
        self.service.record_payment("S1", "V1")
        booking = self.service.book("S1", "V1", "1")
        self.service.add_user("S3", "Student Three", "s3@test", "0305", "student", "ROLL-3", "pass")
        self.service.record_payment("S2", "V1")
        self.service.record_payment("S3", "V1")
        first_waitlist = self.service.join_waitlist("S2", "V1")
        next_waitlist = self.service.join_waitlist("S3", "V1")

        self.service.cancel_booking(booking["id"], "S1")
        next_offer = self.service.leave_waitlist("S2", first_waitlist["id"])
        self.assertEqual(next_offer, "S3")
        self.assertEqual(first_waitlist["status"], "cancelled")
        self.assertEqual(next_waitlist["status"], "offered")
        self.assertEqual(next_waitlist["offered_seat"], "1")


if __name__ == "__main__":
    unittest.main()
