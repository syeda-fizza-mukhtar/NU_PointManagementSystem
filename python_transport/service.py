"""Business rules and JSON persistence for the Tkinter portals."""
import json
import os
from datetime import date, datetime
from uuid import uuid4

from structures import Graph, HashTable, Queue, SinglyLinkedList, merge_sort


class TransportError(Exception): pass
class NotFoundError(TransportError): pass
class ValidationError(TransportError): pass


class TransportService:
    def __init__(self, data_file=None):
        self.data_file = data_file or os.path.join(os.path.dirname(__file__), "transport_data.json")
        self.data = self._empty_data()
        self.notifications, self.history = [], SinglyLinkedList()
        self.load()

    @staticmethod
    def _empty_data():
        return {"settings": {"active_semester": "", "admin_password": "admin123"}, "semesters": [],
                "users": [], "drivers": [], "providers": [], "routes": [], "vehicles": [],
                "bookings": [], "payments": [], "waitlists": [], "audit_log": []}

    def load(self):
        if not os.path.exists(self.data_file): return
        try:
            with open(self.data_file, "r", encoding="utf-8") as file: loaded = json.load(file)
            self.data.update(loaded)
        except (OSError, json.JSONDecodeError) as error:
            raise ValidationError(f"Could not load saved data: {error}")

    def save(self):
        with open(self.data_file, "w", encoding="utf-8") as file: json.dump(self.data, file, indent=2)

    def _log(self, action, actor="system"):
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "actor": actor, "action": action}
        self.data["audit_log"].append(entry); self.history.append(entry); self.save()

    def records(self, category, semester_scoped=False):
        records = self.data[category]
        if semester_scoped:
            active = self.active_semester_id()
            records = [record for record in records if record.get("semester_id") == active]
        return records

    def active_semester_id(self):
        semester_id = self.data["settings"].get("active_semester")
        if not semester_id: raise ValidationError("Create and activate a semester first.")
        return semester_id

    def create_semester(self, name, starts, ends, student_fare, faculty_fare, ac_surcharge, student_seats=0, faculty_seats=0):
        if any(item["id"] == name for item in self.data["semesters"]): raise ValidationError("Semester name already exists.")
        if float(student_fare) < 0 or float(faculty_fare) < 0 or float(ac_surcharge) < 0: raise ValidationError("Fares cannot be negative.")
        semester = {"id": name, "name": name, "starts": starts, "ends": ends, "active": True,
                    "student_fare": float(student_fare), "faculty_fare": float(faculty_fare),
                    "ac_surcharge": float(ac_surcharge), "student_seats": int(student_seats), "faculty_seats": int(faculty_seats)}
        for item in self.data["semesters"]: item["active"] = False
        self.data["semesters"].append(semester); self.data["settings"]["active_semester"] = name
        self._log(f"Created and activated semester {name}", "admin")

    def activate_semester(self, semester_id):
        semester = self.find("semesters", semester_id)
        for item in self.data["semesters"]: item["active"] = False
        semester["active"] = True; self.data["settings"]["active_semester"] = semester_id
        self._log(f"Activated semester {semester_id}", "admin")

    def semester(self): return self.find("semesters", self.active_semester_id())

    def find(self, category, record_id):
        index = HashTable()
        for record in self.data[category]: index.set(record["id"], record)
        record = index.get(record_id)
        if record is None: raise NotFoundError(f"{category[:-1].title()} '{record_id}' was not found.")
        return record

    def add_record(self, category, record, actor="admin"):
        if not record.get("id"): record["id"] = f"{category[:3].upper()}-{uuid4().hex[:8]}"
        if any(item["id"] == record["id"] for item in self.data[category]): raise ValidationError("That ID is already in use.")
        self.data[category].append(record); self._log(f"Added {category[:-1]} {record['id']}", actor)
        return record

    def add_user(self, user_id, name, email, phone, role, identifier, password):
        if role not in ("student", "faculty"): raise ValidationError("User role must be student or faculty.")
        return self.add_record("users", {"id": user_id, "name": name, "email": email, "phone": phone,
            "role": role, "identifier": identifier, "password": password, "active": True})

    def authenticate(self, role, user_id, password):
        if role == "admin":
            if password == self.data["settings"].get("admin_password"): return {"id": "admin", "role": "admin", "name": "Administrator"}
            raise ValidationError("Incorrect administrator password.")
        source = "drivers" if role == "driver" else ("providers" if role == "provider" else "users")
        person = self.find(source, user_id)
        if person.get("password") != password or person.get("role", role) != role: raise ValidationError("Incorrect portal, ID, or password.")
        return person

    def add_provider(self, provider_id, name, contact, password): return self.add_record("providers", {"id": provider_id, "name": name, "contact": contact, "password": password})
    def add_driver(self, driver_id, name, license_number, phone, password): return self.add_record("drivers", {"id": driver_id, "name": name, "license_number": license_number, "phone": phone, "password": password})
    def add_route(self, route_id, start, end, distance, stops):
        return self.add_record("routes", {"id": route_id, "semester_id": self.active_semester_id(), "start": start, "end": end, "distance": float(distance), "stops": [part.strip() for part in stops.split(",") if part.strip()]})

    def add_vehicle(self, vehicle_id, registration, vehicle_type, ac, route_id, provider_id, capacity, driver_id=""):
        self.find("routes", route_id); self.find("providers", provider_id)
        if driver_id: self._assert_driver_available(driver_id)
        capacity = int(capacity)
        if capacity <= 0: raise ValidationError("Vehicle capacity must be positive.")
        record = {"id": vehicle_id, "semester_id": self.active_semester_id(), "registration": registration, "type": vehicle_type, "ac": bool(ac), "route_id": route_id,
                  "provider_id": provider_id, "capacity": capacity, "driver_id": driver_id}
        return self.add_record("vehicles", record)

    def _assert_driver_available(self, driver_id, ignore_vehicle=None):
        self.find("drivers", driver_id)
        for vehicle in self.records("vehicles", True):
            if vehicle.get("driver_id") == driver_id and vehicle["id"] != ignore_vehicle: raise ValidationError("Driver already has an active vehicle assignment this semester.")

    def assign_driver(self, vehicle_id, driver_id):
        vehicle = self.find("vehicles", vehicle_id); self._assert_driver_available(driver_id, vehicle_id)
        vehicle["driver_id"] = driver_id; self._log(f"Assigned driver {driver_id} to {vehicle_id}", "admin")

    def fare_for(self, user, vehicle):
        semester = self.semester(); base = semester["student_fare"] if user["role"] == "student" else semester["faculty_fare"]
        return base + (semester["ac_surcharge"] if vehicle["ac"] else 0)

    def vehicle_seats(self, vehicle_id):
        vehicle, semester = self.find("vehicles", vehicle_id), self.semester(); capacity = vehicle["capacity"]
        configured = semester["student_seats"] + semester["faculty_seats"]
        student_count = semester["student_seats"] if configured else (capacity * 3) // 4
        student_count = max(0, min(student_count, capacity)); return [(str(i + 1), "student" if i < student_count else "faculty") for i in range(capacity)]

    def active_booking(self, user_id):
        semester_id = self.active_semester_id()
        return next((item for item in self.data["bookings"] if item["semester_id"] == semester_id and item["user_id"] == user_id and item["status"] == "confirmed"), None)

    def available_seats(self, vehicle_id, role):
        taken = {booking["seat"] for booking in self.records("bookings", True) if booking["vehicle_id"] == vehicle_id and booking["status"] == "confirmed"}
        return [number for number, kind in self.vehicle_seats(vehicle_id) if kind == role and number not in taken]

    def record_payment(self, user_id, amount=None):
        user = self.find("users", user_id); semester_id = self.active_semester_id()
        if amount is None: amount = self.semester()["student_fare"] if user["role"] == "student" else self.semester()["faculty_fare"]
        payment = {"id": f"PAY-{uuid4().hex[:8]}", "semester_id": semester_id, "user_id": user_id, "amount": float(amount), "paid_at": datetime.now().isoformat(timespec="seconds"), "status": "paid"}
        self.data["payments"].append(payment); self._log(f"Recorded payment for {user_id}", user_id); return payment

    def has_payment(self, user_id):
        return any(payment["user_id"] == user_id and payment["semester_id"] == self.active_semester_id() and payment["status"] == "paid" for payment in self.data["payments"])

    def book(self, user_id, vehicle_id, seat):
        user, vehicle = self.find("users", user_id), self.find("vehicles", vehicle_id)
        if self.active_booking(user_id): raise ValidationError("Only one active seat reservation is allowed per semester.")
        if not self.has_payment(user_id): raise ValidationError("Record payment before confirming a booking.")
        if seat not in self.available_seats(vehicle_id, user["role"]): raise ValidationError("Seat is unavailable or not eligible for this user role.")
        booking = {"id": f"BKG-{uuid4().hex[:8]}", "semester_id": self.active_semester_id(), "user_id": user_id, "vehicle_id": vehicle_id,
                   "seat": seat, "fare": self.fare_for(user, vehicle), "booked_at": datetime.now().isoformat(timespec="seconds"), "status": "confirmed", "cancelled_at": None}
        self.data["bookings"].append(booking); self._log(f"Confirmed booking {booking['id']}", user_id); return booking

    def join_waitlist(self, user_id, vehicle_id):
        user = self.find("users", user_id); self.find("vehicles", vehicle_id)
        if self.available_seats(vehicle_id, user["role"]): raise ValidationError("An eligible seat is available; book it directly.")
        if any(item["semester_id"] == self.active_semester_id() and item["vehicle_id"] == vehicle_id and item["user_id"] == user_id for item in self.data["waitlists"]): raise ValidationError("User is already on this waiting list.")
        entry = {"id": f"WAIT-{uuid4().hex[:8]}", "semester_id": self.active_semester_id(), "vehicle_id": vehicle_id, "user_id": user_id, "joined_at": datetime.now().isoformat(timespec="seconds"), "status": "waiting"}
        self.data["waitlists"].append(entry); self._log(f"Added {user_id} to waitlist for {vehicle_id}", user_id); return entry

    def cancel_booking(self, booking_id, actor):
        booking = self.find("bookings", booking_id)
        if booking["status"] != "confirmed": raise ValidationError("Only a confirmed booking can be cancelled.")
        booking["status"], booking["cancelled_at"] = "cancelled", datetime.now().isoformat(timespec="seconds")
        offered = self._offer_waitlisted_seat(booking["vehicle_id"], booking["seat"])
        self._log(f"Cancelled booking {booking_id}" + (f"; offered seat to {offered}" if offered else ""), actor)
        return offered

    def _offer_waitlisted_seat(self, vehicle_id, seat):
        seat_type = next(kind for number, kind in self.vehicle_seats(vehicle_id) if number == seat)
        queue = Queue()
        entries = merge_sort([entry for entry in self.records("waitlists", True) if entry["vehicle_id"] == vehicle_id and entry["status"] == "waiting"], "joined_at")
        for entry in entries: queue.enqueue(entry)
        while queue.size:
            entry = queue.dequeue(); user = self.find("users", entry["user_id"])
            if user["role"] == seat_type and self.has_payment(user["id"]):
                entry["status"] = "offered"; entry["offered_seat"] = seat; return user["id"]
        return None

    def route_graph(self):
        graph = Graph()
        for route in self.records("routes", True):
            stops = [route["start"]] + route.get("stops", []) + [route["end"]]
            segment = route["distance"] / max(1, len(stops) - 1)
            for left, right in zip(stops, stops[1:]): graph.add_edge(left, right, segment)
        return graph

    def report_bookings(self): return merge_sort(self.records("bookings", True), "booked_at")
