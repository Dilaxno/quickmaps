"""
Auto-generated diagram functionality using Groq API for extracting structured logic
and generating Mermaid.js diagrams from learning notes and transcriptions.
"""

import logging
import json
import re
from typing import Optional, Dict, List, Tuple
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, ENABLE_NOTES_GENERATION

logger = logging.getLogger(__name__)

class DiagramGenerator:
    """Generate diagrams from notes and transcriptions using Groq API"""
    
    def __init__(self):
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not set. Diagram generation will be disabled.")
            self.client = None
            self.model = None
        else:
            self.client = Groq(api_key=GROQ_API_KEY)
            self.model = GROQ_MODEL
    
    def is_available(self) -> bool:
        """Check if Groq API is available for diagram generation"""
        return self.client is not None and ENABLE_NOTES_GENERATION
    
    def generate_diagram_from_notes(self, notes: str, diagram_type: str = "flowchart") -> Optional[Dict]:
        """
        Generate diagram from structured notes
        
        Args:
            notes: Structured learning notes
            diagram_type: Type of diagram - "flowchart", "mindmap", "sequence", "process"
            
        Returns:
            Dictionary containing diagram data or None if generation fails
        """
        if not self.is_available():
            logger.warning("Groq API not available. Skipping diagram generation.")
            return None
        
        if not notes or len(notes.strip()) < 100:
            logger.warning("Notes too short for diagram generation")
            return None
        
        try:
            # Generate diagram directly from notes using the new approach
            mermaid_syntax = self._generate_diagram_direct(notes, diagram_type)
            if not mermaid_syntax:
                return None
            
            # Create comprehensive diagram data
            diagram_data = {
                "type": diagram_type,
                "mermaid_syntax": mermaid_syntax,
                "structured_data": None,  # Not needed with direct approach
                "title": self._extract_title_from_notes(notes),
                "description": f"Auto-generated {diagram_type} diagram from learning notes",
                "rendering_options": self._get_rendering_options(diagram_type)
            }
            
            return diagram_data
            
        except Exception as e:
            logger.error(f"Error generating diagram from notes: {e}")
            return None
    
    def generate_process_diagram(self, content: str) -> Optional[Dict]:
        """Generate process/workflow diagram from content"""
        return self.generate_diagram_from_notes(content, "flowchart")
    
    def generate_mindmap_diagram(self, content: str) -> Optional[Dict]:
        """Generate mind map diagram from content"""
        result = self.generate_diagram_from_notes(content, "mindmap")
        # If mindmap fails, fallback to a simple graph representation
        if not result:
            logger.info("Mindmap generation failed, trying graph fallback")
            result = self.generate_diagram_from_notes(content, "graph")
            if result:
                result["type"] = "mindmap"  # Keep the original type for UI
                result["description"] = "Mind map diagram (rendered as graph due to compatibility)"
        return result
    
    def generate_sequence_diagram(self, content: str) -> Optional[Dict]:
        """Generate sequence diagram from content"""
        return self.generate_diagram_from_notes(content, "sequence")
    
    def generate_concept_map(self, content: str) -> Optional[Dict]:
        """Generate concept map diagram from content"""
        return self.generate_diagram_from_notes(content, "graph")
    
    def _generate_diagram_direct(self, content: str, diagram_type: str) -> Optional[str]:
        """Generate diagram directly from content using the new strict approach"""
        try:
            prompt = self._get_extraction_prompt(content, diagram_type)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise diagram generation engine. You create diagrams that exactly match the provided notes without adding any information not explicitly stated. You output only clean diagram syntax with no explanations or commentary."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Very low temperature for precision
                max_tokens=1500,
                top_p=0.7
            )
            
            result = response.choices[0].message.content.strip()
            
            # Clean the result to ensure it's only diagram syntax
            cleaned_result = self._clean_diagram_output(result)
            
            # Validate the syntax before returning
            if self._validate_diagram_syntax(cleaned_result, diagram_type):
                return cleaned_result
            else:
                logger.warning(f"Generated {diagram_type} syntax failed validation")
                return None
                
        except Exception as e:
            logger.error(f"Error generating diagram directly: {e}")
            return None
    
    def _clean_diagram_output(self, output: str) -> str:
        """Clean the diagram output to ensure it contains only diagram syntax"""
        # Remove markdown code blocks if present
        output = re.sub(r'```\w*\n?', '', output)
        output = re.sub(r'```', '', output)
        
        # Remove any explanatory text before or after the diagram
        lines = output.split('\n')
        diagram_lines = []
        diagram_started = False
        
        for line in lines:
            line = line.strip()
            if not line:
                if diagram_started:
                    diagram_lines.append('')
                continue
                
            # Check if this line starts a diagram
            if (line.startswith('flowchart') or line.startswith('graph') or 
                line.startswith('mindmap') or line.startswith('sequenceDiagram')):
                diagram_started = True
                diagram_lines.append(line)
            elif diagram_started:
                # If we're in a diagram, keep adding lines
                diagram_lines.append(line)
            # Skip any explanatory text before the diagram starts
        
        result = '\n'.join(diagram_lines).strip()
        
        # Apply diagram-specific cleaning
        if result.startswith('mindmap'):
            result = self._clean_mindmap_syntax(result)
        elif result.startswith('graph'):
            result = self._clean_graph_syntax(result)
        
        return result
    
    def _clean_mindmap_syntax(self, syntax: str) -> str:
        """Clean mindmap syntax to ensure compatibility"""
        lines = syntax.split('\n')
        cleaned_lines = []
        
        for line in lines:
            if line.strip().startswith('mindmap'):
                cleaned_lines.append(line.strip())
            elif line.strip().startswith('root(('):
                # Ensure proper root syntax
                cleaned_lines.append('  ' + line.strip())
            elif line.strip() and not line.strip().startswith('mindmap'):
                # Clean branch names - remove problematic characters
                cleaned_line = line.strip()
                # Remove brackets, parentheses, and other special chars from branch names
                cleaned_line = re.sub(r'[^\w\s\-]', '', cleaned_line)
                # Ensure proper indentation based on content
                if cleaned_line and not cleaned_line.startswith('root'):
                    # Count original indentation to preserve hierarchy
                    original_indent = len(line) - len(line.lstrip())
                    if original_indent == 0:
                        cleaned_lines.append('    ' + cleaned_line)  # Main branch
                    else:
                        cleaned_lines.append('      ' + cleaned_line)  # Sub-branch
        
        return '\n'.join(cleaned_lines)
    
    def _clean_graph_syntax(self, syntax: str) -> str:
        """Clean graph syntax to ensure compatibility"""
        lines = syntax.split('\n')
        cleaned_lines = []
        
        for line in lines:
            if line.strip().startswith('graph'):
                cleaned_lines.append(line.strip())
            elif line.strip() and '-->' in line.strip():
                # Clean node connections
                cleaned_line = line.strip()
                # Ensure proper indentation
                cleaned_lines.append('    ' + cleaned_line)
            elif line.strip():
                # Other graph elements
                cleaned_lines.append('    ' + line.strip())
        
        return '\n'.join(cleaned_lines)
    
    def _validate_diagram_syntax(self, syntax: str, diagram_type: str) -> bool:
        """Validate diagram syntax for basic correctness"""
        if not syntax or not syntax.strip():
            return False
        
        lines = syntax.strip().split('\n')
        if not lines:
            return False
        
        first_line = lines[0].strip()
        
        # Check if it starts with the expected diagram type
        if diagram_type == "mindmap":
            if not first_line.startswith('mindmap'):
                return False
            # Check for root element
            has_root = any('root((' in line for line in lines)
            return has_root
        
        elif diagram_type == "flowchart":
            if not (first_line.startswith('flowchart') or first_line.startswith('graph')):
                return False
            # Check for at least one connection
            has_connection = any('-->' in line for line in lines)
            return has_connection
        
        elif diagram_type == "sequence":
            if not first_line.startswith('sequenceDiagram'):
                return False
            # Check for at least one message
            has_message = any('->>' in line or '-->' in line for line in lines)
            return has_message
        
        elif diagram_type == "graph":
            if not first_line.startswith('graph'):
                return False
            # Check for at least one connection
            has_connection = any('-->' in line for line in lines)
            return has_connection
        
        return True
    
    # Removed _generate_mermaid_syntax method as we now use direct generation
    
    def _get_extraction_prompt(self, content: str, diagram_type: str) -> str:
        """Get prompt for extracting structured logic based on diagram type"""
        
        # Use the new direct diagram generation approach
        return f"""You are a diagram generation engine.
INPUT: A set of notes that summarize a video.

Notes:
{content[:4000]}

TASK:
1. Read the notes carefully.
2. Identify only the processes, sequences, relationships, and hierarchies explicitly mentioned in the notes.
3. Generate a {diagram_type} diagram.
4. Do NOT add any information that is not explicitly stated in the notes.
5. Preserve all terminology exactly as it appears in the notes.
6. Maintain logical accuracy: ensure all steps, nodes, and connections match the source text.

OUTPUT FORMAT:
- Respond only with a valid {diagram_type} diagram in the specified syntax.
- Do not include any explanations, summaries, or commentary.
- Do not wrap the diagram in extra text — output diagram code only.

STRICTNESS RULES:
- If the notes are incomplete, leave gaps in the diagram rather than guessing.
- Do not infer events, steps, or relationships that are not 100% supported by the notes.
- The diagram must be directly mappable back to the exact wording in the notes.

{self._get_diagram_specific_instructions(diagram_type)}

Generate the {diagram_type} now:"""
    
    def _get_diagram_specific_instructions(self, diagram_type: str) -> str:
        """Get specific instructions for each diagram type"""
        
        if diagram_type == "flowchart":
            return """
FLOWCHART SYNTAX REQUIREMENTS:
- Use Mermaid.js flowchart syntax
- Start with "flowchart TD" or "graph TD"
- Use appropriate node shapes: [ ] for processes, { } for decisions, (( )) for start/end
- Arrow syntax: Use --> for connections, -->|label| for labeled connections
- Keep node labels clear and concise
- Maximum 10-12 nodes for readability

EXAMPLE:
flowchart TD
    A[Start Process] --> B{Decision Point?}
    B -->|Yes| C[Action A]
    B -->|No| D[Action B]
    C --> E[End]
    D --> E"""
        
        elif diagram_type == "mindmap":
            return """
MINDMAP SYNTAX REQUIREMENTS:
- Use Mermaid.js mindmap syntax (compatible with v10.9+)
- Start with "mindmap"
- Use proper indentation (2 spaces per level)
- Central topic in double parentheses: root((Central Topic))
- Branch names should be simple text without special characters
- Keep branch names concise and clear
- Maximum 6-8 main branches for readability
- Avoid parentheses, brackets, or special symbols in branch names

EXAMPLE:
mindmap
  root((Machine Learning))
    Supervised Learning
      Classification
      Regression
    Unsupervised Learning
      Clustering
      Dimensionality Reduction
    Deep Learning
      Neural Networks
      CNN"""
        
        elif diagram_type == "sequence":
            return """
SEQUENCE DIAGRAM SYNTAX REQUIREMENTS:
- Use Mermaid.js sequence diagram syntax
- Start with "sequenceDiagram"
- Define participants clearly
- Use ->> for synchronous messages, -->> for asynchronous
- Keep interactions concise and clear

EXAMPLE:
sequenceDiagram
    participant A as Actor 1
    participant B as Actor 2
    A->>B: Message 1
    B-->>A: Response
    A->>B: Follow-up"""
        
        else:  # concept graph
            return """
CONCEPT GRAPH SYNTAX REQUIREMENTS:
- Use Mermaid.js graph syntax (compatible with v10.9+)
- Start with "graph TD" (top-down) or "graph LR" (left-right)
- Use [ ] for rectangular nodes, ( ) for rounded nodes
- Node IDs should be simple (A, B, C, etc.)
- Show meaningful relationships with labeled arrows
- Use -->|label| for labeled connections
- Keep node labels concise and avoid special characters
- Maximum 8-10 nodes for readability

EXAMPLE:
graph TD
    A[Machine Learning] -->|uses| B[Data]
    A --> C[Algorithms]
    B -->|processed by| D[Models]
    C -->|creates| D
    D -->|produces| E[Predictions]"""
    
    # Removed old methods - using direct generation approach now
    
    # Removed _clean_mermaid_syntax - using _clean_diagram_output instead
    
    def _fix_mermaid_syntax_issues(self, syntax: str) -> str:
        """Fix common Mermaid syntax issues"""
        # Fix arrow syntax: -->|label|> should be -->|label|
        syntax = re.sub(r'-->\|([^|]+)\|>', r'-->|\1|', syntax)
        
        # Fix node labels with parentheses - wrap in quotes if not already quoted
        def fix_node_labels(match):
            full_match = match.group(0)
            node_id = match.group(1)
            label = match.group(2)
            
            # If label contains parentheses and isn't already quoted, add quotes
            if '(' in label and ')' in label and not (label.startswith('"') and label.endswith('"')):
                return f'{node_id}["{label}"]'
            return full_match
        
        # Apply the fix to node definitions like: node_id[Label with (parentheses)]
        syntax = re.sub(r'(\w+)\[([^\]]+)\]', fix_node_labels, syntax)
        
        # Remove extra whitespace and ensure proper indentation
        lines = syntax.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line:
                # Add consistent indentation for non-header lines
                if not any(line.startswith(keyword) for keyword in ['graph', 'flowchart', 'sequenceDiagram', 'mindmap']):
                    line = '    ' + line
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _extract_title_from_notes(self, notes: str) -> str:
        """Extract title from notes"""
        lines = notes.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
            elif line.startswith('## '):
                return line[3:].strip()
        
        return "Learning Diagram"
    
    def _get_rendering_options(self, diagram_type: str) -> Dict:
        """Get rendering options for different diagram types"""
        base_options = {
            "theme": "default",
            "background": "white",
            "primaryColor": "#4f46e5",
            "primaryTextColor": "#1f2937",
            "primaryBorderColor": "#6366f1",
            "lineColor": "#6b7280",
            "secondaryColor": "#f3f4f6",
            "tertiaryColor": "#ffffff"
        }
        
        if diagram_type == "flowchart":
            return {
                **base_options,
                "flowchart": {
                    "htmlLabels": True,
                    "curve": "basis",
                    "padding": 10
                }
            }
        elif diagram_type == "mindmap":
            return {
                **base_options,
                "mindmap": {
                    "padding": 10,
                    "maxNodeSizeX": 200,
                    "maxNodeSizeY": 100
                }
            }
        elif diagram_type == "sequence":
            return {
                **base_options,
                "sequence": {
                    "diagramMarginX": 50,
                    "diagramMarginY": 10,
                    "actorMargin": 50,
                    "width": 150,
                    "height": 65,
                    "boxMargin": 10,
                    "boxTextMargin": 5,
                    "noteMargin": 10,
                    "messageMargin": 35
                }
            }
        else:
            return base_options
    
    def generate_html_with_diagram(self, diagram_data: Dict, include_libraries: bool = True) -> str:
        """Generate HTML page with embedded diagram and rendering libraries"""
        if not diagram_data:
            return None
        
        mermaid_syntax = diagram_data.get("mermaid_syntax", "")
        title = diagram_data.get("title", "Diagram")
        description = diagram_data.get("description", "")
        diagram_type = diagram_data.get("type", "flowchart")
        
        # Library CDN links
        libraries = ""
        if include_libraries:
            libraries = """
    <!-- Mermaid.js -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
    
    <!-- D3.js for advanced interactions -->
    <script src="https://d3js.org/d3.v7.min.js"></script>
    
    <!-- Dagre-D3 for layout algorithms -->
    <script src="https://cdn.jsdelivr.net/npm/dagre-d3@0.6.4/dist/dagre-d3.min.js"></script>
    
    <!-- Excalidraw integration (optional) -->
    <script src="https://unpkg.com/@excalidraw/excalidraw@0.17.0/dist/excalidraw.production.min.js"></script>
"""
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f8fafc;
            color: #1f2937;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: white;
            padding: 24px;
            text-align: center;
        }}
        
        .header h1 {{
            margin: 0;
            font-size: 2rem;
            font-weight: 700;
        }}
        
        .header p {{
            margin: 8px 0 0 0;
            opacity: 0.9;
            font-size: 1.1rem;
        }}
        
        .diagram-container {{
            padding: 32px;
            text-align: center;
            min-height: 400px;
        }}
        
        .mermaid {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }}
        
        .controls {{
            margin: 20px 0;
            display: flex;
            justify-content: center;
            gap: 12px;
            flex-wrap: wrap;
        }}
        
        .btn {{
            background: #4f46e5;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: background-color 0.2s;
        }}
        
        .btn:hover {{
            background: #4338ca;
        }}
        
        .btn-secondary {{
            background: #6b7280;
        }}
        
        .btn-secondary:hover {{
            background: #4b5563;
        }}
        
        .info-panel {{
            background: #f1f5f9;
            border-left: 4px solid #4f46e5;
            padding: 16px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
        }}
        
        .info-panel h3 {{
            margin: 0 0 8px 0;
            color: #4f46e5;
        }}
        
        .footer {{
            background: #f8fafc;
            padding: 16px 24px;
            text-align: center;
            color: #6b7280;
            font-size: 14px;
        }}
        
        @media (max-width: 768px) {{
            .container {{
                margin: 10px;
                border-radius: 8px;
            }}
            
            .diagram-container {{
                padding: 16px;
            }}
            
            .header {{
                padding: 16px;
            }}
            
            .header h1 {{
                font-size: 1.5rem;
            }}
        }}
    </style>
    {libraries}
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p>{description}</p>
        </div>
        
        <div class="diagram-container">
            <div class="controls">
                <button class="btn" onclick="zoomIn()">Zoom In</button>
                <button class="btn" onclick="zoomOut()">Zoom Out</button>
                <button class="btn" onclick="resetZoom()">Reset Zoom</button>
                <button class="btn btn-secondary" onclick="downloadSVG()">Download SVG</button>
                <button class="btn btn-secondary" onclick="downloadPNG()">Download PNG</button>
            </div>
            
            <div class="info-panel">
                <h3>Diagram Type: {diagram_type.title()}</h3>
                <p>This diagram was automatically generated from your learning content using AI analysis.</p>
            </div>
            
            <div class="mermaid" id="diagram">
{mermaid_syntax}
            </div>
        </div>
        
        <div class="footer">
            <p>Generated with Mermaid.js, D3.js, and Dagre-D3 • Auto-created from learning notes</p>
        </div>
    </div>

    <script>
        // Initialize Mermaid
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            flowchart: {{
                htmlLabels: true,
                curve: 'basis'
            }},
            sequence: {{
                diagramMarginX: 50,
                diagramMarginY: 10,
                actorMargin: 50,
                width: 150,
                height: 65
            }},
            mindmap: {{
                padding: 10,
                maxNodeSizeX: 200,
                maxNodeSizeY: 100
            }}
        }});
        
        let currentZoom = 1;
        
        function zoomIn() {{
            currentZoom += 0.2;
            applyZoom();
        }}
        
        function zoomOut() {{
            currentZoom = Math.max(0.2, currentZoom - 0.2);
            applyZoom();
        }}
        
        function resetZoom() {{
            currentZoom = 1;
            applyZoom();
        }}
        
        function applyZoom() {{
            const diagram = document.getElementById('diagram');
            diagram.style.transform = `scale(${{currentZoom}})`;
            diagram.style.transformOrigin = 'center';
        }}
        
        function downloadSVG() {{
            const svg = document.querySelector('#diagram svg');
            if (svg) {{
                const svgData = new XMLSerializer().serializeToString(svg);
                const svgBlob = new Blob([svgData], {{type: 'image/svg+xml;charset=utf-8'}});
                const svgUrl = URL.createObjectURL(svgBlob);
                const downloadLink = document.createElement('a');
                downloadLink.href = svgUrl;
                downloadLink.download = '{title.replace(" ", "_")}_diagram.svg';
                document.body.appendChild(downloadLink);
                downloadLink.click();
                document.body.removeChild(downloadLink);
            }}
        }}
        
        function downloadPNG() {{
            const svg = document.querySelector('#diagram svg');
            if (svg) {{
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                const data = new XMLSerializer().serializeToString(svg);
                const DOMURL = window.URL || window.webkitURL || window;
                const img = new Image();
                const svgBlob = new Blob([data], {{type: 'image/svg+xml;charset=utf-8'}});
                const url = DOMURL.createObjectURL(svgBlob);
                
                img.onload = function() {{
                    canvas.width = img.width;
                    canvas.height = img.height;
                    ctx.drawImage(img, 0, 0);
                    DOMURL.revokeObjectURL(url);
                    
                    const imgURI = canvas.toDataURL('image/png').replace('image/png', 'image/octet-stream');
                    const downloadLink = document.createElement('a');
                    downloadLink.href = imgURI;
                    downloadLink.download = '{title.replace(" ", "_")}_diagram.png';
                    document.body.appendChild(downloadLink);
                    downloadLink.click();
                    document.body.removeChild(downloadLink);
                }};
                
                img.src = url;
            }}
        }}
        
        // Add interactive features
        document.addEventListener('DOMContentLoaded', function() {{
            // Add click handlers for diagram elements
            setTimeout(() => {{
                const diagramElements = document.querySelectorAll('#diagram .node, #diagram .edgePath');
                diagramElements.forEach(element => {{
                    element.style.cursor = 'pointer';
                    element.addEventListener('click', function(e) {{
                        // Highlight clicked element
                        diagramElements.forEach(el => el.style.opacity = '0.5');
                        this.style.opacity = '1';
                        this.style.filter = 'drop-shadow(0 0 8px #4f46e5)';
                        
                        // Reset after 2 seconds
                        setTimeout(() => {{
                            diagramElements.forEach(el => {{
                                el.style.opacity = '1';
                                el.style.filter = 'none';
                            }});
                        }}, 2000);
                    }});
                }});
            }}, 1000);
        }});
    </script>
</body>
</html>"""
        
        return html_content
    
    def save_diagram_html(self, diagram_data: Dict, filename: str = None) -> Optional[str]:
        """Save diagram as HTML file"""
        if not diagram_data:
            return None
        
        html_content = self.generate_html_with_diagram(diagram_data)
        if not html_content:
            return None
        
        if not filename:
            title = diagram_data.get("title", "diagram").replace(" ", "_").lower()
            filename = f"{title}_diagram.html"
        
        try:
            filepath = f"d:\\Quick\\{filename}"
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"Diagram HTML saved to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving diagram HTML: {e}")
            return None

# Global instance
diagram_generator = DiagramGenerator()