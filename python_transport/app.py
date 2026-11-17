"""Tkinter desktop application entry point.

Run from this folder with:  python app.py
Default administrator password: admin123
"""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from service import NotFoundError, TransportError, TransportService, ValidationError


class TransportApp(tk.Tk):
    def __init__(self):
        super().__init__()
        super().title("FAST-NUCES Transport Management System")
        self.geometry("1040x690")
        self.minsize(900, 600)
        self.service, self.user = TransportService(), None
        self._frame = None
        self.show_login()

    def show(self, builder):
        if self._frame: self._frame.destroy()
        self._frame = ttk.Frame(self, padding=24); self._frame.pack(fill="both", expand=True)
        builder(self._frame)

    def heading(self, parent, text, subtitle=""):
        ttk.Label(parent, text=text, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        if subtitle: ttk.Label(parent, text=subtitle, foreground="#555").pack(anchor="w", pady=(3, 20))

    def button(self, parent, text, command, row=None, column=None):
        widget = ttk.Button(parent, text=text, command=command)
        if row is None: widget.pack(fill="x", pady=4)
        else: widget.grid(row=row, column=column, padx=6, pady=6, sticky="ew")
        return widget

    def run_action(self, callback):
        try: callback()
        except TransportError as error: messagebox.showerror("Transport system", str(error))
        except ValueError: messagebox.showerror("Invalid value", "Please enter a valid number where required.")

    def show_login(self):
        def build(parent):
            self.heading(parent, "FAST-NUCES Transport Management", "Python desktop system | Semester-based transport records")
            card = ttk.LabelFrame(parent, text="Sign in to a portal", padding=20); card.pack(fill="x", pady=15)
            ttk.Label(card, text="Portal").grid(row=0, column=0, sticky="w", pady=8)
            role = tk.StringVar(value="student")
            roles = ttk.Combobox(card, textvariable=role, state="readonly", values=("admin", "student", "faculty", "driver", "provider")); roles.grid(row=0, column=1, sticky="ew", pady=8)
            ttk.Label(card, text="ID (administrator ID is optional)").grid(row=1, column=0, sticky="w", pady=8)
            user_id = ttk.Entry(card); user_id.grid(row=1, column=1, sticky="ew", pady=8)
            ttk.Label(card, text="Password").grid(row=2, column=0, sticky="w", pady=8)
            password = ttk.Entry(card, show="*"); password.grid(row=2, column=1, sticky="ew", pady=8)
            card.columnconfigure(1, weight=1)
            def login():
                self.user = self.service.authenticate(role.get(), user_id.get().strip(), password.get())
                self.show_portal()
            self.button(card, "Sign in", lambda: self.run_action(login), 3, 1)
            ttk.Label(parent, text="The administrator sets all fares, capacity rules and active semesters. Initial admin password: admin123", foreground="#555").pack(anchor="w", pady=10)
        self.show(build)

    def topbar(self, parent, name):
        row = ttk.Frame(parent); row.pack(fill="x")
        ttk.Label(row, text=f"{name} portal", font=("Segoe UI", 22, "bold")).pack(side="left")
        ttk.Button(row, text="Sign out", command=self.show_login).pack(side="right")
        try: active = self.service.semester()["name"]
        except TransportError: active = "No active semester"
        ttk.Label(parent, text=f"Active semester: {active}", foreground="#555").pack(anchor="w", pady=(3, 18))

    def show_portal(self):
        role = self.user["role"]
        if role == "admin": self.admin_portal()
        elif role in ("student", "faculty"): self.member_portal()
        elif role == "driver": self.driver_portal()
        else: self.provider_portal()

    def admin_portal(self):
        def build(parent):
            self.topbar(parent, "Administrator")
            grid = ttk.Frame(parent); grid.pack(fill="x")
            actions = [("Semester & fares", self.semester_form), ("Register users", self.user_form), ("Providers", self.provider_form),
                       ("Drivers", self.driver_form), ("Routes", self.route_form), ("Vehicles", self.vehicle_form),
                       ("Assign driver", self.assign_driver), ("View records", self.admin_records), ("Route explorer", self.route_explorer), ("Booking report", self.booking_report)]
            for index, (label, action) in enumerate(actions): self.button(grid, label, action, index // 2, index % 2)
            for col in range(2): grid.columnconfigure(col, weight=1)
            ttk.Label(parent, text="Administrator controls: semester settings, price rules, accounts, providers, vehicles, routes, driver assignments, and reports.", wraplength=850, foreground="#555").pack(anchor="w", pady=20)
        self.show(build)

    def member_portal(self):
        def build(parent):
            self.topbar(parent, self.user["role"].title())
            ttk.Label(parent, text=f"Welcome, {self.user['name']}", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(0, 12))
            grid = ttk.Frame(parent); grid.pack(fill="x")
            actions = [("Browse routes & vehicles", self.member_vehicles), ("Record semester payment", self.payment_form),
                       ("Book a seat", self.booking_form), ("Join waiting list", self.waitlist_form),
                       ("My bookings", self.my_bookings), ("Cancel a booking", self.cancel_my_booking), ("Route explorer", self.route_explorer)]
            for index, (label, action) in enumerate(actions): self.button(grid, label, action, index // 2, index % 2)
            for col in range(2): grid.columnconfigure(col, weight=1)
        self.show(build)

    def driver_portal(self):
        def build(parent):
            self.topbar(parent, "Driver")
            ttk.Label(parent, text=f"Welcome, {self.user['name']}", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(0, 12))
            assignment = next((v for v in self.service.records("vehicles", True) if v.get("driver_id") == self.user["id"]), None)
            if assignment:
                route = self.service.find("routes", assignment["route_id"])
                ttk.Label(parent, text=f"Assigned vehicle: {assignment['id']} ({assignment['registration']})\nRoute: {route['start']} → {route['end']}\nCapacity: {assignment['capacity']}").pack(anchor="w")
                self.button(parent, "View confirmed passenger list", lambda: self.passenger_list(assignment["id"]))
            else: ttk.Label(parent, text="No active vehicle assignment for the current semester.").pack(anchor="w")
            self.button(parent, "Route explorer", self.route_explorer)
        self.show(build)

    def provider_portal(self):
        def build(parent):
            self.topbar(parent, "Transport provider")
            ttk.Label(parent, text=f"Welcome, {self.user['name']}", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(0, 12))
            vehicles = [v for v in self.service.records("vehicles", True) if v["provider_id"] == self.user["id"]]
            self.table(parent, ["ID", "Registration", "Type", "Driver", "Capacity"], [[v["id"], v["registration"], v["type"], v.get("driver_id", "Unassigned"), v["capacity"]] for v in vehicles])
            self.button(parent, "View provider passenger lists", lambda: self.provider_passengers(vehicles))
        self.show(build)

    def form_window(self, title, fields, submit_text, handler):
        window = tk.Toplevel(self); window.title(title); window.geometry("520x520"); body = ttk.Frame(window, padding=18); body.pack(fill="both", expand=True)
        values = {}
        for row, (key, label, default, kind) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", padx=5, pady=6)
            if kind == "bool": value = tk.BooleanVar(value=bool(default)); widget = ttk.Checkbutton(body, variable=value)
            elif kind.startswith("choice:"):
                value = tk.StringVar(value=default); widget = ttk.Combobox(body, textvariable=value, values=kind.split(":", 1)[1].split("|"), state="readonly")
            else: value = tk.StringVar(value=str(default)); widget = ttk.Entry(body, textvariable=value, show="*" if kind == "password" else "")
            widget.grid(row=row, column=1, sticky="ew", padx=5, pady=6); values[key] = value
        body.columnconfigure(1, weight=1)
        def submit():
            try: handler({key: value.get() for key, value in values.items()}); window.destroy(); self.show_portal()
            except TransportError as error: messagebox.showerror(title, str(error), parent=window)
            except ValueError: messagebox.showerror(title, "Enter valid numeric values.", parent=window)
        ttk.Button(body, text=submit_text, command=submit).grid(row=len(fields), column=1, sticky="e", pady=14)

    def semester_form(self):
        self.form_window("Create and activate semester", [("name", "Semester name", "Spring-2027", "text"), ("starts", "Start date (YYYY-MM-DD)", "2027-01-01", "text"), ("ends", "End date (YYYY-MM-DD)", "2027-06-30", "text"), ("student_fare", "Student base fare (Rs.)", "0", "text"), ("faculty_fare", "Faculty base fare (Rs.)", "0", "text"), ("ac_surcharge", "AC surcharge (Rs.)", "0", "text"), ("student_seats", "Student seats per vehicle (0=automatic)", "0", "text"), ("faculty_seats", "Faculty seats per vehicle (0=automatic)", "0", "text")], "Save semester", lambda v: self.service.create_semester(**v))

    def user_form(self):
        self.form_window("Register student or faculty", [("id", "User ID", "", "text"), ("name", "Full name", "", "text"), ("email", "Email", "", "text"), ("phone", "Phone", "", "text"), ("role", "Role", "student", "choice:student|faculty"), ("identifier", "Roll / employee number", "", "text"), ("password", "Portal password", "", "password")], "Register", lambda v: self.service.add_user(**v))

    def provider_form(self):
        self.form_window("Add transport provider", [("provider_id", "Provider ID", "", "text"), ("name", "Provider name", "", "text"), ("contact", "Contact", "", "text"), ("password", "Portal password", "", "password")], "Save", lambda v: self.service.add_provider(**v))

    def driver_form(self):
        self.form_window("Add driver", [("driver_id", "Driver ID", "", "text"), ("name", "Name", "", "text"), ("license_number", "License number", "", "text"), ("phone", "Phone", "", "text"), ("password", "Portal password", "", "password")], "Save", lambda v: self.service.add_driver(**v))

    def route_form(self):
        self.form_window("Add route", [("route_id", "Route ID", "", "text"), ("start", "Start location", "", "text"), ("end", "End location", "", "text"), ("distance", "Total distance (km)", "0", "text"), ("stops", "Intermediate stops (comma-separated)", "", "text")], "Save", lambda v: self.service.add_route(**v))

    def vehicle_form(self):
        self.form_window("Add vehicle", [("vehicle_id", "Vehicle ID", "", "text"), ("registration", "Registration number", "", "text"), ("vehicle_type", "Type (Bus/Coaster)", "Bus", "text"), ("ac", "Air conditioned", False, "bool"), ("route_id", "Route ID", "", "text"), ("provider_id", "Provider ID", "", "text"), ("capacity", "Capacity", "52", "text"), ("driver_id", "Driver ID (optional)", "", "text")], "Save", lambda v: self.service.add_vehicle(**v))

    def assign_driver(self):
        self.form_window("Assign driver", [("vehicle_id", "Vehicle ID", "", "text"), ("driver_id", "Driver ID", "", "text")], "Assign", lambda v: self.service.assign_driver(**v))

    def member_vehicles(self):
        def build(parent):
            self.topbar(parent, self.user["role"].title())
            rows = []
            for vehicle in self.service.records("vehicles", True):
                route = self.service.find("routes", vehicle["route_id"]); fare = self.service.fare_for(self.user, vehicle)
                rows.append([vehicle["id"], vehicle["type"], f"{route['start']} → {route['end']}", "AC" if vehicle["ac"] else "Non-AC", str(len(self.service.available_seats(vehicle["id"], self.user["role"]))), f"Rs. {fare:.0f}"])
            self.table(parent, ["Vehicle", "Type", "Route", "Amenity", "Eligible seats", "Semester fare"], rows)
            self.button(parent, "Back", self.show_portal)
        self.show(build)

    def payment_form(self):
        def paid():
            payment = self.service.record_payment(self.user["id"]); messagebox.showinfo("Payment recorded", f"Payment of Rs. {payment['amount']:.0f} was recorded."); self.show_portal()
        self.run_action(paid)

    def booking_form(self):
        def build(parent):
            self.topbar(parent, self.user["role"].title()); self.heading(parent, "Book an eligible seat")
            ttk.Label(parent, text="Vehicle ID").pack(anchor="w"); vehicle_id = ttk.Entry(parent); vehicle_id.pack(fill="x", pady=4)
            seats = tk.StringVar(value="Select a vehicle and load seats.")
            ttk.Label(parent, textvariable=seats, wraplength=850).pack(anchor="w", pady=8)
            seat = ttk.Entry(parent); seat.pack(fill="x", pady=4); seat.insert(0, "Seat number")
            def load(): seats.set("Available eligible seats: " + ", ".join(self.service.available_seats(vehicle_id.get().strip(), self.user["role"])))
            def book():
                item = self.service.book(self.user["id"], vehicle_id.get().strip(), seat.get().strip()); messagebox.showinfo("Booking confirmed", f"{item['id']} confirmed. Fare: Rs. {item['fare']:.0f}"); self.show_portal()
            self.button(parent, "Load eligible seats", lambda: self.run_action(load)); self.button(parent, "Confirm booking", lambda: self.run_action(book)); self.button(parent, "Back", self.show_portal)
        self.show(build)

    def waitlist_form(self):
        vehicle_id = simpledialog.askstring("Waiting list", "Vehicle ID:", parent=self)
        if vehicle_id: self.run_action(lambda: (self.service.join_waitlist(self.user["id"], vehicle_id.strip()), messagebox.showinfo("Waiting list", "You were added to the waiting list.")))

    def my_bookings(self):
        self.show_records("My bookings", [item for item in self.service.records("bookings", True) if item["user_id"] == self.user["id"]])

    def cancel_my_booking(self):
        booking_id = simpledialog.askstring("Cancel booking", "Booking ID:", parent=self)
        if booking_id:
            def cancel():
                offered = self.service.cancel_booking(booking_id.strip(), self.user["id"]); messagebox.showinfo("Booking cancelled", "Seat released." + (f" It has been offered to {offered}." if offered else "")); self.show_portal()
            self.run_action(cancel)

    def admin_records(self):
        category = simpledialog.askstring("View records", "Category: users, providers, drivers, routes, vehicles, bookings, payments, waitlists", parent=self)
        if category in self.service.data: self.show_records(category.title(), self.service.records(category, category in ("vehicles", "routes", "bookings", "payments", "waitlists")))
        elif category: messagebox.showerror("View records", "Unknown category.")

    def booking_report(self): self.show_records("Current semester booking report", self.service.report_bookings())

    def passenger_list(self, vehicle_id):
        bookings = [item for item in self.service.records("bookings", True) if item["vehicle_id"] == vehicle_id and item["status"] == "confirmed"]
        rows = [[item["seat"], self.service.find("users", item["user_id"])["name"], item["user_id"], item["id"]] for item in bookings]
        self.show_table_page(f"Passengers for {vehicle_id}", ["Seat", "Name", "User ID", "Booking"], rows)

    def provider_passengers(self, vehicles):
        vehicle_id = simpledialog.askstring("Passenger list", "Vehicle ID:", parent=self)
        if vehicle_id and any(v["id"] == vehicle_id for v in vehicles): self.passenger_list(vehicle_id)
        elif vehicle_id: messagebox.showerror("Passenger list", "That vehicle is not assigned to this provider.")

    def route_explorer(self):
        start = simpledialog.askstring("Route explorer", "Start stop:", parent=self)
        if not start: return
        end = simpledialog.askstring("Route explorer", "Destination stop (leave blank for BFS/DFS):", parent=self) or ""
        def build(parent):
            self.topbar(parent, self.user["role"].title()); graph = self.service.route_graph()
            if end:
                path, distance = graph.shortest_path(start, end); message = f"Shortest path: {' → '.join(path)}\nDistance: {distance:.2f} km" if path else "No connected path found."
            else: message = f"BFS reachable stops: {' → '.join(graph.bfs(start))}\n\nDFS reachable stops: {' → '.join(graph.dfs(start))}"
            ttk.Label(parent, text=message, wraplength=850, justify="left").pack(anchor="w"); self.button(parent, "Back", self.show_portal)
        self.run_action(lambda: self.show(build))

    def show_records(self, title, records): self.show_table_page(title, ["Record"], [[str(record)] for record in records])
    def show_table_page(self, title, columns, rows):
        def build(parent): self.topbar(parent, self.user["role"].title()); self.heading(parent, title); self.table(parent, columns, rows); self.button(parent, "Back", self.show_portal)
        self.show(build)
    def table(self, parent, columns, rows):
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=18)
        for column in columns: tree.heading(column, text=column); tree.column(column, width=max(110, min(350, len(column) * 18)), stretch=True)
        for row in rows: tree.insert("", "end", values=row)
        tree.pack(fill="both", expand=True, pady=8)


if __name__ == "__main__":
    TransportApp().mainloop()
