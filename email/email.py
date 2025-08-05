
import re
from email.message import EmailMessage 
import aiosmtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import os 
import markdown2
import asyncpg
 

load_dotenv()

FROM=os.getenv("FROM")
APP_PASSWORD=os.getenv("APP_PASSWORD")
HOST_NAME=os.getenv("HOST_NAME")
PORT=os.getenv("PORT") 

async def send_email(subject: str, body: str, to_email: str):
    name_match = re.match(r"([^@]+)", to_email)
    user_name = name_match.group(1).replace('.', ' ').replace('_', ' ').title() if name_match else "User"

    personalized_body = body.replace("[Your Name]", user_name)

    html_content = markdown2.markdown(personalized_body)

    msg = EmailMessage()
    msg["From"] = FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(personalized_body)
    msg.add_alternative(html_content, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=HOST_NAME,
        port=PORT,
        username=FROM,
        password=APP_PASSWORD, 
        start_tls=True,
    )