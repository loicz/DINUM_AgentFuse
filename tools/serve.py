from pathlib import Path
import argparse
import sys
import uvicorn
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from agentfuse.app import create_app
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8787);args=parser.parse_args()
uvicorn.run(create_app(),host='127.0.0.1',port=args.port,access_log=False)
