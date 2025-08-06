import base64
import pickle
import pprint
from googleapiclient.discovery import build
from base64 import urlsafe_b64decode, urlsafe_b64encode
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from mimetypes import guess_type as guess_mime_type
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Request all access (permission to read/send/receive emails, manage the inbox, and more)
SCOPES = ['https://mail.google.com/']
our_email = 'slava.dmitriev1312@gmail.com'

def gmail_authentication():
  creds = None
  if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "credentials.json", SCOPES
      )
      creds = flow.run_local_server(port=0)
    with open("token.json", "w") as token:
      token.write(creds.to_json())

  try:
    service = build("gmail", "v1", credentials=creds)
    return service

  except HttpError as error:
    return 0    

def get_unread_emails(service, user_id='me'):
    try: 
        results = service.users().messages().list(userId=user_id, labelIds='UNREAD', maxResults=10).execute()
        messages = results.get('messages', [])
        return messages
    except HttpError as error:
        print(f'An error occurred: {error}')
        return []

# Adds the attachment with the given filename to the given message
def add_attachment(message, filename):
    content_type, encoding = guess_mime_type(filename)
    if content_type is None or encoding is not None:
        content_type = 'application/octet-stream'
    main_type, sub_type = content_type.split('/', 1)
    if main_type == 'text':
        fp = open(filename, 'rb')
        msg = MIMEText(fp.read().decode(), _subtype=sub_type)
        fp.close()
    elif main_type == 'image':
        fp = open(filename, 'rb')
        msg = MIMEImage(fp.read(), _subtype=sub_type)
        fp.close()
    elif main_type == 'audio':
        fp = open(filename, 'rb')
        msg = MIMEAudio(fp.read(), _subtype=sub_type)
        fp.close()
    else:
        fp = open(filename, 'rb')
        msg = MIMEBase(main_type, sub_type)
        msg.set_payload(fp.read())
        fp.close()
    filename = os.path.basename(filename)
    msg.add_header('Content-Disposition', 'attachment', filename=filename)
    message.attach(msg)

def build_message(destination, obj, body, attachments=[]):
    if not attachments: # no attachments given
        message = MIMEText(body)
        message['to'] = destination
        message['from'] = our_email
        message['subject'] = obj
    else:
        message = MIMEMultipart()
        message['to'] = destination
        message['from'] = our_email
        message['subject'] = obj
        message.attach(MIMEText(body))
        for filename in attachments:
            add_attachment(message, filename)
    return {'raw': urlsafe_b64encode(message.as_bytes()).decode()}

def send_message(service, destination, obj, body, attachments = None):
    return service.users().messages().send(
      userId="me",
      body=build_message(destination, obj, body, attachments)
    ).execute()

def get_last_email(service, user_id='me'):
    try:
        results = service.users().messages().list(userId=user_id, maxResults=2).execute()
        messages = results.get('messages', [])
        if not messages:
            return None
        message = service.users().messages().get(userId=user_id, id=messages[0]['id']).execute()
        return message
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None
# send_message(gmail_authentication(), 'anastasiaroganina@gmail.com', 'Important message', 'Какой фильм смотреть сегодня будем? Шерлок Холмс?')
service = gmail_authentication()
messages = get_unread_emails(service)
body_data = service.users().messages().get(userId='me', id=messages[4]['id']).execute()['payload']['parts'][0]['body']["data"]
value = service.users().messages().get(userId='me', id=messages[4]['id']).execute()['payload']['parts'][0]["headers"][1]["value"]
# charset = value = service.users().messages().get(userId='me', id=messages[4]['id']).execute()['payload']['parts'][0]["headers"][1]["charset"]
print(value)
# for message in messages:
#     retrieved_message = service.users().messages().get(userId='me', id=message['id']).execute()
#     payload = retrieved_message['payload']
#     parts = payload.get('parts', [])
#     for part in parts:
#         if part['mimeType'] == 'text/plain':
#             data = part['body']['data']
#             text = base64.urlsafe_b64decode(data).decode('utf-8')
#             print(f"Plain Text Body: {text}")
#         elif part['mimeType'] == 'text/html':
#             data = part['body']['data']
#             html = base64.urlsafe_b64decode(data).decode('utf-8')
#             print(f"HTML Body: {html}")
