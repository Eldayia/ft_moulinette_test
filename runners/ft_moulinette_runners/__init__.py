"""Moteurs d'exécution de ft-moulinette : interface commune, protocole distant et implémentations.

Le cœur du paquet n'utilise que la bibliothèque standard. Seule l'obtention d'un ID token
Google (CloudRunRunner) demande l'extra « cloudrun » (google-auth), importé à la demande.
"""
__version__ = '0.1.0'
