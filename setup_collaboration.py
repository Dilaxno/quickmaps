#!/usr/bin/env python3
"""
Setup script for collaboration features
This script helps verify that all collaboration components are properly configured.
"""

import os
import sys
import importlib.util

def check_file_exists(file_path, description):
    """Check if a file exists and report status"""
    if os.path.exists(file_path):
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} (MISSING)")
        return False

def check_import(module_name, description):
    """Check if a Python module can be imported"""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is not None:
            print(f"✅ {description}: {module_name}")
            return True
        else:
            print(f"❌ {description}: {module_name} (NOT FOUND)")
            return False
    except Exception as e:
        print(f"❌ {description}: {module_name} (ERROR: {e})")
        return False

def main():
    print("🚀 Collaboration Feature Setup Verification")
    print("=" * 50)
    
    all_good = True
    
    # Check backend files
    print("\n📁 Backend Files:")
    backend_files = [
        ("collaboration_service.py", "Collaboration Service"),
        ("brevo_service.py", "Email Service"),
        ("auth_service.py", "Authentication Service"),
        ("job_manager.py", "Job Manager"),
    ]
    
    for file_path, description in backend_files:
        if not check_file_exists(file_path, description):
            all_good = False
    
    # Check frontend files
    print("\n🎨 Frontend Files:")
    frontend_files = [
        ("frontend-old/src/pages/CollaborationPage.jsx", "Collaboration Page"),
        ("frontend-old/src/pages/WorkspaceDetailPage.jsx", "Workspace Detail Page"),
        ("frontend-old/src/pages/AcceptInvitationPage.jsx", "Accept Invitation Page"),
        ("frontend-old/src/hooks/useCollaboration.js", "Collaboration Hook"),
        ("frontend-old/src/components/WorkspaceIndicator.jsx", "Workspace Indicator"),
    ]
    
    for file_path, description in frontend_files:
        if not check_file_exists(file_path, description):
            all_good = False
    
    # Check Python imports
    print("\n🐍 Python Dependencies:")
    python_modules = [
        ("firebase_admin", "Firebase Admin SDK"),
        ("secrets", "Secrets Module"),
        ("uuid", "UUID Module"),
        ("datetime", "DateTime Module"),
    ]
    
    for module_name, description in python_modules:
        if not check_import(module_name, description):
            all_good = False
    
    # Check environment variables
    print("\n🔧 Environment Configuration:")
    env_vars = [
        ("BREVO_API_KEY", "Brevo Email Service API Key"),
        ("FIREBASE_PROJECT_ID", "Firebase Project ID"),
    ]
    
    for var_name, description in env_vars:
        if os.getenv(var_name):
            print(f"✅ {description}: {var_name} (SET)")
        else:
            print(f"⚠️  {description}: {var_name} (NOT SET - may use defaults)")
    
    # Check main.py integration
    print("\n🔗 Integration Check:")
    main_py_path = "main.py"
    if os.path.exists(main_py_path):
        with open(main_py_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        checks = [
            ("collaboration_service import", "from collaboration_service import collaboration_service"),
            ("Collaboration routes", "@app.post(\"/api/workspaces\")"),
            ("Workspace models", "class CreateWorkspaceRequest"),
        ]
        
        for check_name, search_text in checks:
            if search_text in content:
                print(f"✅ {check_name}: Found in main.py")
            else:
                print(f"❌ {check_name}: Not found in main.py")
                all_good = False
    else:
        print("❌ main.py: File not found")
        all_good = False
    
    # Final status
    print("\n" + "=" * 50)
    if all_good:
        print("🎉 All collaboration components are properly set up!")
        print("\nNext steps:")
        print("1. Start your FastAPI server: uvicorn main:app --reload")
        print("2. Start your frontend: cd frontend-old && npm run dev")
        print("3. Navigate to /collaboration to test the feature")
        print("4. Create a workspace and invite a collaborator")
    else:
        print("⚠️  Some components are missing or not configured properly.")
        print("Please review the items marked with ❌ above.")
        print("\nFor detailed setup instructions, see COLLABORATION_README.md")
    
    return 0 if all_good else 1

if __name__ == "__main__":
    sys.exit(main())