import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_mindmap(data):
    """Generate a beautiful, organized jsMind mind map from Phi-3 educational data with intelligent structure"""
    try:
        logger.info("Generating beautiful jsMind mind map from Phi-3 educational summary with intelligent structure")
        
        # Extract main topic
        main_topic = data.get("title", "Educational Content")
        
        # Create jsMind format with proper metadata
        mindmap = {
            "meta": {
                "name": f"mindmap_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "author": "QuickMind AI - Phi3 Educational Assistant",
                "version": "1.0",
                "created": datetime.now().isoformat(),
                "processing_model": data.get("processing_model", "phi3-ollama"),
                "transcript_stats": {
                    "length": data.get("transcript_length", 0),
                    "segments": data.get("segment_count", 0),
                    "sections": data.get("section_count", 0),
                    "duration": data.get("total_duration", 0)
                }
            },
            "format": "node_tree",
            "data": {
                "id": "root",
                "topic": f"🎓 {main_topic}",
                "backgroundColor": "#4A90E2",
                "foregroundColor": "#FFFFFF",
                "children": []
            }
        }
        
        # First, check if we have intelligent sections from our new segmentation
        if "sections_info" in data and data["sections_info"]:
            # Use intelligent sections for better organization
            mindmap["data"]["children"] = _create_intelligent_structure(data)
        else:
            # Fallback to traditional structure
            mindmap["data"]["children"] = _create_traditional_structure(data)
        
        # Ensure we have content, add fallback if needed
        if not mindmap["data"]["children"]:
            mindmap["data"]["children"] = _create_fallback_structure(data)
        
        # Add metadata footer
        _add_metadata_node(mindmap, data)
        
        logger.info(f"Beautiful jsMind educational mind map generated with {len(mindmap['data']['children'])} main branches")
        return mindmap
        
    except Exception as e:
        logger.error(f"Error generating jsMind mind map: {e}")
        return _create_error_mindmap(data, str(e))

