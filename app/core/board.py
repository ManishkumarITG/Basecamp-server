"""Card Table board configuration.

Columns are a fixed default set (the screenshots' stages). Each card stores its
column ``key``; the labels/accents here drive rendering. Kept in one place so the
backend validates moves and the frontend renders consistent columns.
"""

DEFAULT_COLUMNS = [
    {"key": "triage", "label": "Triage", "accent": "slate"},
    {"key": "figuring_it_out", "label": "Figuring it out", "accent": "violet"},
    {"key": "in_progress", "label": "In progress", "accent": "amber"},
    {"key": "qa", "label": "QA", "accent": "rose"},
    {"key": "delivered", "label": "Delivered to Manager", "accent": "indigo"},
    {"key": "done", "label": "Done", "accent": "green"},
    {"key": "not_now", "label": "Not now", "accent": "slate"},
]

COLUMN_KEYS = {column["key"] for column in DEFAULT_COLUMNS}
COLUMN_LABELS = {column["key"]: column["label"] for column in DEFAULT_COLUMNS}
DEFAULT_COLUMN = "triage"
