"""Which inventory version this APK is.  "A" = Automatic posting (journal entries are written for you),
"B" = Separate list (stock list only, the journal is never touched).  The GitHub build sets this for you."""
import os
VARIANT = os.environ.get("JM_VARIANT", "A")
AUTO_POST = VARIANT == "A"
VARIANT_NAME = "Automatic posting" if AUTO_POST else "Separate list"
DATA_FILE = "jm_data_inventory_auto.json" if AUTO_POST else "jm_data_inventory_separate.json"
