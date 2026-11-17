# FAST-NUCES Transport Management System

The Flask application is organized into just two project directories:

- `backend/` — Flask routes, transport service, persistence, custom data
  structures, and tests.
- `frontend/` — Jinja templates and static assets.

## Run

From the repository root:

```powershell
python -m pip install -r requirements.txt
python backend/app.py
```

Open `http://127.0.0.1:5000` for member and staff sign-in. Administrator sign-in
is separate at `http://127.0.0.1:5000/admin`. The initial administrator password
is `admin123`. The app stores records in `transport_data.json` at the repository root. Set
`TRANSPORT_SECRET` to a long, random value before deployment; if unset, the
app generates a development-only secret on startup.

## Portals

- **Administrator:** manages each master-data type on its own records page,
  reviews retained booking/payment/audit history, and cancels bookings without
  deleting their records.
- **Student and faculty:** browse eligible seats and fares, record payments,
  book/cancel seats, join or leave waitlists, and view history across semesters.
- **Driver and provider:** view only their assigned vehicles and confirmed passengers.
- **All roles:** explore routes using breadth-first search, depth-first search,
  and shortest-path results.

Backend workflows use 13 custom structures/algorithms: the stack uses a dynamic
array; the linked list stores audit history; a FIFO queue handles waitlists and
BFS; a circular queue keeps recent notifications; a binary heap runs Dijkstra;
a hash table indexes IDs; a binary search tree orders booking reports; an
adjacency-list graph models routes; disjoint sets group connected networks;
linear search checks duplicate IDs; merge sort orders waitlists and search
indexes; and binary search finds records by ID.

## Tests

```powershell
python -m unittest backend.test_service -v
python -m unittest backend.test_web -v
```
