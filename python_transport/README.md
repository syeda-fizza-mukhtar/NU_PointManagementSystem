# FAST-NUCES Transport Management System — Python/Tkinter

Run the desktop application from this directory:

```powershell
python app.py
```

The application saves data in `transport_data.json` next to the source code. The initial administrator password is `admin123`. Change it in the JSON file before real use.

## Portal features

**Administrator portal** creates and activates semesters, configures all semester fares and AC surcharges, configures student/faculty seat allocations, registers users and transport providers, manages drivers, routes and vehicles, assigns drivers, views records, runs booking reports, and explores connected routes.

**Student portal** shows eligible vehicles, routes, seat availability and the semester price; records a payment; confirms one active booking for the semester; joins a vehicle waiting list; views booking history; cancels a booking; and explores routes.

**Faculty portal** provides the same booking flow as the student portal, using the dynamically configured faculty price and faculty-designated seats.

**Driver portal** shows the current-semester vehicle assignment, route and capacity, then provides the confirmed passenger list for that vehicle.

**Transport provider portal** lists the provider's current-semester fleet and provides passenger lists for its vehicles.

## Dynamic semester records

Users, drivers and providers persist between semesters. Routes, vehicles, bookings, payments and waiting-list records are tied to an active semester. Each new semester has its own fares, AC surcharge, seat-allocation rules and operational records. Cancellations remain in booking history and automatically offer the released eligible seat to the first paid person on the matching waiting list.

## Custom data structures and algorithms

`structures.py` implements these without importing Python's data-structure libraries:

1. Dynamic array
2. Singly linked list
3. Stack
4. FIFO queue
5. Circular queue
6. Priority queue (binary heap)
7. Hash table (separate chaining)
8. Binary search tree
9. Adjacency-list graph
10. Disjoint-set / union-find
11. Linear search
12. Merge sort
13. Binary search

The system uses the custom queue for waiting lists, priority queue plus graph for Dijkstra shortest paths, queue/stack plus graph for BFS/DFS, hash table for record lookup, linked list for the audit history, and merge sort for chronological reports.
