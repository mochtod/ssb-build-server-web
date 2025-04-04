import requests
import sys
import json

def fetch_next_ip(range, token):
    url = f"https://netbox.chrobinson.com/api/ipam/prefixes/{range}/available-ips/"
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()[0]["address"]

if __name__ == "__main__":
    query = json.loads(sys.stdin.read())
    range = query["range"]
    token = query["token"]
    ip = fetch_next_ip(range, token)
    print(json.dumps({"ip": ip}))