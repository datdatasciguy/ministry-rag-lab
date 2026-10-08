# Let a friend try it

The easiest route is the [desktop installer](desktop_install.md) plus a privately
supplied index that the recipient is permitted to use. It bundles Python and
Python dependencies. The manual source setup below remains available.

Send the GitHub link or a code-only ZIP prepared by `package_app.py`. They also
need Python 3.11+, Ollama for model features, and a collection they are permitted
to use. GitHub does not contain the books, Bible, footnotes, your index, or models.
No paid API key or cloud account is required for local inference.

Your `http://127.0.0.1:8766` address points to your own computer. On their computer,
that address points to their computer. The current app is a local application;
sending your URL does not give them access to your running instance.

## Install on Windows

Install [Python](https://www.python.org/downloads/) and
[Ollama](https://ollama.com/download). Keep Ollama running. Download the repository
as a ZIP and extract it, or clone it:

```powershell
git clone https://github.com/datdatasciguy/ministry-rag-lab.git
cd ministry-rag-lab
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup.py
```

Setup asks which model fits their computer and explains all eight choices,
including download sizes, RAM/GPU suggestions and answer limitations. The initial
suggestion is 1.7B for a basic laptop; they can choose smaller or larger. See
[the full model guide](models.md). Run setup again to add another model; the
interface switches among installed choices. A GPU improves speed; CPU inference
can be slow. Leave room for model downloads and the collection/index. The full index
on the developer's PC is about 1.65 GB, plus roughly 0.75 GB for cached vectors
when loaded; the model and other Python allocations require additional memory.
A smaller collection requires less storage and vector memory.

## Supply their own collection

Supported inputs are `sections.jsonl` exports, UTF-8 text/Markdown/HTML, or an
archive with readable `books/clean_html/<title>/page_NNN.html` companions. iSilo
PDB files alone are not supported. Exported JSONL rows need a book title and text;
book IDs, chapter/section indices, labels and page URLs preserve useful structure.

For the supported local Jubilee Recovery Version HTML layout, convert Bible
verses and numbered footnotes first:

```powershell
.\.venv\Scripts\python.exe bible_html.py --source "D:\MyCollection\Recovery Version" --output data/bible.jsonl
```

Build a private combined index, adjusting the input paths:

```powershell
.\.venv\Scripts\python.exe rag.py build --source "D:\MyCollection\Books" --source data/bible.jsonl --index data/books.sqlite --embedding-model nomic-embed-text:v1.5
```

Omit the Bible source if they only have ministry books. Building a large index
takes time because each passage is embedded. It checkpoints; repeat the same
command with `--resume` after an interruption. Choose a new filename for a new
collection or changed model. Text never needs to be sent to a cloud model.

For Witness Lee/Watchman Nee filtering, attach a publisher title/author catalog
they already have, such as a compatible archived booklist. Names mentioned in
the text are not author metadata:

```powershell
.\.venv\Scripts\python.exe catalog.py --index data/books.sqlite --source "D:\MyCollection\booklist.html" --output data/books-with-authors.sqlite
```

## Open the app

```powershell
.\.venv\Scripts\python.exe app.py --index data/books-with-authors.sqlite
```

Without a catalog, use `data/books.sqlite` and select all authors. Open
`http://127.0.0.1:8766` in their browser. Keyword search can use an index built
without embeddings; semantic search needs Nomic embeddings, and generated answers
need the chosen downloaded answer model. Balanced mode needs ministry, Bible and footnote
collections. The displayed verse is optional private metadata, not bundled text.

Sharing the code grants no rights to distribute a book collection. A friend
must obtain their permitted source files separately. Do not place books, private
indexes or models in GitHub, public ZIPs, or publicly accessible hosting.


## Use your phone on the same home network

The PC runs the model; your phone only needs a browser. Keep the PC awake and
connect the phone to the same home network as the PC (Ethernet also works).
Find the PC's IPv4 address and subnet with `ipconfig`. For example, a PC at
`192.168.1.66` with subnet mask `255.255.255.0` uses `192.168.1.0/24`:

```powershell
.\.venv\Scripts\python.exe app.py --index data/books-with-authors.sqlite --lan-address 192.168.1.66 --lan-subnet 192.168.1.0/24
```

Replace the example addresses and index path with yours. On the phone, open
`http://192.168.1.66:8766/` in Safari or Chrome. The app allows localhost and
devices in the selected subnet, rejects other client addresses and Host headers,
and ignores forwarded client-address headers. Everyone on that subnet can use
the app and read its indexed sources; there is no account login.

Windows may need an inbound TCP 8766 firewall rule restricted to the selected
subnet, the PC's LAN address and its home-network interface. No router port
forwarding is needed. Guest Wi-Fi may isolate devices; use the main network.
Stop LAN access by restarting without the two flags. Update the address if
DHCP changes it. These flags apply to the command-line app; the installer stays
on localhost by default.

This is plain HTTP for a trusted home network. A subnet allowlist is not user
authentication. Do not expose the collection to the internet.
