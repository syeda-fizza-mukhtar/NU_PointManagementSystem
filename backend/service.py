"""Business rules and JSON persistence for the Flask portals."""
import json
import math
import os
import tempfile
from datetime import date, datetime
from uuid import uuid4

try:  # Enables both ``python app.py`` and package imports by the Flask backend.
    from .structures import (
        BinarySearchTree,
        CircularQueue,
        DisjointSet,
        Graph,
        HashTable,
        Queue,
        SinglyLinkedList,
        binary_search,
        linear_search,
        merge_sort,
    )
except ImportError:
    from structures import (
        BinarySearchTree,
        CircularQueue,
        DisjointSet,
        Graph,
        HashTable,
        Queue,
        SinglyLinkedList,
        binary_search,
        linear_search,
        merge_sort,
    )


class TransportError(Exception): pass
class NotFoundError(TransportError): pass
class ValidationError(TransportError): pass


class TransportService:
    def __init__(self, data_file=None):
        self.data_file = data_file or os.path.join(os.path.dirname(__file__), "transport_data.json")
        self.data = self._empty_data()
        self.notifications, self.history = CircularQueue(), SinglyLinkedList()
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
        directory = os.path.dirname(os.path.abspath(self.data_file))
        descriptor, temporary_path = tempfile.mkstemp(prefix=".transport-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(self.data, file, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self.data_file)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def _log(self, action, actor="system"):
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "actor": actor, "action": action}
        self.data["audit_log"].append(entry); self.history.append(entry); self.notifications.enqueue(entry); self.save()

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
        name = self._required_text(name, "Semester name")
        if any(item["id"] == name for item in self.data["semesters"]): raise ValidationError("Semester name already exists.")
        starts, ends = self._required_text(starts, "Start date"), self._required_text(ends, "End date")
        self._validated_dates(starts, ends)
        semester = {"id": name, "name": name, "starts": starts, "ends": ends, "active": True,
                    "student_fare": self._validated_amount(student_fare, "Student fare"),
                    "faculty_fare": self._validated_amount(faculty_fare, "Faculty fare"),
                    "ac_surcharge": self._validated_amount(ac_surcharge, "AC surcharge"),
                    "student_seats": self._validated_count(student_seats, "Student seats"),
                    "faculty_seats": self._validated_count(faculty_seats, "Faculty seats")}
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

    def search_records(self, category, record_id, semester_scoped=False):
        records = merge_sort(self.records(category, semester_scoped), "id")
        return binary_search(records, record_id)

    def add_record(self, category, record, actor="admin"):
        if not record.get("id"): record["id"] = f"{category[:3].upper()}-{uuid4().hex[:8]}"
        if linear_search(self.data[category], record["id"]) is not None: raise ValidationError("That ID is already in use.")
        self.data[category].append(record); self._log(f"Added {category[:-1]} {record['id']}", actor)
        return record

    @staticmethod
    def _required_text(value, label):
        value = str(value or "").strip()
        if not value:
            raise ValidationError(f"{label} is required.")
        return value

    @staticmethod
    def _validated_dates(starts, ends):
        try:
            start_date, end_date = date.fromisoformat(starts), date.fromisoformat(ends)
        except (TypeError, ValueError):
            raise ValidationError("Enter valid semester start and end dates.") from None
        if end_date < start_date:
            raise ValidationError("Semester end date cannot be before its start date.")

    @staticmethod
    def _validated_amount(value, label, positive=False):
        try:
            amount = float(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{label} must be a valid number.") from None
        if not math.isfinite(amount) or amount < 0 or (positive and amount == 0):
            qualifier = "greater than zero" if positive else "zero or greater"
            raise ValidationError(f"{label} must be {qualifier}.")
        return amount

    @staticmethod
    def _validated_count(value, label, minimum=0):
        try:
            count = int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"{label} must be a whole number.") from None
        if count < minimum:
            raise ValidationError(f"{label} must be at least {minimum}.")
        return count

    @staticmethod
    def _validated_boolean(value, label):
        if isinstance(value, bool):
            return value
        if value is None or value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in ("", "0", "false", "off"):
                return False
            if normalized in ("1", "true", "on"):
                return True
        raise ValidationError(f"{label} must be a valid checkbox value.")

    def add_user(self, user_id, name, email, phone, role, identifier, password):
        if role not in ("student", "faculty"): raise ValidationError("User role must be student or faculty.")
        record = {"id": self._required_text(user_id, "User ID"),
                  "name": self._required_text(name, "Name"),
                  "email": self._required_text(email, "Email"),
                  "phone": self._required_text(phone, "Phone"),
                  "role": role,
                  "identifier": self._required_text(identifier, "Roll or employee number"),
                  "password": self._required_text(password, "Password"), "active": True}
        self._validate_user_identity(record)
        return self.add_record("users", record)

    def _validate_user_identity(self, candidate, ignore_id=None):
        for user in self.data["users"]:
            if user["id"] == ignore_id:
                continue
            if user["email"].casefold() == candidate["email"].casefold():
                raise ValidationError("That email address is already assigned to another user.")
            if user["role"] == candidate["role"] and user["identifier"].casefold() == candidate["identifier"].casefold():
                raise ValidationError("That roll or employee number is already assigned to this portal.")

    def authenticate(self, role, user_id, password):
        if role == "admin":
            if password == self.data["settings"].get("admin_password"): return {"id": "admin", "role": "admin", "name": "Administrator"}
            raise ValidationError("Incorrect administrator password.")
        if role not in ("student", "faculty", "driver", "provider"):
            raise ValidationError("Choose a supported sign-in portal.")
        source = "drivers" if role == "driver" else ("providers" if role == "provider" else "users")
        person = self.find(source, user_id)
        if person.get("active", True) is False:
            raise ValidationError("This account is inactive. Contact an administrator.")
        if person.get("password") != password or person.get("role", role) != role: raise ValidationError("Incorrect portal, ID, or password.")
        return person

    def add_provider(self, provider_id, name, contact, password):
        return self.add_record("providers", {"id": self._required_text(provider_id, "Provider ID"),
            "name": self._required_text(name, "Name"), "contact": self._required_text(contact, "Contact"),
            "password": self._required_text(password, "Password")})

    def add_driver(self, driver_id, name, license_number, phone, password):
        record = {"id": self._required_text(driver_id, "Driver ID"),
            "name": self._required_text(name, "Name"),
            "license_number": self._required_text(license_number, "License number"),
            "phone": self._required_text(phone, "Phone"), "password": self._required_text(password, "Password")}
        if any(driver["license_number"].casefold() == record["license_number"].casefold()
               for driver in self.data["drivers"]):
            raise ValidationError("That license number is already assigned to another driver.")
        return self.add_record("drivers", record)

    def add_route(self, route_id, start, end, distance, stops):
        route_id = self._required_text(route_id, "Route ID")
        start, end = self._required_text(start, "Starting stop"), self._required_text(end, "Destination stop")
        if start.casefold() == end.casefold():
            raise ValidationError("Starting stop and destination must be different.")
        distance = self._validated_amount(distance, "Route distance", positive=True)
        stops = [part.strip() for part in (stops or "").split(",") if part.strip()]
        if any(stop.casefold() in (start.casefold(), end.casefold()) for stop in stops):
            raise ValidationError("Intermediate stops cannot repeat the start or destination.")
        return self.add_record("routes", {"id": route_id, "semester_id": self.active_semester_id(),
            "start": start, "end": end, "distance": distance, "stops": stops})

    def add_vehicle(self, vehicle_id, registration, vehicle_type, ac, route_id, provider_id, capacity, driver_id=""):
        vehicle_id = self._required_text(vehicle_id, "Vehicle ID")
        registration = self._required_text(registration, "Registration")
        vehicle_type = self._required_text(vehicle_type, "Vehicle type")
        if vehicle_type not in ("Bus", "Coaster"):
            raise ValidationError("Vehicle type must be Bus or Coaster.")
        semester_id = self.active_semester_id()
        route_id = self._required_text(route_id, "Route")
        provider_id = self._required_text(provider_id, "Provider")
        route = self.find("routes", route_id)
        if route.get("semester_id") != semester_id:
            raise ValidationError("Choose a route from the active semester.")
        self.find("providers", provider_id)
        driver_id = str(driver_id or "").strip()
        if driver_id: self._assert_driver_available(driver_id)
        capacity = self._validated_count(capacity, "Vehicle capacity", minimum=1)
        self._validate_vehicle_seat_allocation(capacity)
        if any(item.get("semester_id") == semester_id and item["registration"].casefold() == registration.casefold()
               for item in self.data["vehicles"]):
            raise ValidationError("That registration is already used by an active-semester vehicle.")
        record = {"id": vehicle_id, "semester_id": semester_id, "registration": registration, "type": vehicle_type,
                  "ac": self._validated_boolean(ac, "Air-conditioning setting"), "route_id": route_id,
                  "provider_id": provider_id, "capacity": capacity,
                  "driver_id": driver_id or ""}
        return self.add_record("vehicles", record)

    def _assert_driver_available(self, driver_id, ignore_vehicle=None):
        driver = self.find("drivers", driver_id)
        if driver.get("active", True) is False:
            raise ValidationError("This driver account is inactive.")
        for vehicle in self.records("vehicles", True):
            if vehicle.get("driver_id") == driver_id and vehicle["id"] != ignore_vehicle: raise ValidationError("Driver already has an active vehicle assignment this semester.")

    def assign_driver(self, vehicle_id, driver_id):
        vehicle = self._active_record("vehicles", vehicle_id)
        if vehicle.get("driver_id") and vehicle["driver_id"] != driver_id:
            raise ValidationError("Vehicle already has a driver assigned. Remove the current assignment first.")
        self._assert_driver_available(driver_id, vehicle_id)
        vehicle["driver_id"] = driver_id; self._log(f"Assigned driver {driver_id} to {vehicle_id}", "admin")

    def _active_record(self, category, record_id):
        record = self.find(category, record_id)
        if record.get("semester_id") != self.active_semester_id():
            raise ValidationError(f"Choose a {category[:-1]} from the active semester.")
        return record

    def _validate_vehicle_seat_allocation(self, capacity):
        semester = self.semester()
        allocated = semester["student_seats"] + semester["faculty_seats"]
        if allocated and capacity < allocated:
            raise ValidationError(f"Vehicle capacity must be at least the configured seat allocation of {allocated}.")

    def update_record(self, category, record_id, values, actor="admin"):
        editable = {
            "semesters": ("starts", "ends", "student_fare", "faculty_fare", "ac_surcharge", "student_seats", "faculty_seats"),
            "users": ("name", "email", "phone", "role", "identifier", "password", "active"),
            "providers": ("name", "contact", "password"),
            "drivers": ("name", "license_number", "phone", "password"),
            "routes": ("start", "end", "distance", "stops"),
            "vehicles": ("registration", "type", "ac", "route_id", "provider_id", "capacity", "driver_id"),
        }
        if category not in editable:
            raise ValidationError("This record type is managed through its operational workflow.")
        record = self.find(category, record_id)
        if category in ("routes", "vehicles"):
            record = self._active_record(category, record_id)
        changes = {key: values[key] for key in editable[category] if key in values}
        if "password" in changes and not str(changes["password"] or "").strip():
            changes.pop("password")
        if not changes:
            raise ValidationError("No changes were provided.")

        if category == "semesters":
            related = ("routes", "vehicles", "bookings", "payments", "waitlists")
            if any(item.get("semester_id") == record_id for table in related for item in self.data[table]):
                raise ValidationError("Semester settings cannot be edited after routes, vehicles, or transactions are recorded.")
            starts = self._required_text(changes.get("starts", record["starts"]), "Start date")
            ends = self._required_text(changes.get("ends", record["ends"]), "End date")
            self._validated_dates(starts, ends)
            changes.update({
                "starts": starts, "ends": ends,
                "student_fare": self._validated_amount(changes.get("student_fare", record["student_fare"]), "Student fare"),
                "faculty_fare": self._validated_amount(changes.get("faculty_fare", record["faculty_fare"]), "Faculty fare"),
                "ac_surcharge": self._validated_amount(changes.get("ac_surcharge", record["ac_surcharge"]), "AC surcharge"),
                "student_seats": self._validated_count(changes.get("student_seats", record["student_seats"]), "Student seats"),
                "faculty_seats": self._validated_count(changes.get("faculty_seats", record["faculty_seats"]), "Faculty seats"),
            })
        elif category == "users":
            if changes.get("role", record["role"]) not in ("student", "faculty"):
                raise ValidationError("User role must be student or faculty.")
            for key, label in (("name", "Name"), ("email", "Email"), ("phone", "Phone"), ("identifier", "Roll or employee number")):
                if key in changes:
                    changes[key] = self._required_text(changes[key], label)
            if "active" in changes:
                changes["active"] = self._validated_boolean(changes["active"], "Account status")
            candidate = dict(record, **changes)
            self._validate_user_identity(candidate, ignore_id=record_id)
            if candidate["role"] != record["role"] and any(
                item["user_id"] == record_id
                for table in ("bookings", "payments", "waitlists")
                for item in self.data[table]
            ):
                raise ValidationError("A user's portal cannot change while booking, payment, or waitlist history exists.")
        elif category == "providers":
            for key, label in (("name", "Name"), ("contact", "Contact")):
                if key in changes:
                    changes[key] = self._required_text(changes[key], label)
        elif category == "drivers":
            for key, label in (("name", "Name"), ("license_number", "License number"), ("phone", "Phone")):
                if key in changes:
                    changes[key] = self._required_text(changes[key], label)
            license_number = changes.get("license_number", record["license_number"])
            if any(driver["id"] != record_id and driver["license_number"].casefold() == license_number.casefold()
                   for driver in self.data["drivers"]):
                raise ValidationError("That license number is already assigned to another driver.")
        elif category == "routes":
            has_bookings = any(
                vehicle["route_id"] == record_id and any(
                    item["vehicle_id"] == vehicle["id"] for table in ("bookings", "payments", "waitlists")
                    for item in self.data[table]
                )
                for vehicle in self.data["vehicles"]
            )
            if has_bookings:
                raise ValidationError("A route with payment or booking history cannot be changed.")
            start = self._required_text(changes.get("start", record["start"]), "Starting stop")
            end = self._required_text(changes.get("end", record["end"]), "Destination stop")
            if start.casefold() == end.casefold():
                raise ValidationError("Starting stop and destination must be different.")
            stops_value = changes.get("stops", record.get("stops", []))
            stops = stops_value if isinstance(stops_value, list) else str(stops_value or "").split(",")
            stops = [str(part).strip() for part in stops if str(part).strip()]
            if any(stop.casefold() in (start.casefold(), end.casefold()) for stop in stops):
                raise ValidationError("Intermediate stops cannot repeat the start or destination.")
            changes.update({"start": start, "end": end, "stops": stops,
                            "distance": self._validated_amount(changes.get("distance", record["distance"]), "Route distance", positive=True)})
        elif category == "vehicles":
            route_id = self._required_text(changes.get("route_id", record["route_id"]), "Route")
            route = self.find("routes", route_id)
            if route.get("semester_id") != record["semester_id"]:
                raise ValidationError("Choose a route from the vehicle's semester.")
            provider_id = self._required_text(changes.get("provider_id", record["provider_id"]), "Provider")
            self.find("providers", provider_id)
            driver_id = str(changes.get("driver_id", record.get("driver_id", "")) or "").strip()
            if driver_id and driver_id != record.get("driver_id"):
                self._assert_driver_available(driver_id, record_id)
            capacity = self._validated_count(changes.get("capacity", record["capacity"]), "Vehicle capacity", minimum=1)
            self._validate_vehicle_seat_allocation(capacity)
            registration = self._required_text(changes.get("registration", record["registration"]), "Registration")
            vehicle_type = self._required_text(changes.get("type", record["type"]), "Vehicle type")
            if vehicle_type not in ("Bus", "Coaster"):
                raise ValidationError("Vehicle type must be Bus or Coaster.")
            if any(item["id"] != record_id and item.get("semester_id") == record["semester_id"]
                   and item["registration"].casefold() == registration.casefold()
                   for item in self.data["vehicles"]):
                raise ValidationError("That registration is already used by another vehicle this semester.")
            has_history = any(
                item["vehicle_id"] == record_id
                for table in ("bookings", "payments", "waitlists")
                for item in self.data[table]
            )
            if has_history and any(
                changes.get(key, record.get(key)) != record.get(key)
                for key in ("registration", "type", "ac", "route_id", "provider_id", "capacity")
            ):
                raise ValidationError("A vehicle with transaction history cannot have its fare or transport details changed.")
            used_seats = [int(item["seat"]) for item in self.data["bookings"]
                          if item["vehicle_id"] == record_id and item["status"] == "confirmed"]
            used_seats.extend(int(item["offered_seat"]) for item in self.data["waitlists"]
                              if item["vehicle_id"] == record_id and item["status"] == "offered")
            if used_seats and capacity < max(used_seats):
                raise ValidationError("Capacity cannot be lower than a confirmed or offered seat.")
            changes.update({"registration": registration, "type": vehicle_type,
                            "route_id": route_id, "provider_id": provider_id, "driver_id": driver_id,
                            "capacity": capacity,
                            "ac": self._validated_boolean(changes.get("ac", record["ac"]), "Air-conditioning setting")})

        record.update(changes)
        self._log(f"Updated {category[:-1]} {record_id}", actor)
        return record

    def delete_record(self, category, record_id, actor="admin"):
        allowed = {"semesters", "users", "providers", "drivers", "routes", "vehicles"}
        if category not in allowed:
            raise ValidationError("Bookings, payments, waitlists, and audit history cannot be deleted.")
        record = self.find(category, record_id)
        dependencies = {
            "semesters": (("routes", "semester_id"), ("vehicles", "semester_id"), ("bookings", "semester_id"),
                          ("payments", "semester_id"), ("waitlists", "semester_id")),
            "users": (("bookings", "user_id"), ("payments", "user_id"), ("waitlists", "user_id")),
            "providers": (("vehicles", "provider_id"),),
            "drivers": (("vehicles", "driver_id"),),
            "routes": (("vehicles", "route_id"),),
            "vehicles": (("bookings", "vehicle_id"), ("payments", "vehicle_id"), ("waitlists", "vehicle_id")),
        }
        if category == "semesters" and record_id == self.data["settings"].get("active_semester"):
            raise ValidationError("Activate another semester before deleting this one.")
        if any(item.get(field) == record_id for table, field in dependencies[category] for item in self.data[table]):
            raise ValidationError(f"This {category[:-1]} is still referenced by related records and cannot be deleted.")
        self.data[category].remove(record)
        self._log(f"Deleted {category[:-1]} {record_id}", actor)

    def fare_for(self, user, vehicle):
        semester = self.semester(); base = semester["student_fare"] if user["role"] == "student" else semester["faculty_fare"]
        return base + (semester["ac_surcharge"] if vehicle["ac"] else 0)

    def vehicle_seats(self, vehicle_id):
        vehicle, semester = self._active_record("vehicles", vehicle_id), self.semester(); capacity = vehicle["capacity"]
        configured = semester["student_seats"] + semester["faculty_seats"]
        if configured:
            student_count = min(semester["student_seats"], capacity)
            faculty_count = min(semester["faculty_seats"], capacity - student_count)
        else:
            student_count = (capacity * 3) // 4
            faculty_count = capacity - student_count
        return ([(str(i + 1), "student") for i in range(student_count)] +
                [(str(student_count + i + 1), "faculty") for i in range(faculty_count)])

    def active_booking(self, user_id):
        semester_id = self.active_semester_id()
        return next((item for item in self.data["bookings"] if item["semester_id"] == semester_id and item["user_id"] == user_id and item["status"] == "confirmed"), None)

    def available_seats(self, vehicle_id, role):
        taken = {booking["seat"] for booking in self.records("bookings", True) if booking["vehicle_id"] == vehicle_id and booking["status"] == "confirmed"}
        taken.update(entry.get("offered_seat") for entry in self.records("waitlists", True)
                     if entry["vehicle_id"] == vehicle_id and entry["status"] == "offered")
        return [number for number, kind in self.vehicle_seats(vehicle_id) if kind == role and number not in taken]

    def record_payment(self, user_id, vehicle_id, amount=None):
        user, vehicle = self.find("users", user_id), self._active_record("vehicles", vehicle_id)
        semester_id, required = self.active_semester_id(), self.fare_for(user, vehicle)
        if self.has_payment(user_id, vehicle_id):
            raise ValidationError("Payment is already recorded for this vehicle and semester.")
        if amount is None: amount = required
        amount = self._validated_amount(amount, "Payment")
        if amount < required: raise ValidationError(f"Payment must cover the full semester fare of Rs. {required:.0f}.")
        payment = {"id": f"PAY-{uuid4().hex[:8]}", "semester_id": semester_id, "user_id": user_id, "vehicle_id": vehicle_id, "amount": amount, "paid_at": datetime.now().isoformat(timespec="seconds"), "status": "paid"}
        self.data["payments"].append(payment); self._log(f"Recorded payment for {user_id}", user_id); return payment

    def has_payment(self, user_id, vehicle_id):
        return any(payment["user_id"] == user_id and payment.get("vehicle_id") == vehicle_id and payment["semester_id"] == self.active_semester_id() and payment["status"] == "paid" for payment in self.data["payments"])

    def book(self, user_id, vehicle_id, seat):
        user, vehicle = self.find("users", user_id), self._active_record("vehicles", vehicle_id)
        if self.active_booking(user_id): raise ValidationError("Only one active seat reservation is allowed per semester.")
        if not self.has_payment(user_id, vehicle_id): raise ValidationError("Record the full payment for this vehicle before confirming a booking.")
        seat_role = next((kind for number, kind in self.vehicle_seats(vehicle_id) if number == seat), None)
        offer = next((entry for entry in self.records("waitlists", True)
                      if entry["vehicle_id"] == vehicle_id and entry["user_id"] == user_id
                      and entry["status"] == "offered" and entry.get("offered_seat") == seat), None)
        if seat_role != user["role"] or (offer is None and seat not in self.available_seats(vehicle_id, user["role"])):
            raise ValidationError("Seat is unavailable or not eligible for this user role.")
        booking = {"id": f"BKG-{uuid4().hex[:8]}", "semester_id": self.active_semester_id(), "user_id": user_id, "vehicle_id": vehicle_id,
                   "seat": seat, "fare": self.fare_for(user, vehicle), "booked_at": datetime.now().isoformat(timespec="seconds"), "status": "confirmed", "cancelled_at": None}
        self.data["bookings"].append(booking)
        if offer is not None: offer["status"] = "accepted"
        self._log(f"Confirmed booking {booking['id']}", user_id); return booking

    def join_waitlist(self, user_id, vehicle_id):
        user = self.find("users", user_id); self._active_record("vehicles", vehicle_id)
        if self.active_booking(user_id): raise ValidationError("Cancel your active semester booking before joining another waiting list.")
        if not self.has_payment(user_id, vehicle_id): raise ValidationError("Record the full payment for this vehicle before joining its waiting list.")
        if self.available_seats(vehicle_id, user["role"]): raise ValidationError("An eligible seat is available; book it directly.")
        if any(item["semester_id"] == self.active_semester_id() and item["vehicle_id"] == vehicle_id
               and item["user_id"] == user_id and item["status"] in ("waiting", "offered")
               for item in self.data["waitlists"]):
            raise ValidationError("User is already on this waiting list.")
        entry = {"id": f"WAIT-{uuid4().hex[:8]}", "semester_id": self.active_semester_id(), "vehicle_id": vehicle_id, "user_id": user_id, "joined_at": datetime.now().isoformat(timespec="seconds"), "status": "waiting"}
        self.data["waitlists"].append(entry); self._log(f"Added {user_id} to waitlist for {vehicle_id}", user_id); return entry

    def leave_waitlist(self, user_id, entry_id):
        entry = self.find("waitlists", entry_id)
        if entry["user_id"] != user_id:
            raise ValidationError("You can only leave your own waiting-list entries.")
        if entry["semester_id"] != self.active_semester_id():
            raise ValidationError("Only current-semester waiting-list entries can be changed.")
        if entry["status"] not in ("waiting", "offered"):
            raise ValidationError("This waiting-list entry is no longer active.")
        seat = entry.get("offered_seat") if entry["status"] == "offered" else None
        entry["status"] = "cancelled"
        entry["cancelled_at"] = datetime.now().isoformat(timespec="seconds")
        next_offer = self._offer_waitlisted_seat(entry["vehicle_id"], seat) if seat else None
        self._log(f"Removed {user_id} from waitlist {entry_id}" +
                  (f"; offered seat to {next_offer}" if next_offer else ""), user_id)
        return next_offer

    def cancel_booking(self, booking_id, actor):
        booking = self.find("bookings", booking_id)
        if booking["semester_id"] != self.active_semester_id():
            raise ValidationError("Only current-semester bookings can be cancelled.")
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
            if user["role"] == seat_type and not self.active_booking(user["id"]) and self.has_payment(user["id"], vehicle_id):
                entry["status"] = "offered"; entry["offered_seat"] = seat; return user["id"]
        return None

    def route_graph(self):
        graph = Graph()
        for route in self.records("routes", True):
            stops = [route["start"]] + route.get("stops", []) + [route["end"]]
            segment = route["distance"] / max(1, len(stops) - 1)
            for left, right in zip(stops, stops[1:]): graph.add_edge(left, right, segment)
        return graph

    def route_networks(self):
        networks, connected = {}, DisjointSet()
        for route in self.records("routes", True):
            stops = [route["start"]] + route.get("stops", []) + [route["end"]]
            for stop in stops:
                connected.add(stop)
            for left, right in zip(stops, stops[1:]):
                connected.union(left, right)
        for stop in connected.parent:
            root = connected.find(stop)
            networks.setdefault(root, []).append(stop)
        return list(networks.values())

    def report_bookings(self):
        tree = BinarySearchTree()
        for booking in self.records("bookings", True):
            tree.insert((booking["booked_at"], booking["id"]), booking)
        return tree.inorder()
