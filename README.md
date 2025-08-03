# QuickMaps Backend

This is the backend API for QuickMaps, a mind mapping application that processes various content types including YouTube videos, PDFs, and text to generate interactive mind maps.

## Features

- **Content Processing**: Supports YouTube videos, PDFs, and text input
- **AI-Powered**: Uses advanced AI models for transcription and summarization
- **Mind Map Generation**: Creates structured mind maps from processed content
- **User Management**: Firebase authentication and user credit system
- **Cloud Storage**: Cloudflare R2 integration for file storage
- **Email Services**: MJML-based email templates and notifications
- **Security**: Device fingerprinting and IP detection for security

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   Create a `.env` file with the following variables:
   ```
   # Firebase
   FIREBASE_PROJECT_ID=your_project_id
   FIREBASE_PRIVATE_KEY=your_private_key
   FIREBASE_CLIENT_EMAIL=your_client_email
   
   # Cloudflare R2
   R2_ACCESS_KEY_ID=your_access_key
   R2_SECRET_ACCESS_KEY=your_secret_key
   R2_BUCKET_NAME=your_bucket_name
   R2_ENDPOINT_URL=your_endpoint_url
   
   # Email Service
   MJML_API_KEY=your_mjml_api_key
   MJML_SECRET_KEY=your_mjml_secret_key
   
   # Other configurations...
   ```

3. **Run the Application**:
   ```bash
   uvicorn main:app --reload
   ```

## API Endpoints

- `POST /process-content` - Process various content types
- `GET /mindmaps` - Retrieve user's mind maps
- `POST /auth/verify` - Verify user authentication
- `GET /credits` - Get user credit information
- And more...

## Project Structure

```
backend/
├── config/          # Configuration files
├── utils/           # Utility modules
│   ├── transcription.py    # Audio/video transcription
│   ├── summarizer.py       # Content summarization
│   ├── mindmap.py          # Mind map generation
│   ├── firebase_auth.py    # Firebase authentication
│   ├── r2_storage.py       # Cloud storage
│   └── ...
├── main.py          # FastAPI application
├── requirements.txt # Python dependencies
└── README.md        # This file
```

## Technologies Used

- **FastAPI** - Web framework
- **Firebase** - Authentication and database
- **Cloudflare R2** - Object storage
- **OpenAI Whisper** - Audio transcription
- **MJML** - Email templates
- **PyTorch** - AI model inference
- **And more...**

## Security Features

- Device fingerprinting for user tracking
- IP detection and VPN/proxy detection
- Secure file upload and processing
- Rate limiting and credit system

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is proprietary software.