"""Commande installée du point d’entrée HTTP de la démonstration."""
import argparse


def main():
    parser = argparse.ArgumentParser(description='Entrée HTTP de la messagerie locale AgentFuse')
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    import uvicorn
    from .app import create_app
    uvicorn.run(create_app(), host='127.0.0.1', port=args.port, access_log=False)
