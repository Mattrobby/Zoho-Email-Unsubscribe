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
    scope = 'ZohoMail.messages.READ,ZohoMail.messages.DELETE,ZohoMail.accounts.READ'
    auth_url = f'https://accounts.zoho.com/oauth/v2/auth?scope={scope}&client_id={client_id}&response_type=code&access_type=offline&redirect_uri={redirect_uri}'
    return redirect(auth_url)


@app.route('/callback')
def callback():
    global account_id, access_token  # Use global variables

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


@app.route('/fetch-emails')
def fetch_emails():
    global account_id, access_token  # Use global variables

    offset = 0
    limit = 500

    if not account_id or not access_token:
        # Store the URL that initiated the login process
        session['redirect_back_to'] = request.url
        return redirect('/login')

    # Endpoint to fetch emails
    api_url = f'https://mail.zoho.com/api/accounts/{account_id}/messages/view?limit={limit}'
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(api_url, headers=headers)

    if response.status_code == 200:
        return response.json()  # Returns the list of emails in JSON format
    else:
        return f"Error fetching emails: {response.status_code} {response.text}", 500


@app.route('/unsubscribe')
def unsubscribe():
    emails = fetch_emails()
    return emails


if __name__ == '__main__':
    app.run(debug=True)

