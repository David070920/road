"""
Data structure utilities for efficient data storage and management.
This module provides optimized data structures for sensor data collection.
"""

import numpy as np
import threading
import time  # Import time module for timestamp handling
from collections import deque
from typing import List, Dict, Any, Union, TypeVar, Generic, Optional, Iterator

T = TypeVar('T')

class CircularBuffer(Generic[T]):
    """
    A thread-safe circular buffer implementation that minimizes memory allocation.
    
    This buffer preallocates memory and overwrites old data when full,
    which is more efficient than growing arrays for continuous data collection.
    """
    
    def __init__(self, capacity: int, dtype=None, thread_safe: bool = True):
        """
        Initialize a circular buffer.
        
        Args:
            capacity: Maximum number of elements the buffer can hold
            dtype: Data type for numpy-based buffers (None for generic Python objects)
            thread_safe: Whether to use thread safety locks
        """
        self.capacity = capacity
        self.dtype = dtype
        self.thread_safe = thread_safe
        self._lock = threading.RLock() if thread_safe else None
        
        # Use numpy array for numeric data types for better performance
        if dtype is not None:
            self._buffer = np.zeros(capacity, dtype=dtype)
        else:
            self._buffer = [None] * capacity
            
        self._start = 0  # Index of the first element
        self._size = 0   # Current number of elements
        self._wrapped = False  # Whether we've wrapped around
    
    def __len__(self) -> int:
        """Return the current number of elements in the buffer."""
        if self.thread_safe:
            with self._lock:
                return self._size
        return self._size
    
    def __iter__(self) -> Iterator[T]:
        """Make the buffer iterable. Returns an iterator over all elements."""
        # Return a list iterator to avoid threading issues during iteration
        return iter(self.get_all())
    
    def __getitem__(self, index: int) -> T:
        """Enable indexing support for the buffer (e.g., buffer[0])."""
        if self.thread_safe:
            with self._lock:
                if index < 0:
                    # Handle negative indexing
                    index = self._size + index
                
                if index < 0 or index >= self._size:
                    raise IndexError("CircularBuffer index out of range")
                
                actual_idx = (self._start + index) % self.capacity
                return self._buffer[actual_idx]
        else:
            if index < 0:
                # Handle negative indexing
                index = self._size + index
            
            if index < 0 or index >= self._size:
                raise IndexError("CircularBuffer index out of range")
                
            actual_idx = (self._start + index) % self.capacity
            return self._buffer[actual_idx]
        
    def clear(self) -> None:
        """Clear all elements from the buffer."""
        if self.thread_safe:
            with self._lock:
                self._start = 0
                self._size = 0
                self._wrapped = False
                if self.dtype is not None:
                    self._buffer = np.zeros(self.capacity, dtype=self.dtype)
                else:
                    self._buffer = [None] * self.capacity
        else:
            self._start = 0
            self._size = 0
            self._wrapped = False
            if self.dtype is not None:
                self._buffer = np.zeros(self.capacity, dtype=self.dtype)
            else:
                self._buffer = [None] * self.capacity
    
    def append(self, item: T) -> None:
        """
        Add an item to the end of the buffer.
        If the buffer is full, this overwrites the oldest item.
        """
        if self.thread_safe:
            with self._lock:
                self._append_no_lock(item)
        else:
            self._append_no_lock(item)
    
    def _append_no_lock(self, item: T) -> None:
        """Non-thread-safe version of append."""
        if self._size < self.capacity:
            # Buffer is not full yet
            idx = (self._start + self._size) % self.capacity
            self._buffer[idx] = item
            self._size += 1
        else:
            # Buffer is full, overwrite oldest item
            self._buffer[self._start] = item
            self._start = (self._start + 1) % self.capacity
            self._wrapped = True
    
    def extend(self, items: List[T]) -> None:
        """Add multiple items to the buffer."""
        if self.thread_safe:
            with self._lock:
                for item in items:
                    self._append_no_lock(item)
        else:
            for item in items:
                self._append_no_lock(item)
    
    def get_all(self) -> List[T]:
        """Get all items in the buffer in order (oldest to newest)."""
        if self.thread_safe:
            with self._lock:
                return self._get_all_no_lock()
        return self._get_all_no_lock()
    
    def _get_all_no_lock(self) -> List[T]:
        """Non-thread-safe version of get_all."""
        if self._size == 0:
            return []
        
        if isinstance(self._buffer, np.ndarray):
            if self._start + self._size <= self.capacity:
                # No wrap-around
                return self._buffer[self._start:self._start + self._size].tolist()
            else:
                # Handle wrap-around
                first_part = self._buffer[self._start:].tolist()
                second_part = self._buffer[:self._size - (self.capacity - self._start)].tolist()
                return first_part + second_part
        else:
            result = []
            for i in range(self._size):
                idx = (self._start + i) % self.capacity
                result.append(self._buffer[idx])
            return result
    
    def get_last(self, n: int) -> List[T]:
        """Get the last n items from the buffer."""
        if self.thread_safe:
            with self._lock:
                return self._get_last_no_lock(n)
        return self._get_last_no_lock(n)
    
    def _get_last_no_lock(self, n: int) -> List[T]:
        """Non-thread-safe version of get_last."""
        if self._size == 0:
            return []
            
        n = min(n, self._size)
        
        if isinstance(self._buffer, np.ndarray):
            last_idx = (self._start + self._size - 1) % self.capacity
            if last_idx >= n - 1:
                # No wrap-around needed
                return self._buffer[last_idx - n + 1:last_idx + 1].tolist()
            else:
                # Handle wrap-around
                first_part = self._buffer[self.capacity - (n - 1 - last_idx):].tolist()
                second_part = self._buffer[:last_idx + 1].tolist()
                return first_part + second_part
        else:
            result = []
            for i in range(n):
                idx = (self._start + self._size - n + i) % self.capacity
                result.append(self._buffer[idx])
            return result

