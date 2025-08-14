"""
Email service for sending emails via SMTP with secure token handling.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosmtplib
import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import get_settings

logger = structlog.get_logger(__name__)


class EmailService:
    """Service for sending emails with template support and security features."""
    
    def __init__(self):
        """Initialize the email service with configuration."""
        self.settings = get_settings()
        self.smtp_server = self.settings.smtp_server or self.settings.mail_server
        self.smtp_port = self.settings.smtp_port or self.settings.mail_port
        self.smtp_username = self.settings.smtp_username or self.settings.mail_username
        self.smtp_password = self.settings.smtp_password or self.settings.mail_password
        self.sender_email = self.settings.smtp_sender_email or self.settings.mail_from
        self.sender_name = self.settings.smtp_sender_name
        self.use_tls = self.settings.smtp_use_tls or self.settings.mail_starttls
        self.use_ssl = self.settings.smtp_use_ssl or self.settings.mail_ssl_tls
        self.timeout = self.settings.smtp_timeout
        
        # Setup templates directory
        self.templates_dir = Path(__file__).parent.parent.parent / self.settings.email_templates_dir
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Jinja2 environment with security features
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            enable_async=True
        )
        
        self._connection_pool: Optional[aiosmtplib.SMTP] = None
        self._pool_lock = asyncio.Lock()
    
    def _validate_configuration(self) -> None:
        """Validate email configuration."""
        if not all([self.smtp_server, self.smtp_username, self.smtp_password, self.sender_email]):
            missing_fields = []
            if not self.smtp_server:
                missing_fields.append("SMTP_SERVER")
            if not self.smtp_username:
                missing_fields.append("SMTP_USERNAME") 
            if not self.smtp_password:
                missing_fields.append("SMTP_PASSWORD")
            if not self.sender_email:
                missing_fields.append("SMTP_SENDER_EMAIL")
            
            raise ValueError(
                f"Email service not configured. Missing: {', '.join(missing_fields)}"
            )

    async def _get_connection(self) -> aiosmtplib.SMTP:
        """Get SMTP connection with connection pooling."""
        async with self._pool_lock:
            if self._connection_pool is None or not self._connection_pool.is_connected:
                self._connection_pool = aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    timeout=self.timeout,
                    use_tls=False,
                    start_tls=False,
                )
                await self._connection_pool.connect()
                
                if self.use_tls:
                    await self._connection_pool.starttls()
                
                await self._connection_pool.login(self.smtp_username, self.smtp_password)
                
            return self._connection_pool
    
    async def _close_connection(self) -> None:
        """Close SMTP connection."""
        async with self._pool_lock:
            if self._connection_pool and self._connection_pool.is_connected:
                await self._connection_pool.quit()
                self._connection_pool = None
    
    async def send_email(
        self, 
        to_email: str, 
        subject: str, 
        template_name: str, 
        context: Dict[str, Any],
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        priority: str = "normal"
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
            priority: Email priority (high, normal, low)
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        try:
            self._validate_configuration()
            
            # Load and render the template
            template = self.jinja_env.get_template(f"{template_name}.html")
            html_content = await template.render_async(**context)
            
            # Create the email message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.sender_name} <{self.sender_email}>"
            message["To"] = to_email
            message["X-Mailer"] = "Study Assistant Email Service"
            
            # Set priority
            if priority == "high":
                message["X-Priority"] = "1"
                message["Importance"] = "high"
            elif priority == "low":
                message["X-Priority"] = "5"
                message["Importance"] = "low"
            
            if cc:
                message["Cc"] = ", ".join(cc)
            
            if bcc:
                message["Bcc"] = ", ".join(bcc)
            
            # Attach HTML content
            html_part = MIMEText(html_content, "html", "utf-8")
            message.attach(html_part)
            
            # Create a list of all recipients
            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            # Send the email
            smtp = await self._get_connection()
            await smtp.sendmail(self.sender_email, recipients, message.as_string())
            
            logger.info(
                "Email sent successfully",
                to_email=to_email,
                subject=subject,
                template=template_name,
                priority=priority
            )
            return True
        
        except Exception as e:
            logger.error(
                "Failed to send email",
                error=str(e),
                to_email=to_email,
                subject=subject,
                template=template_name,
                exc_info=True
            )
            return False
    
    async def send_verification_email(
        self, 
        to_email: str, 
        user_name: str, 
        verification_url: str
    ) -> bool:
        """Send email verification email."""
        context = {
            "user_name": user_name,
            "verification_url": verification_url,
            "app_name": self.settings.app_name,
            "support_email": self.sender_email,
        }
        
        return await self.send_email(
            to_email=to_email,
            subject=f"Verify your {self.settings.app_name} account",
            template_name="verification",
            context=context,
            priority="high"
        )
    
    async def send_password_reset_email(
        self, 
        to_email: str, 
        user_name: str, 
        reset_url: str
    ) -> bool:
        """Send password reset email."""
        context = {
            "user_name": user_name,
            "reset_url": reset_url,
            "app_name": self.settings.app_name,
            "support_email": self.sender_email,
            "expire_hours": self.settings.password_reset_expire_hours,
        }
        
        return await self.send_email(
            to_email=to_email,
            subject=f"Reset your {self.settings.app_name} password",
            template_name="password_reset",
            context=context,
            priority="high"
        )
    
    async def send_welcome_email(
        self, 
        to_email: str, 
        user_name: str
    ) -> bool:
        """Send welcome email after successful verification."""
        context = {
            "user_name": user_name,
            "app_name": self.settings.app_name,
            "support_email": self.sender_email,
        }
        
        return await self.send_email(
            to_email=to_email,
            subject=f"Welcome to {self.settings.app_name}!",
            template_name="welcome",
            context=context
        )
    
    async def send_password_changed_notification(
        self, 
        to_email: str, 
        user_name: str
    ) -> bool:
        """Send notification when password is changed."""
        context = {
            "user_name": user_name,
            "app_name": self.settings.app_name,
            "support_email": self.sender_email,
        }
        
        return await self.send_email(
            to_email=to_email,
            subject=f"Password changed for {self.settings.app_name}",
            template_name="password_changed",
            context=context
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check email service health."""
        try:
            self._validate_configuration()
            
            # Test connection
            smtp = aiosmtplib.SMTP(
                hostname=self.smtp_server,
                port=self.smtp_port,
                timeout=5
            )
            await smtp.connect()
            
            if self.use_tls:
                await smtp.starttls()
            
            await smtp.login(self.smtp_username, self.smtp_password)
            await smtp.quit()
            
            return {
                "status": "healthy",
                "smtp_server": self.smtp_server,
                "smtp_port": self.smtp_port,
                "sender_email": self.sender_email,
            }
        
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "smtp_server": self.smtp_server,
                "smtp_port": self.smtp_port,
            }
    
    async def cleanup(self) -> None:
        """Cleanup email service resources."""
        await self._close_connection()


# Global email service instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


async def cleanup_email_service() -> None:
    """Cleanup email service on shutdown."""
    global _email_service
    if _email_service:
        await _email_service.cleanup()
        _email_service = None
