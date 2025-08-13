"""
User-friendly error messages for the QuickMaps application.
This module provides functions to convert technical errors into user-friendly messages.
"""

def get_user_friendly_error(error_type: str, context: str = "general") -> str:
    """
    Convert technical error types to user-friendly messages.
    
    Args:
        error_type: The technical error type (e.g., "auth/email-already-in-use")
        context: The context where the error occurred (e.g., "signup", "login", "email")
    
    Returns:
        A user-friendly error message
    """
    
    # Firebase Auth errors
    firebase_auth_errors = {
        "auth/email-already-in-use": "This email address is already registered. Please try signing in instead, or use a different email address.",
        "auth/invalid-email": "Please enter a valid email address.",
        "auth/operation-not-allowed": "This sign-in method is not enabled. Please contact support.",
        "auth/weak-password": "Please choose a stronger password with at least 6 characters.",
        "auth/user-disabled": "This account has been disabled. Please contact support for assistance.",
        "auth/user-not-found": "We couldn't find an account with this email address. Please check your email or create a new account.",
        "auth/wrong-password": "The password you entered is incorrect. Please try again or reset your password.",
        "auth/too-many-requests": "Too many failed attempts. Please wait a few minutes before trying again.",
        "auth/network-request-failed": "Please check your internet connection and try again.",
        "auth/invalid-credential": "The credentials you provided are not valid. Please try again.",
        "auth/credential-already-in-use": "This credential is already associated with another account.",
        "auth/invalid-verification-code": "The verification code you entered is incorrect. Please check and try again.",
        "auth/invalid-verification-id": "The verification process has expired. Please request a new code.",
        "auth/missing-verification-code": "Please enter the verification code.",
        "auth/missing-verification-id": "Verification session has expired. Please start over.",
        "auth/code-expired": "This verification code has expired. Please request a new one.",
        "auth/session-cookie-expired": "Your session has expired. Please sign in again.",
        "auth/id-token-expired": "Your session has expired. Please sign in again.",
        "auth/id-token-revoked": "Your session is no longer valid. Please sign in again.",
        "auth/insufficient-permission": "You don't have permission to perform this action.",
        "auth/internal-error": "We're experiencing technical difficulties. Please try again in a few moments.",
        "auth/invalid-argument": "Invalid information provided. Please check your input and try again.",
        "auth/invalid-creation-time": "Account creation failed. Please try again.",
        "auth/invalid-disabled-field": "Account status update failed. Please contact support.",
        "auth/invalid-display-name": "Please enter a valid display name.",
        "auth/invalid-dynamic-link-domain": "Invalid link. Please contact support.",
        "auth/invalid-email-verified": "Email verification failed. Please try again.",
        "auth/invalid-hash-algorithm": "Authentication failed. Please contact support.",
        "auth/invalid-hash-block-size": "Authentication failed. Please contact support.",
        "auth/invalid-hash-derived-key-length": "Authentication failed. Please contact support.",
        "auth/invalid-hash-key": "Authentication failed. Please contact support.",
        "auth/invalid-hash-memory-cost": "Authentication failed. Please contact support.",
        "auth/invalid-hash-parallelization": "Authentication failed. Please contact support.",
        "auth/invalid-hash-rounds": "Authentication failed. Please contact support.",
        "auth/invalid-hash-salt-separator": "Authentication failed. Please contact support.",
        "auth/invalid-id-token": "Your session is invalid. Please sign in again.",
        "auth/invalid-last-sign-in-time": "Authentication failed. Please try signing in again.",
        "auth/invalid-page-token": "Session expired. Please refresh the page and try again.",
        "auth/invalid-password": "Please enter a valid password.",
        "auth/invalid-password-hash": "Authentication failed. Please contact support.",
        "auth/invalid-password-salt": "Authentication failed. Please contact support.",
        "auth/invalid-phone-number": "Please enter a valid phone number.",
        "auth/invalid-photo-url": "Please provide a valid photo URL.",
        "auth/invalid-provider-data": "Authentication provider error. Please try a different sign-in method.",
        "auth/invalid-provider-id": "Authentication provider error. Please try a different sign-in method.",
        "auth/invalid-oauth-responsetype": "Authentication error. Please try again.",
        "auth/invalid-session-cookie-duration": "Session expired. Please sign in again.",
        "auth/invalid-uid": "Invalid user ID. Please contact support.",
        "auth/invalid-user-import": "Account import failed. Please contact support.",
        "auth/maximum-user-count-exceeded": "Maximum number of users reached. Please contact support.",
        "auth/missing-android-pkg-name": "App configuration error. Please contact support.",
        "auth/missing-continue-uri": "Authentication flow error. Please try again.",
        "auth/missing-hash-algorithm": "Authentication configuration error. Please contact support.",
        "auth/missing-ios-bundle-id": "App configuration error. Please contact support.",
        "auth/missing-uid": "User identification error. Please try signing in again.",
        "auth/reserved-claims": "Account setup error. Please contact support.",
        "auth/session-cookie-revoked": "Your session has been revoked. Please sign in again.",
        "auth/uid-already-exists": "This account already exists. Please try signing in instead.",
        "auth/unauthorized-continue-uri": "Authentication flow error. Please try again.",
        "auth/user-not-disabled": "Account is already active.",
        "auth/claims-too-large": "Account information too large. Please contact support.",
        "auth/email-change-needs-verification": "Please verify your new email address.",
        "auth/multi-factor-auth-required": "Additional verification required. Please complete the security check.",
        "auth/multi-factor-info-not-found": "Security verification failed. Please try again.",
        "auth/multi-factor-session-expired": "Security verification expired. Please start over.",
        "auth/second-factor-already-in-use": "This security method is already set up.",
        "auth/second-factor-limit-exceeded": "Too many security methods. Please remove one first.",
        "auth/unsupported-first-factor": "This sign-in method is not supported.",
        "auth/unverified-email": "Please verify your email address before continuing.",
    }
    
    # Firestore errors
    firestore_errors = {
        "permission-denied": "You don't have permission to access this information.",
        "not-found": "The requested information could not be found.",
        "already-exists": "This information already exists.",
        "resource-exhausted": "Service temporarily unavailable. Please try again later.",
        "failed-precondition": "Unable to complete this action. Please try again.",
        "aborted": "Operation was interrupted. Please try again.",
        "out-of-range": "Invalid input provided. Please check your information.",
        "unimplemented": "This feature is not available yet.",
        "internal": "We're experiencing technical difficulties. Please try again later.",
        "unavailable": "Service temporarily unavailable. Please try again later.",
        "data-loss": "Data synchronization error. Please refresh and try again.",
        "unauthenticated": "Please sign in to continue.",
        "deadline-exceeded": "Request timed out. Please try again.",
        "cancelled": "Operation was cancelled. Please try again.",
        "invalid-argument": "Invalid information provided. Please check your input.",
        "unknown": "An unexpected error occurred. Please try again.",
    }
    
    # Email service errors
    email_errors = {
        "EMAIL_FAILED": "We couldn't send your email. Please check your email address and try again.",
        "RESEND_COOLDOWN": "Please wait a moment before requesting another email.",
        "INVALID_EMAIL": "Please enter a valid email address.",
        "EMAIL_NOT_VERIFIED": "Please verify your email address first.",
        "EMAIL_ALREADY_VERIFIED": "Your email address is already verified.",
        "BREVO_API_ERROR": "Email service temporarily unavailable. Please try again later.",
        "SMTP_ERROR": "Email delivery failed. Please try again later.",
        "RATE_LIMIT_EXCEEDED": "Too many email requests. Please wait before trying again.",
    }
    
    # Payment errors
    payment_errors = {
        "PAYMENT_FAILED": "Payment could not be processed. Please check your payment method and try again.",
        "CARD_DECLINED": "Your card was declined. Please try a different payment method.",
        "INSUFFICIENT_FUNDS": "Insufficient funds. Please check your account balance or try a different card.",
        "EXPIRED_CARD": "Your card has expired. Please update your payment method.",
        "INVALID_CARD": "Invalid card information. Please check your details and try again.",
        "PAYMENT_TIMEOUT": "Payment timed out. Please try again.",
        "SUBSCRIPTION_CANCELLED": "Your subscription has been cancelled.",
        "SUBSCRIPTION_EXPIRED": "Your subscription has expired. Please renew to continue.",
        "CREDIT_LIMIT_EXCEEDED": "You've reached your credit limit. Please upgrade your plan.",
    }
    
    # File upload errors
    upload_errors = {
        "FILE_TOO_LARGE": "File is too large. Please choose a smaller file.",
        "INVALID_FILE_TYPE": "File type not supported. Please choose a different file.",
        "UPLOAD_FAILED": "File upload failed. Please try again.",
        "STORAGE_FULL": "Storage limit reached. Please delete some files or upgrade your plan.",
        "VIRUS_DETECTED": "File contains malicious content and cannot be uploaded.",
        "PROCESSING_FAILED": "We couldn't process your file. Please try a different file.",
    }
    
    # Network errors
    network_errors = {
        "NETWORK_ERROR": "Please check your internet connection and try again.",
        "TIMEOUT": "Request timed out. Please try again.",
        "CONNECTION_FAILED": "Connection failed. Please check your internet and try again.",
        "SERVER_UNAVAILABLE": "Service temporarily unavailable. Please try again later.",
    }
    
    # Combine all error mappings
    all_errors = {
        **firebase_auth_errors,
        **firestore_errors,
        **email_errors,
        **payment_errors,
        **upload_errors,
        **network_errors,
    }
    
    # Return user-friendly message or a generic one
    return all_errors.get(error_type, "Something went wrong. Please try again or contact support if the problem persists.")


