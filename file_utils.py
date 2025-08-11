"""
File Utilities Module

Contains utility functions for file operations, cleanup, and format conversions.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

class FileUtils:
    """Utility functions for file operations"""
    
    @staticmethod
    def cleanup_temp_files(job_id: str, *file_paths: str) -> None:
        """
        Clean up temporary files for a job
        
        Args:
            job_id (str): Job ID
            *file_paths: Variable number of file paths to clean up
        """
        for file_path in file_paths:
            if file_path and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                    logger.info(f"Cleaned up temporary file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up file {file_path}: {e}")
    
    @staticmethod
    def convert_markdown_to_text(markdown_content: str) -> str:
        """
        Convert markdown content to plain text
        
        Args:
            markdown_content (str): Markdown formatted text
            
        Returns:
            str: Plain text version
        """
        # Remove markdown headers
        text = re.sub(r'^#{1,6}\s+', '', markdown_content, flags=re.MULTILINE)
        
        # Remove bold and italic formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # Italic
        text = re.sub(r'__([^_]+)__', r'\1', text)      # Bold
        text = re.sub(r'_([^_]+)_', r'\1', text)        # Italic
        
        # Remove code blocks
        text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
        text = re.sub(r'`([^`]+)`', r'\1', text)  # Inline code
        
        # Remove links
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        
        # Convert bullet points
        text = re.sub(r'^\s*[\*\-\+]\s+', '• ', text, flags=re.MULTILINE)
        
        # Remove horizontal rules
        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
        
        # Clean up extra whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Multiple newlines
        text = text.strip()
        
        return text
    
    @staticmethod
    def ensure_directory_exists(directory_path: str) -> Path:
        """
        Ensure a directory exists, create if it doesn't
        
        Args:
            directory_path (str): Path to directory
            
        Returns:
            Path: Path object for the directory
        """
        path = Path(directory_path)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @staticmethod
    def get_file_size(file_path: str) -> int:
        """
        Get file size in bytes
        
        Args:
            file_path (str): Path to file
            
        Returns:
            int: File size in bytes, 0 if file doesn't exist
        """
        try:
            return os.path.getsize(file_path)
        except (OSError, FileNotFoundError):
            return 0
    
    @staticmethod
    def is_valid_file_extension(filename: str, allowed_extensions: List[str]) -> bool:
        """
        Check if file has a valid extension
        
        Args:
            filename (str): Name of the file
            allowed_extensions (list): List of allowed extensions (with dots)
            
        Returns:
            bool: True if extension is valid
        """
        file_extension = Path(filename).suffix.lower()
        return file_extension in [ext.lower() for ext in allowed_extensions]
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename by removing/replacing invalid characters
        
        Args:
            filename (str): Original filename
            
        Returns:
            str: Sanitized filename
        """
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove control characters
        filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
        # Limit length
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[:255-len(ext)] + ext
        return filename.strip()
    
    @staticmethod
    def create_unique_filename(directory: str, base_name: str, extension: str) -> str:
        """
        Create a unique filename in the given directory
        
        Args:
            directory (str): Target directory
            base_name (str): Base name for the file
            extension (str): File extension (with dot)
            
        Returns:
            str: Unique filename
        """
        counter = 1
        filename = f"{base_name}{extension}"
        file_path = os.path.join(directory, filename)
        
        while os.path.exists(file_path):
            filename = f"{base_name}_{counter}{extension}"
            file_path = os.path.join(directory, filename)
            counter += 1
        
        return filename
    
    @staticmethod
    def read_file_safely(file_path: str, encoding: str = 'utf-8') -> Optional[str]:
        """
        Safely read a file with error handling
        
        Args:
            file_path (str): Path to file
            encoding (str): File encoding
            
        Returns:
            str: File content or None if error
        """
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return None
    
    @staticmethod
    def write_file_safely(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
        """
        Safely write content to a file with error handling
        
        Args:
            file_path (str): Path to file
            content (str): Content to write
            encoding (str): File encoding
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            directory = os.path.dirname(file_path)
            if directory:
                FileUtils.ensure_directory_exists(directory)
            
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return False

# Global instance
file_utils = FileUtils()