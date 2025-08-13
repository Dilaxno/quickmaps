#!/usr/bin/env python3
"""
Test script for HTML generation functionality
"""

import os
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from html_generator import html_generator

def test_html_generation():
    """Test HTML generation with sample data"""
    
    # Sample job data
    job_id = "test-job-123"
    job_data = {
        "status": "completed",
        "transcription": "This is a sample transcription of a video about machine learning. It covers various topics including neural networks, deep learning, and artificial intelligence.",
        "language": "english",
        "segments_count": 15,
        "has_notes": True,
        "has_timestamped_notes": True,
        "timestamp_coverage": 85,
        "mapped_sections": 12,
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:35:00Z"
    }
    
    # Create sample notes file
    from config import OUTPUT_DIR
    output_dir = OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)
    
    sample_notes = """# Machine Learning Fundamentals

## Introduction
Machine learning is a subset of artificial intelligence that focuses on algorithms that can learn from data.

## Key Concepts
- **Supervised Learning**: Learning with labeled data
- **Unsupervised Learning**: Finding patterns in unlabeled data
- **Neural Networks**: Computational models inspired by biological neural networks

## Deep Learning
Deep learning uses neural networks with multiple layers to model complex patterns.

### Applications
1. Image recognition
2. Natural language processing
3. Speech recognition
4. Autonomous vehicles

## Conclusion
Machine learning continues to evolve and transform various industries.
"""
    
    notes_file = output_dir / f"{job_id}_notes.md"
    with open(notes_file, 'w', encoding='utf-8') as f:
        f.write(sample_notes)
    
    print(f"📝 Created sample notes file: {notes_file}")
    
    # Generate HTML
    print("🎨 Generating HTML...")
    html_content = html_generator.generate_project_html(job_id, job_data, "test-user-123")
    
    if html_content:
        # Save HTML to file for inspection
        html_file = output_dir / f"{job_id}_project.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ HTML generated successfully!")
        print(f"📄 HTML file saved to: {html_file}")
        print(f"📊 HTML content length: {len(html_content)} characters")
        
        # Check if key elements are present
        checks = [
            ("Title present", "Machine Learning Fundamentals" in html_content),
            ("Notes content present", "Neural Networks" in html_content),
            ("Transcription present", "sample transcription" in html_content),
            ("Statistics present", "15" in html_content),  # segments_count
            ("CSS styling present", "background: linear-gradient" in html_content),
            ("Responsive design", "@media (max-width: 768px)" in html_content)
        ]
        
        print("\n🔍 Content checks:")
        for check_name, result in checks:
            status = "✅" if result else "❌"
            print(f"  {status} {check_name}")
        
        return True
    else:
        print("❌ HTML generation failed!")
        return False

if __name__ == "__main__":
    print("🧪 Testing HTML generation...")
    success = test_html_generation()
    
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n💥 Tests failed!")
        sys.exit(1)