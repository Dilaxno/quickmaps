"""
Processing Service Module

Handles the main processing workflows for video, audio, and PDF files.
"""

import os
import time
import asyncio
import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

# Import services
from transcription_service import transcription_service
from youtube_service import youtube_service
from job_manager import job_manager
from file_utils import file_utils
from config import TEMP_DIR, OUTPUT_DIR, CLEANUP_TEMP_FILES, MAX_WORKERS

# Import existing services
from groq_processor import groq_generator
from timestamp_mapper import timestamp_mapper
from r2_storage import r2_storage
from video_validation_service import video_validation_service
from credit_service import credit_service, CreditAction

logger = logging.getLogger(__name__)

# Thread pool for CPU-intensive tasks
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

class ProcessingService:
    """Service for handling file processing workflows"""
    
    def __init__(self, db_client=None):
        self.db = db_client
    
    async def process_audio_from_r2(self, job_id: str, r2_key: str, user_id: Optional[str] = None):
        """Download audio from R2, process with existing pipeline, then clean up R2."""
        local_path = str(TEMP_DIR / f"{job_id}_uploaded{Path(r2_key).suffix or ''}")
        try:
            job_manager.update_job_progress(job_id, "Fetching audio from storage...")
            if not r2_storage.is_available():
                raise Exception("R2 storage is not available")
            ok = r2_storage.download_to_path(r2_key, local_path)
            if not ok:
                raise Exception("Failed to download audio from storage")

            # Reuse the existing video/audio processing pipeline
            await self.process_video_file(job_id, local_path, user_id)
        finally:
            # Cleanup R2 object regardless of success/failure
            try:
                if r2_storage.is_available():
                    r2_storage.delete_key(r2_key)
            except Exception:
                pass
            # Local cleanup handled by process_video_file, but ensure if early failure
            try:
                if os.path.exists(local_path):
                    os.unlink(local_path)
            except Exception:
                pass

    async def process_video_file(self, job_id: str, video_path: str, user_id: Optional[str] = None):
        """
        Process uploaded video file
        
        Args:
            job_id (str): Job ID
            video_path (str): Path to video file
            user_id (str, optional): User ID for credit tracking
        """
        try:
            # Validate media duration based on user's plan (applies to all uploads)
            if user_id and self.db:
                job_manager.update_job_progress(job_id, "Validating media duration...")
                user_plan = video_validation_service.get_user_plan_from_firestore(self.db, user_id)
                validation_result = video_validation_service.validate_video_duration(
                    video_path=video_path,
                    user_plan=user_plan,
                    user_id=user_id
                )
                if not validation_result.is_valid:
                    # Suggest upgrade if applicable
                    upgrade_suggestion = video_validation_service.get_plan_upgrade_suggestion(
                        user_plan, validation_result.duration_minutes or 0
                    )
                    error_message = f"{validation_result.message}"
                    if upgrade_suggestion:
                        error_message += f" {upgrade_suggestion['message']}"
                    raise Exception(error_message)

            job_manager.update_job_progress(job_id, "Extracting audio...")
            
            # Extract audio from video
            audio_path = str(TEMP_DIR / f"{job_id}_audio.wav")
            
            # Use ffmpeg to extract audio
            loop = asyncio.get_event_loop()
            actual_audio_path = await loop.run_in_executor(
                executor, 
                youtube_service.extract_audio, 
                video_path, 
                audio_path
            )
            
            job_manager.update_job_progress(job_id, "Transcribing audio...")
            
            # Transcribe audio
            transcription_result = await loop.run_in_executor(
                executor,
                transcription_service.transcribe_audio,
                actual_audio_path
            )
            
            # Generate structured notes if Groq is available
            structured_notes = None
            if groq_generator.is_available():
                job_manager.update_job_progress(job_id, "Generating structured learning notes...")
                logger.info(f"Generating structured notes for job {job_id}")
                
                structured_notes = await loop.run_in_executor(
                    executor,
                    groq_generator.generate_video_notes,
                    transcription_result["text"]
                )
                
                if structured_notes:
                    logger.info(f"Successfully generated structured notes for job {job_id}")
                else:
                    logger.warning(f"Failed to generate structured notes for job {job_id}")
            
            # Save transcription to file
            await self._save_transcription_file(job_id, transcription_result)
            
            # Save structured notes and generate timestamped data
            timestamped_data = None
            if structured_notes:
                await self._save_notes_files(job_id, structured_notes)
                timestamped_data = await self._generate_timestamped_notes(
                    job_id, structured_notes, transcription_result["segments"]
                )
                
                # Save to R2 storage if available
                await self._save_to_r2_storage(job_id, structured_notes, transcription_result, user_id)
                
                # Auto-create bookmarks for important sections if user is authenticated
                if user_id and self.db:
                    try:
                        await self._create_auto_bookmarks(job_id, structured_notes, user_id)
                    except Exception as e:
                        logger.error(f"❌ Failed to create auto-bookmarks for job {job_id}: {e}")
            
            # Deduct credits only after successful processing and note generation
            if user_id and self.db and structured_notes:
                try:
                    job_manager.update_job_progress(job_id, "Processing payment...")
                    credit_result = await credit_service.check_and_deduct_credits(
                        user_id=user_id,
                        action=CreditAction.VIDEO_UPLOAD
                    )
                    
                    if not credit_result.has_credits:
                        logger.warning(f"⚠️ Credit deduction failed for job {job_id}: {credit_result.message}")
                        # Don't fail the job, but log the issue
                    else:
                        logger.info(f"✅ Credits deducted successfully for job {job_id}: {credit_result.message}")
                        
                except Exception as credit_error:
                    logger.error(f"❌ Credit deduction error for job {job_id}: {credit_error}")
                    # Don't fail the job due to credit issues
            
            # Set job as completed
            result_data = {
                "transcription": transcription_result["text"],
                "language": transcription_result["language"],
                "segments_count": len(transcription_result["segments"]),
                "has_notes": structured_notes is not None,
                "has_timestamped_notes": timestamped_data is not None,
                "notes_preview": structured_notes[:200] + "..." if structured_notes and len(structured_notes) > 200 else structured_notes,
                "timestamp_coverage": timestamped_data.get('coverage_percentage', 0) if timestamped_data else 0,
                "mapped_sections": timestamped_data.get('mapped_sections', 0) if timestamped_data else 0,
                "credits_deducted": user_id and self.db and structured_notes  # Indicate if credits were deducted
            }
            job_manager.set_job_completed(job_id, result_data)
            
            # Update user statistics (non-blocking)
            if user_id:
                try:
                    await self._increment_user_statistics(user_id, {
                        'total_videos_processed': 1,
                        'total_notes_generated': 1 if structured_notes else 0,
                        'total_mindmaps': 1 if structured_notes else 0
                    })
                except Exception as stats_error:
                    logger.warning(f"Failed to update user statistics: {stats_error}")
            
            # Cleanup temporary files
            if CLEANUP_TEMP_FILES:
                file_utils.cleanup_temp_files(job_id, video_path, actual_audio_path)
            
        except Exception as e:
            logger.error(f"Video processing failed for job {job_id}: {str(e)}")
            job_manager.set_job_error(job_id, str(e))
            if CLEANUP_TEMP_FILES:
                file_utils.cleanup_temp_files(job_id, video_path)
    
    async def process_youtube_url(self, job_id: str, url: str, user_id: Optional[str] = None, cookies_path: Optional[str] = None):
        """
        Process YouTube URL
        
        Args:
            job_id (str): Job ID
            url (str): YouTube URL
            user_id (str, optional): User ID for validation and credit tracking
        """
        try:
            # Determine platform for appropriate messaging
            if 'udemy.com' in url.lower():
                platform = "Udemy course"
                job_manager.update_job_progress(job_id, "Downloading video from Udemy...")
                logger.info(f"Starting Udemy download for job {job_id}: {url}")
            elif 'ted.com' in url.lower():
                platform = "TED Talk"
                job_manager.update_job_progress(job_id, "Downloading TED Talk...")
                logger.info(f"Starting TED Talk download for job {job_id}: {url}")
            elif 'khanacademy.org' in url.lower():
                platform = "Khan Academy video"
                job_manager.update_job_progress(job_id, "Downloading video from Khan Academy...")
                logger.info(f"Starting Khan Academy download for job {job_id}: {url}")
            else:
                platform = "YouTube video"
                job_manager.update_job_progress(job_id, "Downloading video from YouTube...")
                logger.info(f"Starting YouTube download for job {job_id}: {url}")
            
            # Download video
            loop = asyncio.get_event_loop()
            video_path = await loop.run_in_executor(
                executor,
                youtube_service.download_video,
                url,
                str(TEMP_DIR),
                cookies_path
            )
            
            logger.info(f"{platform} download completed for job {job_id}: {video_path}")
            
            # Validate video duration based on user's plan
            if user_id and self.db:
                job_manager.update_job_progress(job_id, "Validating video duration...")
                user_plan = video_validation_service.get_user_plan_from_firestore(self.db, user_id)
                validation_result = video_validation_service.validate_video_duration(
                    video_path=video_path,
                    user_plan=user_plan,
                    user_id=user_id
                )
                
                if not validation_result.is_valid:
                    # Clean up downloaded file
                    if os.path.exists(video_path):
                        os.unlink(video_path)
                    
                    # Get upgrade suggestion
                    upgrade_suggestion = video_validation_service.get_plan_upgrade_suggestion(
                        user_plan, validation_result.duration_minutes or 0
                    )
                    
                    error_message = f"{validation_result.message}"
                    if upgrade_suggestion:
                        error_message += f" {upgrade_suggestion['message']}"
                    
                    raise Exception(error_message)
            
            # Process the downloaded video
            await self.process_video_file(job_id, video_path, user_id)
            
        except Exception as e:
            logger.error(f"YouTube processing failed for job {job_id}: {str(e)}")
            job_manager.set_job_error(job_id, str(e))
    
    async def process_pdf_file(self, job_id: str, pdf_path: str, user_id: Optional[str] = None):
        """
        Process PDF file and generate structured notes
        
        Args:
            job_id (str): Job ID
            pdf_path (str): Path to PDF file
            user_id (str, optional): User ID for credit tracking
        """
        start_time = time.time()
        
        try:
            # PDF -> Images (pdf2image) -> OCR (Tesseract) pipeline
            job_manager.update_job_progress(job_id, "Converting PDF pages to images...")
            
            loop = asyncio.get_event_loop()

            # Convert PDF to images
            def _convert_pdf_to_images(_pdf_path: str) -> list[str]:
                from pdf2image import convert_from_path
                from pathlib import Path as _Path
                import tempfile as _tempfile
                imgs = convert_from_path(_pdf_path, dpi=300)
                out_paths = []
                temp_dir = _Path(OUTPUT_DIR) / f"{job_id}_pdf_pages"
                try:
                    temp_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                for idx, img in enumerate(imgs):
                    out_path = temp_dir / f"{_Path(_pdf_path).stem}_page_{idx+1:03d}.png"
                    img.save(str(out_path), format='PNG')
                    out_paths.append(str(out_path))
                return out_paths
            
            image_paths = await loop.run_in_executor(executor, _convert_pdf_to_images, pdf_path)
            if not image_paths:
                raise Exception("Failed to render PDF pages. Please ensure the PDF is not corrupted.")

            # Run OCR on rendered images (same as page scan pipeline)
            job_manager.update_job_progress(job_id, f"Running OCR on {len(image_paths)} pages...")
            from ocr_service import ocr_service
            ocr_results = await loop.run_in_executor(
                executor,
                ocr_service.process_multiple_images,
                image_paths
            )

            if not ocr_results['total_text'] or len(ocr_results['total_text'].strip()) < 100:
                raise Exception("PDF appears to contain insufficient readable text after OCR.")

            # Save OCR results and extracted text
            ocr_results_file = OUTPUT_DIR / f"{job_id}_ocr_results.json"
            file_utils.write_file_safely(str(ocr_results_file), json.dumps(ocr_results, indent=2))

            extracted_text_file = OUTPUT_DIR / f"{job_id}_extracted_text.txt"
            file_utils.write_file_safely(str(extracted_text_file), ocr_results['total_text'])

            # Generate structured notes if Groq is available
            structured_notes = None
            if groq_generator.is_available():
                job_manager.update_job_progress(job_id, "Generating structured learning notes from OCR text...")
                logger.info(f"Generating structured notes for PDF OCR job {job_id}")

                structured_notes = await loop.run_in_executor(
                    executor,
                    groq_generator.generate_pdf_notes,
                    ocr_results['total_text']
                )

                if structured_notes:
                    logger.info(f"Successfully generated structured notes for PDF job {job_id}")
                    await self._save_notes_files(job_id, structured_notes)

                    # Save to R2 storage if available
                    if r2_storage.is_available():
                        try:
                            metadata = {
                                "job_id": job_id,
                                "user_id": user_id,
                                "processing_date": datetime.now().isoformat(),
                                "file_type": "pdf_notes",
                                "page_count": ocr_results['page_count'],
                                "successful_pages": ocr_results['successful_pages'],
                                "average_confidence": ocr_results['total_confidence'],
                                "processing_time": time.time() - start_time
                            }
                            r2_key = r2_storage.save_notes(job_id, structured_notes, metadata, user_id)
                            if r2_key:
                                logger.info(f"✅ PDF notes saved to R2 storage: {r2_key}")
                            else:
                                logger.warning("⚠️ Failed to save PDF notes to R2 storage")
                        except Exception as e:
                            logger.error(f"❌ R2 storage error: {e}")
                else:
                    logger.warning(f"Failed to generate structured notes for PDF job {job_id}")

            # Deduct credits only after successful processing and note generation
            if user_id and self.db and structured_notes:
                try:
                    job_manager.update_job_progress(job_id, "Processing payment...")
                    credit_result = await credit_service.check_and_deduct_credits(
                        user_id=user_id,
                        action=CreditAction.PDF_UPLOAD
                    )

                    if not credit_result.has_credits:
                        logger.warning(f"⚠️ Credit deduction failed for PDF job {job_id}: {credit_result.message}")
                    else:
                        logger.info(f"✅ Credits deducted successfully for PDF job {job_id}: {credit_result.message}")

                except Exception as credit_error:
                    logger.error(f"❌ Credit deduction error for PDF job {job_id}: {credit_error}")
                    # Don't fail the job due to credit issues

            # Set job as completed
            result_data = {
                "extracted_text": ocr_results['total_text'][:500] + "..." if len(ocr_results['total_text']) > 500 else ocr_results['total_text'],
                "text_length": len(ocr_results['total_text']),
                "page_count": ocr_results['page_count'],
                "successful_pages": ocr_results['successful_pages'],
                "failed_pages": len(ocr_results['failed_pages']),
                "average_confidence": ocr_results['total_confidence'],
                "word_count": ocr_results['total_word_count'],
                "has_notes": structured_notes is not None,
                "notes_preview": structured_notes[:200] + "..." if structured_notes and len(structured_notes) > 200 else structured_notes,
                "processing_time": time.time() - start_time,
                "credits_deducted": user_id and self.db and structured_notes
            }
            job_manager.set_job_completed(job_id, result_data)
            
            # Update user statistics (non-blocking)
            if user_id:
                try:
                    await self._increment_user_statistics(user_id, {
                        'total_pdfs_processed': 1,
                        'total_notes_generated': 1 if structured_notes else 0
                    })
                except Exception as stats_error:
                    logger.warning(f"Failed to update user statistics: {stats_error}")
            
            # Cleanup temporary files
            if CLEANUP_TEMP_FILES:
                file_utils.cleanup_temp_files(job_id, pdf_path)
            
        except Exception as e:
            logger.error(f"PDF processing failed for job {job_id}: {str(e)}")
            job_manager.set_job_error(job_id, str(e))
            if CLEANUP_TEMP_FILES:
                file_utils.cleanup_temp_files(job_id, pdf_path)
    
    async def process_page_scan(self, job_id: str, image_paths: list, user_id: Optional[str] = None):
        """
        Process scanned page images using OCR and generate structured notes
        
        Args:
            job_id (str): Job ID
            image_paths (list): List of paths to image files
            user_id (str, optional): User ID for credit tracking
        """
        start_time = time.time()
        
        try:
            job_manager.update_job_progress(job_id, f"Processing {len(image_paths)} scanned pages...")
            
            # Import OCR service
            from ocr_service import ocr_service
            
            # Check if OCR service is available
            if not ocr_service.is_available():
                raise Exception("OCR service is not available. Please check Tesseract installation.")
            
            # Process all images with OCR
            loop = asyncio.get_event_loop()
            ocr_results = await loop.run_in_executor(
                executor,
                ocr_service.process_multiple_images,
                image_paths
            )
            
            # Check if we got any text
            if not ocr_results['total_text'] or len(ocr_results['total_text'].strip()) < 50:
                raise Exception("No readable text was found in the uploaded images. Please ensure the images are clear and contain readable text.")
            
            # Save OCR results
            ocr_results_file = OUTPUT_DIR / f"{job_id}_ocr_results.json"
            file_utils.write_file_safely(str(ocr_results_file), json.dumps(ocr_results, indent=2))
            
            # Save extracted text
            extracted_text_file = OUTPUT_DIR / f"{job_id}_extracted_text.txt"
            file_utils.write_file_safely(str(extracted_text_file), ocr_results['total_text'])
            
            # Generate structured notes if Groq is available
            structured_notes = None
            if groq_generator.is_available():
                job_manager.update_job_progress(job_id, "Generating structured learning notes from scanned text...")
                logger.info(f"Generating structured notes for page scan job {job_id}")
                
                # Use PDF notes generator as it's suitable for text-based content
                structured_notes = await loop.run_in_executor(
                    executor,
                    groq_generator.generate_pdf_notes,
                    ocr_results['total_text']
                )
                
                if structured_notes:
                    logger.info(f"Successfully generated structured notes for page scan job {job_id}")
                    await self._save_notes_files(job_id, structured_notes)
                    
                    # Save to R2 storage if available
                    if r2_storage.is_available():
                        try:
                            metadata = {
                                "job_id": job_id,
                                "user_id": user_id,
                                "processing_date": datetime.now().isoformat(),
                                "file_type": "page_scan_notes",
                                "page_count": ocr_results['page_count'],
                                "successful_pages": ocr_results['successful_pages'],
                                "average_confidence": ocr_results['total_confidence'],
                                "processing_time": time.time() - start_time
                            }
                            
                            r2_key = r2_storage.save_notes(job_id, structured_notes, metadata, user_id)
                            if r2_key:
                                logger.info(f"✅ Page scan notes saved to R2 storage: {r2_key}")
                            else:
                                logger.warning("⚠️ Failed to save page scan notes to R2 storage")
                        except Exception as e:
                            logger.error(f"❌ R2 storage error: {e}")
                else:
                    logger.warning(f"Failed to generate structured notes for page scan job {job_id}")
            
            # Deduct credits only after successful processing and note generation
            if user_id and self.db and structured_notes:
                try:
                    job_manager.update_job_progress(job_id, "Processing payment...")
                    credit_result = await credit_service.check_and_deduct_credits(
                        user_id=user_id,
                        action=CreditAction.PDF_UPLOAD  # Use PDF_UPLOAD action for page scanning
                    )
                    
                    if not credit_result.has_credits:
                        logger.warning(f"⚠️ Credit deduction failed for page scan job {job_id}: {credit_result.message}")
                    else:
                        logger.info(f"✅ Credits deducted successfully for page scan job {job_id}: {credit_result.message}")
                        
                except Exception as credit_error:
                    logger.error(f"❌ Credit deduction error for page scan job {job_id}: {credit_error}")
                    # Don't fail the job due to credit issues
            
            # Set job as completed
            result_data = {
                "extracted_text": ocr_results['total_text'][:500] + "..." if len(ocr_results['total_text']) > 500 else ocr_results['total_text'],
                "text_length": len(ocr_results['total_text']),
                "page_count": ocr_results['page_count'],
                "successful_pages": ocr_results['successful_pages'],
                "failed_pages": len(ocr_results['failed_pages']),
                "average_confidence": ocr_results['total_confidence'],
                "word_count": ocr_results['total_word_count'],
                "has_notes": structured_notes is not None,
                "notes_preview": structured_notes[:200] + "..." if structured_notes and len(structured_notes) > 200 else structured_notes,
                "processing_time": time.time() - start_time,
                "credits_deducted": user_id and self.db and structured_notes,
                "pages": ocr_results['pages']  # Include page-by-page results
            }
            job_manager.set_job_completed(job_id, result_data)
            
            # Update user statistics (non-blocking)
            if user_id:
                try:
                    await self._increment_user_statistics(user_id, {
                        'total_page_scans_processed': 1,
                        'total_pages_scanned': ocr_results['successful_pages'],
                        'total_notes_generated': 1 if structured_notes else 0
                    })
                except Exception as stats_error:
                    logger.warning(f"Failed to update user statistics: {stats_error}")
            
            # Cleanup temporary files
            if CLEANUP_TEMP_FILES:
                for image_path in image_paths:
                    file_utils.cleanup_temp_files(job_id, image_path)
            
        except Exception as e:
            logger.error(f"Page scan processing failed for job {job_id}: {str(e)}")
            job_manager.set_job_error(job_id, str(e))
            if CLEANUP_TEMP_FILES:
                for image_path in image_paths:
                    file_utils.cleanup_temp_files(job_id, image_path)
    
    async def _save_transcription_file(self, job_id: str, transcription_result: Dict[str, Any]):
        """Save transcription to file"""
        output_file = OUTPUT_DIR / f"{job_id}_transcription.txt"
        content = f"Transcription Result\n"
        content += f"Language: {transcription_result['language']}\n"
        content += f"{'='*50}\n\n"
        content += transcription_result["text"]
        content += f"\n\n{'='*50}\n"
        content += "Detailed Segments:\n\n"
        for segment in transcription_result["segments"]:
            content += f"[{segment['start']:.2f}s - {segment['end']:.2f}s]: {segment['text']}\n"
        
        file_utils.write_file_safely(str(output_file), content)
    
    async def _save_notes_files(self, job_id: str, structured_notes: str):
        """Save structured notes in multiple formats"""
        # Save as both markdown (.md) and plain text (.txt) formats
        notes_file_md = OUTPUT_DIR / f"{job_id}_notes.md"
        notes_file_txt = OUTPUT_DIR / f"{job_id}_notes.txt"
        
        # Save markdown version
        file_utils.write_file_safely(str(notes_file_md), structured_notes)
        
        # Save plain text version (strip markdown formatting)
        plain_text_notes = file_utils.convert_markdown_to_text(structured_notes)
        file_utils.write_file_safely(str(notes_file_txt), plain_text_notes)
    
    async def _generate_timestamped_notes(self, job_id: str, structured_notes: str, segments: list) -> Optional[Dict[str, Any]]:
        """Generate timestamped notes mapping"""
        job_manager.update_job_progress(job_id, "Mapping notes to audio timestamps...")
        logger.info(f"Generating timestamp mappings for job {job_id}")
        
        try:
            timestamped_data = timestamp_mapper.map_notes_to_timestamps(
                structured_notes, 
                segments
            )
            
            # Save timestamped notes in multiple formats
            timestamped_json_file = OUTPUT_DIR / f"{job_id}_timestamped_notes.json"
            timestamped_md_file = OUTPUT_DIR / f"{job_id}_timestamped_notes.md"
            timestamped_srt_file = OUTPUT_DIR / f"{job_id}_notes.srt"
            timestamped_vtt_file = OUTPUT_DIR / f"{job_id}_notes.vtt"
            
            # Save JSON format (for API consumption)
            json_content = timestamp_mapper.export_timestamped_notes(timestamped_data, 'json')
            file_utils.write_file_safely(str(timestamped_json_file), json_content)
            
            # Save enhanced markdown with timestamps
            md_content = timestamp_mapper.export_timestamped_notes(timestamped_data, 'markdown')
            file_utils.write_file_safely(str(timestamped_md_file), md_content)
            
            # Save SRT format (for video players)
            srt_content = timestamp_mapper.export_timestamped_notes(timestamped_data, 'srt')
            file_utils.write_file_safely(str(timestamped_srt_file), srt_content)
            
            # Save VTT format (for web players)
            vtt_content = timestamp_mapper.export_timestamped_notes(timestamped_data, 'vtt')
            file_utils.write_file_safely(str(timestamped_vtt_file), vtt_content)
            
            logger.info(f"✅ Timestamp mappings generated successfully for job {job_id}")
            logger.info(f"Coverage: {timestamped_data.get('coverage_percentage', 0):.1f}% of audio mapped to notes")
            
            return timestamped_data
            
        except Exception as e:
            logger.error(f"❌ Failed to generate timestamp mappings for job {job_id}: {e}")
            return None
    
    async def _save_to_r2_storage(self, job_id: str, structured_notes: str, transcription_result: Dict[str, Any], user_id: Optional[str]):
        """Save notes to R2 storage if available"""
        if r2_storage.is_available():
            try:
                metadata = {
                    "job_id": job_id,
                    "user_id": user_id,
                    "language": transcription_result["language"],
                    "segments_count": len(transcription_result["segments"]),
                    "processing_date": datetime.now().isoformat(),
                    "file_type": "video_transcription"
                }
                
                r2_key = r2_storage.save_notes(job_id, structured_notes, metadata, user_id)
                if r2_key:
                    logger.info(f"✅ Notes saved to R2 storage: {r2_key}")
                else:
                    logger.warning("⚠️ Failed to save notes to R2 storage")
            except Exception as e:
                logger.error(f"❌ R2 storage error: {e}")
    
    async def _create_auto_bookmarks(self, job_id: str, structured_notes: str, user_id: str):
        """Auto-bookmarking disabled - bookmarks should only be created when users manually bookmark sections"""
        # Note: Auto-bookmarking has been disabled to ensure bookmarks are intentional user actions
        # rather than automatic system behavior. Users can manually bookmark sections they find important.
        logger.info(f"ℹ️ Auto-bookmarking disabled for job {job_id} - bookmarks will be created only when users manually bookmark sections")
    
    async def _increment_user_statistics(self, user_id: str, stats_updates: dict):
        """Helper function to increment user statistics without blocking main processing"""
        if not user_id or not self.db:
            return
        
        try:
            from firebase_admin import firestore
            
            # Get document reference
            doc_ref = self.db.collection("user_statistics").document(user_id)
            
            # Use Firestore transaction for atomic updates
            @firestore.transactional
            def update_stats(transaction, doc_ref, updates):
                doc = doc_ref.get(transaction=transaction)
                if doc.exists:
                    current_data = doc.to_dict()
                    new_data = {'updated_at': datetime.now(timezone.utc)}
                    
                    for field, increment in updates.items():
                        current_value = current_data.get(field, 0)
                        new_data[field] = current_value + increment
                    
                    transaction.update(doc_ref, new_data)
                else:
                    # Create new document if it doesn't exist
                    initial_stats = {
                        'user_id': user_id,
                        'created_at': datetime.now(timezone.utc),
                        'updated_at': datetime.now(timezone.utc)
                    }
                    initial_stats.update(updates)
                    transaction.set(doc_ref, initial_stats)
            
            # Execute transaction
            transaction = self.db.transaction()
            update_stats(transaction, doc_ref, stats_updates)
            
            logger.info(f"✅ Updated user statistics for {user_id}: {stats_updates}")
            
        except Exception as e:
            logger.warning(f"Failed to update user statistics for {user_id}: {e}")
    
    def _extract_title_from_notes(self, notes_content: str) -> Optional[str]:
        """Extract title from notes content"""
        if not notes_content:
            return None
        
        lines = notes_content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
            elif line.startswith('## ') and not line.startswith('### '):
                return line[3:].strip()
        
        # Fallback: use first non-empty line
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                return line[:50] + ('...' if len(line) > 50 else '')
        
        return None

# Global instance - will be initialized with db in main.py
processing_service = ProcessingService()