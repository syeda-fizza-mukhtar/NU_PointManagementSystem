"""Custom data structures and algorithms used by the transport system.

The application deliberately does not depend on ``collections``, ``heapq`` or
other library implementations for these structures.  Python's built-in list is
only used as the raw storage of the custom structures.
"""


class DynamicArray:
    """Resizable array: append is amortized O(1), lookup is O(1)."""
    def __init__(self, capacity=4):
        self._data = [None] * capacity
        self._size = 0

    def append(self, value):
        if self._size == len(self._data):
            self._resize(len(self._data) * 2)
        self._data[self._size] = value
        self._size += 1

    def _resize(self, capacity):
        new_data = [None] * capacity
        for index in range(self._size):
            new_data[index] = self._data[index]
        self._data = new_data

    def __getitem__(self, index):
        if index < 0 or index >= self._size:
            raise IndexError("DynamicArray index out of range")
        return self._data[index]

    def __len__(self):
        return self._size

    def values(self):
        return [self._data[index] for index in range(self._size)]


class _Node:
    def __init__(self, value):
        self.value, self.next = value, None


class SinglyLinkedList:
    """Linked list used for chronological booking history, O(1) append."""
    def __init__(self):
        self.head = self.tail = None
        self.size = 0

    def append(self, value):
        node = _Node(value)
        if self.tail:
            self.tail.next = node
        else:
            self.head = node
        self.tail = node
        self.size += 1

    def values(self):
        values, current = [], self.head
        while current:
            values.append(current.value)
            current = current.next
        return values


class Stack:
    """LIFO stack for undo/audit actions: push/pop are O(1)."""
    def __init__(self):
        self._items = DynamicArray()

    def push(self, value): self._items.append(value)
    def pop(self):
        if not len(self._items): raise IndexError("empty stack")
        value = self._items[self._items._size - 1]
        self._items._size -= 1
        return value
    def empty(self): return len(self._items) == 0


class Queue:
    """FIFO linked queue used for seat waiting lists: O(1) enqueue/dequeue."""
    def __init__(self): self.front = self.rear = None; self.size = 0
    def enqueue(self, value):
        node = _Node(value)
        if self.rear: self.rear.next = node
        else: self.front = node
        self.rear = node; self.size += 1
    def dequeue(self):
        if not self.front: raise IndexError("empty queue")
        value = self.front.value; self.front = self.front.next; self.size -= 1
        if not self.front: self.rear = None
        return value
    def values(self):
        values, current = [], self.front
        while current: values.append(current.value); current = current.next
        return values


class CircularQueue:
    """Fixed-capacity circular queue for recent portal notifications."""
    def __init__(self, capacity=20):
        self._data, self._front, self._size = [None] * capacity, 0, 0
    def enqueue(self, value):
        if self._size == len(self._data): self.dequeue()
        self._data[(self._front + self._size) % len(self._data)] = value; self._size += 1
    def dequeue(self):
        if not self._size: raise IndexError("empty circular queue")
        value = self._data[self._front]; self._front = (self._front + 1) % len(self._data); self._size -= 1
        return value
    def values(self): return [self._data[(self._front + i) % len(self._data)] for i in range(self._size)]


class PriorityQueue:
    """Binary min-heap, used by Dijkstra; insert/remove minimum are O(log n)."""
    def __init__(self): self._items = []
    def push(self, priority, value):
        self._items.append((priority, value)); index = len(self._items) - 1
        while index:
            parent = (index - 1) // 2
            if self._items[parent][0] <= priority: break
            self._items[index] = self._items[parent]; index = parent
        self._items[index] = (priority, value)
    def pop(self):
        if not self._items: raise IndexError("empty priority queue")
        minimum, last = self._items[0], self._items.pop()
        if self._items:
            index = 0
            while index * 2 + 1 < len(self._items):
                child = index * 2 + 1
                if child + 1 < len(self._items) and self._items[child + 1][0] < self._items[child][0]: child += 1
                if self._items[child][0] >= last[0]: break
                self._items[index] = self._items[child]; index = child
            self._items[index] = last
        return minimum
    def empty(self): return not self._items


