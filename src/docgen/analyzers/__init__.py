from .web_analyzer import analyze_web_interface
from .db_analyzer import analyze_database
from .request_analyzer import analyze_request

__all__ = ["analyze_web_interface", "analyze_database", "analyze_request"]
