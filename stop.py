#!/usr/bin/env python3
"""Arrêter tous les services de la démonstration en conservant les données."""
import sys

from tools.manage import main


if __name__ == "__main__":
    sys.exit(main(["stop", *sys.argv[1:]]))
