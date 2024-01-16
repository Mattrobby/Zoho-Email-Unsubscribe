from flask import Flask, request, redirect, session, render_template, jsonify
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import requests
import httpx
import asyncio
import os

load_dotenv()

app = Flask(__name__)
# Set a strong, secret key for session handling
app.secret_key = 'your_secret_key'

# Your credentials
client_id = os.getenv('CLIENT_ID')
client_secret = os.getenv('CLIENT_SECRET')
redirect_uri = os.getenv('REDIRECT_URL')

# Global variables to store account ID and access token
account_id = None
access_token = None


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/login')
def login():
    scope = 'ZohoMail.accounts.READ,ZohoMail.messages.ALL,ZohoMail.folders.READ'
    auth_url = f'https://accounts.zoho.com/oauth/v2/auth?scope={scope}&client_id={client_id}&response_type=code&access_type=offline&redirect_uri={redirect_uri}'
    return redirect(auth_url)


@app.route('/callback')
def callback():
    global account_id, access_token

    code = request.args.get('code')
    if not code:
        return "No code provided", 400

    # Exchange the authorization code for an access token
    token_url = 'https://accounts.zoho.com/oauth/v2/token'
    token_data = {
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'authorization_code'
    }
    response = requests.post(token_url, data=token_data)
    if response.status_code == 200:
        access_token = response.json().get('access_token')
        if not access_token:
            return "Access token not found in response", 500

        # Fetch account details
        api_url = 'https://mail.zoho.com/api/accounts'
        headers = {'Authorization': f'Bearer {access_token}'}
        api_response = requests.get(api_url, headers=headers)

        if api_response.status_code == 200:
            account_data = api_response.json()
            account_id = account_data['data'][0]['accountId']

            # Redirect back to the original URL after successful login
            redirect_url = session.pop('redirect_back_to', None)
            if redirect_url:
                return redirect(redirect_url)
            return f"Account ID: {account_id}"
        else:
            return f"Error fetching account details: {api_response.status_code} {api_response.text}", 500
    else:
        return "Error obtaining access token", 500


async def get_unsubscribe_link(client, email, account_id, access_token, folder_map):
    message_id = email['messageId']
    folder_id = email['folderId']
    subject = email['subject']
    sender = email['sender']
    from_address = email['fromAddress']
    api_url = f'https://mail.zoho.com/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/content'
    headers = {'Authorization': f'Bearer {access_token}'}
    response = await client.get(api_url, headers=headers)

    unsubscribe_url = None
    if response.status_code == 200:
        data = response.json().get("data", {})
        content = data.get("content", "").lower()

        if 'unsubscribe' in content:
            soup = BeautifulSoup(content, 'html.parser')
            for anchor in soup.find_all('a'):
                anchor_text = anchor.get_text().lower()
                anchor_title = anchor.get('title', '').lower()
                if 'unsubscribe' in anchor_text or 'unsubscribe' in anchor_title or 'here' in anchor_text:
                    unsubscribe_url = anchor.get('href')
                    break
            else:
                unsubscribe_url = None  # None if no matching URLs found
        else:
            return None
    else:
        return f"Error reading email content for {message_id}", 500

    return {
        "subject": subject,
        "sender": sender,
        "from_address": from_address,
        # "content": content,
        "folder": folder_map.get(folder_id),
        "unsubscribe_url": unsubscribe_url,
        "message_id": message_id,
        "folder_id": folder_id
    }


async def process_emails(account_id, access_token, emails, folder_map, unsubscribe=True):
    async with httpx.AsyncClient() as client:
        tasks = [get_unsubscribe_link(
            client, email, account_id, access_token, folder_map) for email in emails]
        email_details = await asyncio.gather(*tasks)
        # Filter out None values
        if unsubscribe:
            return [detail for detail in email_details if detail is not None]
        else:
            return email_details


@app.route('/unsubscribe')
def unsubscribe():
    global account_id, access_token

    # Checks if user is logged in
    if not account_id or not access_token:
        session['redirect_back_to'] = request.url
        return redirect('/login')

    # Gets the folder_id of the inbox
    api_url = f'https://mail.zoho.com/api/accounts/{account_id}/folders'
    headers = {'Authorization': f'Bearer {access_token}'}
    folder_response = requests.get(api_url, headers=headers)

    if folder_response.status_code != 200:
        return f"Error fetching inbox_id: {folder_response.status_code} {folder_response.text}", 500

    folder_data = folder_response.json()
    folder_map = {item["folderId"]: item["path"]
                  for item in folder_data["data"]}

    # Creates a list of all emails stored in the inbox
    emails = []
    limit = 200
    start = 0
    email_count = 200

    while email_count >= 200:
        api_url = f'https://mail.zoho.com/api/accounts/{account_id}/messages/view?start={start}&limit={limit}'
        headers = {'Authorization': f'Bearer {access_token}'}
        emails_response = requests.get(api_url, headers=headers)

        if emails_response.status_code != 200:
            return f"Error fetching emails: {emails_response.status_code} {emails_response.text}", 500

        email_data = emails_response.json()['data']
        email_count = len(email_data)
        emails.extend(email_data)
        start += limit

    # Process all emails asynchronously to get unsubscribe links
    unsubscribe_links = asyncio.run(process_emails(
        account_id, access_token, emails, folder_map))

    # Reformat the data into a hashmap
    email_map = {}
    for email in unsubscribe_links:
        from_address = email['from_address']
        if from_address not in email_map:
            email_map[from_address] = []
        email_map[from_address].append(email)

    # Render an HTML template instead of returning JSON
    return render_template('unsubscribe.html', email_map=email_map)
    # return emails


@app.route('/delete', methods=['POST'])
def delete():
    global account_id, access_token

    # Checks if user is logged in
    if not account_id or not access_token:
        session['redirect_back_to'] = request.url
        return redirect('/login')

    # Retrieve folder_id and message_id from the request
    folder_id = request.form.get('folder_id')
    message_id = request.form.get('message_id')

    # Validate folder_id and message_id
    if not folder_id or not message_id:
        return jsonify({"error": "Missing folder_id or message_id"}), 400

    # The API URL to delete the email
    api_url = f'https://mail.zoho.com/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}'
    headers = {'Authorization': f'Bearer {access_token}'}

    # Send the DELETE request
    response = requests.delete(api_url, headers=headers)

    # Check if the deletion was successful
    if response.status_code == 200:
        return jsonify({"message": "Email deleted successfully"}), 200
    else:
        return jsonify({"error": "Failed to delete email", "details": response.text}), response.status_code


if __name__ == '__main__':
    app.run(debug=True)
