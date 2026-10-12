import requests
import json
import time

token = "441829999|iTLGK2FIPKaQvntDX9BVv20iIoE6LHZegF5m5eZd"
target_channel = "sozcutv"

headers = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json',
    'Referer': f'https://kick.com/{target_channel}',
    'Origin': 'https://kick.com',
}

print(f"=== TESTING TOKEN FOR {target_channel} ===")

# 1. Check user info with token
try:
    print("\n1. Testing token identity (/api/v1/user)...")
    r_user = requests.get('https://kick.com/api/v1/user', headers=headers, timeout=10)
    print(f"Status: {r_user.status_code}")
    print(f"Body: {r_user.text[:300]}")
except Exception as e:
    print(f"Error checking user: {e}")

# 2. Get channel details for sozcutv
chatroom_id = None
try:
    print(f"\n2. Getting channel info for {target_channel}...")
    r_chan = requests.get(f'https://kick.com/api/v2/channels/{target_channel}', headers=headers, timeout=10)
    print(f"Status: {r_chan.status_code}")
    if r_chan.status_code == 200:
        data = r_chan.json()
        chatroom_id = data.get('chatroom', {}).get('id')
        print(f"Channel found! Chatroom ID: {chatroom_id}")
    else:
        print(f"Chan body: {r_chan.text[:300]}")
except Exception as e:
    print(f"Error getting channel info: {e}")

if not chatroom_id:
    chatroom_id = 71783953  # Fallback known chatroom_id for sozcutv

# 3. Test Follow
try:
    print(f"\n3. Testing Follow ({target_channel})...")
    follow_url = f'https://kick.com/api/v2/channels/{target_channel}/follow'
    r_follow = requests.post(follow_url, headers=headers, timeout=10)
    print(f"Follow Status: {r_follow.status_code}")
    print(f"Follow Body: {r_follow.text[:300]}")
except Exception as e:
    print(f"Error following: {e}")

# 4. Test Send "sa" to chat
try:
    print(f"\n4. Testing Send 'sa' to chatroom {chatroom_id}...")
    msg_url = f'https://kick.com/api/v2/messages/send/{chatroom_id}'
    payload = {'content': 'sa', 'type': 'message'}
    r_msg = requests.post(msg_url, json=payload, headers=headers, timeout=10)
    print(f"Message Status: {r_msg.status_code}")
    print(f"Message Body: {r_msg.text[:300]}")
except Exception as e:
    print(f"Error sending message: {e}")
