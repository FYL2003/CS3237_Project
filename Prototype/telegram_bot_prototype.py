"""
Telegram Bot — Simple Instruction Sender
----------------------------------------
Features:
 - Reads bot token and chat ID from BotAPI.txt
 - Sends a predefined instruction message to a Telegram chat
 - Uses Telegram Bot API via HTTPS POST request
 - Useful for testing notification functionality independently

Author : Feng Yilong
"""

import requests

# Read token and chat ID from BoxAPI.txt
with open("BotAPI.txt", "r") as f:
    lines = f.read().splitlines()
    TOKEN = lines[0].strip()      # first line = bot token
    CHAT_ID = lines[1].strip()    # second line = chat ID

# Instruction you want to send
instruction = "Please eat banana! It only have less than n days to rot!"

# Telegram API endpoint
url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": instruction
}

# Send the message
response = requests.post(url, json=payload)
if response.status_code == 200:
    print("Message sent successfully!")
else:
    print("Failed to send message:", response.status_code, response.text)