def _create_intelligent_structure(data):
    """Create beautiful mind map structure using intelligent transcript sections"""
    children = []
    
    # Color scheme for different section types
    colors = {
        'definition': {'bg': '#E8F5E8', 'fg': '#2E7D32'},      # Green for definitions
        'example': {'bg': '#FFF3E0', 'fg': '#F57C00'},        # Orange for examples  
        'process': {'bg': '#E3F2FD', 'fg': '#1976D2'},        # Blue for processes
        'explanation': {'bg': '#F3E5F5', 'fg': '#7B1FA2'},    # Purple for explanations
        'question': {'bg': '#FFEBEE', 'fg': '#C62828'},       # Red for questions
        'summary': {'bg': '#F1F8E9', 'fg': '#558B2F'},        # Light green for summaries
        'default': {'bg': '#F5F5F5', 'fg': '#424242'}         # Gray for others
    }
    
    # 1. OVERVIEW SECTION (left side)
    overview_children = []
    
    # Add summary if available
    if data.get("summary"):
        summary_parts = _split_text_smart(data["summary"], 120)
        summary_children = []
        for i, part in enumerate(summary_parts[:3]):  # Max 3 parts
            summary_children.append({
                "id": f"summary_part_{i}",
                "topic": part,
                "backgroundColor": "#E8F6F3",
                "foregroundColor": "#00695C"
            })
        
        overview_children.append({
            "id": "summary",
            "topic": "📋 Overview",
            "direction": "left",
            "backgroundColor": "#4DB6AC",
            "foregroundColor": "#FFFFFF",
            "children": summary_children
        })
    
    # Add learning objectives
    objectives_children = []
    if data.get("key_points"):
        objectives_children.append({
            "id": "obj_concepts",
            "topic": f"🎯 Master {len(data['key_points'])} key concepts"
        })
    if data.get("definitions"):
        objectives_children.append({
            "id": "obj_terms",
            "topic": f"📚 Learn {len(data['definitions'])} important terms"
        })
    if data.get("examples"):
        objectives_children.append({
            "id": "obj_examples", 
            "topic": f"💡 Explore {len(data['examples'])} examples"
        })
    
    if objectives_children:
        overview_children.append({
            "id": "objectives",
            "topic": "🎯 Learning Goals",
            "direction": "left",
            "backgroundColor": "#81C784",
            "foregroundColor": "#FFFFFF",
            "children": objectives_children
        })
    
    # 2. INTELLIGENT SECTIONS (right side - main content)
    sections_children = []
    sections_info = data.get("sections_info", [])
    
    for i, section in enumerate(sections_info[:8]):  # Limit to 8 sections for readability
        section_type = section.get('type', 'default')
        section_colors = colors.get(section_type, colors['default'])
        
        # Get type-specific emoji
        type_emoji = {
            'definition': '📖',
            'example': '💡', 
            'process': '⚙️',
            'explanation': '🧠',
            'question': '❓',
            'summary': '📝',
            'default': '📄'
        }.get(section_type, '📄')
        
        # Create section children
        section_children = []
        
        # Add duration info
        section_children.append({
            "id": f"section_duration_{i}",
            "topic": f"⏱️ {section['duration']:.1f}s",
            "backgroundColor": "#ECEFF1",
            "foregroundColor": "#455A64"
        })
        
        # Add key concepts
        if section.get('concepts'):
            concepts_text = "🔑 " + ", ".join(section['concepts'][:3])
            if len(concepts_text) > 80:
                concepts_text = concepts_text[:77] + "..."
            section_children.append({
                "id": f"section_concepts_{i}",
                "topic": concepts_text,
                "backgroundColor": section_colors['bg'],
                "foregroundColor": section_colors['fg']
            })
        
        # Create main section node
        section_title = section.get('title', f'Section {i+1}')
        if len(section_title) > 50:
            section_title = section_title[:47] + "..."
            
        sections_children.append({
            "id": f"intelligent_section_{i}",
            "topic": f"{type_emoji} {section_title}",
            "direction": "right",
            "backgroundColor": section_colors['bg'],
            "foregroundColor": section_colors['fg'],
            "children": section_children
        })
    
    # 3. KNOWLEDGE BASE (right side - structured content)
    knowledge_children = []
    
    # Definitions with beautiful structure
    if data.get("definitions"):
        def_children = []
        for i, definition in enumerate(data["definitions"][:6]):
            if isinstance(definition, dict):
                term = definition.get("term", f"Term {i+1}")
                def_text = definition.get("definition", "")
                def_children.append({
                    "id": f"def_{i}",
                    "topic": f"🏷️ {term}",
                    "backgroundColor": "#E8F5E8",
                    "foregroundColor": "#2E7D32",
                    "children": [{
                        "id": f"def_text_{i}",
                        "topic": _truncate_text(def_text, 100),
                        "backgroundColor": "#F1F8E9",
                        "foregroundColor": "#33691E"
                    }] if def_text else []
                })
            else:
                def_children.append({
                    "id": f"def_{i}",
                    "topic": f"📖 {_truncate_text(str(definition), 80)}",
                    "backgroundColor": "#E8F5E8",
                    "foregroundColor": "#2E7D32"
                })
        
        knowledge_children.append({
            "id": "definitions",
            "topic": "📚 Key Definitions",
            "direction": "right",
            "backgroundColor": "#4CAF50",
            "foregroundColor": "#FFFFFF",
            "children": def_children
        })
    
    # Examples with visual appeal
    if data.get("examples"):
        example_children = []
        for i, example in enumerate(data["examples"][:5]):
            example_children.append({
                "id": f"example_{i}",
                "topic": f"💡 {_truncate_text(str(example), 90)}",
                "backgroundColor": "#FFF8E1",
                "foregroundColor": "#F57C00"
            })
        
        knowledge_children.append({
            "id": "examples",
            "topic": "🎯 Examples",
            "direction": "right", 
            "backgroundColor": "#FF9800",
            "foregroundColor": "#FFFFFF",
            "children": example_children
        })
    
    # Key points with hierarchy
    if data.get("key_points"):
        point_children = []
        for i, point in enumerate(data["key_points"][:6]):
            point_children.append({
                "id": f"key_point_{i}",
                "topic": f"🔑 {_truncate_text(str(point), 85)}",
                "backgroundColor": "#E3F2FD",
                "foregroundColor": "#1976D2"
            })
        
        knowledge_children.append({
            "id": "key_points",
            "topic": "🔑 Key Points",
            "direction": "right",
            "backgroundColor": "#2196F3",
            "foregroundColor": "#FFFFFF",
            "children": point_children
        })
    
    # 4. ASSESSMENT (left side)
    assessment_children = []
    
    # Study questions
    if data.get("questions"):
        question_children = []
        for i, question in enumerate(data["questions"][:5]):
            question_children.append({
                "id": f"question_{i}",
                "topic": f"❓ {_truncate_text(str(question), 85)}",
                "backgroundColor": "#FFEBEE",
                "foregroundColor": "#C62828"
            })
        
        assessment_children.append({
            "id": "questions",
            "topic": "❓ Study Questions",
            "direction": "left",
            "backgroundColor": "#F44336",
            "foregroundColor": "#FFFFFF",
            "children": question_children
        })
    
    # Common mistakes
    if data.get("common_mistakes"):
        mistake_children = []
        for i, mistake in enumerate(data["common_mistakes"][:4]):
            mistake_children.append({
                "id": f"mistake_{i}",
                "topic": f"⚠️ {_truncate_text(str(mistake), 85)}",
                "backgroundColor": "#FFF3E0",
                "foregroundColor": "#E65100"
            })
        
        assessment_children.append({
            "id": "mistakes",
            "topic": "⚠️ Common Mistakes", 
            "direction": "left",
            "backgroundColor": "#FF9800",
            "foregroundColor": "#FFFFFF",
            "children": mistake_children
        })
    
    # Combine all sections
    result = []
    result.extend(overview_children)
    result.extend(assessment_children) 
    if sections_children:
        result.append({
            "id": "intelligent_sections",
            "topic": "🧠 Content Sections",
            "direction": "right",
            "backgroundColor": "#9C27B0",
            "foregroundColor": "#FFFFFF", 
            "children": sections_children
        })
    result.extend(knowledge_children)
    
    return result

