"""
Email service for sending emails via SMTP.
"""
import os
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import List, Optional, Dict, Any
from jinja2 import Environment, FileSystemLoader
from core.config import settings
from core.logging import get_logger

logger = get_logger("email_service")

class EmailService:
    """Service for sending emails."""
    
    def __init__(self):
        self.smtp_server = settings.smtp_server
        self.smtp_port = settings.smtp_port
        self.smtp_username = settings.smtp_username
        self.smtp_password = settings.smtp_password
        self.sender_email = settings.smtp_sender_email
        self.templates_dir = Path(__file__).parent.parent / "templates" / "emails"
        
        # Create templates directory if it doesn't exist
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=True
        )
    
    async def send_email(
        self, 
        to_email: str, 
        subject: str, 
        template_name: str, 
        context: Dict[str, Any],
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """
        Send an email using a template.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            template_name: Name of the template file (without extension)
            context: Context data for the template
            cc: Optional list of CC recipients
            bcc: Optional list of BCC recipients
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        try:
            # Load the template
            template = self.jinja_env.get_template(f"{template_name}.html")
            
            # Render the template with context
            html_content = template.render(**context)
            
            # Create the email message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = to_email
            
            if cc:
                message["Cc"] = ", ".join(cc)
            
            if bcc:
                message["Bcc"] = ", ".join(bcc)
            
            # Attach HTML content
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)
            
            # Create a list of all recipients
            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            # Connect to the SMTP server and send the email using aiosmtplib
            async with aiosmtplib.SMTP(hostname=self.smtp_server, port=self.smtp_port) as server:
                await server.starttls()
                await server.login(self.smtp_username, self.smtp_password)
                await server.sendmail(self.sender_email, recipients, message.as_string())
            
            logger.info(
                "Email sent successfully",
                to_email=to_email,
                subject=subject,
                template=template_name
            )
            return True
        
        except Exception as e:
            logger.error(
                "Failed to send email",
                error=str(e),
                to_email=to_email,
                subject=subject,
                template=template_name
            )
            return False
    
    async def send_activation_email(self, to_email: str, username: str, token: str) -> bool:
        """
        Send an account activation email.
        
        Args:
            to_email: Recipient email address
            username: User's username
            token: Activation token
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        activation_link = f"{settings.frontend_url}/auth/activate?token={token}"
        
        context = {
            "username": username,
            "activation_link": activation_link,
            "app_name": settings.app_name,
            "support_email": settings.support_email,
            "expiry_hours": settings.activation_token_expire_hours
        }
        
        return await self.send_email(
            to_email=to_email,
            subject=f"Activate your {settings.app_name} account",
            template_name="account_activation",
            context=context
        )
    
    async def send_password_reset_email(self, to_email: str, username: str, token: str) -> bool:
        """
        Send a password reset email.
        
        Args:
            to_email: Recipient email address
            username: User's username
            token: Reset token
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        reset_link = f"{settings.frontend_url}/auth/reset-password?token={token}"
        
        context = {
            "username": username,
            "reset_link": reset_link,
            "app_name": settings.app_name,
            "support_email": settings.support_email,
            "expiry_hours": settings.password_reset_token_expire_hours
        }
        
        return await self.send_email(
            to_email=to_email,
            subject=f"Reset your {settings.app_name} password",
            template_name="password_reset",
            context=context
        )
    
    async def send_welcome_email(self, to_email: str, username: str) -> bool:
        """
        Send a welcome email after account activation.
        
        Args:
            to_email: Recipient email address
            username: User's username
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        context = {
            "username": username,
            "app_name": settings.app_name,
            "login_url": f"{settings.frontend_url}/auth/login",
            "support_email": settings.support_email
        }
        
        return await self.send_email(
            to_email=to_email,
            subject=f"Welcome to {settings.app_name}!",
            template_name="welcome",
            context=context
        ) 