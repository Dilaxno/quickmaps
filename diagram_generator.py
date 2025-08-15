"""
Auto-generated diagram functionality using Groq API for extracting structured logic
and generating Mermaid.js diagrams from learning notes and transcriptions.

Enhanced with type-specific prompting and validation so different
Mermaid diagram types produce distinct, correct syntax.
"""

import logging
import json
import re
from typing import Optional, Dict, List, Tuple
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, ENABLE_NOTES_GENERATION

logger = logging.getLogger(__name__)

# Supported Mermaid diagram headers for detection/validation
MERMAID_HEADERS = [
    'flowchart',
    'graph',
    'mindmap',
    'sequenceDiagram',
    'classDiagram',
    'stateDiagram',
    'stateDiagram-v2',
    'erDiagram',
    'journey',
    'gantt',
    'pie',
    'gitGraph',
    'timeline',
    'requirementDiagram',
    'quadrantChart',
    'sankey',
]


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

    def _normalize_diagram_type(self, diagram_type: str) -> str:
        """Map incoming diagram type to the exact Mermaid header token."""
        if not diagram_type:
            return 'flowchart'
        dt = str(diagram_type).strip()
        mapping = {
            'flowchart': 'flowchart',
            'graph': 'graph',
            'process': 'flowchart',
            'sequence': 'sequenceDiagram',
            'sequenceDiagram': 'sequenceDiagram',
            'class': 'classDiagram',
            'classDiagram': 'classDiagram',
            'stateDiagram': 'stateDiagram',
            'stateDiagram-v2': 'stateDiagram-v2',
            'er': 'erDiagram',
            'erDiagram': 'erDiagram',
            'journey': 'journey',
            'gantt': 'gantt',
            'pie': 'pie',
            'gitGraph': 'gitGraph',
            'timeline': 'timeline',
            'requirementDiagram': 'requirementDiagram',
            'quadrantChart': 'quadrantChart',
            'sankey': 'sankey',
            'mindmap': 'mindmap',
        }
        # If client passes exact header already, preserve it
        if dt in MERMAID_HEADERS:
            return dt
        return mapping.get(dt, 'flowchart')

    def generate_diagram_from_notes(self, notes: str, diagram_type: str = "flowchart") -> Optional[Dict]:
        """
        Generate diagram from structured notes

        Args:
            notes: Structured learning notes
            diagram_type: Type of diagram requested by client

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
            mermaid_syntax = self._generate_diagram_direct(notes, diagram_type)
            if not mermaid_syntax:
                return None

            normalized_header = self._normalize_diagram_type(diagram_type)

            diagram_data = {
                "type": diagram_type,  # keep original requested type for UI
                "mermaid_syntax": mermaid_syntax,
                "structured_data": None,
                "title": self._extract_title_from_notes(notes),
                "description": f"Auto-generated {diagram_type} diagram from learning notes",
                "rendering_options": self._get_rendering_options(diagram_type)
            }
            logger.info(f"Generated diagram type: requested={diagram_type}, header={normalized_header}")
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
        if not result:
            logger.info("Mindmap generation failed, trying graph fallback")
            result = self.generate_diagram_from_notes(content, "graph")
            if result:
                result["type"] = "mindmap"
                result["description"] = "Mind map diagram (rendered as graph due to compatibility)"
        return result

    def generate_sequence_diagram(self, content: str) -> Optional[Dict]:
        """Generate sequence diagram from content"""
        return self.generate_diagram_from_notes(content, "sequenceDiagram")

    def generate_concept_map(self, content: str) -> Optional[Dict]:
        """Generate concept map diagram from content"""
        return self.generate_diagram_from_notes(content, "graph")

    def _generate_diagram_direct(self, content: str, diagram_type: str) -> Optional[str]:
        """Generate diagram directly from content using strict, type-specific prompts."""
        try:
            header = self._normalize_diagram_type(diagram_type)
            prompt = self._get_extraction_prompt(content, diagram_type, header)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise diagram generation engine. You create Mermaid diagrams that exactly match "
                            "the provided notes without adding any information not explicitly stated. You output only clean "
                            "diagram syntax with no explanations or commentary."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=1800,
                top_p=0.7,
            )

            result = response.choices[0].message.content.strip()
            cleaned_result = self._clean_diagram_output(result)

            if self._validate_diagram_syntax(cleaned_result, diagram_type):
                return cleaned_result
            else:
                logger.warning(f"Generated {diagram_type} syntax failed validation: startswith={cleaned_result.splitlines()[0] if cleaned_result else 'EMPTY'}")
                return None

        except Exception as e:
            logger.error(f"Error generating diagram directly: {e}")
            return None

    def _clean_diagram_output(self, output: str) -> str:
        """Clean the diagram output to ensure it contains only diagram syntax"""
        # Remove markdown code blocks if present
        output = re.sub(r'```\w*\n?', '', output)
        output = re.sub(r'```', '', output)

        # Extract only the diagram section starting with a known header
        lines = output.split('\n')
        diagram_lines = []
        diagram_started = False

        def starts_with_header(line: str) -> bool:
            stripped = line.strip()
            return any(stripped.startswith(h) for h in MERMAID_HEADERS)

        for line in lines:
            line = line.rstrip()
            if not line.strip():
                if diagram_started:
                    diagram_lines.append('')
                continue

            if starts_with_header(line):
                diagram_started = True
                diagram_lines.append(line.strip())
            elif diagram_started:
                diagram_lines.append(line)

        result = '\n'.join(diagram_lines).strip()

        # Apply type-specific cleaning if needed
        if result.startswith('mindmap'):
            result = self._clean_mindmap_syntax(result)
        elif result.startswith('graph'):
            result = self._clean_graph_syntax(result)
        # Other types typically don't require additional cleaning here

        return result

    def _clean_mindmap_syntax(self, syntax: str) -> str:
        """Clean mindmap syntax to ensure compatibility"""
        lines = syntax.split('\n')
        cleaned_lines = []

        for line in lines:
            if line.strip().startswith('mindmap'):
                cleaned_lines.append(line.strip())
            elif line.strip().startswith('root(('):
                cleaned_lines.append('  ' + line.strip())
            elif line.strip() and not line.strip().startswith('mindmap'):
                cleaned_line = line.strip()
                cleaned_line = re.sub(r'[^\w\s\-]', '', cleaned_line)
                if cleaned_line and not cleaned_line.startswith('root'):
                    original_indent = len(line) - len(line.lstrip())
                    if original_indent == 0:
                        cleaned_lines.append('    ' + cleaned_line)
                    else:
                        cleaned_lines.append('      ' + cleaned_line)

        return '\n'.join(cleaned_lines)

    def _clean_graph_syntax(self, syntax: str) -> str:
        """Clean graph syntax to ensure compatibility"""
        lines = syntax.split('\n')
        cleaned_lines = []

        for line in lines:
            if line.strip().startswith('graph'):
                cleaned_lines.append(line.strip())
            elif line.strip() and '-->' in line.strip():
                cleaned_lines.append('    ' + line.strip())
            elif line.strip():
                cleaned_lines.append('    ' + line.strip())

        return '\n'.join(cleaned_lines)

    def _validate_diagram_syntax(self, syntax: str, diagram_type: str) -> bool:
        """Validate diagram syntax for basic correctness and correct header"""
        if not syntax or not syntax.strip():
            return False
        lines = syntax.strip().split('\n')
        if not lines:
            return False
        first_line = lines[0].strip()
        header = self._normalize_diagram_type(diagram_type)

        def starts_with_any(line: str, options: List[str]) -> bool:
            return any(line.startswith(o) for o in options)

        # Header checks per type
        if header == 'mindmap':
            if not first_line.startswith('mindmap'):
                return False
            has_root = any('root((' in line for line in lines)
            return has_root

        if header in ('flowchart', 'graph'):
            if header == 'flowchart':
                if not starts_with_any(first_line, ['flowchart', 'graph']):
                    return False
            else:
                if not first_line.startswith('graph'):
                    return False
            has_connection = any('-->' in line for line in lines)
            return has_connection

        if header == 'sequenceDiagram':
            if not first_line.startswith('sequenceDiagram'):
                return False
            has_message = any('->>' in line or '-->>' in line or '-->' in line for line in lines)
            return has_message

        if header == 'classDiagram':
            return first_line.startswith('classDiagram')

        if header in ('stateDiagram', 'stateDiagram-v2'):
            return starts_with_any(first_line, ['stateDiagram', 'stateDiagram-v2'])

        if header == 'erDiagram':
            return first_line.startswith('erDiagram')

        if header == 'journey':
            return first_line.startswith('journey')

        if header == 'gantt':
            return first_line.startswith('gantt')

        if header == 'pie':
            return first_line.startswith('pie')

        if header == 'gitGraph':
            return first_line.startswith('gitGraph')

        if header == 'timeline':
            return first_line.startswith('timeline')

        if header == 'requirementDiagram':
            return first_line.startswith('requirementDiagram')

        if header == 'quadrantChart':
            return first_line.startswith('quadrantChart')

        if header == 'sankey':
            return first_line.startswith('sankey')

        # Fallback: just ensure it starts with a known header
        return any(first_line.startswith(h) for h in MERMAID_HEADERS)

    def _get_extraction_prompt(self, content: str, diagram_type: str, header: str) -> str:
        """Get prompt for extracting structured logic based on normalized header and original type."""
        base = f"""You are a diagram generation engine.\nINPUT: A set of notes that summarize a video or text.\n\nNotes:\n{content[:4000]}\n\nTASK:\n1. Read the notes carefully.\n2. Identify only the processes, sequences, relationships, and hierarchies explicitly mentioned in the notes.\n3. Generate a Mermaid {diagram_type} diagram.\n4. Start the diagram with EXACTLY: {header}\n5. Do NOT add any information that is not explicitly stated in the notes.\n6. Preserve all terminology exactly as it appears in the notes.\n7. Maintain logical accuracy: ensure all steps, nodes, and connections match the source text.\n\nOUTPUT FORMAT:\n- Respond only with a valid Mermaid diagram in the specified syntax.\n- Do not include any explanations, summaries, or commentary.\n- Do not wrap the diagram in extra text — output diagram code only.\n\nSTRICTNESS RULES:\n- If the notes are incomplete, leave gaps in the diagram rather than guessing.\n- Do not infer events, steps, or relationships that are not 100% supported by the notes.\n- The diagram must be directly mappable back to the exact wording in the notes.\n\n{self._get_diagram_specific_instructions(header)}\n\nGenerate the {diagram_type} now:"""
        return base

    def _get_diagram_specific_instructions(self, header: str) -> str:
        """Get specific instructions and an example for each diagram header"""
        if header == 'flowchart':
            return """
