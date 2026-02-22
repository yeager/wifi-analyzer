"""Undo/Redo stack for application state changes."""


class UndoRedoManager:
    """Simple undo/redo manager with action stack."""

    def __init__(self, max_size=50):
        self._undo_stack = []
        self._redo_stack = []
        self._max_size = max_size

    def push(self, undo_fn, redo_fn, description=""):
        """Push an undoable action."""
        self._undo_stack.append((undo_fn, redo_fn, description))
        if len(self._undo_stack) > self._max_size:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        """Undo the last action. Returns True if successful."""
        if not self._undo_stack:
            return False
        undo_fn, redo_fn, desc = self._undo_stack.pop()
        undo_fn()
        self._redo_stack.append((undo_fn, redo_fn, desc))
        return True

    def redo(self):
        """Redo the last undone action. Returns True if successful."""
        if not self._redo_stack:
            return False
        undo_fn, redo_fn, desc = self._redo_stack.pop()
        redo_fn()
        self._undo_stack.append((undo_fn, redo_fn, desc))
        return True

    def can_undo(self):
        return bool(self._undo_stack)

    def can_redo(self):
        return bool(self._redo_stack)

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
