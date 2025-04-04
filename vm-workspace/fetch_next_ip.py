import requests
import sys
import json

def fetch_next_ip(range, token, api_url=None):
    # Default API URL if not provided
    if not api_url:
        api_url = "https://netbox.chrobinson.com/api"
    
    url = f"{api_url}/ipam/prefixes/{range}/available-ips/"
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()[0]["address"]

if __name__ == "__main__":
    query = json.loads(sys.stdin.read())
    range = query["range"]
    token = query["token"]
    api_url = query.get("api_url")  # Optional parameter
    ip = fetch_next_ip(range, token, api_url)
    print(json.dumps({"ip": ip}))
