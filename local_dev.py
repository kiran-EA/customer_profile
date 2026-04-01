#!/usr/bin/env python3
"""
Local development server for testing before Vercel deployment
Run: python local_dev.py
Then open: http://localhost:5050
"""
import sys
import os

# Add api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

from index import app

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  LampsPlus Customer Dashboard — Local Development Server")
    print("  http://localhost:5050")
    print("="*60 + "\n")
    
    # Load environment variables from .env file if it exists
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        print("  Loading environment variables from .env file...")
        from dotenv import load_dotenv
        load_dotenv(env_file)
    else:
        print("  No .env file found — using mock data / env defaults.")
    
    app.run(
        debug=True,
        port=int(os.environ.get('FLASK_PORT', 5050)),
        host='0.0.0.0'
    )
