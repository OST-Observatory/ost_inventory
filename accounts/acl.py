"""Inventory capabilities assigned to Django groups."""

ROLE_GROUPS = ("student", "supervisor", "staff")

READ = "read"
WRITE = "write"
LOAN_PII = "loan_pii"
INACTIVE = "inactive"
IMPORT = "import"
LABELS = "labels"
DELETE = "delete"
MANAGE_ACL = "manage_acl"

CAPABILITIES = (
    (READ, "Read inventory"),
    (WRITE, "Add and edit items, loans, and locations"),
    (LOAN_PII, "See borrower name and contact"),
    (INACTIVE, "See inactive items"),
    (IMPORT, "Import CSV"),
    (LABELS, "QR labels"),
    (DELETE, "Permanently delete items"),
    (MANAGE_ACL, "Manage access and groups"),
)

CAPABILITY_CODES = tuple(code for code, _label in CAPABILITIES)
CAPABILITY_LABELS = dict(CAPABILITIES)

DEFAULT_GROUP_CAPABILITIES = {
    "student": (READ,),
    "supervisor": (READ, WRITE, LOAN_PII, INACTIVE, IMPORT, LABELS),
    "staff": (
        READ,
        WRITE,
        LOAN_PII,
        INACTIVE,
        IMPORT,
        LABELS,
        DELETE,
        MANAGE_ACL,
    ),
}
