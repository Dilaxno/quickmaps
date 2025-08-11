"""
Processing Service Module

Handles the main processing workflows for video, audio, and PDF files.
"""

import os
import time
import asyncio
import logging
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
    
    async def process_video_file(self, job_id: str, video_path: str, user_id: Optional[str] = None):
        """
        Process uploaded video file
        
        Args:
            job_id (str): Job ID
            video_path (str): Path to video file
            user_id (str, optional): User ID for credit tracking
        """
        try:
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
    
    async def process_youtube_url(self, job_id: str, url: str, user_id: Optional[str] = None):
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
                str(TEMP_DIR)
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
            job_manager.update_job_progress(job_id, "Extracting text from PDF...")
            
            # Import PDF processor
            from pdf_processor import pdf_processor
            
            # Extract text from PDF
            loop = asyncio.get_event_loop()
            extracted_text = await loop.run_in_executor(
                executor,
                pdf_processor.extract_text_from_pdf,
                pdf_path
            )
            
            if not extracted_text or len(extracted_text.strip()) < 100:
                raise Exception("PDF appears to be empty or contains insufficient text content")
            
            # Save extracted text
            extracted_text_file = OUTPUT_DIR / f"{job_id}_extracted_text.txt"
            file_utils.write_file_safely(str(extracted_text_file), extracted_text)
            
            # Generate structured notes if Groq is available
            structured_notes = None
            if groq_generator.is_available():
                job_manager.update_job_progress(job_id, "Generating structured learning notes...")
                logger.info(f"Generating structured notes for PDF job {job_id}")
                
                structured_notes = await loop.run_in_executor(
                    executor,
                    groq_generator.generate_pdf_notes,
                    extracted_text
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
                        # Don't fail the job, but log the issue
                    else:
                        logger.info(f"✅ Credits deducted successfully for PDF job {job_id}: {credit_result.message}")
                        
                except Exception as credit_error:
                    logger.error(f"❌ Credit deduction error for PDF job {job_id}: {credit_error}")
                    # Don't fail the job due to credit issues
            
            # Set job as completed
            result_data = {
                "extracted_text": extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text,
                "text_length": len(extracted_text),
                "has_notes": structured_notes is not None,
                "notes_preview": structured_notes[:200] + "..." if structured_notes and len(structured_notes) > 200 else structured_notes,
                "processing_time": time.time() - start_time,
                "credits_deducted": user_id and self.db and structured_notes  # Indicate if credits were deducted
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
        """Automatically create bookmarks for important sections of the notes"""
        try:
            import re
            
            # Parse the structured notes to find important sections
            sections_to_bookmark = []
            
            # Split notes into sections (assuming markdown format)
            lines = structured_notes.split('\n')
            current_section = None
            current_content = []
            
            for line in lines:
                # Check for headers (markdown format)
                if line.startswith('#'):
                    # Save previous section if it exists
                    if current_section and current_content:
                        content = '\n'.join(current_content).strip()
                        if content and len(content) > 50:  # Only bookmark substantial content
                            sections_to_bookmark.append({
                                'title': current_section,
                                'content': content[:500],  # Limit content length
                                'section_type': 'auto-generated'
                            })
                    
                    # Start new section
                    current_section = line.strip('#').strip()
                    current_content = []
                else:
                    if line.strip():  # Only add non-empty lines
                        current_content.append(line)
            
            # Don't forget the last section
            if current_section and current_content:
                content = '\n'.join(current_content).strip()
                if content and len(content) > 50:
                    sections_to_bookmark.append({
                        'title': current_section,
                        'content': content[:500],
                        'section_type': 'auto-generated'
                    })
            
            # If no clear sections found, create bookmarks for key concepts
            if not sections_to_bookmark:
                # Look for bullet points or numbered lists that might be key concepts
                key_concepts = []
                for line in lines:
                    line = line.strip()
                    if (line.startswith('•') or line.startswith('-') or line.startswith('*') or 
                        re.match(r'^\d+\.', line)) and len(line) > 30:
                        key_concepts.append(line)
                
                # Group key concepts into bookmarks (max 5 concepts per bookmark)
                for i in range(0, len(key_concepts), 5):
                    concept_group = key_concepts[i:i+5]
                    if concept_group:
                        sections_to_bookmark.append({
                            'title': f'Key Concepts {i//5 + 1}',
                            'content': '\n'.join(concept_group),
                            'section_type': 'key-concepts'
                        })
            
            # Limit to maximum 10 auto-bookmarks to avoid overwhelming the user
            sections_to_bookmark = sections_to_bookmark[:10]
            
            # Create bookmarks using the r2_storage service
            bookmarks_created = 0
            for section in sections_to_bookmark:
                try:
                    section_id = f"auto_{job_id}_{bookmarks_created}"
                    metadata = {
                        'section_type': section['section_type'],
                        'auto_generated': True,
                        'created_from': 'video_processing'
                    }
                    
                    bookmark_key = r2_storage.save_bookmark(
                        user_id=user_id,
                        job_id=job_id,
                        section_id=section_id,
                        title=section['title'],
                        content=section['content'],
                        metadata=metadata
                    )
                    
                    if bookmark_key:
                        bookmarks_created += 1
                        logger.info(f"✅ Auto-bookmark created: {section['title'][:50]}...")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to create bookmark for section '{section['title']}': {e}")
            
            if bookmarks_created > 0:
                logger.info(f"✅ Created {bookmarks_created} auto-bookmarks for job {job_id}")
            else:
                logger.info(f"ℹ️ No auto-bookmarks created for job {job_id}")
                
        except Exception as e:
            logger.error(f"❌ Failed to create auto-bookmarks for job {job_id}: {e}")
    
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

# Global instance - will be initialized with db in main.py
processing_service = ProcessingService()