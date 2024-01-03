from urllib.parse import urlencode
from flask import Flask, request, redirect, session, render_template
import requests

app = Flask(__name__)
# Set a strong, secret key for session handling
app.secret_key = 'your_secret_key'

# Your credentials
client_id = '1000.RSVJRZHN5FCU92W4C9SMPAXM68X7AC'
client_secret = 'f439ea7bf0093a173b66fee38c2370fbc5cfe804d0'
redirect_uri = 'http://localhost:5000/callback'

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


def get_unsubscribe_link(message_id, folder_id):
    global account_id, access_token

    message_id = "1704232973332110001"
    folder_id = "6314644000000008014"

    api_url = f'https://mail.zoho.com/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/content'

    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(api_url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        return f"Error fetching email message: {response.status_code} {response.text}", 500


@app.route('/unsubscribe')
def unsubscribe():
    global account_id, access_token

    # Checks if user is logged in
    if not account_id or not access_token:
        # Store the URL that initiated the login process
        session['redirect_back_to'] = request.url
        return redirect('/login')

    # Gets the folder_id of the inbox
    api_url = f'https://mail.zoho.com/api/accounts/{account_id}/folders'

    headers = {'Authorization': f'Bearer {access_token}'}
    folder_response = requests.get(api_url, headers=headers)

    if folder_response.status_code == 200:
        folder_data = folder_response.json()
        folder_map = {item["folderId"]: item["path"]
                      for item in folder_data["data"]}

    else:
        return f"Error fetching inbox_id: {folder_response.status_code} {folder_response.text}", 500

    # Creates a list of all emails stored in the inbox
    emails = []
    limit = 200
    start = 0
    email_count = 200

    while email_count >= 200:
        # Endpoint to fetch emails
        api_url = f'https://mail.zoho.com/api/accounts/{account_id}/messages/view?start={start}&limit={limit}'

        headers = {'Authorization': f'Bearer {access_token}'}
        emails_response = requests.get(api_url, headers=headers)

        if emails_response.status_code == 200:
            email_data = emails_response.json()['data']
        else:
            return f"Error fetching emails: {emails_response.status_code} {emails_response.text}", 500
        print(f'Getting emails {start}-{start+200}')

        email_count = len(email_data)
        emails.extend(email_data)
        start = start + 200

        for email in emails:
            message_id = email['messageId']
            folder_id = email['folderId']
            subject = email['subject']
            sender = email['sender']
            from_adderss = email['fromAddress']
            folder = folder_map.get(folder_id)

    return emails


if __name__ == '__main__':
    app.run(debug=True)
