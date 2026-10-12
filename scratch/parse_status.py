with open(r'C:\Users\mama1\.gemini\antigravity-ide\brain\9bfa61bb-95bb-4333-b946-91b05f48c097\.system_generated\tasks\task-316.log', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

import re
matches = re.findall(r'"status":\s*(\d+)', text)
print("Status codes found:", matches)