class HashTable:
    """Separate-chaining hash table: expected O(1) get/set."""
    def __init__(self, buckets=31): self._buckets = [[] for _ in range(buckets)]
    def _bucket(self, key): return self._buckets[hash(key) % len(self._buckets)]
    def set(self, key, value):
        bucket = self._bucket(key)
        for pair in bucket:
            if pair[0] == key: pair[1] = value; return
        bucket.append([key, value])
    def get(self, key, default=None):
        for found_key, value in self._bucket(key):
            if found_key == key: return value
        return default
    def contains(self, key):
        marker = object()
        return self.get(key, marker) is not marker


class _TreeNode:
    def __init__(self, key, value): self.key, self.value, self.left, self.right = key, value, None, None


class BinarySearchTree:
    """BST index for sorted report traversal."""
    def __init__(self): self.root = None
    def insert(self, key, value):
        if not self.root: self.root = _TreeNode(key, value); return
        current = self.root
        while True:
            if key < current.key:
                if not current.left: current.left = _TreeNode(key, value); return
                current = current.left
            elif key > current.key:
                if not current.right: current.right = _TreeNode(key, value); return
                current = current.right
            else: current.value = value; return
    def inorder(self):
        result, stack, current = [], [], self.root
        while stack or current:
            if current: stack.append(current); current = current.left
            else: current = stack.pop(); result.append(current.value); current = current.right
        return result


class Graph:
    """Adjacency-list graph supporting BFS, DFS and Dijkstra route exploration."""
    def __init__(self): self.edges = {}
    def add_edge(self, source, destination, distance, bidirectional=True):
        self.edges.setdefault(source, []).append((destination, float(distance)))
        self.edges.setdefault(destination, [])
        if bidirectional: self.edges[destination].append((source, float(distance)))
    def bfs(self, start):
        queue, seen, result = Queue(), {start}, []; queue.enqueue(start)
        while queue.size:
            node = queue.dequeue(); result.append(node)
            for neighbor, _ in self.edges.get(node, []):
                if neighbor not in seen: seen.add(neighbor); queue.enqueue(neighbor)
        return result
    def dfs(self, start):
        stack, seen, result = Stack(), set(), []; stack.push(start)
        while not stack.empty():
            node = stack.pop()
            if node in seen: continue
            seen.add(node); result.append(node)
            for neighbor, _ in reversed(self.edges.get(node, [])): stack.push(neighbor)
        return result
    def shortest_path(self, start, end):
        pq, distances, previous = PriorityQueue(), {start: 0}, {}; pq.push(0, start)
        while not pq.empty():
            distance, node = pq.pop()
            if distance != distances.get(node) : continue
            if node == end: break
            for neighbor, weight in self.edges.get(node, []):
                candidate = distance + weight
                if candidate < distances.get(neighbor, float('inf')):
                    distances[neighbor], previous[neighbor] = candidate, node; pq.push(candidate, neighbor)
        if end not in distances: return [], None
        path, node = [], end
        while node is not None: path.append(node); node = previous.get(node)
        return list(reversed(path)), distances[end]


class DisjointSet:
    """Union-find structure that can identify disconnected route networks."""
    def __init__(self): self.parent, self.rank = {}, {}
    def add(self, value): self.parent.setdefault(value, value); self.rank.setdefault(value, 0)
    def find(self, value):
        if self.parent[value] != value: self.parent[value] = self.find(self.parent[value])
        return self.parent[value]
    def union(self, first, second):
        self.add(first); self.add(second); a, b = self.find(first), self.find(second)
        if a == b: return
        if self.rank[a] < self.rank[b]: a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]: self.rank[a] += 1


def linear_search(items, key, field="id"):
    for item in items:
        if item.get(field) == key: return item
    return None


def merge_sort(items, field):
    """Stable O(n log n) merge sort returning a new list."""
    if len(items) < 2: return items[:]
    middle = len(items) // 2; left, right = merge_sort(items[:middle], field), merge_sort(items[middle:], field)
    result = []; i = j = 0
    while i < len(left) and j < len(right):
        if left[i].get(field, 0) <= right[j].get(field, 0): result.append(left[i]); i += 1
        else: result.append(right[j]); j += 1
    return result + left[i:] + right[j:]


def binary_search(sorted_items, key, field="id"):
    low, high = 0, len(sorted_items) - 1
    while low <= high:
        middle = (low + high) // 2; value = sorted_items[middle].get(field)
        if value == key: return sorted_items[middle]
        if value < key: low = middle + 1
        else: high = middle - 1
    return None
