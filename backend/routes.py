from functools import wraps
import hmac
import secrets

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from .service import TransportError, TransportService

web = Blueprint("web", __name__)

RECORD_CATEGORIES = ("semesters", "users", "providers", "drivers", "routes", "vehicles", "bookings", "payments", "waitlists", "audit_log")
PORTAL_ROLES = ("student", "faculty", "driver", "provider")
ACCOUNT_CATEGORIES = {"student": "users", "faculty": "users", "driver": "drivers", "provider": "providers"}
MANAGED_CATEGORIES = ("semesters", "users", "providers", "drivers", "routes", "vehicles")
RECORD_COLUMNS = {
    "semesters": ("id", "starts", "ends", "student_fare", "faculty_fare", "ac_surcharge", "student_seats", "faculty_seats", "active"),
    "users": ("id", "name", "email", "phone", "role", "identifier", "active"),
    "providers": ("id", "name", "contact"),
    "drivers": ("id", "name", "license_number", "phone"),
    "routes": ("id", "start", "end", "distance", "stops", "semester_id"),
    "vehicles": ("id", "registration", "type", "ac", "route_id", "provider_id", "capacity", "driver_id", "semester_id"),
    "bookings": ("id", "user_id", "vehicle_id", "seat", "fare", "status", "booked_at", "semester_id"),
    "payments": ("id", "user_id", "vehicle_id", "amount", "status", "paid_at", "semester_id"),
    "waitlists": ("id", "user_id", "vehicle_id", "status", "offered_seat", "joined_at", "semester_id"),
    "audit_log": ("at", "actor", "action"),
}
RECORD_DESCRIPTIONS = {
    "semesters": "Configure semester dates, fares, seat allocation, and activation.",
    "users": "Manage student and faculty accounts. Passwords are never displayed.",
    "providers": "Manage provider accounts referenced by vehicles.",
    "drivers": "Manage driver accounts and license details.",
    "routes": "Manage active-semester routes used by the fleet and route explorer.",
    "vehicles": "Manage active-semester vehicles and driver assignments.",
    "bookings": "Review current-semester reservations. Cancellation retains history and releases eligible seats.",
    "payments": "Review retained payment records; payments cannot be hard-deleted.",
    "waitlists": "Review current-semester queue status; members manage their own waiting-list entries.",
    "audit_log": "Review retained changes made across transport operations.",
}
CREATE_ENDPOINTS = {
    "semesters": "web.add_semester", "users": "web.add_user", "providers": "web.add_provider",
    "drivers": "web.add_driver", "routes": "web.add_route", "vehicles": "web.add_vehicle",
}


def service():
    return current_app.config["TRANSPORT_SERVICE"]


def form_values():
    values = request.form.to_dict()
    values.pop("_csrf_token", None)
    return values


