# Composants tiers

Les notices ci-dessous décrivent les dépendances et leurs licences. Elles ne définissent pas une licence pour le code propre à AgentFuse ; aucune licence de ce code n’est actuellement déclarée dans le dépôt ou les métadonnées du paquet.

- Qwen3-1.7B-GGUF, Apache-2.0 : téléchargé à l’installation dans `.runtime/`, exclu de la distribution. [Version fixée](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/tree/90862c4b9d2787eaed51d12237eafdfe7c5f6077).
- llama.cpp, MIT, version b10883 : téléchargé dans `.runtime/`. [Version fixée](https://github.com/ggml-org/llama.cpp/releases/tag/b10883).
- Noto Sans SC, SIL Open Font License 1.1 : police de la messagerie incluse dans `src/agentfuse/assets/`, avec sa [notice originale](src/agentfuse/assets/OFL.txt). [Projet de la police](https://github.com/google/fonts/tree/main/ofl/notosanssc).
- Les dépendances Python sont fixées dans `requirements.lock` ; chaque distribution conserve ses métadonnées de licence. Les tests navigateur utilisent un Chromium distinct, absent du wheel Python.
- Conversations, MIT, copyright Direction Interministérielle du Numérique : le commit `4d6edc79be5ccfa34e57497a07311e8a1f2bba74` est téléchargé dans `.runtime/` avec son fichier `LICENSE` original. [Projet Conversations](https://github.com/suitenumerique/conversations).
- L’intégration Conversations fixe ses propres dépendances dans `integrations/conversations/requirements.lock` ; elles ne sont pas des dépendances du cœur.
- Polices Inter, SIL Open Font License 1.1 : incluses dans `integrations/conversations/assets/fonts/` avec leur [notice originale](integrations/conversations/assets/fonts/OFL.txt). [Projet Inter](https://github.com/rsms/inter).
- PostgreSQL 18.6, PostgreSQL License : le serveur et ses dépendances Fedora conservent leurs notices dans `.runtime/`. [Licence PostgreSQL](https://www.postgresql.org/about/licence/).
- Node.js 22.23.2 et npm conservent leurs fichiers `LICENSE` dans `.runtime/`. [Projet Node.js](https://nodejs.org/).
- Les données `cl100k_base` de Tiktoken sont téléchargées et vérifiées par empreinte pendant l’installation de la messagerie ; la distribution Python conserve sa licence MIT.
