"""Quick test script to verify auth + project creation against Neon DB."""
import urllib.request
import json

API = "http://localhost:8000"

def post(path, data, token=None):
    body = json.dumps(data).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}{path}", data=body, headers=headers)
    r = urllib.request.urlopen(req)
    return json.loads(r.read().decode())

def get(path, token):
    req = urllib.request.Request(f"{API}{path}", headers={"Authorization": f"Bearer {token}"})
    r = urllib.request.urlopen(req)
    return json.loads(r.read().decode())

# 1. Register
print("=" * 50)
print("1. Registering user...")
tokens = post("/api/v1/auth/register", {
    "email": "admin@defectsync.io",
    "password": "DefectSync2026!",
    "full_name": "Admin User",
    "organization_name": "DefectSync Demo",
})
token = tokens["access_token"]
print(f"   OK — got access_token ({len(token)} chars)")

# 2. Get current user
print("2. Fetching /me...")
user = get("/api/v1/auth/me", token)
print(f"   OK — {user['full_name']} | {user['email']} | role={user['role']}")

# 3. Create a project
print("3. Creating project...")
project = post("/api/v1/projects/", {
    "name": "Highway Bridge Retrofit",
    "description": "Structural assessment of NH-48 bridge",
    "address": "NH-48, Sector 14, Gurgaon",
    "client_name": "NHAI",
}, token)
print(f"   OK — project_id={project['id'][:8]}... name={project['name']}")

# 4. List projects
print("4. Listing projects...")
proj_list = get("/api/v1/projects/", token)
print(f"   OK — {proj_list['total']} project(s) found")

# 5. Detection config
print("5. Checking detection config...")
config = get("/api/v1/detect/config", token)
print(f"   OK — model={config['model_name']} classes={config['supported_classes']}")

print("=" * 50)
print("ALL TESTS PASSED! Backend is fully operational.")
print(f"Project ID for detection: {project['id']}")
