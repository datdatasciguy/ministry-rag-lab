# Desktop downloads

Use the [GitHub release downloads](https://github.com/datdatasciguy/ministry-rag-lab/releases).
Desktop packages contain Python, the application and its Python dependencies.
They contain no books, indexes, model weights, private queries or credentials.
The first release is a preview. Packages are not publisher-signed or Apple
notarized, so operating-system security prompts or launch restrictions can occur.
Manual Python setup remains available if the desktop preview will not launch.

## Windows x64

1. Download and run the Windows `.exe` installer.
2. If Ollama is missing, leave its optional setup selected. The installer downloads
   Ollama from the official vendor and opens its setup window. Finish that setup
   and keep Ollama running. Existing Ollama installations are reused.
3. Open **Ministry Search RAG** from the Start menu.
4. Choose your privately supplied `.sqlite` collection index. The app copies it
   into your local app data and checks that the index is complete.
5. Choose a model, read its hardware/quality tradeoffs, and click **Download models
   and open search**. Only the selected answer model and the needed embedding
   model are downloaded. Already installed local models are reused.

No Git, Python installation, virtual environment or pip command is needed.
Internet is needed for runtime/model downloads; search and answers use local
Ollama. Models have their own provider licenses.

## Mac

Choose the `.dmg` matching your Mac: **arm64** for Apple Silicon, **x86_64** for
Intel. These previews are built and checked on macOS 15 runners; older macOS
versions have not been validated.

1. Open the disk image and drag **Ministry Search RAG** to **Applications**.
2. Install [Ollama for Mac](https://ollama.com/download/mac) once and keep it running.
3. Open the app, select the private index, choose a model and start setup.

The same private index works on both Windows and Mac. Models download on the
recipient's computer. A LoRA is not included; no adapter has been trained yet.
Apple Developer signing/notarization has not been configured for these previews.

## Collection and settings

The index contains actual book text, Bible verses and footnotes. Obtain a
collection you are permitted to use and keep it private; code downloads do not
grant redistribution rights. The public installer contains no private download
link. Files are copied locally, never uploaded to GitHub or a model service.
Allow enough disk space for the downloaded index plus its imported copy.

Settings, imported indexes and a local launcher log live in:

- Windows: `%LOCALAPPDATA%\MinistrySearchRAG`
- Mac: `~/Library/Application Support/MinistrySearchRAG`

Uninstalling the application preserves these files and leaves Ollama/models alone.
The app checks the index's embedding-model digest before enabling semantic search.
A changed embedding version needs a matching index or a rebuild.

Closing the browser keeps the local app running. Use **Setup / Quit app** in
search, then **Quit app**, to stop it. Restart it to change collections or add a
model. Installed answer models can also be switched directly in search. The
browser address is local to this computer and may use another port if 8766 is busy.

## Build from source

Use a clean Python 3.12 environment on the target operating system:

```bash
python -m pip install -r requirements.txt pyinstaller==6.22.3
python build_installer.py --version 0.1.0
```

Windows also needs Inno Setup 6; pass `--compiler /path/to/ISCC.exe` if it is not
in the default location. Mac needs the system `codesign` and `hdiutil` tools.
The GitHub **Desktop installers** workflow builds Apple Silicon and Intel DMGs
and checks packaged startup, ad-hoc signatures and disk-image integrity. Build
outputs and checksums stay in ignored `outputs/installer-build`; release assets
are selected explicitly. A build success is not a full end-user installation test.