FLOWCHART SYNTAX REQUIREMENTS:
- Start with "flowchart TD" or "graph TD".
- Use [ ] for processes, { } for decisions, (( )) for start/end.
- Use --> for connections, -->|label| for labeled connections.
- Keep node labels concise (<= 5 words).

EXAMPLE:
flowchart TD
    A[Start] --> B{Decision?}
    B -->|Yes| C[Action A]
    B -->|No| D[Action B]
    C --> E[(End)]
    D --> E
"""
        if header == 'graph':
            return """
GRAPH SYNTAX REQUIREMENTS:
- Start with "graph TD" or "graph LR".
- Use [ ] for rectangular nodes.
- Use --> for connections, -->|label| for labeled connections.

EXAMPLE:
graph LR
    A[Concept A] -->|relates to| B[Concept B]
    B --> C[Concept C]
"""
        if header == 'mindmap':
            return """
MINDMAP SYNTAX REQUIREMENTS:
- Start with "mindmap".
- Use proper indentation (2 spaces per level).
- Central topic in double parentheses: root((Central Topic)).
- Keep branch names concise.

EXAMPLE:
mindmap
  root((Topic))
    Branch A
      Sub A1
      Sub A2
    Branch B
      Sub B1
"""
        if header == 'sequenceDiagram':
            return """