def _create_traditional_structure(data):
    """Create comprehensive mind map structure with all available data"""
    children = []
    
    # 1. OVERVIEW SECTION (left side)
    if data.get("summary"):
        children.append({
            "id": "summary",
            "topic": "📋 Overview",
            "direction": "left",
            "backgroundColor": "#4DB6AC",
            "foregroundColor": "#FFFFFF",
            "children": [{
                "id": "summary_content",
                "topic": _truncate_text(data["summary"], 150),
                "backgroundColor": "#E8F6F3",
                "foregroundColor": "#00695C"
            }]
        })
    
    # 2. KEY CONCEPTS (right side)
    if data.get("key_concepts"):
        concept_children = []
        for i, concept in enumerate(data["key_concepts"][:6]):
            concept_children.append({
                "id": f"concept_{i}",
                "topic": f"🧠 {_truncate_text(str(concept), 80)}",
                "backgroundColor": "#E3F2FD",
                "foregroundColor": "#1976D2"
            })
        
        children.append({
            "id": "key_concepts",
            "topic": "🧠 Key Concepts",
            "direction": "right",
            "backgroundColor": "#2196F3",
            "foregroundColor": "#FFFFFF",
            "children": concept_children
        })
    
    # 3. DEFINITIONS (right side)
    if data.get("definitions"):
        def_children = []
        definitions = data["definitions"]
        if isinstance(definitions, dict):
            for i, (term, definition) in enumerate(list(definitions.items())[:5]):
                def_children.append({
                    "id": f"def_{i}",
                    "topic": f"📖 {term}",
                    "backgroundColor": "#E8F5E8",
                    "foregroundColor": "#2E7D32",
                    "children": [{
                        "id": f"def_text_{i}",
                        "topic": _truncate_text(str(definition), 120),
                        "backgroundColor": "#F1F8E9",
                        "foregroundColor": "#33691E"
                    }]
                })
        
        if def_children:
            children.append({
                "id": "definitions",
                "topic": "📚 Definitions",
                "direction": "right",
                "backgroundColor": "#4CAF50",
                "foregroundColor": "#FFFFFF",
                "children": def_children
            })
    
    # 4. IMPORTANT FACTS (right side)
    if data.get("important_facts"):
        fact_children = []
        for i, fact in enumerate(data["important_facts"][:5]):
            fact_children.append({
                "id": f"fact_{i}",
                "topic": f"📌 {_truncate_text(str(fact), 90)}",
                "backgroundColor": "#FFF3E0",
                "foregroundColor": "#E65100"
            })
        
        children.append({
            "id": "important_facts",
            "topic": "📌 Important Facts",
            "direction": "right",
            "backgroundColor": "#FF9800",
            "foregroundColor": "#FFFFFF",
            "children": fact_children
        })
    
    # 5. EXAMPLES (right side)
    if data.get("examples"):
        example_children = []
        for i, example in enumerate(data["examples"][:4]):
            example_children.append({
                "id": f"example_{i}",
                "topic": f"💡 {_truncate_text(str(example), 85)}",
                "backgroundColor": "#FFF8E1",
                "foregroundColor": "#F57C00"
            })
        
        children.append({
            "id": "examples",
            "topic": "💡 Examples",
            "direction": "right",
            "backgroundColor": "#FF9800",
            "foregroundColor": "#FFFFFF",
            "children": example_children
        })
    
    # 6. PROCESSES (left side)
    if data.get("processes"):
        process_children = []
        for i, process in enumerate(data["processes"][:3]):
            process_children.append({
                "id": f"process_{i}",
                "topic": f"⚙️ {_truncate_text(str(process), 90)}",
                "backgroundColor": "#E8EAF6",
                "foregroundColor": "#3F51B5"
            })
        
        children.append({
            "id": "processes",
            "topic": "⚙️ Processes",
            "direction": "left",
            "backgroundColor": "#3F51B5",
            "foregroundColor": "#FFFFFF",
            "children": process_children
        })
    
    # 7. APPLICATIONS (left side)
    if data.get("applications"):
        app_children = []
        for i, application in enumerate(data["applications"][:3]):
            app_children.append({
                "id": f"app_{i}",
                "topic": f"🎯 {_truncate_text(str(application), 85)}",
                "backgroundColor": "#F3E5F5",
                "foregroundColor": "#7B1FA2"
            })
        
        children.append({
            "id": "applications",
            "topic": "🎯 Applications",
            "direction": "left",
            "backgroundColor": "#9C27B0",
            "foregroundColor": "#FFFFFF",
            "children": app_children
        })
    
    # 8. LEARNING OBJECTIVES (left side)
    if data.get("learning_objectives"):
        obj_children = []
        for i, objective in enumerate(data["learning_objectives"][:4]):
            obj_children.append({
                "id": f"obj_{i}",
                "topic": f"🎓 {_truncate_text(str(objective), 90)}",
                "backgroundColor": "#E0F2F1",
                "foregroundColor": "#00695C"
            })
        
        children.append({
            "id": "learning_objectives",
            "topic": "🎓 Learning Goals",
            "direction": "left",
            "backgroundColor": "#009688",
            "foregroundColor": "#FFFFFF",
            "children": obj_children
        })
    
    # 9. QUIZ QUESTIONS (left side)
    if data.get("quiz_questions"):
        question_children = []
        for i, question in enumerate(data["quiz_questions"][:5]):
            question_children.append({
                "id": f"question_{i}",
                "topic": f"❓ {_truncate_text(str(question), 85)}",
                "backgroundColor": "#FFEBEE",
                "foregroundColor": "#C62828"
            })
        
        children.append({
            "id": "quiz_questions",
            "topic": "❓ Study Questions",
            "direction": "left",
            "backgroundColor": "#F44336",
            "foregroundColor": "#FFFFFF",
            "children": question_children
        })
    
    return children