def get_context_specific_error(error_type: str, context: str) -> str:
    """
    Get context-specific error messages for better user experience.
    
    Args:
        error_type: The technical error type
        context: The specific context (signup, login, upload, etc.)
    
    Returns:
        A context-specific user-friendly error message
    """
    
    context_messages = {
        "signup": {
            "auth/email-already-in-use": "This email is already registered. Try signing in instead, or use a different email address.",
            "auth/weak-password": "Please choose a stronger password with at least 6 characters, including letters and numbers.",
            "auth/invalid-email": "Please enter a valid email address to create your account.",
            "EMAIL_FAILED": "We couldn't send your welcome email, but your account was created successfully. You can sign in now.",
        },
        "login": {
            "auth/user-not-found": "No account found with this email. Please check your email or create a new account.",
            "auth/wrong-password": "Incorrect password. Please try again or reset your password if you've forgotten it.",
            "auth/too-many-requests": "Too many failed login attempts. Please wait a few minutes before trying again.",
            "auth/user-disabled": "Your account has been temporarily disabled. Please contact support for assistance.",
        },
        "email_verification": {
            "EXPIRED": "Your verification code has expired. Please request a new one to continue.",
            "INVALID_CODE": "The verification code is incorrect. Please check your email and try again.",
            "TOO_MANY_ATTEMPTS": "Too many incorrect attempts. Please request a new verification code.",
            "ALREADY_USED": "This verification code has already been used. Your email is verified!",
        },
        "password_reset": {
            "auth/user-not-found": "No account found with this email address. Please check your email or create a new account.",
            "auth/invalid-action-code": "This password reset link is invalid or has expired. Please request a new one.",
            "auth/expired-action-code": "This password reset link has expired. Please request a new one.",
        },
        "upload": {
            "FILE_TOO_LARGE": "Your file is too large. Please choose a file smaller than 50MB.",
            "INVALID_FILE_TYPE": "This file type isn't supported. Please upload a PDF, image, or video file.",
            "PROCESSING_FAILED": "We couldn't process your file. Please try a different file or contact support.",
        },
        "payment": {
            "PAYMENT_FAILED": "Payment failed. Please check your card details and try again.",
            "CARD_DECLINED": "Your card was declined. Please try a different payment method or contact your bank.",
            "SUBSCRIPTION_EXPIRED": "Your subscription has expired. Please renew to continue using premium features.",
        }
    }
    
    # Get context-specific message or fall back to general message
    context_errors = context_messages.get(context, {})
    if error_type in context_errors:
        return context_errors[error_type]
    
    return get_user_friendly_error(error_type, context)


def format_validation_error(field: str, error_type: str) -> str:
    """
    Format validation errors for form fields.
    
    Args:
        field: The field name that failed validation
        error_type: The type of validation error
    
    Returns:
        A user-friendly validation error message
    """
    
    field_names = {
        "email": "email address",
        "password": "password",
        "name": "name",
        "phone": "phone number",
        "file": "file",
        "url": "URL",
        "date": "date",
        "amount": "amount",
    }
    
    validation_messages = {
        "required": f"Please enter your {field_names.get(field, field)}.",
        "invalid": f"Please enter a valid {field_names.get(field, field)}.",
        "too_short": f"Your {field_names.get(field, field)} is too short.",
        "too_long": f"Your {field_names.get(field, field)} is too long.",
        "weak": f"Please choose a stronger {field_names.get(field, field)}.",
        "mismatch": f"The {field_names.get(field, field)} fields don't match.",
        "exists": f"This {field_names.get(field, field)} is already in use.",
        "not_found": f"We couldn't find an account with this {field_names.get(field, field)}.",
    }
    
    return validation_messages.get(error_type, f"Please check your {field_names.get(field, field)} and try again.")