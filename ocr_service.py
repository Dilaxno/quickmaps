"""
OCR Service using Tesseract (pytesseract)

This service handles optical character recognition (OCR) for scanned images,
extracting text with confidence scores and page detection capabilities.
It uses Tesseract via pytesseract as the primary and only OCR backend.
"""

import os
import logging
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter
import tempfile

# Tesseract OCR
try:
    import pytesseract  # type: ignore
    TESSERACT_AVAILABLE = True
except Exception:
    TESSERACT_AVAILABLE = False

# Setup logging
logger = logging.getLogger(__name__)


class OCRService:
    """Service for handling OCR operations using Tesseract (pytesseract) only"""

    def __init__(self):
        self.use_tesseract = False  # Whether to use pytesseract
        self.backend = None  # 'tesseract' | None
        self._initialize_ocr()

    def _initialize_ocr(self):
        """Initialize OCR engine (Tesseract only)."""
        if TESSERACT_AVAILABLE:
            try:
                # Validate that the tesseract binary is available
                _ = pytesseract.get_tesseract_version()
                self.use_tesseract = True
                self.backend = 'tesseract'
                logger.info("Tesseract (pytesseract) initialized successfully")
                return
            except Exception as e:
                logger.error(f"Tesseract is not operational (binary missing?): {e}")
                self.use_tesseract = False
                self.backend = None

        logger.error("No OCR backend available. Please install tesseract-ocr (with pytesseract).")

    def preprocess_image(self, image_path: str) -> str:
        """
        Preprocess image to improve OCR accuracy

        Args:
            image_path: Path to the input image

        Returns:
            Path to the preprocessed image
        """
        try:
            # Load image
            image = Image.open(image_path)

            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Enhance image for better OCR
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.2)

            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.1)

            # Apply slight denoising
            image = image.filter(ImageFilter.MedianFilter(size=3))

            # Save preprocessed image to temporary file
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                image.save(temp_file.name, 'JPEG', quality=95)
                return temp_file.name
        except Exception as e:
            logger.warning(f"Image preprocessing failed: {e}. Using original image.")
            return image_path

    def detect_page_boundaries(self, image_path: str) -> Optional[Tuple[int, int, int, int]]:
        """
        Detect page boundaries in the image (basic implementation)

        Args:
            image_path: Path to the image

        Returns:
            Tuple of (x, y, width, height) or None if detection fails
        """
        try:
            # Load image with OpenCV
            image = cv2.imread(image_path)
            if image is None:
                return None

            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Apply Gaussian blur
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Edge detection
            edges = cv2.Canny(blurred, 50, 150)

            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return None

            # Find the largest contour (assuming it's the page)
            largest_contour = max(contours, key=cv2.contourArea)

            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(largest_contour)

            # Return boundaries if they seem reasonable
            image_height, image_width = gray.shape
            if w > image_width * 0.5 and h > image_height * 0.5:
                return (x, y, w, h)

            return None
        except Exception as e:
            logger.warning(f"Page boundary detection failed: {e}")
            return None

    def _ocr_with_tesseract(self, image_path: str, boundaries: Optional[Tuple[int, int, int, int]] = None) -> Dict:
        """OCR using pytesseract"""
        # Note: Requires Tesseract binary installed on the system.
        image = Image.open(image_path)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        n = len(data.get('text', []))
        lines = []
        total_confidence = 0.0
        word_count = 0
        for i in range(n):
            text = data['text'][i]
            conf_str = str(data['conf'][i])
            try:
                conf = float(conf_str) / 100.0 if conf_str not in ('-1', '') else 0.0
            except Exception:
                conf = 0.0
            if text and text.strip():
                x = int(data['left'][i]); y = int(data['top'][i])
                w = int(data['width'][i]); h = int(data['height'][i])
                bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
                lines.append({'text': text, 'confidence': conf, 'bbox': bbox})
                total_confidence += conf
                word_count += len(text.split())
        avg_confidence = total_confidence / len(lines) if lines else 0.0
        full_text = ' '.join([l['text'] for l in lines])
        return {
            'text': full_text,
            'confidence': avg_confidence,
            'word_count': word_count,
            'line_count': len(lines),
            'boundaries': boundaries,
            'lines': lines,
            'raw_result': data
        }

    def extract_text_from_image(self, image_path: str, preprocess: bool = True) -> Dict:
        """
        Extract text from a single image using Tesseract backend

        Args:
            image_path: Path to the image file
            preprocess: Whether to preprocess the image

        Returns:
            Dictionary containing extracted text and metadata
        """
        if not self.is_available():
            raise Exception("OCR service is not available. Please check Tesseract installation.")

        # Preprocess image if requested
        processed_image_path = image_path
        if preprocess:
            processed_image_path = self.preprocess_image(image_path)

        # Detect page boundaries (optional)
        boundaries = self.detect_page_boundaries(processed_image_path)

        try:
            result = self._ocr_with_tesseract(processed_image_path, boundaries)
            # Clean up preprocessed image
            if preprocess and processed_image_path != image_path:
                try:
                    os.unlink(processed_image_path)
                except Exception:
                    pass
            return result
        except Exception as e:
            logger.error(f"OCR extraction failed for {image_path}: {e}")
            raise Exception(f"Failed to extract text from image: {str(e)}")

    def process_multiple_images(self, image_paths: List[str]) -> Dict:
        """
        Process multiple images and extract text from each

        Args:
            image_paths: List of paths to image files

        Returns:
            Dictionary containing results for all images
        """
        if not self.is_available():
            raise Exception("OCR service is not available. Please check Tesseract installation.")

        results = {
            'pages': [],
            'total_text': '',
            'total_confidence': 0.0,
            'total_word_count': 0,
            'page_count': len(image_paths),
            'successful_pages': 0,
            'failed_pages': []
        }

        total_confidence_sum = 0.0
        successful_pages = 0

        for i, image_path in enumerate(image_paths):
            try:
                logger.info(f"Processing image {i+1}/{len(image_paths)}: {image_path}")

                # Extract text from this image
                page_result = self.extract_text_from_image(image_path)

                # Add page number
                page_result['page_number'] = i + 1
                page_result['image_path'] = image_path

                results['pages'].append(page_result)

                # Update totals
                if page_result['text'].strip():
                    results['total_text'] += page_result['text'] + '\n\n'
                    total_confidence_sum += page_result['confidence']
                    successful_pages += 1

                results['total_word_count'] += page_result['word_count']

            except Exception as e:
                logger.error(f"Failed to process image {image_path}: {e}")
                results['failed_pages'].append({
                    'page_number': i + 1,
                    'image_path': image_path,
                    'error': str(e)
                })

        # Calculate overall statistics
        results['successful_pages'] = successful_pages
        results['total_confidence'] = total_confidence_sum / successful_pages if successful_pages > 0 else 0.0
        results['total_text'] = results['total_text'].strip()

        return results

    def is_available(self) -> bool:
        """Check if OCR service is available (Tesseract)"""
        if self.backend == 'tesseract' and TESSERACT_AVAILABLE and self.use_tesseract:
            return True
        return False

    def get_supported_formats(self) -> List[str]:
        """Get list of supported image formats"""
        return ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp']


# Create global instance
ocr_service = OCRService()

# Export for easy importing
__all__ = ['ocr_service', 'OCRService']
