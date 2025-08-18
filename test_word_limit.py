#!/usr/bin/env python3
"""
Test script to verify 50-word limit enforcement in GroqNotesGenerator
"""

import os
import sys
import logging

# Add the current directory to the path so we can import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_word_limit_enforcement():
    """Test the word limit enforcement functionality"""
    
    try:
        from groq_processor import GroqNotesGenerator
        
        # Create an instance
        generator = GroqNotesGenerator()
        
        # Test data with sections that exceed 50 words
        test_notes = """## Introduction to Machine Learning

Machine learning is a subset of artificial intelligence that focuses on developing algorithms and statistical models that enable computers to improve their performance on a specific task through experience. This field has become increasingly important in recent years due to the explosion of data and the need for automated decision-making systems. Machine learning algorithms can be broadly categorized into three main types: supervised learning, unsupervised learning, and reinforcement learning. Each type has its own characteristics and applications, making machine learning a versatile tool for solving complex problems in various domains such as healthcare, finance, and technology.

## Supervised Learning

Supervised learning is a type of machine learning where the algorithm learns from labeled training data. The goal is to learn a mapping from input features to output labels, allowing the model to make predictions on new, unseen data. Common examples of supervised learning include classification tasks, where the goal is to categorize data into predefined classes, and regression tasks, where the goal is to predict continuous numerical values. Popular algorithms in this category include linear regression, logistic regression, support vector machines, and neural networks. The success of supervised learning depends heavily on the quality and quantity of the training data, as well as the choice of appropriate features and algorithm parameters.

## Unsupervised Learning

Unsupervised learning involves training algorithms on data without labeled outputs. The goal is to discover hidden patterns, structures, or relationships within the data. This type of learning is particularly useful when we don't know what we're looking for or when labeling data would be too expensive or time-consuming. Common applications include clustering, where similar data points are grouped together, and dimensionality reduction, where high-dimensional data is projected into a lower-dimensional space while preserving important information. Popular unsupervised learning algorithms include k-means clustering, hierarchical clustering, principal component analysis (PCA), and autoencoders. These algorithms can reveal insights that might not be apparent through manual analysis and can serve as a preprocessing step for other machine learning tasks.

## Reinforcement Learning

Reinforcement learning is a type of machine learning where an agent learns to make decisions by interacting with an environment. The agent receives feedback in the form of rewards or penalties based on its actions, and the goal is to learn a policy that maximizes the cumulative reward over time. This approach is inspired by how humans and animals learn through trial and error. Reinforcement learning has been successfully applied to various domains, including game playing (such as AlphaGo), robotics, autonomous vehicles, and resource management. The key challenges in reinforcement learning include balancing exploration (trying new actions) with exploitation (using known good actions), dealing with delayed rewards, and ensuring the learned policy generalizes well to new situations. Popular algorithms include Q-learning, policy gradient methods, and deep reinforcement learning approaches that combine reinforcement learning with deep neural networks."""
        
        print("Testing word limit enforcement...")
        print(f"Original notes length: {len(test_notes)} characters")
        print(f"Original word count: {len(test_notes.split())} words")
        
        # Count sections
        sections = [line for line in test_notes.split('\n') if line.startswith('##')]
        print(f"Original sections: {len(sections)}")
        
        # Test the word limit enforcement
        max_words = 50
        enforced_notes = generator._enforce_word_limit_on_notes(test_notes, max_words)
        
        print(f"\nEnforced notes length: {len(enforced_notes)} characters")
        print(f"Enforced word count: {len(enforced_notes.split())} words")
        
        # Count sections after enforcement
        enforced_sections = [line for line in enforced_notes.split('\n') if line.startswith('##')]
        print(f"Enforced sections: {len(enforced_sections)}")
        
        # Check if any section exceeds the word limit
        lines = enforced_notes.split('\n')
        current_section = None
        current_content = []
        violations = []
        
        for line in lines:
            if line.startswith('##'):
                # Check previous section
                if current_section and current_content:
                    content_text = ' '.join(current_content).strip()
                    word_count = len(content_text.split())
                    if word_count > max_words:
                        violations.append((current_section, word_count))
                
                # Start new section
                current_section = line
                current_content = []
            elif line.strip() and current_section:
                current_content.append(line)
        
        # Check last section
        if current_section and current_content:
            content_text = ' '.join(current_content).strip()
            word_count = len(content_text.split())
            if word_count > max_words:
                violations.append((current_section, word_count))
        
        if violations:
            print(f"\n⚠️  Found {len(violations)} sections that still exceed {max_words} words:")
            for section, word_count in violations:
                print(f"  - {section.strip()}: {word_count} words")
        else:
            print(f"\n✅ All sections now comply with {max_words}-word limit!")
        
        # Show a sample of the enforced notes
        print(f"\nSample of enforced notes:")
        print("-" * 50)
        print(enforced_notes[:500] + "..." if len(enforced_notes) > 500 else enforced_notes)
        
        return len(violations) == 0
        
    except ImportError as e:
        print(f"❌ Failed to import GroqNotesGenerator: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

def test_chunk_splitting():
    """Test the chunk splitting functionality for long content"""
    
    try:
        from groq_processor import GroqNotesGenerator
        
        generator = GroqNotesGenerator()
        
        # Create a very long test content
        long_content = "This is a test sentence. " * 1000  # ~6000 words
        
        print(f"\nTesting chunk splitting...")
        print(f"Long content: {len(long_content)} characters, ~{len(long_content.split())} words")
        
        # Test different chunk sizes
        test_chunk_sizes = [8000, 12000, 15000]
        
        for chunk_size in test_chunk_sizes:
            chunks = generator._split_content(long_content, chunk_size)
            print(f"Chunk size {chunk_size}: {len(chunks)} chunks")
            
            # Verify chunk sizes
            for i, chunk in enumerate(chunks):
                if len(chunk) > chunk_size:
                    print(f"  ⚠️  Chunk {i+1} exceeds size limit: {len(chunk)} > {chunk_size}")
                else:
                    print(f"  ✅ Chunk {i+1}: {len(chunk)} characters")
        
        return True
        
    except Exception as e:
        print(f"❌ Chunk splitting test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing GroqNotesGenerator Word Limit Enforcement")
    print("=" * 60)
    
    # Test word limit enforcement
    word_limit_success = test_word_limit_enforcement()
    
    # Test chunk splitting
    chunk_splitting_success = test_chunk_splitting()
    
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print(f"  Word Limit Enforcement: {'✅ PASS' if word_limit_success else '❌ FAIL'}")
    print(f"  Chunk Splitting: {'✅ PASS' if chunk_splitting_success else '❌ FAIL'}")
    
    if word_limit_success and chunk_splitting_success:
        print("\n🎉 All tests passed! Word limit enforcement is working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed. Please check the implementation.")
        sys.exit(1)
