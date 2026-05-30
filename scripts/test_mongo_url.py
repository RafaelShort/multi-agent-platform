import sys
sys.path.insert(0, ".")

from core.config import settings

print(f"URL usada pelo Python: [{settings.MONGODB_URL}]")
print(f"DB Name: [{settings.MONGODB_DB_NAME}]")