# Specific circular buffer implementations for different sensor types

class AccelerometerBuffer(CircularBuffer[float]):
    """Specialized buffer for accelerometer data."""
    
    def __init__(self, capacity: int = 1000):
        super().__init__(capacity, dtype=np.float32)
    
    def get_statistics(self) -> Dict[str, float]:
        """Calculate statistical measures from the accelerometer data."""
        data = self.get_all()
        if not data:
            return {'mean': 0, 'std': 0, 'min': 0, 'max': 0}
        
        # Using numpy for efficient calculations
        data_array = np.array(data)
        return {
            'mean': float(np.mean(data_array)),
            'std': float(np.std(data_array)),
            'min': float(np.min(data_array)),
            'max': float(np.max(data_array))
        }

class LidarPointBuffer(CircularBuffer[List[float]]):
    """Specialized buffer for LiDAR point data."""
    
    def __init__(self, capacity: int = 1000):
        # For LiDAR, we store objects (lists or tuples), not a numeric dtype
        super().__init__(capacity, dtype=None)

class GPSHistoryBuffer(CircularBuffer[Dict[str, Any]]):
    """Buffer for storing GPS history with efficient storage."""
    
    def __init__(self, capacity: int = 1000):
        super().__init__(capacity, dtype=None)
    
    def add_point(self, lat: float, lon: float, quality: float, timestamp: float) -> None:
        """Add a GPS point with quality data."""
        self.append({
            'lat': lat,
            'lon': lon,
            'quality': quality,
            'timestamp': timestamp
        })

class EnvironmentalDataBuffer(CircularBuffer[Dict[str, Any]]):
    """Buffer for environmental sensor data history."""
    
    def __init__(self, capacity: int = 300):  # Default ~5 minutes at 1 sample/sec
        super().__init__(capacity, dtype=None)
    
    def add_reading(self, temperature: Optional[float] = None, 
                   humidity: Optional[float] = None,
                   pressure: Optional[float] = None,
                   timestamp: float = None) -> None:
        """Add an environmental sensor reading."""
        self.append({
            'temperature': temperature,
            'humidity': humidity, 
            'pressure': pressure,
            'timestamp': timestamp or time.time()
        })