def admin_page_fields(category, app_service):
    active_routes = app_service.records("routes", True) if app_service.data["settings"].get("active_semester") else []
    fields = {
        "semesters": [
            {"name": "name", "label": "Semester name", "placeholder": "e.g. Fall-2027"},
            {"name": "starts", "label": "Start date", "type": "date", "min": "0001-01-01", "max": "9999-12-31"},
            {"name": "ends", "label": "End date", "type": "date", "min": "0001-01-01", "max": "9999-12-31"},
            {"name": "student_fare", "label": "Student fare", "type": "number", "min": "0", "step": "0.01"},
            {"name": "faculty_fare", "label": "Faculty fare", "type": "number", "min": "0", "step": "0.01"},
            {"name": "ac_surcharge", "label": "AC surcharge", "type": "number", "min": "0", "step": "0.01"},
            {"name": "student_seats", "label": "Student seats (0 auto)", "type": "number", "min": "0", "value": "0"},
            {"name": "faculty_seats", "label": "Faculty seats (0 auto)", "type": "number", "min": "0", "value": "0"},
        ],
        "users": [
            {"name": "user_id", "label": "User ID"},
            {"name": "name", "label": "Full name"},
            {"name": "email", "label": "Email", "type": "email"},
            {"name": "phone", "label": "Phone"},
            {"name": "role", "label": "Portal", "type": "select", "options": (("student", "Student"), ("faculty", "Faculty"))},
            {"name": "identifier", "label": "Roll / employee number"},
            {"name": "password", "label": "Portal password", "type": "password"},
        ],
        "providers": [
            {"name": "provider_id", "label": "Provider ID"},
            {"name": "name", "label": "Provider name"},
            {"name": "contact", "label": "Contact"},
            {"name": "password", "label": "Portal password", "type": "password"},
        ],
        "drivers": [
            {"name": "driver_id", "label": "Driver ID"},
            {"name": "name", "label": "Driver name"},
            {"name": "license_number", "label": "License number"},
            {"name": "phone", "label": "Phone"},
            {"name": "password", "label": "Portal password", "type": "password"},
        ],
        "routes": [
            {"name": "route_id", "label": "Route ID"},
            {"name": "start", "label": "Starting stop"},
            {"name": "end", "label": "Destination"},
            {"name": "distance", "label": "Distance (km)", "type": "number", "min": "0.01", "step": "0.1"},
            {"name": "stops", "label": "Intermediate stops", "required": False, "placeholder": "Comma-separated stops"},
        ],
        "vehicles": [
            {"name": "vehicle_id", "label": "Vehicle ID"},
            {"name": "registration", "label": "Registration"},
            {"name": "vehicle_type", "label": "Vehicle type", "type": "select", "options": (("Bus", "Bus"), ("Coaster", "Coaster"))},
            {"name": "route_id", "label": "Route", "type": "select", "options": tuple((item["id"], f'{item["id"]} · {item["start"]} to {item["end"]}') for item in active_routes)},
            {"name": "provider_id", "label": "Provider", "type": "select", "options": tuple((item["id"], f'{item["id"]} · {item["name"]}') for item in app_service.records("providers"))},
            {"name": "capacity", "label": "Capacity", "type": "number", "min": "1", "step": "1"},
            {"name": "driver_id", "label": "Assigned driver (optional)", "type": "select", "required": False,
             "options": (("", "Unassigned"),) + tuple((item["id"], f'{item["id"]} · {item["name"]}') for item in app_service.records("drivers"))},
            {"name": "ac", "label": "Air conditioned", "type": "checkbox", "required": False},
        ],
    }
    create_fields = fields.get(category, [])
    update_fields = []
    for field in create_fields:
        if field["name"] in ("name", "starts", "ends", "student_fare", "faculty_fare", "ac_surcharge",
                             "student_seats", "faculty_seats", "email", "phone", "role", "identifier",
                             "contact", "license_number", "start", "end", "distance", "stops",
                             "registration", "vehicle_type", "route_id", "provider_id", "capacity",
                             "driver_id", "ac"):
            update_name = "type" if field["name"] == "vehicle_type" else field["name"]
            update_field = dict(field, name=update_name)
            update_fields.append(update_field)
    if category in ("users", "providers", "drivers"):
        update_fields.append({"name": "password", "label": "New password (leave blank to keep current)",
                              "type": "password", "required": False})
    if category == "users":
        update_fields.append({"name": "active", "label": "Account enabled", "type": "checkbox", "required": False})
    return create_fields, update_fields