def _create_fallback_structure(data):
    """Create fallback structure when no content is available"""
    return [
        {
            "id": "processed",
            "topic": "✅ Content Analyzed",
            "direction": "right",
            "backgroundColor": "#4CAF50",
            "foregroundColor": "#FFFFFF",
            "children": [
                {
                    "id": "ai_analysis",
                    "topic": "🤖 AI-powered educational content extraction"
                },
                {
                    "id": "model_info",
                    "topic": f"🧠 Processed with {data.get('processing_model', 'Phi-3')}"
                }
            ]
        }
    ]

def _add_metadata_node(mindmap, data):
    """Add metadata information to mind map"""
    metadata_children = []
    
    # Processing info
    metadata_children.append({
        "id": "model",
        "topic": f"🤖 {data.get('processing_model', 'phi3-ollama')}"
    })
    
    # Stats
    if data.get('transcript_length'):
        metadata_children.append({
            "id": "length",
            "topic": f"📄 {data['transcript_length']} chars"
        })
    
    if data.get('section_count'):
        metadata_children.append({
            "id": "sections", 
            "topic": f"🧠 {data['section_count']} sections"
        })
    
    mindmap["data"]["children"].append({
        "id": "metadata",
        "topic": "ℹ️ Processing Info",
        "direction": "left",
        "backgroundColor": "#607D8B",
        "foregroundColor": "#FFFFFF",
        "children": metadata_children
    })

