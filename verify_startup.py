import json
from backend.database import engine
print('dialect:', engine.dialect.name)
print('url:', str(engine.url))
from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)
resp = client.get('/dashboard/sales-trend?period=6m')
print('status:', resp.status_code)
print('body:', resp.json())
