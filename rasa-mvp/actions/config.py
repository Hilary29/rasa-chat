import os
from dotenv import load_dotenv

load_dotenv(verbose=True, override=True)

API_USERS_URL = os.environ.get("API_USERS_URL", "https://jsonplaceholder.typicode.com/users")