SEQUENCE DIAGRAM SYNTAX REQUIREMENTS:
- Start with "sequenceDiagram".
- Define participants using: participant A as Name.
- Use ->> for sync, -->> for async messages.

EXAMPLE:
sequenceDiagram
    participant A as Client
    participant B as Server
    A->>B: Request
    B-->>A: Response
"""
        if header == 'classDiagram':
            return """
CLASS DIAGRAM SYNTAX REQUIREMENTS:
- Start with "classDiagram".
- Define classes, fields, methods, and relationships.

EXAMPLE:
classDiagram
    class User {
      +string id
      +string name
      +login()
    }
    class Session {
      +string token
    }
    User "1" -- "*" Session : creates
"""
        if header in ('stateDiagram', 'stateDiagram-v2'):
            return """
STATE DIAGRAM SYNTAX REQUIREMENTS:
- Start with "stateDiagram" or "stateDiagram-v2".
- Use [*] for start/end, and arrows for transitions.

EXAMPLE:
stateDiagram-v2
    [*] --> Idle
    Idle --> Running: start
    Running --> Idle: stop
    Running --> Error: fail
    Error --> Idle: reset
"""
        if header == 'erDiagram':
            return """
ER DIAGRAM SYNTAX REQUIREMENTS:
- Start with "erDiagram".
- Define entities with fields and relationships.

