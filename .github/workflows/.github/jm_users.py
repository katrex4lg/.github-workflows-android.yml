"""JM-ACCOUNTS SYSTEM - users, roles, permissions and password hashing (no GUI; same logic as the desktop jm_auth.py)."""
import hashlib, hmac, json, os, secrets, time

from jm_core import APP_NAME, data_dir

NAVY, BLUE, SKY, PANEL = "#1F3A5F", "#3F6EA8", "#BBD3EE", "#EAF1F8"
INK, MUTED, LINE, RED, GOLD = "#1B2B45", "#6B7C93", "#C9D3E0", "#C0392B", "#F2B544"

# What a Staff member may edit - only when the Admin ticks it for them. Admin always has everything.
PERMS = [("accounts", "Edit the Chart of Accounts"),
         ("journal", "Edit the General Journal"),
         ("inventory", "Edit Inventory (items and stock movements)"),
         ("settings", "Edit business name, period end, import / restore and Gmail settings")]
DEFAULT_ADMIN = ("admin", "admin123")     # first start only - you are made to change it at once
MIN_PW = 6
ITERATIONS = 200_000


# ============================================================ users and passwords
def _hash(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), ITERATIONS).hex()


class Session:
    """Who is signed in, and what they are allowed to do."""
    def __init__(self, user):
        self.username, self.name, self.role = user["username"], user.get("name") or user["username"], user["role"]
        self.perms = set(user.get("perms", []))

    @property
    def display_name(self):
        """What the header shows: the person's name; the built-in placeholder 'Administrator' becomes their username."""
        n = (self.name or "").strip()
        return self.username if not n or n.lower() == "administrator" else n

    @property
    def is_admin(self):
        return self.role == "admin"

    def can(self, perm):
        return self.is_admin or perm in self.perms

    @property
    def role_label(self):
        return "Admin" if self.is_admin else "Staff"


class UserStore:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "jm_users.json")
        self.users = []
        self.load()

    # ---------- persistence
    def load(self):
        self.users = []
        if os.path.exists(self.path):
            try:
                self.users = json.load(open(self.path, encoding="utf-8")).get("users", [])
            except Exception:
                try: os.replace(self.path, self.path + ".corrupt")
                except OSError: pass
                self.users = []
        if not any(u["role"] == "admin" and u.get("active", True) for u in self.users):
            self._make_default_admin()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": self.users}, f, indent=1)
        os.replace(tmp, self.path)

    def _make_default_admin(self):
        name, pw = DEFAULT_ADMIN
        self.users = [u for u in self.users if u["username"].lower() != name]
        self.users.insert(0, self._new(name, "Administrator", pw, "admin", [], True, must_change=True))
        self.save()

    @staticmethod
    def _new(username, name, password, role, perms, active, must_change=False):
        salt = secrets.token_hex(16)
        return {"username": username, "name": name, "salt": salt, "hash": _hash(password, salt), "role": role,
                "perms": sorted(set(perms) & {k for k, _ in PERMS}), "active": bool(active), "must_change": must_change}

    # ---------- look-ups
    def user(self, username):
        u = (username or "").strip().lower()
        return next((x for x in self.users if x["username"].lower() == u), None)

    def _active_admins(self):
        return [u for u in self.users if u["role"] == "admin" and u.get("active", True)]

    def authenticate(self, username, password):
        u = self.user(username)
        if not u:
            _hash(password, "00" * 16)             # same delay whether or not the name exists
            return None
        ok = hmac.compare_digest(_hash(password, u["salt"]), u["hash"])
        return dict(u) if ok and u.get("active", True) else None

    # ---------- changes
    @staticmethod
    def check_password(pw):
        if len(pw) < MIN_PW: raise ValueError(f"The password must be at least {MIN_PW} characters.")

    def add_user(self, username, name, password, role, perms, active=True):
        username = (username or "").strip()
        if not username: raise ValueError("Enter a username.")
        if any(ch.isspace() for ch in username): raise ValueError("The username cannot contain spaces.")
        if self.user(username): raise ValueError(f"The username '{username}' is already taken.")
        if role not in ("admin", "staff"): raise ValueError("Choose a role.")
        self.check_password(password)
        self.users.append(self._new(username, (name or "").strip() or username, password, role,
                                    [] if role == "admin" else perms, active, must_change=True))
        self.save()

    def update_user(self, username, name, role, perms, active):
        u = self.user(username)
        if not u: raise ValueError("User not found.")
        if role not in ("admin", "staff"): raise ValueError("Choose a role.")
        if u["role"] == "admin" and u.get("active", True) and (role != "admin" or not active) and len(self._active_admins()) <= 1:
            raise ValueError("There must always be at least one active Admin.")
        u.update(name=(name or "").strip() or u["username"], role=role, active=bool(active),
                 perms=[] if role == "admin" else sorted(set(perms) & {k for k, _ in PERMS}))
        self.save()

    def rename_user(self, old, new):
        u = self.user(old)
        if not u: raise ValueError("User not found.")
        new = (new or "").strip()
        if not new: raise ValueError("Enter the new username.")
        if any(ch.isspace() for ch in new): raise ValueError("The username cannot contain spaces.")
        other = self.user(new)
        if other is not None and other is not u: raise ValueError(f"The username '{new}' is already taken.")
        u["username"] = new; self.save()
        return new

    def set_password(self, username, new_password, must_change=False):
        u = self.user(username)
        if not u: raise ValueError("User not found.")
        self.check_password(new_password)
        u["salt"] = secrets.token_hex(16); u["hash"] = _hash(new_password, u["salt"]); u["must_change"] = must_change
        self.save()

    def delete_user(self, username, current_username):
        u = self.user(username)
        if not u: raise ValueError("User not found.")
        if u["username"].lower() == (current_username or "").lower(): raise ValueError("You cannot delete the account you are signed in with.")
        if u["role"] == "admin" and u.get("active", True) and len(self._active_admins()) <= 1:
            raise ValueError("There must always be at least one active Admin.")
        self.users = [x for x in self.users if x is not u]; self.save()


