import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from typing import Optional
from dotenv import load_dotenv
import logging
import base64
from mjml import mjml_to_html

# Load environment variables
load_dotenv()

# Initialize logger
logger = logging.getLogger(__name__)

class MJMLEmailService:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.sender_email = os.getenv("GMAIL_SENDER_EMAIL")
        self.sender_password = os.getenv("GMAIL_APP_PASSWORD")
        self.sender_name = os.getenv("GMAIL_SENDER_NAME", "QuickMind")
        
        # Validate configuration
        if not self.sender_email or not self.sender_password:
            logger.warning("Gmail SMTP configuration incomplete. Email functionality will be disabled.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("MJML Gmail SMTP service initialized successfully")
    
    def get_logo_base64(self) -> str:
        """Get the QuickMind logo as base64 string"""
        logo_path = "D:\\quickmind\\frontend\\public\\LogoIcon.png"
        try:
            with open(logo_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
                return f"data:image/png;base64,{encoded_string}"
        except Exception as e:
            logger.warning(f"Could not load logo: {e}")
            # Return a fallback base64 encoded logo
            return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAfQAAAH0CAYAAADL1t+KAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAEv2lUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSfvu78nIGlkPSdXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQnPz4KPHg6eG1wbWV0YSB4bWxuczp4PSdhZG9iZTpuczptZXRhLyc+CjxyZGY6UkRGIHhtbG5zOnJkZj0naHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyc+CgogPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9JycKICB4bWxuczpBdHRyaWI9J2h0dHA6Ly9ucy5hdHRyaWJ1dGlvbi5jb20vYWRzLzEuMC8nPgogIDxBdHRyaWI6QWRzPgogICA8cmRmOlNlcT4KICAgIDxyZGY6bGkgcmRmOnBhcnNlVHlwZT0nUmVzb3VyY2UnPgogICAgIDxBdHRyaWI6Q3JlYXRlZD4yMDI1LTA4LTAyPC9BdHRyaWI6Q3JlYXRlZD4KICAgICA8QXR0cmliOkV4dElkPjI5NWUyY2I0LTkyOWMtNDM4Yi1hNWUxLTg0NTU2MDJiZmQzMjwvQXR0cmliOkV4dElkPgogICAgIDxBdHRyaWI6RmJJZD41MjUyNjU5MTQxNzk1ODA8L0F0dHJpYjpGYklkPgogICAgIDxBdHRyaWI6VG91Y2hUeXBlPjI8L0F0dHJpYjpUb3VjaFR5cGU+CiAgICA8L3JkZjpsaT4KICAgPC9yZGY6U2VxPgogIDwvQXR0cmliOkFkcz4KIDwvcmRmOkRlc2NyaXB0aW9uPgoKIDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PScnCiAgeG1sbnM6ZGM9J2h0dHA6Ly9wdXJsLm9yZy9kYy9lbGVtZW50cy8xLjEvJz4KICA8ZGM6dGl0bGU+CiAgIDxyZGY6QWx0PgogICAgPHJkZjpsaSB4bWw6bGFuZz0neC1kZWZhdWx0Jz5Mb2dvSWNvbkJyYW5kZWQgLSAxPC9yZGY6bGk+CiAgIDwvcmRmOkFsdD4KICA8L2RjOnRpdGxlPgogPC9yZGY6RGVzY3JpcHRpb24+CgogPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9JycKICB4bWxuczpwZGY9J2h0dHA6Ly9ucy5hZG9iZS5jb20vcGRmLzEuMy8nPgogIDxwZGY6QXV0aG9yPlNvdWZpYW5lIEVzc3RhZmE8L3BkZjpBdXRob3I+CiA8L3JkZjpEZXNjcmlwdGlvbj4KCiA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0nJwogIHhtbG5zOnhtcD0naHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyc+CiAgPHhtcDpDcmVhdG9yVG9vbD5DYW52YSAoUmVuZGVyZXIpIGRvYz1EQUd1NF9HMkNhQSB1c2VyPVVBR3NOXzBLdUpvIGJyYW5kPUJBR3NONG1yYVlRIHRlbXBsYXRlPTwveG1wOkNyZWF0b3JUb29sPgogPC9yZGY6RGVzY3JpcHRpb24+CjwvcmRmOlJERj4KPC94OnhtcG1ldGE+Cjw/eHBhY2tldCBlbmQ9J3InPz6lL3G9AAAkOUlEQVR4nOzdaawddR2H8afFK/zLViqSYlguoWylAQQKQjSOiSipyiJLYsAXCjEEt8QYDRJAJPUNGAgQX2hKlEUTi8ayxgJhWCRsImG1FsplUQwJi6UwIpfWF3OITVPa3vV35neeTzK5Sd/02/T2PJ1z58zMQJIkdd6M6AGSJGniDLokSQkYdEmSEjDokiQlYNAlSUrAoEuSlIBBlyQpAYMuSVICBl2SpAQMuiRJCRh0SZISMOiSJCVg0CVJSsCgS5KUgEGXJCkBgy5JUgIGXZKkBAy6JEkJGHRJkhIw6JIkJWDQJUlKwKBLkpSAQZckKQGDLklSAgZdkqQEDLokSQkYdEmSEjDokiQlYNAlSUrAoEuSlIBBlyQpAYMuSVICBl2SpAQMuiRJCRh0SZISMOiSJCVg0CVJSsCgS5KUgEGXJCkBgy5JUgIGXZKkBAy6JEkJGHRJkhIw6JIkJWDQJUlKwKBLkpSAQZckKQGDLklSAgZdkqQEDLokSQkYdEmSEjDokiQlYNAlSUrAoEuSlIBBlyQpAYMuSVICBl2SpAQMuiRJCRh0SZISMOiSJCVg0CVJSsCgS5KUgEGXJCkBgy5JUgIGXZKkBAy6JEkJGHRJkhIw6JIkJWDQJUlKwKBLkpSAQZckKQGDLklSAgZdkqQEDLokSQkYdEmSEjDokiQlYNAlSUrAoEuSlIBBlyQpAYMuSVICBl2SpAQMuiRJCRh0SZISMOiSJCVg0CVJSsCgS5KUgEGXJCkBgy5JUgIGXZKkBAy6JEkJGHRJkhIw6JIkJWDQJUlKwKBLkpSAQZckKQGDLklSAgZd6qBCtSMwa72j9I5te1/X//VZwFZAA7y9wdc1wH82+PW3gbcb6mb6/kSSJsqgS32mUM0G5gN7AXts5NhhGueMAM8DLwIv9I5VwLMN9app3CFpMwy6FKRQ7QAspI33Ab1jPrBL5K4x+iuwAngKeBJ4vKFeGTtJGkwGXZoGhaoAh9EGfCFwODCPnP8GXwce7h0PAQ811C/FTpLyy/hiIoUqVDOBBcCRwBG940Dan2MPqn8BDwAPvv+1oX4zdpKUi0GXJkGh2gs4BVhEG/JtYhd1whPAncBNDfXy6DFS1xl0aRx6Z+FHA8f1jv1iF3XeauBW4AbawK8O3iN1jkGXxqBQHQqcDnwFmBs8J6t3aeN+DXBjQ/1O8B6pEwy6tBmFanfgq7QhPyB4zqD5N3A9cC1wV0O9LniP1LcMurQRvbfUvwicDXwO/630g1XAz4ElDfUb0WOkfuOLlLSeQjUH+AZwFrBn8BxtXAP8FriioX40eozULwy6BBSqecA5wNejt2hM7gcuaah/Hz1EimbQNdAK1XzgfNqPnM0MnqPxewz4KbC0oV4bPUaKYNA1kArV4cAFtD8nVx7PABc11FdHD5Gmm0HXQOmF/CLg2OgtmlLPAYuBqxvqd6PHSNPBoGsg9EK+mPaKdQ2OEdq/918bdmVn0JVaoRoGrgS+EDxFsZ4HvtNQ3xA9RJoqBl0pFaoPAz8AzsX7quv/lgFnN9T/jB4iTTaDrnQK1dHA1cDe0VvUl9bQXhB5mVfEKxODrjQK1Y7ApcDXoreoEx4FzmioH4keIk2GQX4+sxIpVCcDtwCfit6izpgLnDHE8Kwhhu8dZeS96EHSRHiGrk4rVLsAV+CFb5qYVcBpDfX90UOk8fIMXZ1VqI4H7gAOit6iztsJOHOI4VmjjNwePUYaD8/Q1Tm9J6EtBn6I38OafPcAJzbUr0YPkcbCF0N1Su9paH8APh29Ram9BJzQUP8leoi0pXwYhTqjUB1Me2WyMddU2w14uFD5iQl1hj9DVycUqlOAm4GPRG/RQDl+iOHZQwzfNsrIuugx0qb4lrv6WqGaQfswlXOjt2ig3Q6c1FCvjh4ifRCDrr5VqGYBS4FF0Vsk2kezHtNQj0QPkTbGoKsv9T5fvhw4OHqLtJ7XgWMb6gejh0gbMujqO70npN0JDMcukTaqAb7UUN8RPURan1e5q68Uqv2BBzDm6l8FuLV3YyOpb3iVu/pGoToCqPFKdvW/rYBThxh+dpSRx6PHSGDQ1ScK1WHAXcD20VukLTQDOHGI4VWjjDwWPUbyZ+gKV6gOAu4GdozeIo3DWtqPtP0xeogGm0FXqEK1D3A/MCd6izQBo8DxDfUt0UM0uAy6whSqvYA/A7tGb5EmwX9pP6d+d/QQDSaDrhCFaifgEbyaXbm8BSxsqJ+OHqLB48fWNO0K1da092UfDp4iTbZtgeWFaufoIRo8Bl0RrgOOih4hTZHdaD+nXqKHaLAYdE2rQnUhcFL0DmmKHQ78rvdwIWla+Dl0TZtCdSpwZfQOaZrsCzDKSB28QwPC/z1qWhSqBcCDtLfNlAbFOtr7vt8cPUT5GXRNuUI1B3gU2D16ixRgDXBIQ/1s9BDl5s/QNaUK1UxgGcZcg2s74KZCtV30EOVm0DXVFgOfjB4hBdsf+FX0COXmRXGaMoVqIe2LmD/akWD+EMN/H2XkieghyskXWk2JQrUN8ASwd/QWqY+8BhzQUL8SPUT5+Ja7pspijLm0oTnAVdEjlJNvuWvS9d5qX4LvAEkbs+8Qw38bZeTJ6CHKxTN0TYXrMObSplxRqGZHj1AuBl2TqlBdAOwTvUPqcx8FLo4eoVw8i9Kk6T3f/Glg6+gtUkcsbKgfjh6hHD4UPUCpLMGYT5c3gZXAit6xEngRaDY8Guo3AArV9rS33t3wmA0sAObR3n98P2DuNP5ZBtkS4ODoEcrBM3RNikJ1OnBN9I6kVgP3Aff0vq5oqF+eyt+wUM2ijfxC4GjamwPtMZW/5wD7fkP9s+gR6j6DrgnrPfd5FZ7VTZbVwK3AvcB9DfUjwXsAKFQfow37Z4DP0p7Ra+LWAMN9Q/1q9BB1m0HXhBWq84CfRO/ouNdo731/KXDbqGc6feEGdjhBB9bWkPGLST5fveMl7kty0G1euRyCDqydIeNtSb6TZF/1lpfxdJK75kzfqx7CziLowNoYMl6V5EtZ3S536Q4nuXPO9I/qIewMgg6shSHjdUl+mOSj1Vteg0eSfMwV9LgUgg60N2R8R5IpyQ3FUy7H8SQH5kyPVQ9h2QQdaG3IeH1WV6p7V/WWK/C3JLfMmR6tHsJyCTrQ1pBxI8mRrK7Mt9M9keSmOdNz1UNYpquqBwBspa+kR8yT1WVn76gewXLtqh4AsBWGjB9J8s3qHZvsvRvZ+/i5HPPSO//DS+5AO0PGa5IcTfLO6i1b4JkkN8yZnqkewrJ4yR3o6GB6xjxZXbf/UPUIlscJHWjl/PXsj2fz7pC2RHOS6+dMJ6uHsBxO6EA3n03vmCerG+7cXT2CZXFCB1oZMj6ZZV6jfbP9JcmeOdML1UNYBid0oI0h4weyHjFPkrcn2V89guUQdKCTT1QP2Ga3Vw9gOQQd6GQn3XhlM6zb18ur8B460MKQ8c1JTmX9vq/tnjOdqh5BPSd0oIsPZv1iniQ3Vw9gGQQd6OLG6gFFduItYdkCgg508Z7qAUXW9evmIoIOdHFt9YAie6oHsAyCDnSxrneP3F09gGUQdKCLdf1+9pbqASzDuv4HAPr5Z/WAIhvVA1gGQQe6eL56QJHnqgewDIIOdLGuQT9dPYBlEHSgiz9XDyjyVPUAlkHQgS6eqB5Q5PfVA1gGQQe6WNegH60ewDIIOtDF0azn++i/qR7AMgg60MKc6VySX1bv2GYn5kyPV49gGQQd6OQX1QO22Y+rB7Acgg508v3qAdvsR9UDWA5BB9qYMx1PcqR6xzZ5NslPqkewHIIOdPNA9YBt8sCc6V/VI1gOQQe6uT/JyeoRW+xski9Xj2BZBB1oZc50Nsk91Tu22P1zJleI478IOtDRN9L3CmqnkxyqHsHyCDrQzvlT+h1JXqjesgU+M2c6UT2C5dlVPQBgKw0Z35Dkp0k+XL3lCjya5NY506nqISyXoAPtDRmvTvLzJDdXb7kMjyXZP2d6unoIy+Yld6C9OdOZJAeS/Kx6y2v0cJJRzLkUfigOWAvncuzsRvYeTjIk+VD1nkvw3SS3z5lOVw9hZ/CSO7B2howHknwryburt7yMp5LcNWf6QfUQdhYndGDtnMuxJzey996sDjXvT7JRPOmCryX5+Jzpkeoh7DxO6MBaGzLuTnIwyaeTXFsw4e9Jvp3kHheM4UoIOkBe/En4O5PcnWTvNjzlH5N8Pcm93idnMwg6wEWGjDcluS3JmOTWJG/ahE/7fJJfJZmSTHOmhzfhc8KLBB3g/xgyvi/JLUn2Jdmd5K1JrnmVf3Imq1u4PpPkD0gemjP9bqt3st4EHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABgQdABoQdABoQNABoAFBB4AGBB0AGhB0AGhA0AGgAUEHgAYEHQAaEHQAaEDQAaABQQeABr4N06BNqX2ks8AAAAAAElFTkSuQmCC"
    
    def get_welcome_email_mjml_template(self, recipient_name: str) -> str:
        """Generate the MJML template for welcome email"""
        logo_base64 = self.get_logo_base64()
        
        return f"""
<mjml>
  <mj-head>
    <mj-title>Welcome to QuickMind!</mj-title>
    <mj-preview>Transform your content into interactive mind maps</mj-preview>
    <mj-attributes>
      <mj-all font-family="Inter, Arial, sans-serif" />
      <mj-text font-weight="400" font-size="16px" color="#ffffff" line-height="24px" />
      <mj-section background-color="#090040" />
    </mj-attributes>
    <mj-style inline="inline">
      .gradient-bg {{
        background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%);
      }}
      .feature-icon {{
        width: 48px;
        height: 48px;
        background: #ffffff;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        margin: 0 auto 16px;
      }}
      .cta-button {{
        background: #ffffff !important;
        color: #090040 !important;
        border-radius: 50px !important;
        padding: 16px 32px !important;
        text-decoration: none !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        display: inline-block !important;
        box-shadow: 0 10px 30px rgba(255, 255, 255, 0.2) !important;
        transition: all 0.3s ease !important;
      }}
      .social-icon {{
        width: 40px;
        height: 40px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: #ffffff;
        text-decoration: none;
        margin: 0 8px;
        transition: all 0.3s ease;
      }}
    </mj-style>
  </mj-head>
  <mj-body background-color="#090040">
    
    <!-- Header Section -->
    <mj-section css-class="gradient-bg" padding="40px 20px">
      <mj-column>
        <!-- Logo -->
        <mj-image 
          src="{logo_base64}" 
          alt="QuickMind Logo" 
          width="80px" 
          height="80px" 
          border-radius="50%" 
          background-color="#ffffff"
          padding="10px"
        />
        
        <!-- Main Title -->
        <mj-text align="center" font-size="32px" font-weight="700" color="#ffffff" padding="20px 0 10px">
          Welcome to QuickMind!
        </mj-text>
        
        <!-- Subtitle -->
        <mj-text align="center" font-size="18px" color="#ffffff" opacity="0.9" padding="0 0 20px">
          Transform your content into interactive mind maps
        </mj-text>
      </mj-column>
    </mj-section>

    <!-- Welcome Message -->
    <mj-section background-color="rgba(255, 255, 255, 0.05)" padding="40px 20px">
      <mj-column>
        <mj-text align="center" font-size="18px" color="#ffffff" line-height="28px" padding="0 0 30px">
          <strong>Hi {recipient_name},</strong><br/><br/>
          Thank you for joining QuickMind! We're excited to help you transform your videos and content into beautiful, interactive mind maps powered by AI.
        </mj-text>
      </mj-column>
    </mj-section>

    <!-- Features Section -->
    <mj-section background-color="rgba(255, 255, 255, 0.05)" padding="0 20px 40px">
      <mj-column>
        
        <!-- Feature 1: Video Processing -->
        <mj-section background-color="rgba(255, 255, 255, 0.1)" border-radius="12px" padding="20px" margin="0 0 20px">
          <mj-column width="20%" vertical-align="top">
            <mj-text align="center" font-size="32px" padding="0">🎥</mj-text>
          </mj-column>
          <mj-column width="80%" vertical-align="top">
            <mj-text font-size="18px" font-weight="600" color="#ffffff" padding="0 0 8px">
              Video Processing
            </mj-text>
            <mj-text font-size="14px" color="#ffffff" opacity="0.9" padding="0">
              Upload any video and get AI-generated mind maps in minutes
            </mj-text>
          </mj-column>
        </mj-section>

        <!-- Feature 2: YouTube Integration -->
        <mj-section background-color="rgba(255, 255, 255, 0.1)" border-radius="12px" padding="20px" margin="0 0 20px">
          <mj-column width="20%" vertical-align="top">
            <mj-text align="center" font-size="32px" padding="0">📺</mj-text>
          </mj-column>
          <mj-column width="80%" vertical-align="top">
            <mj-text font-size="18px" font-weight="600" color="#ffffff" padding="0 0 8px">
              YouTube Integration
            </mj-text>
            <mj-text font-size="14px" color="#ffffff" opacity="0.9" padding="0">
              Process YouTube videos directly with just a URL
            </mj-text>
          </mj-column>
        </mj-section>

        <!-- Feature 3: Interactive Mind Maps -->
        <mj-section background-color="rgba(255, 255, 255, 0.1)" border-radius="12px" padding="20px" margin="0 0 20px">
          <mj-column width="20%" vertical-align="top">
            <mj-text align="center" font-size="32px" padding="0">🧠</mj-text>
          </mj-column>
          <mj-column width="80%" vertical-align="top">
            <mj-text font-size="18px" font-weight="600" color="#ffffff" padding="0 0 8px">
              Interactive Mind Maps
            </mj-text>
            <mj-text font-size="14px" color="#ffffff" opacity="0.9" padding="0">
              Navigate and interact with your content in new ways
            </mj-text>
          </mj-column>
        </mj-section>

        <!-- Feature 4: Save and Export -->
        <mj-section background-color="rgba(255, 255, 255, 0.1)" border-radius="12px" padding="20px" margin="0 0 30px">
          <mj-column width="20%" vertical-align="top">
            <mj-text align="center" font-size="32px" padding="0">💾</mj-text>
          </mj-column>
          <mj-column width="80%" vertical-align="top">
            <mj-text font-size="18px" font-weight="600" color="#ffffff" padding="0 0 8px">
              Save &amp; Export
            </mj-text>
            <mj-text font-size="14px" color="#ffffff" opacity="0.9" padding="0">
              Save your mind maps and export in multiple formats
            </mj-text>
          </mj-column>
        </mj-section>

      </mj-column>
    </mj-section>

    <!-- CTA Section -->
    <mj-section background-color="rgba(255, 255, 255, 0.05)" padding="40px 20px">
      <mj-column>
        <mj-button 
          href="http://localhost:3000/dashboard" 
          css-class="cta-button"
          background-color="#ffffff"
          color="#090040"
          border-radius="50px"
          font-size="16px"
          font-weight="600"
          padding="16px 32px"
        >
          Get Started Now →
        </mj-button>
      </mj-column>
    </mj-section>

    <!-- Footer Section -->
    <mj-section background-color="#090040" padding="40px 20px">
      <mj-column>
        <mj-text align="center" color="#ffffff" font-size="16px" padding="0 0 20px">
          Ready to revolutionize how you process information?
        </mj-text>
        
        <!-- Social Links -->
        <mj-social font-size="15px" icon-size="20px" mode="horizontal" padding="20px 0" align="center">
          <mj-social-element name="twitter" href="#" background-color="rgba(255, 255, 255, 0.1)" color="#ffffff">
            Twitter
          </mj-social-element>
          <mj-social-element name="linkedin" href="#" background-color="rgba(255, 255, 255, 0.1)" color="#ffffff">
            LinkedIn
          </mj-social-element>
          <mj-social-element name="github" href="#" background-color="rgba(255, 255, 255, 0.1)" color="#ffffff">
            GitHub
          </mj-social-element>
        </mj-social>
        
        <!-- Footer Text -->
        <mj-text align="center" color="#ffffff" font-size="12px" opacity="0.7" padding="20px 0 0">
          Need help? Reply to this email or visit our support center.<br/>
          © 2024 QuickMind. All rights reserved.
        </mj-text>
      </mj-column>
    </mj-section>

  </mj-body>
</mjml>
        """
    
    def create_welcome_email(self, recipient_email: str, recipient_name: str) -> MIMEMultipart:
        """Create a branded welcome email using MJML"""
        msg = MIMEMultipart('related')
        msg['From'] = f"{self.sender_name} <{self.sender_email}>"
        msg['To'] = recipient_email
        msg['Subject'] = f"Welcome to QuickMind, {recipient_name}! 🚀"
        
        # Generate MJML template
        mjml_template = self.get_welcome_email_mjml_template(recipient_name)
        
        # Convert MJML to HTML
        try:
            html_content = mjml_to_html(mjml_template)
            if html_content.get('errors'):
                logger.warning(f"MJML conversion warnings: {html_content['errors']}")
            html_content = html_content['html']
        except Exception as e:
            logger.error(f"MJML conversion failed: {e}")
            # Fallback to basic HTML
            html_content = self.get_fallback_html_template(recipient_name)
        
        # Create alternative container
        msg_alternative = MIMEMultipart('alternative')
        msg.attach(msg_alternative)
        
        # Create plain text version
        text_content = f"""
Welcome to QuickMind, {recipient_name}!

Thank you for joining QuickMind - the AI-powered mind mapping platform that transforms your videos and content into interactive mind maps.

Here's what you can do with QuickMind:
• Upload videos and get AI-generated mind maps
• Process YouTube videos directly
• Interactive mind map navigation
• Save and organize your mind maps
• Export in multiple formats

Ready to get started? Visit your dashboard: http://localhost:3000/dashboard

Best regards,
The QuickMind Team

---
Need help? Reply to this email or visit our support center.
        """
        
        # Attach parts
        msg_alternative.attach(MIMEText(text_content, 'plain'))
        msg_alternative.attach(MIMEText(html_content, 'html'))
        
        return msg
    
    def get_fallback_html_template(self, recipient_name: str) -> str:
        """Fallback HTML template if MJML fails"""
        logo_base64 = self.get_logo_base64()
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to QuickMind</title>
</head>
<body style="margin: 0; padding: 0; font-family: Inter, Arial, sans-serif; background-color: #090040; color: #ffffff;">
    <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #090040 0%, #1a0f5c 100%);">
        
        <!-- Header -->
        <div style="text-align: center; padding: 40px 20px;">
            <div style="width: 80px; height: 80px; background: #ffffff; border-radius: 50%; margin: 0 auto 20px; padding: 10px; display: inline-block;">
                <img src="{logo_base64}" alt="QuickMind Logo" style="width: 100%; height: 100%; object-fit: contain;" />
            </div>
            <h1 style="font-size: 32px; font-weight: 700; margin: 20px 0 10px; color: #ffffff;">Welcome to QuickMind!</h1>
            <p style="font-size: 18px; color: #ffffff; opacity: 0.9; margin: 0;">Transform your content into interactive mind maps</p>
        </div>
        
        <!-- Content -->
        <div style="padding: 40px 20px; background: rgba(255, 255, 255, 0.05);">
            <p style="font-size: 18px; text-align: center; margin-bottom: 30px; color: #ffffff;">
                <strong>Hi {recipient_name},</strong><br/><br/>
                Thank you for joining QuickMind! We're excited to help you transform your videos and content into beautiful, interactive mind maps powered by AI.
            </p>
            
            <!-- CTA Button -->
            <div style="text-align: center; margin: 40px 0;">
                <a href="http://localhost:3000/dashboard" style="background: #ffffff; color: #090040; padding: 16px 32px; border-radius: 50px; text-decoration: none; font-weight: 600; font-size: 16px; display: inline-block;">
                    Get Started Now →
                </a>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="padding: 40px 20px; text-align: center; background: #090040;">
            <p style="color: #ffffff; font-size: 12px; opacity: 0.7; margin: 0;">
                © 2024 QuickMind. All rights reserved.
            </p>
        </div>
        
    </div>
</body>
</html>
        """
    
    async def send_welcome_email(self, recipient_email: str, recipient_name: str = "User") -> bool:
        """Send welcome email to new user"""
        if not self.enabled:
            logger.warning("Email service disabled. Skipping welcome email.")
            return False
        
        try:
            # Create message
            message = self.create_welcome_email(recipient_email, recipient_name)
            
            # Create secure connection and send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.sender_email, self.sender_password)
                
                text = message.as_string()
                server.sendmail(self.sender_email, recipient_email, text)
            
            logger.info(f"MJML Welcome email sent successfully to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send MJML welcome email to {recipient_email}: {e}")
            return False
    
    async def send_custom_email(self, recipient_email: str, subject: str, mjml_content: str, 
                              text_content: Optional[str] = None) -> bool:
        """Send custom email using MJML template"""
        if not self.enabled:
            logger.warning("Email service disabled. Skipping custom email.")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.sender_name} <{self.sender_email}>"
            msg['To'] = recipient_email
            msg['Subject'] = subject
            
            # Convert MJML to HTML
            try:
                html_content = mjml_to_html(mjml_content)
                if html_content.get('errors'):
                    logger.warning(f"MJML conversion warnings: {html_content['errors']}")
                html_content = html_content['html']
            except Exception as e:
                logger.error(f"MJML conversion failed: {e}")
                return False
            
            # Create text version if not provided
            if not text_content:
                # Simple HTML to text conversion
                import re
                text_content = re.sub('<[^<]+?>', '', html_content)
                text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            # Attach parts
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.sender_email, self.sender_password)
                
                text = msg.as_string()
                server.sendmail(self.sender_email, recipient_email, text)
            
            logger.info(f"MJML Custom email sent successfully to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send MJML custom email to {recipient_email}: {e}")
            return False

# Create global MJML email service instance
mjml_email_service = MJMLEmailService()