EXAMPLE:
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE-ITEM : contains
    CUSTOMER {
      string id
      string name
    }
    ORDER {
      string id
      date placed
    }
"""
        if header == 'journey':
            return """
JOURNEY SYNTAX REQUIREMENTS:
- Start with "journey".
- Define sections and steps with ratings.

EXAMPLE:
journey
    title User Journey
    section Onboarding
      Sign Up: 5: User
      Confirm Email: 3: User
"""
        if header == 'gantt':
            return """
GANTT SYNTAX REQUIREMENTS:
- Start with "gantt".
- Define title, dateFormat, and tasks with durations/dependencies.

EXAMPLE:
gantt
    title Project Plan
    dateFormat  YYYY-MM-DD
    section Phase 1
    Task A     :a1, 2024-01-01, 7d
    Task B     :after a1, 5d
"""
        if header == 'pie':
            return """
PIE CHART SYNTAX REQUIREMENTS:
- Start with "pie".
- Use quoted labels and numerical values.

EXAMPLE:
pie title Market Share
    "A" : 40
    "B" : 35
    "C" : 25
"""
        if header == 'gitGraph':
            return """
GITGRAPH SYNTAX REQUIREMENTS:
- Start with "gitGraph".
- Define commits and branches.

EXAMPLE:
gitGraph
    commit
    branch feature
    checkout feature
    commit
    checkout main
    merge feature
"""
        if header == 'timeline':
            return """
TIMELINE SYNTAX REQUIREMENTS:
- Start with "timeline".
- Define sections with dates/events.

EXAMPLE:
timeline
    title History
    2020 : Start
    2021 : Grow
"""
        if header == 'requirementDiagram':
            return """
REQUIREMENT DIAGRAM SYNTAX REQUIREMENTS:
- Start with "requirementDiagram".
- Define requirements and relationships.

EXAMPLE:
requirementDiagram
    requirement R1 { text: "Must do X" }
"""
        if header == 'sankey':
            return """
SANKEY SYNTAX REQUIREMENTS:
- Start with "sankey".
- Define nodes and weighted flows: A,[label]:::class B, value

EXAMPLE:
sankey
    A, B, 10
    B, C, 5
"""
        if header == 'quadrantChart':
            return """
QUADRANT CHART SYNTAX REQUIREMENTS:
- Start with "quadrantChart".
- Define title and axes, then points.

EXAMPLE:
quadrantChart
    title Skills
    x-axis Skill
    y-axis Impact
    A: [2,3]
    B: [4,1]
"""
        # Default fallback
        return """
