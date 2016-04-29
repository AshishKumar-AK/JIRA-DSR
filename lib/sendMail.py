import os
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio
from email.utils import COMMASPACE, formatdate
from email import encoders


class EmailMessage:
    """
    Custom wrapper class to easily create email message object
    """
    def __init__(self):
        self.msgRoot = MIMEMultipart('related')
        self.msgAlternative = MIMEMultipart('alternative')
        self.msgRoot.attach(self.msgAlternative)

    def as_string(self):
        """
        This method will return email message constructed by this class
        :return: (string) email message as string
        """
        return self.msgRoot.as_string()

    def add_mail_headers(self, subject, frm, to=[], cc=[], bcc=[]):
        """
        This method simply adds email message headers like subject, from, to and cc, bcc
        :param subject: (string) email subject
        :param frm: (string) email address
        :param to: (list) email addresses
        :param cc: (list) email addresses
        :param bcc: (list) email addresses
        :return: None
        """
        self.msgRoot['From'] = frm
        self.msgRoot['To'] = COMMASPACE.join(to)
        self.msgRoot['Cc'] = COMMASPACE.join(cc)
        self.msgRoot['Bcc'] = COMMASPACE.join(bcc)
        self.msgRoot['Subject'] = subject
        self.msgRoot['Date'] = formatdate(localtime=True)

    def add_mail_attachments(self, attachments=[]):
        """
        This method adds list of attachments to email message
        :param attachments: (list) of file paths strings
        :return: None
        """
        if attachments:
            for f in attachments:
                with open(f, 'rb') as file:
                    content_type, encoding = mimetypes.guess_type(f)
                    if content_type is None or encoding is not None:
                        content_type = 'application/octet-stream'
                    main_type, sub_type = content_type.split('/', 1)
                    if main_type == 'text':
                        part = MIMEText(file.read().decode('UTF-8'), _subtype=sub_type)
                    elif main_type == 'image':
                        part = MIMEImage(file.read().decode('UTF-8'), _subtype=sub_type)
                    elif main_type == 'audio':
                        part = MIMEAudio(file.read().decode('UTF-8'), _subtype=sub_type)
                    else:
                        part = MIMEBase(main_type, sub_type)
                        part.set_payload(file.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', 'attachment; filename="{0}"'
                                    .format(os.path.basename(f)))
                    self.msgRoot.attach(part)

    def add_plaintext_msg(self, text):
        """
        This method simply adds text email body to email message
        :param text: (String) text email content
        :return: None
        """
        self.msgAlternative.attach(MIMEText(text))

    def add_html_msg(self, html_body, inline_imgs=[]):
        """
        This method adds HTML email body to email message
        :param html_body: (String) HTML email content
        :param inline_imgs: (list) of image paths referenced as inline content in email
        :return: None
        """
        msg = MIMEText(html_body, 'html', 'utf-8')
        self.msgAlternative.attach(msg)
        if inline_imgs:
            for f in inline_imgs:
                filename = os.path.basename(f)
                with open(f, 'rb') as file:
                    image = MIMEImage(file.read(), name=filename)
                    image.add_header('Content-ID', '<{}>'.format(filename))
                    self.msgRoot.attach(image)


class SMTPMailer:
    """
    Custom wrapper class to send SMTP(TLS) emails
    """
    @staticmethod
    def send_mail(email_message, server='localhost', port=25,
                  is_tls=False, user=None, passwd=None):
        try:
            import smtplib
        except ImportError:
            raise
        smtp = smtplib.SMTP(server, port)
        try:
            if is_tls:
                    smtp.ehlo()
                    smtp.starttls()
                    if user and passwd:
                        smtp.login(user, passwd)
            smtp.sendmail(email_message.msgRoot['From'],
                          email_message.msgRoot['To'],
                          email_message.msgRoot.as_string())
        finally:
            smtp.quit()


class GMAILAPIMailer:
    """
    Custom wrapper class to send emails using gmail api
    """
    @staticmethod
    def send_mail(email_message, secret, storage):
        try:
            import httplib2
            import base64
            from apiclient import discovery
            from oauth2client.client import flow_from_clientsecrets
            from oauth2client.file import Storage
            from oauth2client.tools import run_flow
        except ImportError:
            raise

        raw = base64.urlsafe_b64encode(email_message.as_string().encode('ascii'))
        content = {'raw': raw.decode('UTF-8')}

        scope = 'https://www.googleapis.com/auth/gmail.compose'
        __STORAGE = Storage(storage)
        flow = flow_from_clientsecrets(secret, scope=scope)
        http = httplib2.Http()

        credentials = __STORAGE.get()
        if credentials is None or credentials.invalid:
            credentials = run_flow(flow, __STORAGE, http=http)

        http = credentials.authorize(http)
        gmail_service = discovery.build('gmail', 'v1', http=http)
        try:
            messages = gmail_service.users().messages()
            messages.send(userId="me", body=content).execute()
        except Exception as error:
            raise Exception('An error occurred while sending email: %s' % error)