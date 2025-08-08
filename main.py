import os
import sys
import json

# Activate the virtual environment (embedded)
venv_site_packages = os.path.join(os.path.dirname(__file__), r"venv\Lib\site-packages")
if venv_site_packages not in sys.path:
    sys.path.insert(0, venv_site_packages)

print("Virtual environment activated within script.")
print("sys.path includes:", venv_site_packages)

# Load configuration from config file for flexibility
CONFIG_FILE = "setup-config.json"

def load_entry_point():
    if not os.path.exists(CONFIG_FILE):
        print(f"{CONFIG_FILE} not found.")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    main_file = config.get("main_file", "app.py")
    if not os.path.exists(main_file):
        print(f"{main_file} does not exist.")
        sys.exit(1)

    print(f"Running: {main_file}")
    with open(main_file, encoding="utf-8") as f:
        exec(f.read(), globals())

if __name__ == "__main__":
    load_entry_point()