GENERAL MERMAID REQUIREMENTS:
- Use the appropriate Mermaid header and syntax for the requested diagram type.
- Keep labels concise; avoid special characters when possible.
"""

    # Clean/validation helpers retained/extended above

    def _fix_mermaid_syntax_issues(self, syntax: str) -> str:
        """Fix common Mermaid syntax issues"""
        syntax = re.sub(r'-->\|([^|]+)\|>', r'-->|\1|', syntax)

        def fix_node_labels(match):
            full_match = match.group(0)
            node_id = match.group(1)
            label = match.group(2)
            if '(' in label and ')' in label and not (label.startswith('"') and label.endswith('"')):
                return f'{node_id}["{label}"]'
            return full_match

        syntax = re.sub(r'(\w+)\[([^\]]+)\]', fix_node_labels, syntax)

        lines = syntax.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line:
                if not any(line.startswith(keyword) for keyword in MERMAID_HEADERS):
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
            "tertiaryColor": "#ffffff",
        }

        if diagram_type == "flowchart":
            return {**base_options, "flowchart": {"htmlLabels": True, "curve": "basis", "padding": 10}}
        if diagram_type == "mindmap":
            return {**base_options, "mindmap": {"padding": 10, "maxNodeSizeX": 200, "maxNodeSizeY": 100}}
        if diagram_type in ("sequence", "sequenceDiagram"):
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
                    "messageMargin": 35,
                },
            }
        return base_options

    def generate_html_with_diagram(self, diagram_data: Dict, include_libraries: bool = True) -> str:
        """Generate HTML page with embedded diagram and rendering libraries"""
        if not diagram_data:
            return None

        mermaid_syntax = diagram_data.get("mermaid_syntax", "")
        title = diagram_data.get("title", "Diagram")
        description = diagram_data.get("description", "")
        diagram_type = diagram_data.get("type", "flowchart")

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
        .header h1 {{ margin: 0; font-size: 2rem; font-weight: 700; }}
        .header p {{ margin: 8px 0 0 0; opacity: 0.9; font-size: 1.1rem; }}
        .diagram-container {{ padding: 32px; text-align: center; min-height: 400px; }}
        .mermaid {{ background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .controls {{ margin: 20px 0; display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }}
        .btn {{ background: #4f46e5; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: background-color 0.2s; }}
        .btn:hover {{ background: #4338ca; }}
        .btn-secondary {{ background: #6b7280; }}
        .btn-secondary:hover {{ background: #4b5563; }}
        .info-panel {{ background: #f1f5f9; border-left: 4px solid #4f46e5; padding: 16px; margin: 20px 0; border-radius: 0 8px 8px 0; }}
        .info-panel h3 {{ margin: 0 0 8px 0; color: #4f46e5; }}
        .footer {{ background: #f8fafc; padding: 16px 24px; text-align: center; color: #6b7280; font-size: 14px; }}
        @media (max-width: 768px) {{
            .container {{ margin: 10px; border-radius: 8px; }}
            .diagram-container {{ padding: 16px; }}
            .header {{ padding: 16px; }}
            .header h1 {{ font-size: 1.5rem; }}
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
            <p>Generated with Mermaid.js • Auto-created from learning notes</p>
        </div>
    </div>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            flowchart: {{ htmlLabels: true, curve: 'basis' }},
            sequence: {{ diagramMarginX: 50, diagramMarginY: 10, actorMargin: 50, width: 150, height: 65 }},
            mindmap: {{ padding: 10, maxNodeSizeX: 200, maxNodeSizeY: 100 }}
        }});
        let currentZoom = 1;
        function zoomIn() {{ currentZoom += 0.2; applyZoom(); }}
        function zoomOut() {{ currentZoom = Math.max(0.2, currentZoom - 0.2); applyZoom(); }}
        function resetZoom() {{ currentZoom = 1; applyZoom(); }}
        function applyZoom() {{ const diagram = document.getElementById('diagram'); diagram.style.transform = `scale(${{currentZoom}})`; diagram.style.transformOrigin = 'center'; }}
        function downloadSVG() {{ const svg = document.querySelector('#diagram svg'); if (svg) {{ const svgData = new XMLSerializer().serializeToString(svg); const svgBlob = new Blob([svgData], {{type: 'image/svg+xml;charset=utf-8'}}); const svgUrl = URL.createObjectURL(svgBlob); const downloadLink = document.createElement('a'); downloadLink.href = svgUrl; downloadLink.download = '{title.replace(" ", "_")}_diagram.svg'; document.body.appendChild(downloadLink); downloadLink.click(); document.body.removeChild(downloadLink); }} }}
        function downloadPNG() {{ const svg = document.querySelector('#diagram svg'); if (svg) {{ const canvas = document.createElement('canvas'); const ctx = canvas.getContext('2d'); const data = new XMLSerializer().serializeToString(svg); const DOMURL = window.URL || window.webkitURL || window; const img = new Image(); const svgBlob = new Blob([data], {{type: 'image/svg+xml;charset=utf-8'}}); const url = DOMURL.createObjectURL(svgBlob); img.onload = function() {{ canvas.width = img.width; canvas.height = img.height; ctx.drawImage(img, 0, 0); DOMURL.revokeObjectURL(url); const imgURI = canvas.toDataURL('image/png').replace('image/png', 'image/octet-stream'); const downloadLink = document.createElement('a'); downloadLink.href = imgURI; downloadLink.download = '{title.replace(" ", "_")}_diagram.png'; document.body.appendChild(downloadLink); downloadLink.click(); document.body.removeChild(downloadLink); }}; img.src = url; }} }}
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