def _create_error_mindmap(data, error_msg):
    """Create error fallback mind map"""
    return {
        "meta": {
            "name": "error_mindmap",
            "author": "QuickMind AI",
            "version": "1.0"
        },
        "format": "node_tree",
        "data": {
            "id": "root",
            "topic": data.get("title", "Educational Content"),
            "backgroundColor": "#F44336",
            "foregroundColor": "#FFFFFF",
            "children": [
                {
                    "id": "error",
                    "topic": "⚠️ Processing Error",
                    "children": [
                        {"id": "msg", "topic": f"Error: {error_msg[:100]}"},
                        {"id": "fallback", "topic": "Using basic content structure"}
                    ]
                }
            ]
        }
    }

def _truncate_text(text, max_length):
    """Intelligently truncate text while preserving meaning"""
    if len(text) <= max_length:
        return text
    
    # Try to break at sentence boundary
    if '. ' in text[:max_length]:
        return text[:text.rfind('. ', 0, max_length) + 1]
    
    # Try to break at word boundary
    if ' ' in text[:max_length]:
        return text[:text.rfind(' ', 0, max_length)] + "..."
    
    # Force truncate
    return text[:max_length-3] + "..."

def _split_text_smart(text, chunk_size):
    """Split text into chunks intelligently"""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    remaining = text
    
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break
        
        # Find best break point
        break_point = chunk_size
        if '. ' in remaining[:chunk_size]:
            break_point = remaining.rfind('. ', 0, chunk_size) + 2
        elif ' ' in remaining[:chunk_size]:
            break_point = remaining.rfind(' ', 0, chunk_size)
        
        chunks.append(remaining[:break_point].strip())
        remaining = remaining[break_point:].strip()
    
    return chunks