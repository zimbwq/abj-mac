"""Testable triple-click state, independent of Cocoa."""
from collections import deque


class TripleClick:
    def __init__(self, interval=0.65, distance=12):
        self.interval = interval
        self.distance = distance
        self.clicks = deque(maxlen=3)

    def reset(self):
        self.clicks.clear()

    def click(self, timestamp, x, y):
        self.clicks.append((timestamp, x, y))
        if len(self.clicks) != 3:
            return False
        first = self.clicks[0]
        if timestamp - first[0] > self.interval:
            return False
        if any((cx-x)**2 + (cy-y)**2 > self.distance**2 for _, cx, cy in self.clicks):
            return False
        self.reset()
        return True
