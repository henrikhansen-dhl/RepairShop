import threading


_thread_locals = threading.local()


def set_current_db(db_name: str) -> None:
    _thread_locals.current_db = db_name


def get_current_db(default: str = "default") -> str:
    return getattr(_thread_locals, "current_db", default)


def clear_current_db() -> None:
    if hasattr(_thread_locals, "current_db"):
        delattr(_thread_locals, "current_db")