@web.before_app_request
def protect_post_requests():
    if request.method == "POST":
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("_csrf_token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            abort(400, description="The form expired or its security token is invalid. Reload the page and try again.")


@web.context_processor
def csrf_context():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return {"csrf_token": token}


def login_required(*roles):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            user = session.get("user")
            if not user:
                endpoint = "web.admin_login" if "admin" in roles else "web.login"
                return redirect(url_for(endpoint))
            if roles and user["role"] not in roles:
                flash("This portal cannot access that operation.", "error")
                return redirect(url_for("web.dashboard"))
            category = ACCOUNT_CATEGORIES.get(user["role"])
            if category:
                try:
                    account = service().find(category, user["id"])
                except TransportError:
                    session.clear()
                    flash("This account is no longer available. Sign in again or contact an administrator.", "error")
                    return redirect(url_for("web.login"))
                if account.get("active", True) is False or account.get("role", user["role"]) != user["role"]:
                    session.clear()
                    flash("This account is inactive or its portal access changed. Sign in again.", "error")
                    return redirect(url_for("web.login"))
                account_name = account.get("name")
                if account_name and account_name != user.get("name"):
                    user["name"] = account_name
                    session["user"] = user
            return function(*args, **kwargs)
        return wrapped
    return decorate


def perform(action, success, destination="web.dashboard"):
    try:
        action()
        flash(success, "success")
    except (TransportError, ValueError, KeyError) as error:
        flash(str(error), "error")
    return redirect(url_for(destination))


def establish_session(role, user_id, password):
    authenticated = service().authenticate(role, user_id, password)
    session.clear()
    session["user"] = {"id": authenticated["id"], "role": authenticated.get("role", role),
                       "name": authenticated["name"]}
    return redirect(url_for("web.dashboard"))


@web.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role", "")
        if role not in PORTAL_ROLES:
            flash("Use the dedicated administrator sign-in page for administrator access.", "error")
            return redirect(url_for("web.login"))
        try:
            return establish_session(role, request.form.get("user_id", "").strip(),
                                     request.form.get("password", ""))
        except TransportError as error:
            flash(str(error), "error")
    return render_template("login.html")


@web.route("/admin", methods=["GET", "POST"])
def admin_login():
    current_user = session.get("user")
    if current_user:
        if current_user["role"] != "admin":
            flash("Sign out of the current portal before administrator sign in.", "error")
        return redirect(url_for("web.dashboard"))
    if request.method == "POST":
        if request.form.get("role") != "admin":
            flash("Invalid administrator sign-in request.", "error")
        else:
            try:
                return establish_session("admin", "", request.form.get("password", ""))
            except TransportError as error:
                flash(str(error), "error")
    return render_template("login.html", admin_only=True)


@web.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.login"))


@web.route("/dashboard")
@login_required()
def dashboard():
    user, app_service = session["user"], service()
    try:
        semester = app_service.semester()
    except TransportError:
        semester = None
    context = {"user": user, "semester": semester, "vehicles": [], "bookings": [], "routes": [], "stats": {},
               "payments": [], "waitlists": [], "active_booking": None, "semesters": app_service.records("semesters"),
               "record_categories": RECORD_CATEGORIES}
    if user["role"] == "admin":
        context["stats"] = {"users": len(app_service.records("users")),
                            "vehicles": len(app_service.records("vehicles", True)) if semester else 0,
                            "bookings": len(app_service.records("bookings", True)) if semester else 0,
                            "waitlists": len(app_service.records("waitlists", True)) if semester else 0}
        if semester:
            context["vehicles"] = [dict(vehicle, route=app_service.find("routes", vehicle["route_id"]))
                                   for vehicle in app_service.records("vehicles", True)]
            context["routes"] = app_service.records("routes", True)
            context["bookings"] = app_service.report_bookings()
    elif user["role"] in ("student", "faculty"):
        if semester:
            context["active_booking"] = app_service.active_booking(user["id"])
            current_waitlists = app_service.records("waitlists", True)
            member_vehicles = []
            for vehicle in app_service.records("vehicles", True):
                entry = next((item for item in current_waitlists
                              if item["vehicle_id"] == vehicle["id"] and item["user_id"] == user["id"]
                              and item["status"] in ("waiting", "offered")), None)
                member_vehicles.append(dict(
                    vehicle,
                    seats=app_service.available_seats(vehicle["id"], user["role"]),
                    fare=app_service.fare_for(user, vehicle),
                    route=app_service.find("routes", vehicle["route_id"]),
                    paid=app_service.has_payment(user["id"], vehicle["id"]),
                    offered_seat=entry.get("offered_seat") if entry and entry["status"] == "offered" else None,
                    waitlist_status=entry["status"] if entry else None))
            context["vehicles"] = member_vehicles
        context["bookings"] = [booking for booking in app_service.records("bookings")
                               if booking["user_id"] == user["id"]]
        context["payments"] = [payment for payment in app_service.records("payments")
                               if payment["user_id"] == user["id"]]
        context["waitlists"] = [entry for entry in app_service.records("waitlists")
                                if entry["user_id"] == user["id"]]
    elif user["role"] == "driver" and semester:
        context["vehicles"] = [v for v in app_service.records("vehicles", True) if v.get("driver_id") == user["id"]]
        context["bookings"] = [dict(b, passenger_name=app_service.find("users", b["user_id"])["name"])
                               for b in app_service.records("bookings", True)
                               if any(v["id"] == b["vehicle_id"] for v in context["vehicles"])
                               and b["status"] == "confirmed"]
    elif user["role"] == "provider" and semester:
        context["vehicles"] = [v for v in app_service.records("vehicles", True) if v["provider_id"] == user["id"]]
        context["bookings"] = [dict(b, passenger_name=app_service.find("users", b["user_id"])["name"])
                               for b in app_service.records("bookings", True)
                               if any(v["id"] == b["vehicle_id"] for v in context["vehicles"])
                               and b["status"] == "confirmed"]
    if user["role"] in ("driver", "provider"):
        for vehicle in context["vehicles"]:
            vehicle["route"] = app_service.find("routes", vehicle["route_id"])
    return render_template("dashboard.html", **context)


@web.post("/admin/semester")
@login_required("admin")
def add_semester():
    return perform_admin_record(lambda: service().create_semester(**form_values()), "semesters", "Semester activated.")


@web.post("/admin/user")
@login_required("admin")
def add_user():
    values = form_values()
    return perform_admin_record(lambda: service().add_user(**values), "users", "User account created.")


@web.post("/admin/provider")
@login_required("admin")
def add_provider():
    return perform_admin_record(lambda: service().add_provider(**form_values()), "providers", "Provider created.")


@web.post("/admin/driver")
@login_required("admin")
def add_driver():
    return perform_admin_record(lambda: service().add_driver(**form_values()), "drivers", "Driver created.")


@web.post("/admin/route")
@login_required("admin")
def add_route():
    return perform_admin_record(lambda: service().add_route(**form_values()), "routes", "Route saved.")


@web.post("/admin/vehicle")
@login_required("admin")
def add_vehicle():
    values = form_values()
    values["ac"] = request.form.get("ac") == "on"
    return perform_admin_record(lambda: service().add_vehicle(**values), "vehicles", "Vehicle added.")


@web.post("/admin/assignment")
@login_required("admin")
def assign_driver():
    return perform_admin_record(lambda: service().assign_driver(request.form["vehicle_id"], request.form["driver_id"]),
                                "vehicles", "Driver assigned.")


@web.post("/admin/semester/<semester_id>/activate")
@login_required("admin")
def activate_semester(semester_id):
    return perform_admin_record(lambda: service().activate_semester(semester_id), "semesters", "Semester activated.")


def perform_admin_record(action, category, success):
    try:
        action()
        flash(success, "success")
    except (TransportError, ValueError, KeyError) as error:
        flash(str(error), "error")
    return redirect(url_for("web.admin_records", category=category))


@web.post("/admin/records/<category>/<record_id>/update")
@login_required("admin")
def update_admin_record(category, record_id):
    if category not in MANAGED_CATEGORIES:
        abort(404)
    values = form_values()
    if category == "users":
        values["active"] = request.form.get("active") == "on"
    elif category == "vehicles":
        values["type"] = request.form.get("type", "").strip()
        values["ac"] = request.form.get("ac") == "on"
    return perform_admin_record(lambda: service().update_record(category, record_id, values),
                                category, f"{category[:-1].title()} updated.")


@web.post("/admin/records/<category>/<record_id>/delete")
@login_required("admin")
def delete_admin_record(category, record_id):
    if category not in MANAGED_CATEGORIES:
        abort(404)
    return perform_admin_record(lambda: service().delete_record(category, record_id),
                                category, f"{category[:-1].title()} deleted.")


@web.get("/admin/records/<category>")
@login_required("admin")
def admin_records(category):
    if category not in RECORD_CATEGORIES:
        abort(404)
    app_service = service()
    scoped = category in ("routes", "vehicles", "bookings", "payments", "waitlists")
    no_active_semester = scoped and not app_service.data["settings"].get("active_semester")
    searchable = category != "audit_log"
    search_query = request.args.get("q", "").strip() if searchable else ""
    active_semester_id = app_service.data["settings"].get("active_semester")
    if no_active_semester:
        records = []
    else:
        if search_query:
            match = app_service.search_records(category, search_query, scoped)
            records = [match] if match else []
        else:
            records = app_service.records(category, scoped)
    safe_records = [{key: value for key, value in record.items() if key != "password"} for record in records]
    columns = list(RECORD_COLUMNS[category])
    for record in safe_records:
        for key in record:
            if key not in columns:
                columns.append(key)
    create_fields, update_fields = admin_page_fields(category, app_service)
    return render_template("records.html", category=category, records=safe_records, columns=columns,
                           searchable=searchable, search_query=search_query,
                           create_endpoint=CREATE_ENDPOINTS.get(category), create_fields=create_fields,
                           update_fields=update_fields, editable=category in MANAGED_CATEGORIES,
                           no_active_semester=no_active_semester,
                           can_cancel_bookings=category == "bookings",
                           active_semester_id=active_semester_id,
                           description=RECORD_DESCRIPTIONS[category])


@web.get("/admin/report")
@login_required("admin")
def booking_report():
    app_service = service()
    records = app_service.report_bookings() if app_service.data["settings"].get("active_semester") else []
    return render_template("records.html", category="Current semester booking report", records=records,
                           columns=("id", "user_id", "vehicle_id", "seat", "fare", "status", "booked_at"),
                           searchable=False, search_query="",
                           description="Ordered booking report for the active semester.")


@web.post("/admin/bookings/<booking_id>/cancel")
@login_required("admin")
def admin_cancel_booking(booking_id):
    return perform_admin_record(lambda: service().cancel_booking(booking_id, "admin"), "bookings",
                                "Booking cancelled; eligible waiting-list users were checked.")


@web.post("/member/payment")
@login_required("student", "faculty")
def payment():
    user = session["user"]
    return perform(lambda: service().record_payment(user["id"], request.form["vehicle_id"]), "Payment recorded for this vehicle.")


@web.post("/member/book")
@login_required("student", "faculty")
def book():
    user = session["user"]
    return perform(lambda: service().book(user["id"], request.form["vehicle_id"], request.form["seat"]), "Seat booking confirmed.")


@web.post("/member/waitlist")
@login_required("student", "faculty")
def join_waitlist():
    user = session["user"]
    return perform(lambda: service().join_waitlist(user["id"], request.form["vehicle_id"]), "Added to the waiting list.")


@web.post("/waitlist/<entry_id>/leave")
@login_required("student", "faculty")
def leave_waitlist(entry_id):
    user = session["user"]
    return perform(lambda: service().leave_waitlist(user["id"], entry_id),
                   "Removed from the waiting list; any offered seat was released.")


@web.post("/booking/<booking_id>/cancel")
@login_required("student", "faculty")
def cancel(booking_id):
    user = session["user"]
    try:
        booking = service().find("bookings", booking_id)
    except TransportError as error:
        flash(str(error), "error")
        return redirect(url_for("web.dashboard"))
    if booking["user_id"] != user["id"]:
        flash("You can only cancel your own booking.", "error")
        return redirect(url_for("web.dashboard"))
    return perform(lambda: service().cancel_booking(booking_id, user["id"]), "Booking cancelled; eligible waiting-list users were checked.")


@web.route("/routes", methods=["GET", "POST"])
@login_required()
def route_explorer():
    app_service = service()
    try:
        routes = app_service.records("routes", True)
        graph = app_service.route_graph()
        networks = app_service.route_networks()
        result = None
        if request.method == "POST":
            start = request.form.get("start", "").strip()
            end = request.form.get("end", "").strip()
            if not start:
                flash("Enter a starting stop.", "error")
            elif end:
                path, distance = graph.shortest_path(start, end)
                result = {"kind": "shortest", "path": path, "distance": distance}
            else:
                result = {"kind": "traversal", "bfs": graph.bfs(start), "dfs": graph.dfs(start)}
        return render_template("routes.html", routes=routes, networks=networks, result=result)
    except TransportError as error:
        flash(str(error), "error")
        return render_template("routes.html", routes=[], networks=[], result=None)


@web.get("/passengers/<vehicle_id>")
@login_required("admin", "driver", "provider")
def passenger_list(vehicle_id):
    app_service, user = service(), session["user"]
    try:
        vehicle = next((item for item in app_service.records("vehicles", True) if item["id"] == vehicle_id), None)
        if vehicle is None:
            abort(404)
        if user["role"] == "driver" and vehicle.get("driver_id") != user["id"]:
            abort(403)
        if user["role"] == "provider" and vehicle.get("provider_id") != user["id"]:
            abort(403)
        passengers = []
        for booking in app_service.records("bookings", True):
            if booking["vehicle_id"] == vehicle_id and booking["status"] == "confirmed":
                member = app_service.find("users", booking["user_id"])
                passengers.append({"seat": booking["seat"], "name": member["name"], "user_id": member["id"],
                                   "booking_id": booking["id"]})
        return render_template("passengers.html", vehicle=vehicle, passengers=passengers)
    except TransportError as error:
        flash(str(error), "error")
        return redirect(url_for("web.dashboard"))
